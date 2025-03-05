from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.eval_runner import EvalJob, EvalRunner
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalOutputScore,
    EvalRun,
    EvalScores,
)
from kiln_ai.datamodel.task import RunConfigProperties, TaskRunConfig


@pytest.fixture
def mock_task(tmp_path):
    task = Task(
        name="test",
        description="test",
        instruction="do the thing",
        path=tmp_path / "task.kiln",
    )
    task.save_to_file()
    return task


@pytest.fixture
def mock_eval(mock_task):
    eval = Eval(
        id="test",
        name="test",
        description="test",
        eval_set_filter_id="all",
        eval_configs_filter_id="all",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check if the output is accurate",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=mock_task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def data_source():
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "gpt-4",
            "model_provider": "openai",
            "adapter_name": "test_adapter",
        },
    )


@pytest.fixture
def mock_eval_config(mock_eval):
    eval_config = EvalConfig(
        name="test",
        model_name="gpt-4",
        model_provider="openai",
        parent=mock_eval,
        properties={
            "eval_steps": ["step1", "step2", "step3"],
        },
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_run_config(
    mock_task,
):
    rc = TaskRunConfig(
        name="test",
        description="test",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
        ),
        parent=mock_task,
    )
    rc.save_to_file()
    return rc


@pytest.fixture
def mock_eval_runner(mock_eval, mock_task, mock_eval_config, mock_run_config):
    return EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
    )


# Test with and without concurrency
@pytest.mark.parametrize("concurrency", [1, 25])
@pytest.mark.asyncio
async def test_async_eval_runner_status_updates(mock_eval_runner, concurrency):
    # Real async testing!

    job_count = 50
    # Job objects are not the right type, but since we're mocking run_job, it doesn't matter
    jobs = [{} for _ in range(job_count)]

    # Mock collect_tasks to return our fake jobs
    mock_eval_runner.collect_tasks = lambda: jobs

    # Mock run_job to return True immediately
    mock_eval_runner.run_job = AsyncMock(return_value=True)

    # Expect the status updates in order, and 1 for each job
    expected_compelted_count = 0
    async for progress in mock_eval_runner.run(concurrency=concurrency):
        assert progress.complete == expected_compelted_count
        expected_compelted_count += 1
        assert progress.errors == 0
        assert progress.total == job_count

    # Verify last status update was complete
    assert expected_compelted_count == job_count + 1

    # Verify run_job was called for each job
    assert mock_eval_runner.run_job.call_count == job_count


def test_collect_tasks_filtering(
    mock_eval,
    mock_eval_runner,
    mock_task,
    mock_eval_config,
    data_source,
    mock_run_config,
):
    """Test that tasks are properly filtered based on eval filters"""
    tags = ["tag1", "tag2", "tag3"]
    task_runs = []
    for tag in tags:
        # Create some task runs with different tags
        task_run = TaskRun(
            parent=mock_task,
            input="test1",
            input_source=data_source,
            output=TaskOutput(
                output="test1",
            ),
            tags=[tag],
        )
        task_run.save_to_file()
        task_runs.append(task_run)

    mock_eval.eval_set_filter_id = "tag::tag1"
    mock_eval.eval_configs_filter_id = "tag::tag2"

    # Create a new runner of type task run eval
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
    )
    jobs = runner.collect_tasks()

    # Should only get task_run1 jobs, the one with tag1
    assert len(jobs) == 1
    job = jobs[0]
    # job should be the tag1 item, and setup as a task run eval for mock_run_config
    assert job.item.tags == ["tag1"]
    assert job.task_run_config.id == mock_run_config.id
    assert job.eval_config.id == mock_eval_config.id

    # Change to an eval config set filter
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=None,
        eval_run_type="eval_config_eval",
    )
    jobs = runner.collect_tasks()

    # Should only get eval_config1 jobs
    assert len(jobs) == 1
    job = jobs[0]
    # job should be the tag2 item, and setup as a eval config eval for mock_eval_config
    assert job.item.tags == ["tag2"]
    assert job.eval_config.id == mock_eval_config.id
    assert job.task_run_config is None

    # Add a second task run config, and call a new runner with multiple run configs
    rc = TaskRunConfig(
        name="test2",
        description="test2",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
        ),
        parent=mock_task,
    )
    rc.save_to_file()
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config, rc],
        eval_run_type="task_run_eval",
    )
    jobs = runner.collect_tasks()
    assert len(jobs) == 2
    for job in jobs:
        assert job.item.tags == ["tag1"]
        assert job.task_run_config.id in [mock_run_config.id, rc.id]
        assert job.eval_config.id == mock_eval_config.id
    assert jobs[0].task_run_config.id != jobs[1].task_run_config.id

    # add a second eval config, and call a new runner with multiple eval configs
    eval_config = EvalConfig(
        name="test2",
        model_name="gpt-4",
        model_provider="openai",
        parent=mock_eval,
        properties={
            "eval_steps": ["step1", "step2", "step3"],
        },
    )
    eval_config.save_to_file()
    runner = EvalRunner(
        eval_configs=[mock_eval_config, eval_config],
        run_configs=None,
        eval_run_type="eval_config_eval",
    )
    jobs = runner.collect_tasks()
    # Check we get 2 jobs, one for each eval config
    assert len(jobs) == 2
    for job in jobs:
        assert job.item.tags == ["tag2"]
        assert job.eval_config.id in [mock_eval_config.id, eval_config.id]
        assert job.task_run_config is None
    assert jobs[0].eval_config.id != jobs[1].eval_config.id


