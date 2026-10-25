import asyncio
import gc
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Awaitable, Callable

import pytest

from kiln_ai.adapters.eval import trace_index
from kiln_ai.adapters.eval.trace_index import (
    TraceIndex,
    TraceKey,
    trace_key,
    world_trace_tag,
)
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.eval_splits import ItemSource
from kiln_ai.datamodel.task_run import EvalItemSource, eval_item_key
from kiln_ai.datamodel.world import WorldEpisode, WorldReset

KEY: TraceKey = ("eval_input", "item1", "rc1", "")


@pytest.fixture
def task(tmp_path):
    task = Task(
        name="test",
        description="test",
        instruction="do the thing",
        path=tmp_path / "task.kiln",
    )
    task.save_to_file()
    return task


def output_source(run_config_id: str | None) -> DataSource:
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "gpt-4",
            "model_provider": "openai",
            "adapter_name": "test_adapter",
        },
        run_config_id=run_config_id,
    )


def save_run(
    task: Task,
    *,
    run_config_id: str | None = "rc1",
    eval_source: EvalItemSource | None = None,
    output: str = "generated",
    world_episode: WorldEpisode | None = None,
) -> TaskRun:
    run = TaskRun(
        parent=task,
        input="the input",
        output=TaskOutput(output=output, source=output_source(run_config_id)),
        eval_source=eval_source,
        world_episode=world_episode,
    )
    run.save_to_file()
    return run


def save_trace(
    task: Task,
    *,
    source_type: ItemSource = "eval_input",
    source_id: str = "item1",
    run_config_id: str | None = "rc1",
    output: str = "generated",
    world_version: str | None = None,
) -> TaskRun:
    return save_run(
        task,
        run_config_id=run_config_id,
        eval_source=EvalItemSource(source_type=source_type, source_id=source_id),
        output=output,
        world_episode=episode_for(source_id, world_version),
    )


def episode_for(source_id: str, world_version: str | None) -> WorldEpisode | None:
    """A world run's settled episode record, carrying the version the trace key is read
    from."""
    if not world_version:
        return None
    return WorldEpisode(
        reset=WorldReset(world_id="w1"),
        episode_id=f"ep_{source_id}",
        world_version=world_version,
        final_state={"notes": []},
    )


class Generator:
    """Builds `generate` callables, and records how many of them ran.

    `for_key` mirrors what Phase 3's runner does: it closes over the job it is generating
    for, and stamps the persisted run with that job's item and run config. Tests that
    want the mismatch case ask for a key the index was not asked about.
    """

    def __init__(self, task: Task, *, persist: bool = True, raises: bool = False):
        self.task = task
        self.persist = persist
        self.raises = raises
        self.calls = 0
        self.rendezvous: "Rendezvous | None" = None

    def for_key(self, key: TraceKey) -> Callable[[], Awaitable[TaskRun]]:
        source_type, source_id, run_config_id, world_version = key

        async def generate() -> TaskRun:
            self.calls += 1
            # Real generation is a network call. Yielding here is what makes the
            # concurrency tests able to fail: without it, a generator that never suspends
            # would let every caller run to completion in turn, and an unlocked index
            # would look correct.
            await asyncio.sleep(0)
            if self.rendezvous is not None:
                await self.rendezvous.wait()
            if self.raises:
                raise RuntimeError("generation failed")
            if not self.persist:
                return TaskRun(
                    input="the input",
                    output=TaskOutput(
                        output="unsaved", source=output_source(run_config_id)
                    ),
                    eval_source=EvalItemSource(
                        source_type=source_type,
                        source_id=source_id,
                    ),
                    world_episode=episode_for(source_id, world_version),
                )
            return save_trace(
                self.task,
                source_type=source_type,
                source_id=source_id,
                run_config_id=run_config_id,
                output=f"generated {self.calls}",
                world_version=world_version or None,
            )

        return generate


