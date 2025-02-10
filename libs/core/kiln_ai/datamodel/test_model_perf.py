import shutil
import uuid

import pytest

from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)

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


@pytest.fixture
def task_run(tmp_path):
    # setup a valid project/task/task_run for testing
    output_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "test-model",
            "model_provider": "test-provider",
            "adapter_name": "test-adapter",
        },
    )

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
        source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "test-model",
                "model_provider": "test-provider",
                "adapter_name": "test-adapter",
            },
        ),
    )

    # Save for later usage
    task_run = TaskRun(
        input='{"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side"}',
        input_source=output_source,
        output=task_output,
    )
    task_run.parent = task
    task_run.save_to_file()

    return task_run


@pytest.mark.benchmark
def test_benchmark_load_from_file(benchmark, task_run):
    task_run_path = task_run.path

    iterations = 500
    total_time = 0

    for _ in range(iterations):
        # Copy the task to a new temp path, so we don't get warm loads/cached loads
        temp_path = task_run.path.parent / f"temp_task_run_{uuid.uuid4()}.json"
        shutil.copy(str(task_run_path), str(temp_path))

        # only time loading the model (and one accessor for delayed validation)
        start_time = benchmark._timer()
        loaded = TaskRun.load_from_file(temp_path)
        assert loaded.id == task_run.id
        end_time = benchmark._timer()

        total_time += end_time - start_time

    avg_time_per_iteration = total_time / iterations
    ops_per_second = 1.0 / avg_time_per_iteration

    # I get 8k ops per second on my MBP. Lower value here for CI.
    # Prior to optimization was 290 ops per second.
    if ops_per_second < 1000:
        pytest.fail(f"Ops per second: {ops_per_second:.6f}, expected more than 1k ops")
