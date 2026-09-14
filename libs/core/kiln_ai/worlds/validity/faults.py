"""World servers and the fault gate.

Two jobs that belong together because the fault step is the only part of the harness that
runs more than one world server: starting, watching and stopping a server (the harness does
this, never the Kiln app), and deciding whether a seeded fault was caught.

Nothing here knows what world it is starting. The command, the environment, the port, the
SQL that reads the world's trigger table and the fault table itself all arrive from the
driver; this module contributes the lifecycle, the trigger plumbing and the detection rule.

The detection rule has one asymmetry worth stating: a fault whose line the inputs never
executed is **inconclusive**, not undetected. It says nothing about whether the harness can
see that fault, and it blocks the gate until the missing input is written.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import JsonValue

from kiln_ai.datamodel.world import OpenEnvTool, WorldEpisode
from kiln_ai.datamodel.world import World as KilnWorld
from kiln_ai.worlds.session_manager import ToolCallOutcome, WorldSessionManager

from .metrics import (
    Gate,
    GateName,
    GateThresholds,
    PairedStat,
    moved_beyond_interval,
    moved_gates,
)

logger = logging.getLogger(__name__)

METADATA_TIMEOUT_S = 5.0


class WorldServerError(RuntimeError):
    """A world server could not be started, or came up wrong."""


class WorldServerDown(WorldServerError):
    """A running world server stopped answering. The step is aborted, not retried."""


@dataclass
class WorldServer:
    process: subprocess.Popen[bytes]
    port: int
    url: str
    version: str
    max_concurrent_envs: int | None
    """What the server reports it can serve at once, or None when its /metadata does not
    say. The capacity check applies only to a server that reports one; when it does not,
    `capacity_caveat` gives the report the sentence that says so."""
    min_concurrent_envs: int = 0
    """What this step asked for, kept so the caveat can name it."""


def port_is_free(port: int) -> bool:
    """Whether a world server can bind `127.0.0.1:port`.

    A listener on the wildcard address (`0.0.0.0:port`) does not always block a loopback
    bind, so this can answer True where a server on every interface is already up. The
    worlds this starts bind loopback, which is the case it does cover."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def start_world_server(
    cmd: Sequence[str],
    env: Mapping[str, str],
    port: int,
    *,
    min_concurrent_envs: int,
    expect_version_suffix: str | None = None,
    ready_timeout_s: float = 60.0,
    log_path: Path | None = None,
) -> WorldServer:
    """Launch `cmd`, wait for `/metadata`, and check what answered is the world we asked for.

    A bound port is refused before launching: the alternative is a run that silently grades
    against whatever was already listening there — a previous fault's server, most
    dangerously, whose version suffix would not match the traces being written."""
    if not port_is_free(port):
        raise WorldServerError(
            f"port {port} is already bound; refusing to start a world there"
        )

    # The child's output goes to `log_path` or nowhere. A pipe nobody drains fills at
    # about 64 KB and blocks the server mid-`write()`, which surfaces hours later as a
    # liveness failure and aborts a paid step for no reason at all.
    sink = log_path.open("ab") if log_path is not None else None
    stream = sink if sink is not None else subprocess.DEVNULL
    try:
        process = subprocess.Popen(
            list(cmd),
            env={**os.environ, **dict(env)},
            stdout=stream,
            stderr=subprocess.STDOUT if sink is not None else subprocess.DEVNULL,
        )
    finally:
        if sink is not None:
            sink.close()

    try:
        url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + ready_timeout_s
        metadata: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise WorldServerError(
                    f"world server exited with code {process.returncode} before "
                    f"answering on port {port}"
                    + (f"; see {log_path}" if log_path is not None else "")
                )
            try:
                response = httpx.get(f"{url}/metadata", timeout=METADATA_TIMEOUT_S)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, dict):
                        metadata = payload
                        break
            except (httpx.HTTPError, ValueError):
                # A transport failure or a 200 that is not JSON: both mean "not the
                # world we asked for, not yet".
                pass
            time.sleep(0.1)

        if metadata is None:
            raise WorldServerError(
                f"world server on port {port} was not ready within {ready_timeout_s}s"
            )

        version = str(metadata.get("version", ""))
        capacity = metadata.get("max_concurrent_envs")
        max_concurrent = (
            capacity
            if isinstance(capacity, int) and not isinstance(capacity, bool)
            else None
        )
        if expect_version_suffix is not None and not version.endswith(
            expect_version_suffix
        ):
            raise WorldServerError(
                f"world server on port {port} reports version {version!r}, "
                f"which does not end with {expect_version_suffix!r}"
            )
        if max_concurrent is not None and max_concurrent < min_concurrent_envs:
            raise WorldServerError(
                f"world server on port {port} serves at most {max_concurrent} sessions, "
                f"fewer than the {min_concurrent_envs} this step needs"
            )
        if max_concurrent is None:
            logger.warning(
                "world server on port %s does not report max_concurrent_envs; "
                "cannot check it against the requested %s",
                port,
                min_concurrent_envs,
            )
    except BaseException:
        # Anything at all past the launch leaves a live child holding the port, and the
        # next fault's server would be refused with a misleading "already bound".
        _kill(process)
        raise

    return WorldServer(
        process=process,
        port=port,
        url=url,
        version=version,
        max_concurrent_envs=max_concurrent,
        min_concurrent_envs=min_concurrent_envs,
    )