class Rendezvous:
    """Blocks each arrival until `count` of them have arrived.

    Turns "these ran concurrently" into a pass/fail rather than a timing measurement: if
    the per-key lock were global, the first generator would wait for peers that can never
    start, and the wait times out.
    """

    def __init__(self, count: int, timeout: float = 5.0):
        self.count = count
        self.timeout = timeout
        self.arrived = 0
        self._all_here = asyncio.Event()

    async def wait(self) -> None:
        self.arrived += 1
        if self.arrived >= self.count:
            self._all_here.set()
        await asyncio.wait_for(self._all_here.wait(), timeout=self.timeout)


@pytest.mark.parametrize(
    "item, run_config_id",
    [
        (("task_run", None), "rc1"),
        (("eval_input", None), "rc1"),
        (("task_run", ""), "rc1"),
        (("task_run", "item1"), None),
        (("task_run", "item1"), ""),
        (("task_run", None), None),
    ],
)
def test_trace_key_rejects_missing_ids(item, run_config_id):
    with pytest.raises(ValueError, match="needs both an item id and a run config id"):
        trace_key(item, run_config_id)


@pytest.mark.parametrize("source_type", ["eval_input", "task_run"])
def test_trace_key_from_eval_item_source(source_type: ItemSource):
    source = EvalItemSource(source_type=source_type, source_id="item1")
    assert trace_key(eval_item_key(source), "rc1") == (
        source_type,
        "item1",
        "rc1",
        "",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_type", ["eval_input", "task_run"])
async def test_seed_reuses_existing_trace(task, source_type: ItemSource):
    existing = save_trace(task, source_type=source_type, source_id="item1")
    generate = Generator(task)
    key: TraceKey = (source_type, "item1", "rc1", "")

    index = TraceIndex(task)
    trace, was_generated = await index.get_or_create(key, generate.for_key(key))

    assert was_generated is False
    assert trace.id == existing.id
    assert trace.output.output == "generated"
    assert generate.calls == 0


@pytest.mark.asyncio
async def test_seed_ignores_ordinary_dataset_runs(task):
    dataset_run = save_run(task)
    generate = Generator(task)
    key: TraceKey = ("task_run", str(dataset_run.id), "rc1", "")

    index = TraceIndex(task)
    trace, was_generated = await index.get_or_create(key, generate.for_key(key))

    assert was_generated is True
    assert trace.id != dataset_run.id
    assert generate.calls == 1


@pytest.mark.asyncio
async def test_seed_ignores_trace_without_run_config(task):
    """Half a key matches nothing: a trace with no run config can't be claimed by a job."""
    save_trace(task, run_config_id=None)
    generate = Generator(task)

    index = TraceIndex(task)
    _, was_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is True
    assert generate.calls == 1


@pytest.mark.asyncio
async def test_seed_duplicate_keys_first_wins(task):
    save_trace(task, output="first")
    save_trace(task, output="second")
    # Asserted against the order the seed itself iterates, not filesystem ordering: which
    # of two synced duplicates wins is arbitrary (D8), that it is stable is not.
    expected = next(
        run
        for run in task.runs(readonly=True, include_eval_generated=True)
        if run.eval_source is not None
    )
    generate = Generator(task)

    index = TraceIndex(task)
    trace, was_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is False
    assert trace.id == expected.id
    assert generate.calls == 0


def test_concurrent_seeds_of_one_task_read_it_one_at_a_time(task, monkeypatch):
    """Eval jobs that start together each seed an index. On a cold cache, each reader of
    the task parses its own copy of every TaskRun, so the reads must not overlap."""
    save_trace(task)
    real_runs = Task.runs
    active = 0
    most_active = 0
    counter_lock = threading.Lock()

    def counting_runs(self, *args, **kwargs):
        nonlocal active, most_active
        with counter_lock:
            active += 1
            most_active = max(most_active, active)
        try:
            time.sleep(0.05)
            return real_runs(self, *args, **kwargs)
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(Task, "runs", counting_runs)

    with ThreadPoolExecutor(max_workers=4) as pool:
        indexes = list(pool.map(lambda _: TraceIndex(task), range(4)))

    assert most_active == 1
    assert all(KEY in index._paths for index in indexes)


def test_seeds_of_different_tasks_do_not_wait_for_each_other(
    task, tmp_path, monkeypatch
):
    other = Task(
        name="other",
        description="other",
        instruction="do the other thing",
        path=tmp_path / "other" / "task.kiln",
    )
    other.save_to_file()
    real_runs = Task.runs
    # Each seed waits here for the other: a lock shared across tasks breaks the barrier.
    both_reading = threading.Barrier(2, timeout=5)

    def meeting_runs(self, *args, **kwargs):
        both_reading.wait()
        return real_runs(self, *args, **kwargs)

    monkeypatch.setattr(Task, "runs", meeting_runs)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(TraceIndex, [task, other]))


