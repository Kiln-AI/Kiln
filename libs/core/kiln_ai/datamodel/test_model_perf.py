import gc
import json
import shutil
import tracemalloc
import uuid
from pathlib import Path

import pytest

from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.model_cache import ModelCache

MIB = 1024**2

test_json_schema = """{
  "type": "object",
  "properties": {
    "setup": {
      "description": "The setup of the joke",
      "title": "Setup",
      "type": "string"
    },
    "punchline": {
      "description": "The punchline to the joke",
      "title": "Punchline",
      "type": "string"
    },
    "rating": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "How funny the joke is, from 1 to 10",
      "title": "Rating"
    }
  },
  "required": [
    "setup",
    "punchline"
  ]
}
"""


def synthetic_source() -> DataSource:
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "test-model",
            "model_provider": "test-provider",
            "adapter_name": "test-adapter",
        },
    )


@pytest.fixture
def task_run(tmp_path):
    # setup a valid project/task/task_run for testing
    project_path = tmp_path / "project.kiln"
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    task = Task(
        name="Test Task",
        instruction="Test Instruction",
        parent=project,
        output_json_schema=test_json_schema,
        input_json_schema=test_json_schema,
    )

    task.save_to_file()

    task_output = TaskOutput(
        output='{"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side"}',
        source=synthetic_source(),
    )

    # Save for later usage
    task_run = TaskRun(
        input='{"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side"}',
        input_source=synthetic_source(),
        output=task_output,
    )
    task_run.parent = task
    task_run.save_to_file()

    return task_run


@pytest.mark.benchmark
@pytest.mark.parametrize(
    "readonly", [False, True], ids=["mutable_cache_off", "readonly_cache_on"]
)
def test_benchmark_load_from_file(benchmark, task_run, readonly, request):
    if readonly:
        # The app's first loads: readonly with the cache on, so each load also takes
        # the run's large values out of the cached record.
        request.getfixturevalue("model_cache_enabled")
    task_run_path = task_run.path

    iterations = 500
    total_time = 0

    for _ in range(iterations):
        # Copy the task to a new temp path, so we don't get warm loads/cached loads
        temp_path = task_run.path.parent / f"temp_task_run_{uuid.uuid4()}.json"
        shutil.copy(str(task_run_path), str(temp_path))

        # only time loading the model (and one accessor for delayed validation)
        start_time = benchmark._timer()
        loaded = TaskRun.load_from_file(temp_path, readonly=readonly)
        assert loaded.id == task_run.id
        end_time = benchmark._timer()

        total_time += end_time - start_time

    avg_time_per_iteration = total_time / iterations
    ops_per_second = 1.0 / avg_time_per_iteration

    # I get 8k ops per second on my MBP. Lower value here for CI and parallel testing.
    # Prior to optimization was 290 ops per second.
    # sys.stdout.write(f"Ops per second: {ops_per_second:.6f}")
    if ops_per_second < 500:
        pytest.fail(f"Ops per second: {ops_per_second:.6f}, expected more than 1k ops")


def prose(word_count: int) -> str:
    words = "the quick brown fox jumps over a lazy dog while it rains".split()
    return " ".join(words[i % len(words)] for i in range(word_count))


@pytest.fixture
def plaintext_task(tmp_path) -> Task:
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()
    task = Task(name="Test Task", instruction="Test Instruction", parent=project)
    task.save_to_file()
    return task


def save_runs(task: Task, count: int, turns: int) -> list[Path]:
    """Saves `count` runs of `task` with `turns` turns each, and returns their paths.

    The runs are copies of one run under different ids, written as JSON, which is much
    faster than saving each one. Assistant messages carry reasoning, as a reasoning
    model's do.
    """
    run = TaskRun(
        parent=task,
        input=prose(60),
        input_source=synthetic_source(),
        output=TaskOutput(output=prose(120), source=synthetic_source()),
    )
    run.save_to_file()
    assert run.path is not None
    raw = json.loads(run.path.read_text(encoding="utf-8"))
    raw["trace"] = [{"role": "system", "content": prose(150)}]
    for _ in range(turns):
        raw["trace"].append({"role": "user", "content": prose(60)})
        raw["trace"].append(
            {
                "role": "assistant",
                "content": prose(120),
                "reasoning_content": prose(300),
            }
        )
    runs_folder = run.path.parent.parent
    shutil.rmtree(run.path.parent)
    paths = []
    for i in range(count):
        raw["id"] = f"run{i:08d}"
        path = runs_folder / raw["id"] / TaskRun.base_filename()
        path.parent.mkdir()
        path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    return paths


@pytest.mark.slow
def test_benchmark_cache_memory(plaintext_task, monkeypatch):
    """Loading runs far beyond the budget keeps the cache's estimated size within the
    budget, and the memory it really holds within 50% of the estimate."""
    paths = save_runs(plaintext_task, count=2000, turns=20)
    budget = 20 * MIB
    cache = ModelCache(enabled=True, budget_bytes=budget)
    monkeypatch.setattr(ModelCache, "_shared_instance", cache)
    task = Task.load_from_file(plaintext_task.path, readonly=True)
    # A first load also fills process-wide caches (pydantic's, the lazy field plans),
    # which aren't the cache's memory.
    assert TaskRun.load_from_file(paths[0], readonly=True, parent=task).trace
    cache.invalidate(paths[0])
    gc.collect()

    most_bytes = 0
    tracemalloc.start()
    try:
        baseline = tracemalloc.get_traced_memory()[0]
        for path in paths:
            TaskRun.load_from_file(path, readonly=True, parent=task)
            most_bytes = max(most_bytes, cache.stats().total_bytes)
        gc.collect()
        retained = tracemalloc.get_traced_memory()[0] - baseline
    finally:
        tracemalloc.stop()

    stats = cache.stats()
    assert most_bytes <= budget
    # Some records keep their large values and most don't, so both parts' estimates
    # are measured.
    assert 0 < stats.records_with_large_values < stats.records / 2
    assert abs(retained - stats.total_bytes) <= 0.5 * stats.total_bytes, (
        f"retained {retained} bytes, estimated {stats.total_bytes}"
    )


@pytest.mark.benchmark
def test_benchmark_warm_list_load(benchmark, plaintext_task, model_cache_enabled):
    run_count = 1000
    save_runs(plaintext_task, count=run_count, turns=1)
    cached_runs = plaintext_task.runs(readonly=True)
    assert len(cached_runs) == run_count

    benchmark(plaintext_task.runs, readonly=True)

    # About 15 µs per run on a Linux dev machine. CI machines are slower, and file
    # stats on Windows much slower.
    seconds_per_run = benchmark.stats.stats.mean / run_count
    if seconds_per_run > 100e-6:
        pytest.fail(f"{seconds_per_run * 1e6:.1f} µs per run, expected under 100 µs")
