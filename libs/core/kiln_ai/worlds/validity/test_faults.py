from __future__ import annotations

import asyncio
import json
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from kiln_ai.datamodel.world import OpenEnvTool, WorldEpisode, WorldReset
from kiln_ai.datamodel.world import World as KilnWorld
from kiln_ai.worlds.session_manager import ToolCallOutcome

from . import faults as faults_module
from .faults import (
    FaultSpec,
    TriggerCounter,
    WorldServer,
    WorldServerDown,
    WorldServerError,
    capacity_caveat,
    count_for,
    detect,
    evaluable,
    port_is_free,
    start_world_server,
    stop_world_server,
    trigger_count_in_process,
    watch_liveness,
)
from .metrics import Gate, GateThresholds, Interval, PairedStat

SERVER = """
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

payload = json.loads(sys.argv[1])
port = int(sys.argv[2])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""

IGNORES_SIGTERM = """
import signal, sys, time, pathlib
signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text("ready")
while True:
    time.sleep(0.05)
"""

STAYS_UP = """
import sys, time, pathlib
pathlib.Path(sys.argv[1]).write_text("ready")
while True:
    time.sleep(0.05)
"""


def wait_ready(flag, process) -> None:
    """A signal sent before the child has installed its handler proves nothing."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if flag.exists():
            return
        assert process.poll() is None, "the child exited before it was ready"
        time.sleep(0.02)
    raise AssertionError("the child never came up")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def metadata_cmd(payload: dict[str, Any], port: int) -> list[str]:
    return [sys.executable, "-c", SERVER, json.dumps(payload), str(port)]


@pytest.fixture
def started():
    servers: list[WorldServer] = []

    def start(payload: dict[str, Any], **kwargs) -> WorldServer:
        port = kwargs.pop("port", None) or free_port()
        server = start_world_server(
            metadata_cmd(payload, port),
            {},
            port,
            min_concurrent_envs=kwargs.pop("min_concurrent_envs", 2),
            ready_timeout_s=kwargs.pop("ready_timeout_s", 20.0),
            **kwargs,
        )
        servers.append(server)
        return server

    yield start
    for server in servers:
        stop_world_server(server, grace_s=2.0)


def test_port_is_free_sees_a_bound_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert port_is_free(port) is False
    assert port_is_free(free_port()) is True


def test_start_world_server_refuses_bound_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        with pytest.raises(WorldServerError, match="already bound"):
            start_world_server(
                [sys.executable, "-c", "pass"], {}, port, min_concurrent_envs=1
            )


def test_start_world_server_checks_version_suffix_and_capacity(started):
    server = started(
        {
            "name": "notes",
            "version": "notes@1+fault.per_page",
            "max_concurrent_envs": 8,
        },
        expect_version_suffix="+fault.per_page",
        min_concurrent_envs=4,
    )
    assert server.version == "notes@1+fault.per_page"
    assert server.max_concurrent_envs == 8
    assert server.url.endswith(str(server.port))

    with pytest.raises(WorldServerError, match="does not end with"):
        started(
            {"name": "notes", "version": "notes@1", "max_concurrent_envs": 8},
            expect_version_suffix="+fault.per_page",
        )

    with pytest.raises(WorldServerError, match="fewer than the 4"):
        started(
            {"name": "notes", "version": "notes@1", "max_concurrent_envs": 1},
            min_concurrent_envs=4,
        )


def test_start_world_server_caveats_a_capacity_it_could_not_check(started):
    """A server that does not publish a capacity is accepted — but a run that never
    verified it must not read in validity.json exactly like one that did."""
    server = started({"name": "notes", "version": "notes@1"}, min_concurrent_envs=50)
    assert server.max_concurrent_envs is None
    caveat = capacity_caveat(server)
    assert caveat is not None
    assert "was not verified" in caveat and "50" in caveat

    checked = started(
        {"name": "notes", "version": "notes@1", "max_concurrent_envs": 60},
        min_concurrent_envs=50,
    )
    assert capacity_caveat(checked) is None