@pytest.mark.asyncio
async def test_generated_trace_is_reused_without_reseeding(task):
    """The live half: a trace generated during a run is visible to the rest of it.

    This is what makes a retry after a scoring failure re-score rather than regenerate.
    """
    generate = Generator(task)
    index = TraceIndex(task)

    first, first_generated = await index.get_or_create(KEY, generate.for_key(KEY))
    second, second_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert first_generated is True
    assert second_generated is False
    assert second.id == first.id
    assert generate.calls == 1


@pytest.mark.asyncio
async def test_generated_trace_is_found_by_a_fresh_index(task):
    """The cross-run half, and the whole point of the project.

    A later eval builds a new index from disk, and must find what this one generated —
    which only works if the run's own stored fields agree with the key it was generated
    for. Nothing in a single run's behavior would reveal it if they didn't.
    """
    generate = Generator(task)
    generated, _ = await TraceIndex(task).get_or_create(KEY, generate.for_key(KEY))

    next_run = Generator(task)
    trace, was_generated = await TraceIndex(task).get_or_create(
        KEY, next_run.for_key(KEY)
    )

    assert was_generated is False
    assert trace.id == generated.id
    assert next_run.calls == 0
    assert generate.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stamped_key",
    [
        ("eval_input", "item1", "rc_other", ""),
        ("eval_input", "item_other", "rc1", ""),
        ("task_run", "item1", "rc1", ""),
    ],
)
async def test_generated_run_stamped_with_another_key_raises(
    task, stamped_key: TraceKey
):
    """A trace that files itself elsewhere is a silent, permanent regeneration."""
    generate = Generator(task)
    index = TraceIndex(task)

    with pytest.raises(ValueError, match="files itself under"):
        await index.get_or_create(KEY, generate.for_key(stamped_key))


@pytest.mark.asyncio
async def test_generated_run_without_eval_source_raises(task):
    """The same failure by omission: an unflagged run is not a trace at all.

    It would also be a dataset run, visible in every fine-tune set and few-shot prompt.
    """
    index = TraceIndex(task)

    async def generate_unflagged() -> TaskRun:
        return save_run(task)

    with pytest.raises(ValueError, match="files itself under None"):
        await index.get_or_create(KEY, generate_unflagged)

    retry = Generator(task)
    _, was_generated = await index.get_or_create(KEY, retry.for_key(KEY))
    assert was_generated is True


@pytest.mark.asyncio
async def test_distinct_keys_do_not_share_a_trace(task):
    generate = Generator(task)
    index = TraceIndex(task)
    keys: list[TraceKey] = [
        ("eval_input", "item1", "rc1", ""),
        ("eval_input", "item1", "rc2", ""),
        ("task_run", "item1", "rc1", ""),
    ]

    traces = [
        (await index.get_or_create(key, generate.for_key(key)))[0] for key in keys
    ]

    assert generate.calls == 3
    assert len({trace.id for trace in traces}) == 3
    # Each is findable on its own key by a later index, not just distinguishable now.
    fresh = TraceIndex(task)
    reused = Generator(task)
    for key, trace in zip(keys, traces):
        found, was_generated = await fresh.get_or_create(key, reused.for_key(key))
        assert was_generated is False
        assert found.id == trace.id
    assert reused.calls == 0


@pytest.mark.asyncio
async def test_concurrent_callers_on_one_key_generate_once(task):
    """The test that protects the money.

    25 is `AsyncJobRunner`'s default concurrency, and jobs collide on one key whenever
    several eval configs score the same item under the same run config.
    """
    generate = Generator(task)
    index = TraceIndex(task)

    results = await asyncio.gather(
        *(index.get_or_create(KEY, generate.for_key(KEY)) for _ in range(25))
    )

    assert generate.calls == 1
    assert [was_generated for _, was_generated in results].count(True) == 1
    assert len({trace.id for trace, _ in results}) == 1