def test_validate_same_task(
    mock_eval_runner,
    mock_task,
    data_source,
    tmp_path,
    mock_eval_config,
    mock_run_config,
):
    # second eval config has a different task
    eval_config = EvalConfig(
        name="test2",
        model_name="gpt-4",
        model_provider="openai",
        properties={
            "eval_steps": ["step1", "step2", "step3"],
        },
        parent=Eval(
            name="test",
            description="test",
            eval_set_filter_id="all",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="Accuracy",
                    instruction="Check if the output is accurate",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            parent=Task(
                name="test",
                description="test",
                instruction="do the thing",
            ),
        ),
    )

    with pytest.raises(
        ValueError, match="All eval configs must have the same parent eval"
    ):
        EvalRunner(
            eval_configs=[mock_eval_config, eval_config],
            run_configs=[mock_run_config],
            eval_run_type="eval_config_eval",
        )


def test_collect_tasks_excludes_already_run_task_run_eval(
    mock_eval_runner, mock_task, data_source, mock_eval_config, mock_run_config
):
    """Test that already run tasks are excluded"""
    # Create a task run
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(
            output="test",
        ),
    )
    task_run.save_to_file()

    # Prior to any eval runs, we should get the task run
    jobs = mock_eval_runner.collect_tasks()
    assert len(jobs) == 1
    assert jobs[0].item.id == task_run.id
    assert jobs[0].task_run_config.id == mock_run_config.id
    assert jobs[0].eval_config.id == mock_eval_config.id

    # Create an eval run for this task
    EvalRun(
        parent=mock_eval_config,
        dataset_id=task_run.id,
        task_run_config_id=mock_run_config.id,
        input="test",
        output="test",
        scores={"accuracy": 1.0},
    ).save_to_file()

    # Set filter to match the task
    mock_eval_runner.eval.eval_set_filter_id = "tag::tag1"
    mock_eval_runner.eval.eval_configs_filter_id = "tag::nonexistent"

    jobs = mock_eval_runner.collect_tasks()

    # Should get no jobs since the task was already run
    assert len(jobs) == 0


def test_collect_tasks_excludes_already_run_eval_config_eval(
    mock_task, data_source, mock_eval_config, mock_eval, mock_run_config
):
    """Test that already run tasks are excluded"""
    # Create a task run
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(
            output="test",
        ),
    )
    task_run.save_to_file()

    mock_eval.eval_set_filter_id = "tag::nonexistent"
    mock_eval.eval_configs_filter_id = "tag::tag1"
    mock_eval.save_to_file()

    # Prior to any eval runs, we should get 1 job for the eval config
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=None,
        eval_run_type="eval_config_eval",
    )
    jobs = runner.collect_tasks()
    assert len(jobs) == 1
    assert jobs[0].item.id == task_run.id
    assert jobs[0].eval_config.id == mock_eval_config.id
    assert jobs[0].task_run_config is None

    # Create an eval run for this eval config task run pair, so now we should get no jobs (already run)
    EvalRun(
        parent=mock_eval_config,
        dataset_id=task_run.id,
        task_run_config_id=None,
        eval_config_eval=True,
        input="test",
        output="test",
        scores={
            "accuracy": 1.0,
        },
    ).save_to_file()

    jobs = runner.collect_tasks()

    # Should get no jobs since the task was already run
    assert len(jobs) == 0


def test_collect_tasks_multiple_run_configs(
    mock_eval_runner, mock_task, data_source, mock_run_config
):
    """Test handling multiple run configs"""
    # Create a task run
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(
            output="test",
        ),
    )
    task_run.save_to_file()

    # Add another run config
    second_config = TaskRunConfig(
        name="test2",
        description="test2",
        run_config_properties=RunConfigProperties(
            model_name="gpt-3.5",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
        ),
        parent=mock_task,
    )
    second_config.save_to_file()
    mock_eval_runner.run_configs.append(second_config)

    # Set filter to match the task
    mock_eval_runner.eval.eval_set_filter_id = "tag::tag1"

    jobs = mock_eval_runner.collect_tasks()

    # Should get 2 jobs, one for each config
    assert len(jobs) == 2
    assert {job.task_run_config.id for job in jobs} == {
        second_config.id,
        mock_run_config.id,
    }