def test_start_world_server_kills_the_child_on_a_bad_body():
    """A 200 that is not JSON must not leave the child holding the port: the next fault's
    server would be refused with a misleading "already bound"."""
    port = free_port()
    script = (
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        body = b'not json'\n"
        "        self.send_response(200)\n"
        "        self.send_header('Content-Length', str(len(body)))\n"
        "        self.end_headers()\n"
        "        self.wfile.write(body)\n"
        "    def log_message(self, *a):\n"
        "        pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    with pytest.raises(WorldServerError):
        start_world_server(
            [sys.executable, "-c", script, str(port)],
            {},
            port,
            min_concurrent_envs=1,
            ready_timeout_s=1.0,
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not port_is_free(port):
        time.sleep(0.05)
    assert port_is_free(port), "the child kept the port"


def test_start_world_server_writes_the_child_output_to_a_log(started, tmp_path):
    """Piped-and-undrained output blocks the server at about 64 KB. It goes to a file or
    to /dev/null, never to a pipe nobody reads."""
    log = tmp_path / "world.log"
    server = started(
        {"name": "notes", "version": "notes@1"}, min_concurrent_envs=1, log_path=log
    )
    assert server.process.stdout is None
    assert log.exists()


def test_start_world_server_ready_timeout():
    port = free_port()
    with pytest.raises(WorldServerError, match="not ready within"):
        start_world_server(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            {},
            port,
            min_concurrent_envs=1,
            ready_timeout_s=0.5,
        )


def test_start_world_server_reports_an_early_exit():
    port = free_port()
    with pytest.raises(WorldServerError, match="exited with code"):
        start_world_server(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('bad world'); sys.exit(3)",
            ],
            {},
            port,
            min_concurrent_envs=1,
            ready_timeout_s=10.0,
        )


def test_start_world_server_passes_the_environment_through(started, tmp_path):
    """The fault name reaches the world through the environment the caller chose."""
    port = free_port()
    script = (
        "import os, json, sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "fault = os.environ.get('WORLD_FAULT', '')\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        body = json.dumps({'version': 'notes@1+fault.' + fault}).encode()\n"
        "        self.send_response(200)\n"
        "        self.send_header('Content-Length', str(len(body)))\n"
        "        self.end_headers()\n"
        "        self.wfile.write(body)\n"
        "    def log_message(self, *a):\n"
        "        pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n"
    )
    server = start_world_server(
        [sys.executable, "-c", script, str(port)],
        {"WORLD_FAULT": "per_page"},
        port,
        min_concurrent_envs=1,
        expect_version_suffix="+fault.per_page",
        ready_timeout_s=20.0,
    )
    try:
        assert server.version == "notes@1+fault.per_page"
    finally:
        stop_world_server(server, grace_s=2.0)


def test_stop_world_server_sigterm_then_sigkill(tmp_path):
    flag = tmp_path / "ready"
    process = subprocess.Popen([sys.executable, "-c", IGNORES_SIGTERM, str(flag)])
    wait_ready(flag, process)
    server = WorldServer(
        process=process, port=0, url="", version="v", max_concurrent_envs=None
    )
    stop_world_server(server, grace_s=0.5)
    assert process.poll() is not None
    assert process.returncode == -signal.SIGKILL

    # stopping an already-dead server is a no-op
    stop_world_server(server, grace_s=0.5)


def test_stop_world_server_asks_politely_first(tmp_path):
    """SIGKILL is the fallback, not the method: a world that closes its sessions on
    SIGTERM must be given the chance to."""
    flag = tmp_path / "ready"
    process = subprocess.Popen([sys.executable, "-c", STAYS_UP, str(flag)])
    wait_ready(flag, process)
    server = WorldServer(
        process=process, port=0, url="", version="v", max_concurrent_envs=None
    )
    stop_world_server(server, grace_s=5.0)
    assert process.returncode == -signal.SIGTERM


class FlakyTransport(httpx.AsyncBaseTransport):
    """Answers to a script of "ok" and "fail", so the liveness rule can be tested for
    *consecutive* failures rather than cumulative ones."""

    def __init__(self, script: list[str]) -> None:
        self.script = list(script)
        self.seen = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        outcome = self.script[min(self.seen, len(self.script) - 1)]
        self.seen += 1
        if outcome == "fail":
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"version": "notes@1"})


def liveness_server() -> WorldServer:
    return WorldServer(
        process=None,  # type: ignore[arg-type]
        port=1,
        url="http://127.0.0.1:1",
        version="v",
        max_concurrent_envs=None,
    )


async def test_watch_liveness_raises_after_five_consecutive_failures(monkeypatch):
    transport = FlakyTransport(["fail"] * 5)
    monkeypatch.setattr(faults_module.httpx, "AsyncClient", _client_with(transport))
    with pytest.raises(WorldServerDown, match="failed 5 liveness polls"):
        await watch_liveness(liveness_server(), interval_s=0.0, max_failures=5)
    assert transport.seen == 5