@pytest.mark.asyncio
async def test_distinct_keys_generate_concurrently(task):
    """The per-key lock must not have become a global one."""
    generate = Generator(task)
    generate.rendezvous = Rendezvous(count=5)
    index = TraceIndex(task)
    keys: list[TraceKey] = [("eval_input", f"item{i}", "rc1", "") for i in range(5)]

    results = await asyncio.gather(
        *(index.get_or_create(key, generate.for_key(key)) for key in keys)
    )

    assert generate.calls == 5
    assert all(was_generated for _, was_generated in results)


@pytest.mark.asyncio
async def test_unsaved_generated_run_raises_and_is_not_indexed(task):
    unsaved = Generator(task, persist=False)
    index = TraceIndex(task)

    with pytest.raises(ValueError, match="returned an unsaved run"):
        await index.get_or_create(KEY, unsaved.for_key(KEY))

    saved = Generator(task)
    _, was_generated = await index.get_or_create(KEY, saved.for_key(KEY))
    assert was_generated is True
    assert saved.calls == 1


@pytest.mark.asyncio
async def test_failed_generation_leaves_the_key_free(task):
    """Architecture §8: generation raises, nothing is persisted, the retry tries again."""
    failing = Generator(task, raises=True)
    index = TraceIndex(task)

    with pytest.raises(RuntimeError, match="generation failed"):
        await index.get_or_create(KEY, failing.for_key(KEY))

    retry = Generator(task)
    trace, was_generated = await index.get_or_create(KEY, retry.for_key(KEY))
    assert was_generated is True
    assert retry.calls == 1
    assert trace.path is not None


@pytest.mark.asyncio
async def test_restamped_trace_file_is_not_served(task):
    """A record that changed identity under an indexed path must not be handed out.

    Only reachable via sync replacing a file in place, and worse than the write-side
    mismatch it mirrors: serving it would score this judge against another item's output,
    and the scores would look entirely normal.
    """
    existing = save_trace(task)
    index = TraceIndex(task)
    assert existing.path is not None
    restamped = TaskRun.load_from_file(existing.path)
    restamped.eval_source = EvalItemSource(
        source_type="eval_input", source_id="item_other"
    )
    restamped.save_to_file()

    generate = Generator(task)
    trace, was_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is True
    assert trace.id != existing.id
    assert generate.calls == 1