def capacity_caveat(server: WorldServer) -> str | None:
    """The caveat for a server whose capacity could not be checked, or None.

    A run that never verified the world could serve its concurrency must not read in
    `validity.json` exactly like one that did."""
    if server.max_concurrent_envs is not None:
        return None
    return (
        f"the world server on port {server.port} does not report max_concurrent_envs, "
        f"so the requested capacity of {server.min_concurrent_envs} concurrent episodes "
        "was not verified"
    )


def _kill(process: subprocess.Popen[bytes]) -> None:
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        pass


def stop_world_server(server: WorldServer, *, grace_s: float = 10.0) -> None:
    """SIGTERM, then SIGKILL after the grace period. A world server that will not close its
    sessions must not keep a port that the next fault needs."""
    process = server.process
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        logger.warning(
            "world server on port %s ignored SIGTERM for %ss; killing",
            server.port,
            grace_s,
        )
        _kill(process)


async def watch_liveness(
    server: WorldServer, *, interval_s: float = 30.0, max_failures: int = 5
) -> None:
    """Poll `/metadata` for the life of a step, raising once the server has missed
    `max_failures` polls in a row. Consecutive, not cumulative: one slow poll during a
    concurrent run is normal, five in a row is a dead server."""
    failures = 0
    async with httpx.AsyncClient(timeout=METADATA_TIMEOUT_S) as client:
        while True:
            try:
                response = await client.get(f"{server.url}/metadata")
                failures = 0 if response.status_code == 200 else failures + 1
            except httpx.HTTPError:
                failures += 1
            if failures >= max_failures:
                raise WorldServerDown(
                    f"world server on port {server.port} failed {failures} liveness polls in a row"
                )
            await asyncio.sleep(interval_s)


def rows_of(result: JsonValue) -> tuple[list[str], list[list[JsonValue]]]:
    """The columns and rows of a `controller_run_sql` answer, or ([], []) if it is not one."""
    if not isinstance(result, dict):
        return [], []
    columns = result.get("columns")
    rows = result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return [], []
    return [str(c) for c in columns], [row for row in rows if isinstance(row, list)]


def count_for(result: JsonValue, fault: str) -> int:
    """The `count` of the row whose `fault` is `fault`, and 0 when there is no such row.

    Zero is the honest answer for a fault that never fired: the table only gains a row when
    the faulted branch runs."""
    columns, rows = rows_of(result)
    if "fault" not in columns or "count" not in columns:
        return 0
    name_at = columns.index("fault")
    count_at = columns.index("count")
    for row in rows:
        if len(row) > max(name_at, count_at) and row[name_at] == fault:
            value = row[count_at]
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return 0


def trigger_count_in_process(instance: Any, sql: str, fault: str) -> int:
    """The trigger count from a shim instance the harness holds directly (the free,
    in-process re-replay of the replay-targeted faults)."""
    return count_for(instance.call("controller_run_sql", sql=sql), fault)


@dataclass
class TriggerCounter:
    """A session manager wrapper that reads the world's fault-trigger table before each
    episode closes.

    The table is untracked: it is outside `changes` and outside the state digest, and Kiln's
    settle step never reads it. `end_episode` is the only seam where the harness can run a
    control tool on the served world while the session is still open, so the read happens
    here, before the wrapped manager closes it."""

    inner: WorldSessionManager
    sql: str
    fault: str
    counts: dict[str, int] = field(default_factory=dict)

    async def world_version(
        self, world: KilnWorld, reset_kwargs: dict[str, JsonValue]
    ) -> str:
        return await self.inner.world_version(world, reset_kwargs)

    async def list_tools(self, world: KilnWorld) -> list[OpenEnvTool]:
        return await self.inner.list_tools(world)

    async def start_episode(
        self, world: KilnWorld, reset_kwargs: dict[str, JsonValue]
    ) -> WorldEpisode:
        return await self.inner.start_episode(world, reset_kwargs)

    async def call_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        return await self.inner.call_tool(episode, tool_name, arguments)

    async def call_control_tool(
        self, episode: WorldEpisode, tool_name: str, arguments: dict[str, Any]
    ) -> ToolCallOutcome:
        return await self.inner.call_control_tool(episode, tool_name, arguments)

    async def end_episode(self, episode: WorldEpisode) -> WorldEpisode:
        try:
            outcome = await self.inner.call_control_tool(
                episode, "controller_run_sql", {"sql": self.sql}
            )
            self.counts[episode.episode_id] = count_for(outcome.result, self.fault)
        except Exception as error:  # a missing count must not lose the episode
            logger.warning(
                "could not read fault triggers for episode %s: %s",
                episode.episode_id,
                error,
            )
            self.counts.setdefault(episode.episode_id, 0)
        return await self.inner.end_episode(episode)

    async def release(self, episode: WorldEpisode) -> None:
        await self.inner.release(episode)

    async def shutdown(self) -> None:
        await self.inner.shutdown()