async def test_watch_liveness_counts_consecutive_failures_not_cumulative(monkeypatch):
    """Four failures spread around a success are a flaky network, not a dead server; a
    cumulative count would abort a healthy paid step."""
    transport = FlakyTransport(
        ["fail", "fail", "ok", "fail", "fail", "ok", "fail", "fail"] + ["ok"] * 50
    )
    monkeypatch.setattr(faults_module.httpx, "AsyncClient", _client_with(transport))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            watch_liveness(liveness_server(), interval_s=0.0, max_failures=5),
            timeout=0.3,
        )
    assert transport.seen > 8


def _client_with(transport: httpx.AsyncBaseTransport):
    # Bound before the patch: `httpx.AsyncClient` is what is being replaced.
    real = httpx.AsyncClient

    def build(*args, **kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("transport", None)
        return real(transport=transport, **kwargs)

    return build


# ---- trigger counting ----

ROWS = {
    "columns": ["fault", "count"],
    "rows": [["page_size", 12], ["other", 3]],
    "row_count": 2,
    "truncated": False,
}


def test_count_for_reads_the_named_row():
    assert count_for(ROWS, "page_size") == 12
    assert count_for(ROWS, "never_fired") == 0
    assert count_for({"columns": [], "rows": []}, "page_size") == 0
    assert count_for(None, "page_size") == 0


@dataclass
class FakeInstance:
    result: Any
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def call(self, name: str, **arguments):
        self.calls.append((name, arguments))
        return self.result


def test_trigger_count_in_process_zero_when_no_row():
    instance = FakeInstance(ROWS)
    assert (
        trigger_count_in_process(instance, "SELECT fault, count FROM t", "page_size")
        == 12
    )
    assert instance.calls == [
        ("controller_run_sql", {"sql": "SELECT fault, count FROM t"})
    ]
    empty = FakeInstance({"columns": ["fault", "count"], "rows": []})
    assert trigger_count_in_process(empty, "SELECT 1", "page_size") == 0


@dataclass
class FakeManager:
    events: list[str] = field(default_factory=list)
    control_result: Any = None
    control_raises: Exception | None = None

    async def world_version(self, world, reset_kwargs) -> str:
        self.events.append("world_version")
        return "notes@1"

    async def list_tools(self, world) -> list[OpenEnvTool]:
        self.events.append("list_tools")
        return [OpenEnvTool(name="get_note")]

    async def start_episode(self, world, reset_kwargs) -> WorldEpisode:
        self.events.append("start_episode")
        return episode_record()

    async def call_tool(self, episode, tool_name, arguments) -> ToolCallOutcome:
        self.events.append(f"call_tool:{tool_name}")
        return ToolCallOutcome(result={}, error=None, reward=None, done=False)

    async def call_control_tool(self, episode, tool_name, arguments) -> ToolCallOutcome:
        self.events.append(f"call_control_tool:{tool_name}")
        if self.control_raises is not None:
            raise self.control_raises
        return ToolCallOutcome(
            result=self.control_result, error=None, reward=None, done=False
        )

    async def end_episode(self, episode) -> WorldEpisode:
        self.events.append("end_episode")
        return episode

    async def release(self, episode) -> None:
        self.events.append("release")

    async def shutdown(self) -> None:
        self.events.append("shutdown")


def episode_record(episode_id: str = "ep-1") -> WorldEpisode:
    return WorldEpisode(
        reset=WorldReset(world_id="w", reset_kwargs={}),
        episode_id=episode_id,
        world_version="notes@1",
    )


async def test_trigger_counter_reads_before_end_episode():
    inner = FakeManager(control_result=ROWS)
    counter = TriggerCounter(
        inner=inner, sql="SELECT fault, count FROM t", fault="page_size"
    )
    await counter.end_episode(episode_record())
    assert inner.events == ["call_control_tool:controller_run_sql", "end_episode"]
    assert counter.counts == {"ep-1": 12}


async def test_trigger_counter_survives_a_failed_read():
    inner = FakeManager(control_raises=RuntimeError("session closed"))
    counter = TriggerCounter(inner=inner, sql="SELECT 1", fault="f")
    await counter.end_episode(episode_record("ep-2"))
    assert counter.counts == {"ep-2": 0}
    assert "end_episode" in inner.events


async def test_trigger_counter_delegates_protocol():
    inner = FakeManager(control_result=ROWS)
    counter = TriggerCounter(inner=inner, sql="SELECT 1", fault="f")
    world = KilnWorld(name="notes")
    assert await counter.world_version(world, {}) == "notes@1"
    assert [t.name for t in await counter.list_tools(world)] == ["get_note"]
    started = await counter.start_episode(world, {})
    await counter.call_tool(started, "get_note", {})
    await counter.call_control_tool(started, "controller_changes", {})
    await counter.release(started)
    await counter.shutdown()
    assert inner.events == [
        "world_version",
        "list_tools",
        "start_episode",
        "call_tool:get_note",
        "call_control_tool:controller_changes",
        "release",
        "shutdown",
    ]


# ---- detection ----


def gate(name: str, passed: bool) -> Gate:
    return Gate(
        name=name,  # type: ignore[arg-type]
        value=0.0,
        threshold=0.0,
        passed=passed,
        outcome="passed" if passed else "failed",
        interval=None,
        inputs={},
        reason=None,
    )


def stat(delta: float, low: float, high: float) -> PairedStat:
    return PairedStat(
        delta=delta, interval=Interval(low, high), cell_agreement=1.0, cells=10
    )


SPEC = FaultSpec(
    name="page_size", target="paired", expected_gates=("paired",), port=8011
)

THRESHOLDS = GateThresholds()


def test_detect_moved_gate():
    result = detect(
        SPEC,
        [gate("paired", True), gate("replay", True)],
        stat(0.02, 0.0, 0.05),
        [gate("paired", False), gate("replay", True)],
        stat(0.03, 0.0, 0.06),
        340,
        THRESHOLDS,
        world_version="notes@1+fault.page_size",
    )
    assert result.detected is True
    assert result.moved == ["paired"]
    assert result.inconclusive is False
    assert result.reason is None
    assert result.statistic_moved is False
    assert result.world_version == "notes@1+fault.page_size"


def test_detect_statistic_beyond_interval():
    result = detect(
        SPEC,
        [gate("paired", True)],
        stat(0.02, 0.0, 0.05),
        [gate("paired", True)],
        stat(0.40, 0.3, 0.5),
        12,
        THRESHOLDS,
        world_version="notes@1+fault.page_size",
    )
    assert result.moved == []
    assert result.statistic_moved is True
    assert result.detected is True


def test_detect_zero_triggers_inconclusive():
    result = detect(
        SPEC,
        [gate("paired", True)],
        stat(0.02, 0.0, 0.05),
        [gate("paired", True)],
        stat(0.02, 0.0, 0.05),
        0,
        THRESHOLDS,
        world_version="notes@1+fault.page_size",
    )
    assert result.detected is False
    assert result.inconclusive is True
    assert result.reason is not None and "never triggered" in result.reason


def test_detect_ignores_the_statistic_for_a_replay_targeted_fault():
    replay_spec = FaultSpec(
        name="page_size", target="replay", expected_gates=("replay",), port=8011
    )
    result = detect(
        replay_spec,
        [gate("replay", True)],
        stat(0.02, 0.0, 0.05),
        [gate("replay", True)],
        stat(0.40, 0.3, 0.5),
        10,
        THRESHOLDS,
        world_version="notes@1+fault.page_size",
    )
    assert result.statistic_moved is False
    assert result.detected is False
    # the comparison was possible and the gate simply did not move: undetected, not
    # inconclusive
    assert result.inconclusive is False


def test_detect_is_inconclusive_when_the_faulted_gate_could_not_move():
    """The fault run is shorter than the clean run. Judged at the clean run's episode
    count every configuration reads as unusable, the gate answers `inconclusive`, and an
    empty `moved` column would read as "the world was faithful" instead of "nothing was
    measured"."""
    unusable = Gate(
        name="paired",
        value=None,
        threshold=None,
        passed=None,
        outcome="inconclusive",
        interval=None,
        inputs={},
        reason="configuration A unusable: 20 of 60 valid",
    )
    result = detect(
        SPEC,
        [gate("paired", True)],
        stat(0.02, 0.0, 0.05),
        [unusable],
        None,
        340,
        THRESHOLDS,
        world_version="notes@1+fault.page_size",
    )
    assert result.detected is False
    assert result.inconclusive is True
    assert result.reason is not None
    assert "could not move" in result.reason
    assert "min_valid_per_config=40 of 60" in result.reason


def test_detect_is_inconclusive_when_the_clean_gate_did_not_pass():
    result = detect(
        SPEC,
        [gate("paired", False)],
        stat(0.02, 0.0, 0.05),
        [gate("paired", False)],
        stat(0.02, 0.0, 0.05),
        10,
        THRESHOLDS,
        world_version="w",
    )
    assert result.inconclusive is True
    assert "did not pass on the clean run" in (result.reason or "")


def test_evaluable_is_none_when_the_comparison_can_be_made():
    assert (
        evaluable(
            SPEC,
            [gate("paired", True)],
            [gate("paired", False)],
            stat(0.02, 0.0, 0.05),
            stat(0.4, 0.3, 0.5),
        )
        is None
    )