@pytest.mark.asyncio
async def test_vanished_trace_file_regenerates(task):
    """A deleted trace degrades to a regeneration, never an error (architecture §8)."""
    existing = save_trace(task)
    index = TraceIndex(task)
    assert existing.path is not None
    existing.path.unlink()

    generate = Generator(task)
    trace, was_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is True
    assert trace.id != existing.id
    assert generate.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corrupt_content",
    [
        # Truncated JSON, as an in-place write interrupted mid-file leaves behind.
        '{"v": 1, "id": ',
        # Valid JSON that no longer validates as a TaskRun.
        '{"v": 1, "model_type": "task_run"}',
        # A schema version from a newer build, refused with a plain ValueError.
        '{"v": 999999, "model_type": "task_run", "input": "i"}',
    ],
)
async def test_corrupt_trace_file_regenerates(task, caplog, corrupt_content):
    """A trace file that no longer parses degrades like a deleted one: drop the entry,
    warn, and regenerate — rather than failing every job on this key forever."""
    existing = save_trace(task)
    index = TraceIndex(task)
    assert existing.path is not None
    existing.path.write_text(corrupt_content, encoding="utf-8")
    # Bump mtime so the model cache cannot serve the previously loaded instance.
    stat = existing.path.stat()
    os.utime(existing.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    generate = Generator(task)
    with caplog.at_level(logging.WARNING, logger="kiln_ai.adapters.eval.trace_index"):
        trace, was_generated = await index.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is True
    assert trace.id != existing.id
    assert generate.calls == 1
    warning = next(r for r in caplog.records if "failed to load" in r.getMessage())
    assert warning.levelno == logging.WARNING
    assert str(existing.path) in warning.getMessage()

    # The regenerated trace is indexed: the next lookup serves it without generating.
    again, was_generated_again = await index.get_or_create(KEY, generate.for_key(KEY))
    assert was_generated_again is False
    assert again.id == trace.id


# ---------------------------------------------------------------------------
# Variant slot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("world_version", [None, ""])
def test_trace_key_without_variant_is_empty_string(world_version):
    assert trace_key(("eval_input", "item1"), "rc1", world_version) == (
        "eval_input",
        "item1",
        "rc1",
        "",
    )


def test_trace_key_carries_variant():
    assert trace_key(("eval_input", "item1"), "rc1", "syn1:abc") == (
        "eval_input",
        "item1",
        "rc1",
        "syn1:abc",
    )


def test_stored_world_version_separates_traces(task):
    """Two generations of one item under one run config, in different world versions, are
    two entries, keyed by the version on each run's episode; a job without a world never
    matches a world trace."""
    plain = save_run(
        task, eval_source=EvalItemSource(source_type="eval_input", source_id="item1")
    )
    fixture_a = save_run(
        task,
        eval_source=EvalItemSource(source_type="eval_input", source_id="item1"),
        world_episode=episode_for("item1", "syn1:a"),
        output="from fixture a",
    )
    index = TraceIndex(task)
    reset = WorldReset(world_id="w1")
    assert index._paths[("eval_input", "item1", "rc1", "")] == plain.path
    assert (
        index._paths[("eval_input", "item1", "rc1", world_trace_tag("syn1:a", reset))]
        == fixture_a.path
    )
    assert (
        "eval_input",
        "item1",
        "rc1",
        world_trace_tag("syn1:b", reset),
    ) not in index._paths


def test_world_trace_tag_separates_resets():
    """The world half of the key covers the reset as well as the version, so an input
    whose world_reset was edited no longer matches the trace made from the old one."""
    a = WorldReset(world_id="w1", reset_kwargs={"fixture_id": "a", "seed": 1})
    same_a = WorldReset(world_id="w1", reset_kwargs={"seed": 1, "fixture_id": "a"})
    b = WorldReset(world_id="w1", reset_kwargs={"fixture_id": "b", "seed": 1})
    assert world_trace_tag("env@1", a) == world_trace_tag("env@1", same_a)
    assert world_trace_tag("env@1", a) != world_trace_tag("env@1", b)
    assert world_trace_tag("env@1", a) != world_trace_tag("env@2", a)
    assert world_trace_tag("env@1", a).startswith("env@1#")


def test_unsettled_world_trace_is_never_indexed(task):
    """A world trace saved before its episode ended records no final state, which is
    what graders read: it files under no key, so its job regenerates rather than
    reusing it."""
    unsettled = episode_for("item1", "syn1:a")
    assert unsettled is not None
    save_run(
        task,
        eval_source=EvalItemSource(source_type="eval_input", source_id="item1"),
        world_episode=unsettled.model_copy(update={"final_state": None}),
    )
    assert TraceIndex(task)._paths == {}


# ---------------------------------------------------------------------------
# Sharing across runners
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_indexes_on_one_task_generate_once(task):
    """Two eval jobs that share a run config under different eval configs.

    Each job builds its own runner, and so its own index, and both are seeded before
    either generates. Without a shared view both miss on the same key and both pay for
    the trace.
    """
    generate = Generator(task)
    first = TraceIndex(task)
    second = TraceIndex(task)

    results = await asyncio.gather(
        first.get_or_create(KEY, generate.for_key(KEY)),
        second.get_or_create(KEY, generate.for_key(KEY)),
    )

    assert generate.calls == 1
    assert [was_generated for _, was_generated in results].count(True) == 1
    assert len({trace.id for trace, _ in results}) == 1


@pytest.mark.asyncio
async def test_indexes_on_separately_loaded_tasks_share(task):
    """Each job loads its own Task from disk, so sharing has to meet on the file, not on
    the object."""
    assert task.path is not None
    generate = Generator(task)
    first = TraceIndex(Task.load_from_file(task.path))
    second = TraceIndex(Task.load_from_file(task.path))

    generated, _ = await first.get_or_create(KEY, generate.for_key(KEY))
    reused, was_generated = await second.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is False
    assert reused.id == generated.id
    assert generate.calls == 1


@pytest.mark.asyncio
async def test_indexes_on_different_tasks_do_not_share(tmp_path):
    """The key carries no task, so the shared state must be per task: a trace of one
    task is never another task's output."""
    tasks = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        other = Task(
            name=name,
            description="test",
            instruction="do the thing",
            path=tmp_path / name / "task.kiln",
        )
        other.save_to_file()
        tasks.append(other)
    generators = [Generator(other) for other in tasks]
    indexes = [TraceIndex(other) for other in tasks]

    results = await asyncio.gather(
        *(
            index.get_or_create(KEY, generator.for_key(KEY))
            for index, generator in zip(indexes, generators)
        )
    )

    assert [generator.calls for generator in generators] == [1, 1]
    assert all(was_generated for _, was_generated in results)


@pytest.mark.asyncio
async def test_a_joining_index_finds_traces_synced_in_after_the_first(task):
    """A long-lived server keeps the shared state while any job on the task runs. A job
    that starts later must still find a trace that sync brought in meanwhile, so joining
    reseeds from disk."""
    generate = Generator(task)
    running = TraceIndex(task)
    synced = save_trace(task)

    joining = TraceIndex(task)
    trace, was_generated = await joining.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is False
    assert trace.id == synced.id
    assert generate.calls == 0
    # The running job sees it too, through the shared view.
    trace, was_generated = await running.get_or_create(KEY, generate.for_key(KEY))
    assert was_generated is False
    assert trace.id == synced.id


@pytest.mark.asyncio
async def test_a_joining_index_replaces_a_shared_entry_whose_file_is_gone(task):
    """Sync can delete the trace a running job indexed and bring in another machine's
    trace for the same key. A job that starts later must reuse the one on disk, not
    drop the dead entry and generate again."""
    indexed = save_trace(task)
    running = TraceIndex(task)
    assert indexed.path is not None
    indexed.path.unlink()
    synced = save_trace(task)

    generate = Generator(task)
    joining = TraceIndex(task)
    trace, was_generated = await joining.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is False
    assert trace.id == synced.id
    assert generate.calls == 0
    trace, was_generated = await running.get_or_create(KEY, generate.for_key(KEY))
    assert was_generated is False
    assert trace.id == synced.id


@pytest.mark.asyncio
async def test_a_joining_index_keeps_a_shared_entry_whose_file_is_there(task):
    """Two traces on disk for one key, as after sync: the entry a running job already
    holds stays, so every job scores the same generation."""
    first = save_trace(task, output="first")
    running = TraceIndex(task)
    assert first.path is not None
    assert running._paths[KEY] == first.path
    save_trace(task, output="second")

    generate = Generator(task)
    joining = TraceIndex(task)
    trace, was_generated = await joining.get_or_create(KEY, generate.for_key(KEY))

    assert was_generated is False
    assert trace.id == first.id
    assert generate.calls == 0


@pytest.mark.asyncio
async def test_shared_state_is_released_with_the_last_index(task):
    """Nothing outlives the jobs that use it, so an idle server holds no task's traces
    and the next job starts from what is on disk."""
    assert task.path is not None
    path = task.path.resolve()
    generate = Generator(task)
    index = TraceIndex(task)
    await index.get_or_create(KEY, generate.for_key(KEY))
    assert path in trace_index._task_traces

    del index
    gc.collect()

    assert path not in trace_index._task_traces


@pytest.mark.asyncio
async def test_a_dropped_entry_does_not_remove_a_newer_one(task):
    """An index drops only the entry that failed to load. A path another index's seed
    filed under the key in the meantime has not failed, and stays."""
    existing = save_trace(task)
    index = TraceIndex(task)
    assert existing.path is not None
    replacement = save_trace(task)
    assert replacement.path is not None
    index._paths[KEY] = replacement.path

    index._drop(KEY, existing.path)

    assert index._paths[KEY] == replacement.path