FaultTarget = Literal["replay", "paired"]


@dataclass(frozen=True)
class FaultSpec:
    name: str
    target: FaultTarget
    expected_gates: tuple[GateName, ...]
    """The gates this fault is expected to move. `evaluable` reads them to say whether the
    comparison was possible at all."""
    port: int


@dataclass(frozen=True)
class FaultResult:
    fault: str
    target: FaultTarget
    port: int
    world_version: str
    triggers: int
    gates: list[Gate]
    moved: list[str]
    statistic_moved: bool
    detected: bool
    inconclusive: bool
    reason: str | None = None
    """Why the fault is inconclusive, when it is. An empty `moved` column that means "the
    gate could not move" reads to a person exactly like one that means "the gate did not
    move", and the two are opposite findings, so the difference is written down."""


def evaluable(
    spec: FaultSpec,
    clean: Sequence[Gate],
    faulted: Sequence[Gate],
    clean_paired: PairedStat | None,
    faulted_paired: PairedStat | None,
) -> str | None:
    """Why this fault's detection comparison could not be made, or None when it could.

    Detection is "a gate that passed clean fails under the fault". That comparison only
    exists when the gate passed clean *and* came back with a verdict under the fault. A
    faulted gate that answers `inconclusive` — most often because the fault run's smaller
    volume was judged against the clean run's episode count, which `fault_thresholds`
    exists to prevent — cannot fail, so the fault is untestable rather than undetected."""
    clean_by_name = {gate.name: gate for gate in clean}
    faulted_by_name = {gate.name: gate for gate in faulted}
    for name in spec.expected_gates:
        before = clean_by_name.get(name)
        after = faulted_by_name.get(name)
        if before is None or after is None:
            return f"gate '{name}' was not evaluated on both the clean and faulted runs"
        if before.passed is not True:
            return (
                f"gate '{name}' did not pass on the clean run ({before.outcome}), "
                "so it cannot move"
            )
        if after.passed is None:
            detail = after.reason or "no reason given"
            return (
                f"gate '{name}' came back {after.outcome} under the fault "
                f"({detail}), so it could not move"
            )
    if spec.target == "paired" and (
        clean_paired is None or faulted_paired is None or clean_paired.cells == 0
    ):
        return "the paired statistic was not computed on both runs"
    return None


def detect(
    spec: FaultSpec,
    clean: Sequence[Gate],
    clean_paired: PairedStat | None,
    faulted: Sequence[Gate],
    faulted_paired: PairedStat | None,
    triggers: int,
    thresholds: GateThresholds,
    *,
    world_version: str,
) -> FaultResult:
    """A fault is detected when one of the clean run's passing gates fails under it, or
    when the paired statistic moves outside the clean run's interval.

    Two things make it inconclusive instead, and both mean "this says nothing about
    whether the harness can see the fault": the fault never triggered, so the inputs never
    ran the faulted line; or the comparison was not evaluable, so no gate could have
    moved. `thresholds` is the set the faulted gates were judged under, recorded so the
    report can show that the fault run was gated at its own volume."""
    moved = moved_gates(clean, faulted)
    statistic_moved = (
        spec.target == "paired"
        and clean_paired is not None
        and faulted_paired is not None
        and moved_beyond_interval(clean_paired, faulted_paired)
    )
    detected = bool(moved) or statistic_moved
    reason = (
        None if triggers else "the fault never triggered: 0 rows in the trigger table"
    )
    if reason is None and not detected:
        reason = evaluable(spec, clean, faulted, clean_paired, faulted_paired)
    return FaultResult(
        fault=spec.name,
        target=spec.target,
        port=spec.port,
        world_version=world_version,
        triggers=triggers,
        gates=list(faulted),
        moved=moved,
        statistic_moved=statistic_moved,
        detected=detected,
        inconclusive=reason is not None,
        reason=(
            reason
            if reason is None
            else f"{reason} (judged at min_valid_per_config="
            f"{thresholds.min_valid_per_config} of {thresholds.episodes_per_config})"
        ),
    )
