"""The live lookup that decides whether an eval job generates a trace or reuses one.

Reuse is keyed on `(source_type, source_id, run_config_id, world)` — the dataset item
plus the run config (and, for a world trace, the environment version and reset it ran
with), and deliberately not the eval config. That is what lets a second judge score
generations the first judge already paid for.

The lookup has to be live, not precomputed like the `already_run` set in
`EvalRunner.collect_tasks`. A set built before the first job runs cannot see a trace
persisted by another job in the same run, and `AsyncJobRunner` runs 25 of them at once:
two jobs sharing an item and a run config but differing in eval config would both miss
and both generate, spending exactly the money this exists to save. The same liveness is
what makes a retry after a scoring failure re-score rather than regenerate.

The same race exists one level up, between runners. Each background eval job builds its
own `EvalRunner`, so jobs posted together for one run config under several eval configs
are each seeded before any of them has generated. Runners that share a
`TraceIndexRegistry` therefore share one live view of each task.
"""

import hashlib
import json
import logging
import threading
import weakref
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Dict, Tuple

from pydantic import ValidationError

from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.eval_splits import ItemKey, ItemSource
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.task_run import TaskRun, eval_item_key
from kiln_ai.datamodel.world import WorldReset
from kiln_ai.utils.lock import AsyncLockManager

logger = logging.getLogger(__name__)

TraceKey = Tuple[ItemSource, str, str, str]
"""What identifies a reusable eval trace: `(source_type, source_id, run_config_id, world)`.

`str` rather than the `ID_TYPE` (`Optional[str]`) the id fields carry, because this tuple
is a dict key: an id-less item and an id-less run config would produce one
`(source_type, None, None, "")` key that every id-less job collides on, handing them each
other's traces. `trace_key()` is where that impossibility is enforced.

`world` is `world_trace_tag()` of the environment version and the reset a world trace
ran with, read from the run's `world_episode` record. It separates generations of the same
item under the same run config made in different versions of a world, or from a reset the
input has since been edited away from. It is `""` for runs without an episode, so ordinary
traces keep matching the jobs that produced them."""