def test_collect_tasks_empty_cases(mock_eval_runner, mock_task, data_source):
    """Test empty cases - no matching tasks or no tasks at all"""
    # Set filter that won't match anything
    mock_eval_runner.eval.eval_set_filter_id = "tag::nonexistent"
    mock_eval_runner.eval.eval_configs_filter_id = "tag::nonexistent"

    jobs = mock_eval_runner.collect_tasks()
    assert len(jobs) == 0

    # Create task run with non-matching tag
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["other_tag"],
        output=TaskOutput(
            output="test",
        ),
    )
    task_run.save_to_file()

    jobs = mock_eval_runner.collect_tasks()
    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_run_job_success_task_run_eval(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    # Create a task run to evaluate
    task_run = TaskRun(
        parent=mock_task,
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="test output"),
    )
    task_run.save_to_file()

    # Create eval job
    job = EvalJob(
        item=task_run,
        task_run_config=mock_run_config,
        type="task_run_eval",
        eval_config=mock_eval_config,
    )

    # Mock the evaluator
    mock_result_run = TaskRun(
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="evaluated output"),
        intermediate_outputs={"intermediate_output": "intermediate output"},
    )
    mock_scores = {"accuracy": 0.95}

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, input_text):
            return (
                mock_result_run,
                mock_scores,
                {"intermediate_output": "intermediate output"},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.eval_adapter_from_type",
        return_value=lambda *args: MockEvaluator(*args),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is True

    # Verify eval run was saved
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 1
    saved_run = eval_runs[0]
    assert saved_run.dataset_id == task_run.id
    assert saved_run.task_run_config_id == mock_run_config.id
    assert saved_run.scores == mock_scores
    assert saved_run.input == "test input"
    assert saved_run.output == "evaluated output"
    assert saved_run.intermediate_outputs == {
        "intermediate_output": "intermediate output"
    }
    assert saved_run.parent_eval_config().id == mock_eval_config.id
    assert saved_run.eval_config_eval is False


@pytest.mark.asyncio
async def test_run_job_success_eval_config_eval(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    # Create a task run to evaluate
    task_run = TaskRun(
        parent=mock_task,
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="test output"),
    )
    task_run.save_to_file()

    # Create eval job
    job = EvalJob(
        item=task_run,
        type="eval_config_eval",
        eval_config=mock_eval_config,
    )

    # Mock the evaluator
    mock_result_run = TaskRun(
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="evaluated output"),
    )
    mock_scores: EvalScores = {"accuracy": 0.95}

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, input_text):
            raise ValueError("Attempted to run task and eval for a config eval")

        async def run_eval(
            self, task_run: TaskRun
        ) -> tuple[EvalScores, Dict[str, str] | None]:
            return mock_scores, {"intermediate_output": "intermediate output"}

    with patch(
        "kiln_ai.adapters.eval.eval_runner.eval_adapter_from_type",
        return_value=lambda *args: MockEvaluator(*args),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is True

    # Verify eval run was saved
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 1
    saved_run = eval_runs[0]
    assert saved_run.dataset_id == task_run.id
    assert saved_run.task_run_config_id is None
    assert saved_run.scores == mock_scores
    assert saved_run.input == "test input"
    assert saved_run.output == "test output"
    assert saved_run.parent_eval_config().id == mock_eval_config.id
    assert saved_run.eval_config_eval is True


@pytest.mark.asyncio
async def test_run_job_invalid_evaluator(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    task_run = TaskRun(
        parent=mock_task,
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="test output"),
    )
    task_run.save_to_file()
    job = EvalJob(
        item=task_run,
        task_run_config=mock_run_config,
        type="task_run_eval",
        eval_config=mock_eval_config,
    )

    # Return an invalid evaluator type
    with patch(
        "kiln_ai.adapters.eval.eval_runner.eval_adapter_from_type",
        return_value=lambda *args: object(),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is False
    assert len(mock_eval_config.runs()) == 0


@pytest.mark.asyncio
async def test_run_job_evaluator_error(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    task_run = TaskRun(
        parent=mock_task,
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="test output"),
    )
    task_run.save_to_file()
    job = EvalJob(
        item=task_run,
        task_run_config=mock_run_config,
        type="task_run_eval",
        eval_config=mock_eval_config,
    )

    class ErrorEvaluator(BaseEval):
        async def run_task_and_eval(self, input_text):
            raise ValueError("Evaluation failed")

    with patch(
        "kiln_ai.adapters.eval.eval_runner.eval_adapter_from_type",
        return_value=lambda *args: ErrorEvaluator(*args),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is False
    assert len(mock_eval_config.runs()) == 0