def world_trace_tag(world_version: str, reset: WorldReset) -> str:
    """The world half of a trace key: the environment version, plus a digest of the
    reset. Both sides build it the same way: the runner from the input's `world_reset`,
    the index from the reset the episode recorded. An input whose reset was edited after
    its trace was made therefore no longer matches that trace, and regenerates."""
    canonical = json.dumps(
        reset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"{world_version}#{digest}"


def trace_key(
    item: ItemKey, run_config_id: ID_TYPE, world: str | None = None
) -> TraceKey:
    """The trace key for running `item` under `run_config_id`.

    The one place `ID_TYPE`'s nullability is resolved, so callers holding an `item.id` or
    a `task_run_config.id` don't each grow their own None check. Empty strings are
    rejected with None: they collide identically, and this key's whole purpose is that a
    collision is impossible.
    """
    source_type, source_id = item
    if not source_id or not run_config_id:
        raise ValueError(
            "A trace key needs both an item id and a run config id "
            f"(got item={item}, run_config_id={run_config_id}). Traces are looked up by "
            "the pair, so a missing half would match every other record missing it."
        )
    return (source_type, source_id, run_config_id, world or "")


def _stored_trace_key(run: TaskRun) -> TraceKey | None:
    """The key this run files itself under, from its own stored fields.

    Read from the run rather than from whatever the caller believes, because this is what
    the *next* process sees: a fresh index has only the record on disk to go on.

    A world trace whose episode never recorded a final state files nowhere: graders
    read that state, so a trace without it is never reused, and its job regenerates.
    """
    if run.eval_source is None:
        return None
    if run.world_episode is not None and run.world_episode.final_state is None:
        return None
    run_config_id = run.output.source.run_config_id if run.output.source else None
    if not run_config_id:
        return None
    episode = run.world_episode
    return trace_key(
        eval_item_key(run.eval_source),
        run_config_id,
        world_trace_tag(episode.world_version, episode.reset)
        if episode is not None
        else None,
    )


class _TaskTraces:
    """The state every `TraceIndex` on one task shares."""

    def __init__(self) -> None:
        # Paths, not TaskRuns: reloading re-reads the record (ModelCache validates on
        # path + mtime), so a long eval never serves a stale trace.
        self.paths: Dict[TraceKey, Path] = {}
        # Held only for dict operations, never across I/O: a seed in a worker thread and
        # jobs on the event loop both write `paths`.
        self.paths_lock = threading.Lock()
        # Held across generation, per key. asyncio locks: every index sharing them must
        # run on one event loop.
        self.locks = AsyncLockManager()
        # Seeds of one task read its runs one at a time. On a cold ModelCache, parallel
        # seeds would each parse and hold their own copy of every TaskRun.
        self.seed_lock = threading.Lock()


class TraceIndexRegistry:
    """Shares eval traces between the `TraceIndex` objects built on one task.

    Each `EvalRunner` builds its own index. Runners given the same registry reuse each
    other's traces, and two runners that need the same trace generate it once. Every
    runner that shares a registry must run on the same event loop. Without a registry,
    an index shares nothing.

    A task's shared state lives only while some index on it is alive, so an idle
    registry holds nothing.
    """

    def __init__(self) -> None:
        # Keyed by the task file's resolved path: each job loads its own Task object.
        self._traces: weakref.WeakValueDictionary[Path, _TaskTraces] = (
            weakref.WeakValueDictionary()
        )
        # A thread lock: runners are built in worker threads.
        self._lock = threading.Lock()

    def _traces_for(self, task: Task) -> _TaskTraces:
        if task.path is None:
            # An unsaved task has no runs on disk and no identity to meet on.
            return _TaskTraces()
        path = task.path.resolve()
        with self._lock:
            traces = self._traces.get(path)
            if traces is None:
                traces = _TaskTraces()
                self._traces[path] = traces
            return traces


class TraceIndex:
    """The eval traces a task already has, and the gate for creating the ones it doesn't.

    Seeded from disk at construction. Indexes built with the same `registry` share
    their view of the task, so a trace one generates is reused by the others. Each one
    still seeds, so an index built while others run also finds traces synced in since.
    """

    def __init__(self, task: Task, registry: TraceIndexRegistry | None = None):
        self._task = task
        self._shared = (
            registry._traces_for(task) if registry is not None else _TaskTraces()
        )
        self._paths = self._shared.paths
        self._locks = self._shared.locks
        self._seed()

    def _seed(self) -> None:
        # include_intermediate_runs stays False, so a trace that is the *parent* of
        # another run is invisible here. Safe because eval traces are always
        # childless: single-turn generations are single runs, and a driven
        # multi-turn conversation persists as one standalone run whose trace holds
        # the whole exchange (chain-leaf scoring reads stored dataset runs without
        # generating at all). Nothing may ever chain a child onto an eval trace
        # without revisiting this seed — the parent would turn invisible here, and
        # the eval would silently regenerate its trace on every run.
        with self._shared.seed_lock:
            runs = self._task.runs(readonly=True, include_eval_generated=True)
        newest: Dict[TraceKey, Tuple[datetime, Path]] = {}
        listed: Dict[Path, datetime] = {}
        for run in runs:
            if run.path is None:
                continue
            key = _stored_trace_key(run)
            if key is None:
                # Not an eval trace, or missing half its key — either way, no job can
                # ever match it.
                continue
            listed[run.path] = run.created_at
            # Newest wins. A drive-only run adds a trace to a key that has one, and a
            # later judge must score that drive. Synced duplicates are all correct, so
            # newest is only a stable pick for them.
            held = newest.get(key)
            if held is None or run.created_at > held[0]:
                newest[key] = (run.created_at, run.path)
        for key, (created_at, path) in newest.items():
            self._seed_entry(key, path, created_at, listed)

    def _seed_entry(
        self,
        key: TraceKey,
        path: Path,
        created_at: datetime,
        listed: Dict[Path, datetime],
    ) -> None:
        """File the newest run found on disk for `key`, unless the key's entry is newer.

        `listed` holds every eval trace the seed read, by path. An entry among them gives
        way to a newer run, as in a new index. An entry the seed did not read was filed
        after the read, by a job that generated it, so it is the newest and stays while
        its file exists. Once its file is gone, the run on disk replaces it.
        """
        existing = self._paths.get(key)
        if existing == path:
            return
        if existing is not None:
            existing_created_at = listed.get(existing)
            if existing_created_at is not None:
                if existing_created_at >= created_at:
                    return
            elif existing.exists():
                return
        with self._shared.paths_lock:
            # Replace only the entry that was checked. While the file was checked, a job
            # can have dropped it and filed a trace it generated and is scoring now.
            if self._paths.get(key) == existing:
                self._paths[key] = path

    async def get_or_create(
        self, key: TraceKey, generate: Callable[[], Awaitable[TaskRun]]
    ) -> Tuple[TaskRun, bool]:
        """The trace for `key`, generating it if this task has none.

        Returns `(trace, was_generated)`. `generate` must persist the TaskRun before
        returning, stamped so the run files itself under `key`: the trace has to be
        durable before scoring is attempted, and durable is only
        useful if the next run can find it.

        Callers racing on one key are serialized, and all but the first reuse the
        winner's trace. A `generate` that raises records nothing, leaving the key free
        for the job's retry.
        """
        async with self._locks.acquire(key):
            trace = self._load_indexed(key)
            if trace is not None:
                logger.debug("Reusing eval trace %s for %s", trace.id, key)
                return trace, False

            return await self._generate_and_index(key, generate), True

    async def create(
        self, key: TraceKey, generate: Callable[[], Awaitable[TaskRun]]
    ) -> TaskRun:
        """A new trace for `key`, generated even when the task already has one.

        For a drive-only run, whose purpose is a fresh generation: the usage the trace
        records (cost, latency) must be of this run, never of an earlier one. `generate`
        has the same contract as in `get_or_create`. The new trace replaces any earlier
        one in this index and in every index sharing it, so a later `get_or_create` on
        the key reuses it, there or in a new index seeded from disk, which keeps the
        newest trace of a key.

        Serialized with `get_or_create` on the same key, so a reuse never races the
        generation of the trace that replaces the one it would read.
        """
        async with self._locks.acquire(key):
            return await self._generate_and_index(key, generate)

    async def _generate_and_index(
        self, key: TraceKey, generate: Callable[[], Awaitable[TaskRun]]
    ) -> TaskRun:
        """Generate the trace for `key` and index it. The caller holds the key's lock."""
        run = await generate()
        self._record(key, self._generated_path(key, run))
        logger.info("Generated eval trace %s for %s", run.id, key)
        return run

    def _load_indexed(self, key: TraceKey) -> TaskRun | None:
        path = self._paths.get(key)
        if path is None:
            return None
        try:
            trace = TaskRun.load_from_file(path)
        except FileNotFoundError:
            # The trace was deleted out from under us — sync, or an external delete that
            # never went through the API's 409 guard. Degrade rather than cascade: drop
            # the entry and regenerate, rather than failing every job that wanted it.
            logger.warning(
                "Indexed eval trace for %s is gone from %s; regenerating", key, path
            )
            self._drop(key, path)
            return None
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            # The file exists but no longer parses as a TaskRun — truncated by a crash
            # mid-write, or rewritten by a newer schema. Same posture as a missing file:
            # drop the entry and regenerate, rather than failing every job on this key.
            logger.warning(
                "Indexed eval trace for %s at %s failed to load (%s); regenerating",
                key,
                path,
                error,
            )
            self._drop(key, path)
            return None

        # The write path's check, applied on read. Entries only enter `_paths` verified,
        # so this fires only if the file changed identity after it was indexed — sync
        # replacing a record in place. Rare, and worse than the write-side mismatch it
        # mirrors: that one costs a regeneration, this one would score a judge against a
        # different item's output and produce numbers that look entirely normal.
        stored = _stored_trace_key(trace)
        if stored != key:
            logger.warning(
                "Indexed eval trace at %s now files itself under %s, not %s; regenerating",
                path,
                stored,
                key,
            )
            self._drop(key, path)
            return None
        return trace

    def _record(self, key: TraceKey, path: Path) -> None:
        with self._shared.paths_lock:
            self._paths[key] = path

    def _drop(self, key: TraceKey, path: Path) -> None:
        # Only the entry that failed. Another index's seed can file a different path
        # under the key while this one was loading, and that one has not failed.
        with self._shared.paths_lock:
            if self._paths.get(key) == path:
                del self._paths[key]

    def _generated_path(self, key: TraceKey, run: TaskRun) -> Path:
        """Where a freshly generated trace was persisted, once it has earned indexing.

        Enforces both halves of `generate`'s contract: persisted, and findable again.

        The index files the run under the key the *caller* asked for, but a later process
        rebuilds the index from the run's own `eval_source`,
        `output.source.run_config_id` and `world_episode`. If those disagree, everything looks right for the
        rest of this run and the trace is never reused again — every future eval
        regenerates it, with no error to notice. So the disagreement is caught here,
        where the mistake was made.
        """
        if run.path is None:
            raise ValueError(
                f"Generating the eval trace for {key} returned an unsaved run. "
                "A trace must be persisted before it is scored, and the index holds "
                "paths rather than objects."
            )
        stored = _stored_trace_key(run)
        if stored != key:
            raise ValueError(
                f"Generating the eval trace for {key} persisted a run that files itself "
                f"under {stored}: its eval_source, output.source.run_config_id and "
                "world_episode are what a later index reads. A run that disagrees with the key it was "
                "generated for is never found again, so the trace is regenerated on "
                "every eval, forever."
            )
        return run.path
