import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Dict
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.conftest import SkippingStubV2Eval, StubV2Eval
from kiln_ai.adapters.eval.drive_fingerprint import compute_drive_fingerprint
from kiln_ai.adapters.eval.eval_runner import (
    EvalJob,
    EvalRunner,
    _is_retryable_error,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import TurnMode
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalOutputScore,
    EvalRun,
    EvalScores,
    EvalTaskInput,
    ExactMatchProperties,
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
    SingleTurnEvalInputData,
    SkippedReason,
    SyntheticUserInfo,
    UserMessage,
    V2EvalResult,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.utils.async_job_runner import RetryableError
from kiln_ai.utils.git_sync_protocols import default_save_context
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


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
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
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
    expected_completed_count = 0
    async for progress in mock_eval_runner.run(concurrency=concurrency):
        assert progress.complete == expected_completed_count
        expected_completed_count += 1
        assert progress.errors == 0
        assert progress.total == job_count

    # Verify last status update was complete
    assert expected_completed_count == job_count + 1

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
    assert job.task_run_config is not None
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
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
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
        assert job.task_run_config is not None
        assert job.task_run_config.id in [mock_run_config.id, rc.id]
        assert job.eval_config.id == mock_eval_config.id
    assert jobs[0].task_run_config is not None
    assert jobs[1].task_run_config is not None
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
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-3.5",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
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
    mock_scores = {"accuracy": 0.95}

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            return (
                TaskRun(
                    input=eval_job_item.input,
                    input_source=data_source,
                    output=TaskOutput(output="evaluated output"),
                    intermediate_outputs={"intermediate_output": "intermediate output"},
                ),
                mock_scores,
                {"intermediate_output": "intermediate output"},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
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
    mock_scores: EvalScores = {"accuracy": 0.95}

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            raise ValueError("Attempted to run task and eval for a config eval")

        async def run_eval(
            self, task_run: TaskRun, eval_job_item: TaskRun | None = None
        ) -> tuple[EvalScores, Dict[str, str] | None]:
            return mock_scores, {"intermediate_output": "intermediate output"}

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
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
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: object(),
    ):
        with pytest.raises(ValueError):
            await mock_eval_runner.run_job(job)

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
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            raise ValueError("Evaluation failed")

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: ErrorEvaluator(*args, **kwargs),
    ):
        with pytest.raises(ValueError):
            await mock_eval_runner.run_job(job)

    assert len(mock_eval_config.runs()) == 0


@pytest.mark.asyncio
async def test_run_job_wrapped_rate_limit_raises_retryable_with_detail(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    # Real adapter failures arrive wrapped in KilnRunError whose own message is the
    # genericized user-facing text. run_job must still classify the failure as
    # transient (RetryableError) and keep the underlying provider detail for the
    # developer-facing job error log.
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

    class RateLimitedEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            raise KilnRunError(
                message="Rate limit exceeded. Wait a moment and try again.",
                partial_trace=None,
                original=litellm.RateLimitError(
                    "rate limit exceeded, please try again later",
                    "fireworks_ai",
                    "model",
                    None,
                ),
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: RateLimitedEvaluator(*args, **kwargs),
    ):
        with pytest.raises(RetryableError) as exc_info:
            await mock_eval_runner.run_job(job)

    assert "rate limit exceeded, please try again later" in str(exc_info.value)
    assert "An unexpected error occurred" not in str(exc_info.value)
    assert len(mock_eval_config.runs()) == 0


@pytest.mark.asyncio
async def test_run_job_with_full_trace_evaluation_data_type(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    """Test EvalRunner with full_trace evaluation_data_type"""
    # Set the eval config to use full_trace evaluation data type
    mock_eval_config.parent.evaluation_data_type = EvalDataType.full_trace
    # Persist the change so validation on reload sees full_trace
    mock_eval_config.parent.save_to_file()

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
    mock_scores = {"accuracy": 0.95}
    mock_trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "test input"},
        {"role": "assistant", "content": "test response"},
    ]

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            result_task_run = TaskRun(
                input=eval_job_item.input,
                input_source=data_source,
                output=TaskOutput(output="evaluated output"),
                intermediate_outputs={"intermediate_output": "intermediate output"},
                trace=mock_trace,
            )
            return (
                result_task_run,
                mock_scores,
                {"intermediate_output": "intermediate output"},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is True

    # Verify eval run was saved with trace
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 1
    saved_run = eval_runs[0]
    assert saved_run.task_run_trace is not None
    assert isinstance(saved_run.task_run_trace, str)
    # Verify the trace was JSON serialized
    import json

    parsed_trace = json.loads(saved_run.task_run_trace)
    assert parsed_trace == mock_trace


@pytest.mark.asyncio
async def test_run_job_with_final_answer_evaluation_data_type(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    """Test EvalRunner with final_answer evaluation_data_type (default)"""
    # Set the eval config to use final_answer evaluation data type (default)
    mock_eval_config.parent.evaluation_data_type = EvalDataType.final_answer

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
    mock_scores = {"accuracy": 0.95}
    mock_trace: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "test"},
        {"role": "assistant", "content": "response"},
    ]

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            result_task_run = TaskRun(
                input=eval_job_item.input,
                input_source=data_source,
                output=TaskOutput(output="evaluated output"),
                intermediate_outputs={"intermediate_output": "intermediate output"},
                trace=mock_trace,
            )
            return (
                result_task_run,
                mock_scores,
                {"intermediate_output": "intermediate output"},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is True

    # Verify eval run was saved without trace
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 1
    saved_run = eval_runs[0]
    assert saved_run.task_run_trace is None


@pytest.mark.asyncio
async def test_run_job_with_none_trace(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    """Test EvalRunner with None trace"""
    # Set the eval config to use full_trace evaluation data type
    mock_eval_config.parent.evaluation_data_type = EvalDataType.full_trace

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
    mock_scores = {"accuracy": 0.95}

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            result_task_run = TaskRun(
                input=eval_job_item.input,
                input_source=data_source,
                output=TaskOutput(output="evaluated output"),
                intermediate_outputs={"intermediate_output": "intermediate output"},
                trace=None,  # None trace
            )
            return (
                result_task_run,
                mock_scores,
                {"intermediate_output": "intermediate output"},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        with pytest.raises(ValueError):
            await mock_eval_runner.run_job(job)

    # For full_trace evals, None trace should fail and not save a run
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 0


@pytest.mark.parametrize(
    "error",
    [
        litellm.RateLimitError("rate limited", "provider", "model", None),
        litellm.APIConnectionError("connection failed", "provider", "model", None),
        litellm.InternalServerError("server error", "provider", "model", None),
        litellm.ServiceUnavailableError("unavailable", "provider", "model", None),
        litellm.BadGatewayError("bad gateway", "provider", "model", None),
        litellm.JSONSchemaValidationError("schema error", "provider", "model", None),
        ValueError(
            "This task requires a specific output schema. While the model produced JSON, that JSON didn't meet the schema."
        ),
    ],
)
def test_is_retryable_error_returns_true(error):
    assert _is_retryable_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        ValueError("some other value error"),
        RuntimeError("runtime error"),
        KeyError("missing key"),
        TypeError("type error"),
    ],
)
def test_is_retryable_error_returns_false(error):
    assert _is_retryable_error(error) is False


def wrapped_rate_limit_error(detail: str) -> KilnRunError:
    """A provider rate limit as the model adapter surfaces it: wrapped in
    KilnRunError whose own message is the genericized user-facing text, with
    the provider detail only on the inner error."""
    return KilnRunError(
        message="Rate limit exceeded. Wait a moment and try again.",
        partial_trace=None,
        original=litellm.RateLimitError(detail, "provider", "model", None),
    )


def test_is_retryable_error_unwraps_kiln_run_error():
    # The model adapter wraps provider exceptions in KilnRunError (to carry the
    # partial trace), so the classifier must look through the wrapper — otherwise
    # rate limits from a real adapter run would never be retried.
    assert _is_retryable_error(wrapped_rate_limit_error("rate limited")) is True


def test_is_retryable_error_wrapped_non_transient_returns_false():
    wrapped = KilnRunError(
        message="An unexpected error occurred.",
        partial_trace=None,
        original=RuntimeError("boom"),
    )
    assert _is_retryable_error(wrapped) is False


def test_is_retryable_error_unwraps_nested_kiln_run_error():
    # Not produced by the current adapter chain (it passes through already-wrapped
    # errors), but the unwrap walks nested wrappers so classification and error
    # detail can't silently diverge if that ever changes.
    nested = KilnRunError(
        message="Rate limit exceeded. Wait a moment and try again.",
        partial_trace=None,
        original=wrapped_rate_limit_error("rate limited"),
    )
    assert _is_retryable_error(nested) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run_kwargs,expected_max_retries,expected_retry_delay",
    [
        ({}, 2, 1.0),
        ({"max_retries": 4, "retry_delay": 5.0}, 4, 5.0),
    ],
)
async def test_run_threads_retry_config_to_async_job_runner(
    mock_eval_runner, run_kwargs, expected_max_retries, expected_retry_delay
):
    # The historical default (2 retries) is kept for existing callers; background
    # jobs override it, and the values must reach the AsyncJobRunner doing the
    # retrying.
    captured: dict = {}

    class FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run(self):
            for _ in ():
                yield  # pragma: no cover — typed as a generator, never yields

    with patch("kiln_ai.adapters.eval.eval_runner.AsyncJobRunner", FakeRunner):
        async for _ in mock_eval_runner.run(**run_kwargs):
            pass

    assert captured["max_retries"] == expected_max_retries
    assert captured["retry_delay"] == expected_retry_delay


# --- save_context tests ---


class _RecordingSaveContext:
    def __init__(self):
        self.enter_count = 0
        self.exit_count = 0
        self.last_exit_exc_type: type | None = None

    def __call__(self):
        @asynccontextmanager
        async def cm() -> AsyncIterator[None]:
            self.enter_count += 1
            try:
                yield
            except BaseException as exc:
                self.last_exit_exc_type = type(exc)
                self.exit_count += 1
                raise
            else:
                self.exit_count += 1

        return cm()


def test_eval_runner_defaults_to_default_save_context(
    mock_eval, mock_eval_config, mock_run_config
):
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
    )
    assert runner._save_context is default_save_context


def test_eval_runner_accepts_custom_save_context(
    mock_eval, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
        save_context=recorder,
    )
    assert runner._save_context is recorder


@pytest.mark.asyncio
async def test_run_job_custom_save_context_wraps_save(
    mock_task, data_source, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
        save_context=recorder,
    )

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

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item):
            return (
                TaskRun(
                    input=eval_job_item.input,
                    input_source=data_source,
                    output=TaskOutput(output="evaluated output"),
                ),
                {"accuracy": 1.0},
                {},
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        success = await runner.run_job(job)

    assert success is True
    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert recorder.last_exit_exc_type is None


@pytest.mark.asyncio
async def test_run_job_save_context_sees_save_exception(
    mock_task, data_source, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
        save_context=recorder,
    )

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

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item):
            return (
                TaskRun(
                    input=eval_job_item.input,
                    input_source=data_source,
                    output=TaskOutput(output="evaluated output"),
                ),
                {"accuracy": 1.0},
                {},
            )

    with (
        patch(
            "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
            return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
        ),
        patch.object(EvalRun, "save_to_file", side_effect=RuntimeError("disk full")),
    ):
        with pytest.raises(RuntimeError, match="disk full"):
            await runner.run_job(job)

    assert recorder.enter_count == 1
    assert recorder.exit_count == 1
    assert recorder.last_exit_exc_type is RuntimeError


@pytest.mark.asyncio
async def test_other_jobs_unaffected_by_save_context_rollback(
    mock_task, data_source, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = EvalRunner(
        eval_configs=[mock_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
        save_context=recorder,
    )

    task_run = TaskRun(
        parent=mock_task,
        input="test input",
        input_source=data_source,
        output=TaskOutput(output="test output"),
    )
    task_run.save_to_file()

    def make_job():
        return EvalJob(
            item=task_run,
            task_run_config=mock_run_config,
            type="task_run_eval",
            eval_config=mock_eval_config,
        )

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item):
            return (
                TaskRun(
                    input=eval_job_item.input,
                    input_source=data_source,
                    output=TaskOutput(output="evaluated output"),
                ),
                {"accuracy": 1.0},
                {},
            )

    call_count = {"n": 0}
    real_save_to_file = EvalRun.save_to_file

    def fail_first_save(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("disk full")
        return real_save_to_file(self, *args, **kwargs)

    with (
        patch(
            "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
            return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
        ),
        patch.object(EvalRun, "save_to_file", fail_first_save),
    ):
        with pytest.raises(RuntimeError, match="disk full"):
            await runner.run_job(make_job())
        success = await runner.run_job(make_job())

    assert success is True
    # Two fresh contexts were opened and both closed; the second job's success
    # proves rollback from the first did not leak into the second's context.
    assert recorder.enter_count == 2
    assert recorder.exit_count == 2


# ===================================================================
# V2 Eval Runner Tests
# ===================================================================


@pytest.fixture
def mock_v2_eval(mock_task):
    """Eval with eval_input_filter_id set (V2 source mode)."""
    eval = Eval(
        id="v2_eval",
        name="v2 test eval",
        description="v2 eval desc",
        eval_input_filter_id="all",
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
def mock_v2_eval_config(mock_v2_eval):
    """V2 EvalConfig with ExactMatchProperties."""
    eval_config = EvalConfig(
        name="v2 config",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(
            expected_value="hello",
        ),
        parent=mock_v2_eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_eval_inputs(mock_task):
    """Create two EvalInput items under the task."""
    input1 = EvalInput(
        id="ei_1",
        data=SingleTurnEvalInputData(
            user_message=UserMessage(text="What is 2+2?"),
        ),
        reference={"answer": "4"},
        tags=["math"],
        parent=mock_task,
    )
    input1.save_to_file()
    input2 = EvalInput(
        id="ei_2",
        data=SingleTurnEvalInputData(
            user_message=UserMessage(text="Say hello"),
        ),
        reference={"answer": "hello"},
        tags=["greeting"],
        parent=mock_task,
    )
    input2.save_to_file()
    return [input1, input2]


@pytest.fixture
def mock_v2_runner(mock_v2_eval, mock_v2_eval_config):
    return EvalRunner(
        eval_configs=[mock_v2_eval_config],
        run_configs=None,
        eval_run_type="eval_config_eval",
    )


# -------------------------------------------------------------------
# Init / source mode tests
# -------------------------------------------------------------------
class TestEvalRunnerV2Init:
    def test_source_mode_eval_input(self, mock_v2_runner):
        assert mock_v2_runner._source_mode == "eval_input"

    def test_source_mode_task_run_default(self, mock_eval_runner):
        assert mock_eval_runner._source_mode == "task_run"

    def test_task_run_eval_with_eval_input_filter_allowed(
        self, mock_v2_eval_config, mock_run_config
    ):
        runner = EvalRunner(
            eval_configs=[mock_v2_eval_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        assert runner._source_mode == "eval_input"
        assert runner.eval_run_type == "task_run_eval"


# -------------------------------------------------------------------
# collect_tasks_for_eval_input tests
# -------------------------------------------------------------------
class TestCollectTasksForEvalInput:
    def test_collects_all_inputs(
        self, mock_v2_eval_config, mock_run_config, mock_eval_inputs
    ):
        runner = EvalRunner(
            eval_configs=[mock_v2_eval_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        jobs = runner.collect_tasks()
        assert len(jobs) == 2
        item_ids = {j.item.id for j in jobs}
        assert item_ids == {"ei_1", "ei_2"}
        for job in jobs:
            assert isinstance(job.item, EvalInput)
            assert job.type == "task_run_eval"
            assert job.task_run_config is mock_run_config

    def test_tag_filter(self, mock_task, mock_run_config, mock_eval_inputs):
        eval = Eval(
            id="tag_eval",
            name="tag eval",
            description="tag eval desc",
            eval_input_filter_id="tag::math",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="Accuracy",
                    instruction="Check",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            parent=mock_task,
        )
        eval.save_to_file()
        eval_config = EvalConfig(
            name="tag config",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="4"),
            parent=eval,
        )
        eval_config.save_to_file()
        runner = EvalRunner(
            eval_configs=[eval_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        jobs = runner.collect_tasks()
        assert len(jobs) == 1
        assert jobs[0].item.id == "ei_1"

    def test_dedup_already_run(
        self, mock_v2_eval_config, mock_run_config, mock_eval_inputs
    ):
        run = EvalRun(
            parent=mock_v2_eval_config,
            eval_input_id="ei_1",
            task_run_config_id=mock_run_config.id,
            eval_config_eval=False,
            scores={"accuracy": 1.0},
            input="What is 2+2?",
            output="4",
        )
        run.save_to_file()
        runner = EvalRunner(
            eval_configs=[mock_v2_eval_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        jobs = runner.collect_tasks()
        assert len(jobs) == 1
        assert jobs[0].item.id == "ei_2"

    def test_eval_config_eval_collects_golden_task_runs(
        self, mock_v2_runner, mock_task, mock_eval_inputs, data_source
    ):
        """eval_config_eval on an EvalInput-sourced eval must still collect
        golden TASKRUNS (via eval_configs_filter_id) — judge validation needs
        stored, human-rated outputs, which EvalInput items don't carry."""
        golden_run = TaskRun(
            input="golden input",
            output=TaskOutput(output="golden output", source=data_source),
            parent=mock_task,
        )
        golden_run.save_to_file()
        jobs = mock_v2_runner.collect_tasks()
        assert len(jobs) == 1
        assert isinstance(jobs[0].item, TaskRun)
        assert jobs[0].item.id == golden_run.id
        assert jobs[0].type == "eval_config_eval"


# -------------------------------------------------------------------
# run_job V2 dispatch tests
# -------------------------------------------------------------------
MULTI_TURN_TRACE: list[ChatCompletionMessageParam] = [
    {"role": "user", "content": "turn 1"},
    {"role": "assistant", "content": "hi"},
    {"role": "user", "content": "turn 2"},
    {"role": "assistant", "content": "reply"},
]


def make_multi_turn_leaf(
    task: Task,
    data_source: DataSource,
    trace: list[ChatCompletionMessageParam] | None = MULTI_TURN_TRACE,
) -> TaskRun:
    """A saved multi-turn chain-leaf TaskRun (parent_task_run_id set).

    parent_task_run_id is only constructible when the task is multiturn;
    turn_mode is frozen, so use a multiturn copy (same path) as parent.
    """
    multiturn_task = task.model_copy(update={"turn_mode": TurnMode.multiturn})
    task_run = TaskRun(
        input="turn 1",
        output=TaskOutput(output="reply", source=data_source),
        parent=multiturn_task,
        parent_task_run_id="some_parent_id",
        trace=trace,
    )
    task_run.save_to_file()
    return task_run


class RecordingStubV2Eval(StubV2Eval):
    """StubV2Eval that records the EvalTaskInput it was asked to evaluate."""

    def __init__(self, eval_config: EvalConfig):
        super().__init__(eval_config)
        self.seen_inputs: list[EvalTaskInput] = []

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        self.seen_inputs.append(eval_input)
        return await super().evaluate(eval_input)


class TestRunV2Job:
    @pytest.mark.asyncio
    async def test_v2_dispatch_from_run_job(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs, data_source
    ):
        task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="hello", source=data_source),
            parent=mock_v2_runner.task,
        )
        task_run.save_to_file()
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.dataset_id == task_run.id
        assert saved.eval_input_id is None
        assert saved.skipped_reason is None
        assert saved.output == "hello"

    @pytest.mark.asyncio
    async def test_type_not_available_skip(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs, data_source
    ):
        task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="hello", source=data_source),
            parent=mock_v2_runner.task,
        )
        task_run.save_to_file()
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=NotImplementedError("not yet implemented"),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {}
        assert saved.skipped_reason == SkippedReason.type_not_available.value
        assert saved.skipped_detail == "V2 eval type not yet implemented"
        assert saved.dataset_id == task_run.id
        assert saved.eval_input_id is None
        assert saved.output is None
        assert saved.input == "test input"

    @pytest.mark.asyncio
    async def test_adapter_skipped_reason(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs, data_source
    ):
        task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="hello", source=data_source),
            parent=mock_v2_runner.task,
        )
        task_run.save_to_file()
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=SkippingStubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {}
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_eval_input_eval_config_eval_clean_skip(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs
    ):
        ei = mock_eval_inputs[0]
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.eval_config_eval is True
        assert saved.skipped_reason == SkippedReason.incompatible_input_shape.value
        assert "deferred" in saved.skipped_detail
        assert "golden subsets use TaskRun sources" in saved.skipped_detail
        assert saved.output is None
        assert saved.scores == {}

    @pytest.mark.asyncio
    async def test_type_not_available_skip_eval_input(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs
    ):
        ei = mock_eval_inputs[1]
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=NotImplementedError("not yet implemented"),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.skipped_reason == SkippedReason.type_not_available.value
        assert saved.input == "Say hello"

    @pytest.mark.asyncio
    async def test_multi_turn_task_run_eval_config_eval_scores_stored_trace(
        self, mock_v2_runner, mock_v2_eval_config, data_source
    ):
        task_run = make_multi_turn_leaf(mock_v2_runner.task, data_source)
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        stub = RecordingStubV2Eval(mock_v2_eval_config)
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=stub,
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True

        # The adapter received the stored conversation, not a regeneration.
        assert len(stub.seen_inputs) == 1
        eval_task_input = stub.seen_inputs[0]
        assert eval_task_input.final_message == "reply"
        assert eval_task_input.task_input == "turn 1"
        assert eval_task_input.trace == MULTI_TURN_TRACE

        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.skipped_reason is None
        assert saved.dataset_id == task_run.id
        assert saved.eval_input_id is None
        assert saved.eval_config_eval is True
        assert saved.task_run_config_id is None
        assert saved.input == "turn 1"
        assert saved.output == "reply"
        # eval_config_eval records stay scores-only: the trace already lives
        # on the golden TaskRun being scored.
        assert saved.task_run_trace is None

    @pytest.mark.asyncio
    async def test_multi_turn_eval_config_eval_full_trace_records_no_trace(
        self, mock_v2_runner, mock_v2_eval_config, data_source
    ):
        # Only task-run-eval records carry the serialized trace (legacy-runner
        # parity); eval_config_eval scores the stored run without copying it.
        mock_v2_eval_config.parent.evaluation_data_type = EvalDataType.full_trace
        mock_v2_eval_config.parent.save_to_file()

        task_run = make_multi_turn_leaf(mock_v2_runner.task, data_source)
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True

        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.task_run_trace is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("trace", [None, []])
    async def test_multi_turn_task_run_without_trace_skipped(
        self, mock_v2_runner, mock_v2_eval_config, data_source, trace
    ):
        task_run = make_multi_turn_leaf(mock_v2_runner.task, data_source, trace=trace)
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {}
        assert saved.skipped_reason == SkippedReason.missing_trace.value
        assert "no stored trace" in saved.skipped_detail
        assert saved.input == "turn 1"
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_multi_turn_task_run_adapter_skip_persists(
        self, mock_v2_runner, mock_v2_eval_config, data_source
    ):
        task_run = make_multi_turn_leaf(mock_v2_runner.task, data_source)
        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=SkippingStubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {}
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_multi_turn_eval_input_config_eval_skipped(
        self, mock_task, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs
    ):
        """eval_config_eval over a multi-turn EvalInput is a typed skip: an
        inputs-only item carries no stored output to judge (golden subsets
        are TaskRun-sourced)."""
        multi_ei = EvalInput(
            id="ei_multi",
            data=MultiTurnSyntheticEvalInputData(
                first_message=UserMessage(text="start chat"),
                synthetic_user_info=SyntheticUserInfo(
                    persona="a curious student", goal="learn about evals"
                ),
            ),
            parent=mock_task,
        )
        multi_ei.save_to_file()
        job = EvalJob(
            item=multi_ei,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_eval_config),
        ):
            result = await mock_v2_runner.run_job(job)
        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {}
        assert saved.skipped_reason == SkippedReason.incompatible_input_shape.value
        assert "no stored output" in saved.skipped_detail
        assert saved.eval_input_id == "ei_multi"
        assert saved.input == "start chat"
        assert saved.output is None


# -------------------------------------------------------------------
# V2 task_run_eval (fresh generation) tests
# -------------------------------------------------------------------
@pytest.fixture
def mock_v2_task_run_eval(mock_task):
    eval = Eval(
        id="v2_eval_tr",
        name="v2 task run eval",
        description="v2 eval for task_run_eval mode",
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
def mock_v2_task_run_eval_config(mock_v2_task_run_eval):
    eval_config = EvalConfig(
        name="v2 tr config",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="hello"),
        parent=mock_v2_task_run_eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_v2_task_run_eval_runner(
    mock_v2_task_run_eval, mock_v2_task_run_eval_config, mock_run_config
):
    return EvalRunner(
        eval_configs=[mock_v2_task_run_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
    )


class TestV2FreshGeneration:
    @pytest.mark.asyncio
    async def test_task_run_eval_generates_fresh_and_evaluates(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        stale_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        stale_task_run.save_to_file()

        fresh_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="hello", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=stale_task_run,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = StubV2Eval(mock_v2_task_run_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run) as mock_rt,
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        mock_rt.assert_awaited_once_with(stale_task_run)
        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.output == "hello"
        assert saved.dataset_id == fresh_task_run.id
        assert saved.scores == {"accuracy": 1.0}
        assert saved.eval_config_eval is False
        assert saved.skipped_reason is None

    @pytest.mark.asyncio
    async def test_task_run_eval_persists_fresh_output_not_stale(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        stale_task_run = TaskRun(
            input="prompt",
            output=TaskOutput(output="old answer", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        stale_task_run.save_to_file()

        fresh_task_run = TaskRun(
            input="prompt",
            output=TaskOutput(output="new answer", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=stale_task_run,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        mock_evaluator = AsyncMock()
        mock_evaluator.run_task = AsyncMock(return_value=fresh_task_run)
        mock_evaluator.evaluate = AsyncMock(
            return_value=V2EvalResult(scores={"accuracy": 0.5})
        )

        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=mock_evaluator,
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.output == "new answer"
        assert saved.output != "old answer"
        assert saved.dataset_id == fresh_task_run.id

    @pytest.mark.asyncio
    async def test_task_run_eval_skip_persists_skipped_eval_run(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        stale_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        stale_task_run.save_to_file()

        fresh_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="fresh output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=stale_task_run,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = SkippingStubV2Eval(mock_v2_task_run_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        assert saved.output is None
        assert saved.scores == {}
        assert saved.eval_config_eval is False
        assert saved.dataset_id == fresh_task_run.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stub_cls", [StubV2Eval, SkippingStubV2Eval])
    async def test_task_run_eval_persists_fresh_run_trace(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
        stub_cls,
    ):
        """A traced fresh generation lands its conversation on the record
        whether the judge scored or skipped — always-persist has no success
        gate and no evaluation_data_type gate (this eval is final_answer)."""
        single_turn_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "test input"},
            {"role": "assistant", "content": "hello"},
        ]
        stale_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        stale_task_run.save_to_file()
        fresh_task_run = TaskRun(
            input="test input",
            output=TaskOutput(output="hello", source=data_source),
            trace=single_turn_trace,
            parent=mock_v2_task_run_eval_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=stale_task_run,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        stub = stub_cls(mock_v2_task_run_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.task_run_trace is not None
        assert json.loads(saved.task_run_trace) == single_turn_trace
        if stub_cls is SkippingStubV2Eval:
            assert saved.skipped_reason == SkippedReason.extraction_failed.value
            assert saved.output is None

    @pytest.mark.asyncio
    async def test_task_run_eval_multi_turn_scores_stored_trace_without_regen(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """Multi-turn leaves can't be regenerated single-shot; task_run_eval
        mode scores the stored trace and never calls run_task."""
        leaf = make_multi_turn_leaf(mock_v2_task_run_eval_runner.task, data_source)
        job = EvalJob(
            item=leaf,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = RecordingStubV2Eval(mock_v2_task_run_eval_config)
        with (
            patch.object(
                stub, "run_task", side_effect=AssertionError("run_task called")
            ),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        assert len(stub.seen_inputs) == 1
        assert stub.seen_inputs[0].trace == MULTI_TURN_TRACE

        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.output == "reply"
        assert saved.dataset_id == leaf.id
        assert saved.scores == {"accuracy": 1.0}
        assert saved.eval_config_eval is False
        assert saved.task_run_config_id == mock_run_config.id
        assert saved.skipped_reason is None
        # Task-run-eval records always carry the evaluated conversation,
        # regardless of the eval's evaluation_data_type (here: final_answer).
        assert saved.task_run_trace is not None
        assert json.loads(saved.task_run_trace) == MULTI_TURN_TRACE
        # Stored-chain scoring involves no drive, so no fingerprint.
        assert saved.drive_fingerprint is None

    @pytest.mark.asyncio
    async def test_task_run_eval_multi_turn_full_trace_serializes_trace(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        mock_v2_task_run_eval_config.parent.evaluation_data_type = (
            EvalDataType.full_trace
        )
        mock_v2_task_run_eval_config.parent.save_to_file()

        # In-memory assistant turns carry a MessageUsage object (not plain
        # JSON) — the serialization must handle it, not crash.
        trace_with_usage: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "turn 1"},
            {
                "role": "assistant",
                "content": "reply",
                "usage": MessageUsage(input_tokens=5, output_tokens=7),
            },
        ]
        leaf = make_multi_turn_leaf(
            mock_v2_task_run_eval_runner.task, data_source, trace=trace_with_usage
        )
        job = EvalJob(
            item=leaf,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=StubV2Eval(mock_v2_task_run_eval_config),
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        runs = mock_v2_task_run_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.task_run_trace is not None
        parsed = json.loads(saved.task_run_trace)
        assert [m["role"] for m in parsed] == ["user", "assistant"]
        assert parsed[1]["content"] == "reply"
        assert parsed[1]["usage"]["input_tokens"] == 5
        assert parsed[1]["usage"]["output_tokens"] == 7

    @pytest.mark.asyncio
    async def test_eval_config_eval_scores_existing_without_fresh_gen(
        self,
        mock_v2_runner,
        mock_v2_eval_config,
        data_source,
    ):
        task_run = TaskRun(
            input="existing input",
            output=TaskOutput(output="existing output", source=data_source),
            parent=mock_v2_runner.task,
        )
        task_run.save_to_file()

        job = EvalJob(
            item=task_run,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )

        stub = StubV2Eval(mock_v2_eval_config)
        with patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            return_value=stub,
        ):
            result = await mock_v2_runner.run_job(job)

        assert result is True
        runs = mock_v2_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.output == "existing output"
        assert saved.dataset_id == task_run.id
        assert saved.eval_config_eval is True
        assert saved.skipped_reason is None


# -------------------------------------------------------------------
# V2 EvalInput + task_run_eval (fresh generation from EvalInput)
# -------------------------------------------------------------------
@pytest.fixture
def mock_v2_eval_input_task_run_eval(mock_task):
    eval = Eval(
        id="v2_ei_tr_eval",
        name="v2 eval input task_run_eval",
        description="v2 eval for EvalInput + task_run_eval mode",
        eval_input_filter_id="all",
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
def mock_v2_ei_tr_eval_config(mock_v2_eval_input_task_run_eval):
    eval_config = EvalConfig(
        name="v2 ei tr config",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="4"),
        parent=mock_v2_eval_input_task_run_eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_v2_ei_tr_runner(
    mock_v2_eval_input_task_run_eval,
    mock_v2_ei_tr_eval_config,
    mock_run_config,
):
    return EvalRunner(
        eval_configs=[mock_v2_ei_tr_eval_config],
        run_configs=[mock_run_config],
        eval_run_type="task_run_eval",
    )


class TestV2EvalInputFreshGeneration:
    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_generates_and_evaluates(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
        data_source,
    ):
        ei = mock_eval_inputs[0]
        fresh_task_run = TaskRun(
            input="What is 2+2?",
            output=TaskOutput(output="4", source=data_source),
            parent=mock_v2_ei_tr_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=ei,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = StubV2Eval(mock_v2_ei_tr_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run) as mock_rt,
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_ei_tr_runner.run_job(job)

        assert result is True
        mock_rt.assert_awaited_once_with(ei)
        runs = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.eval_config_eval is False
        assert saved.scores == {"accuracy": 1.0}
        assert saved.output == "4"
        assert saved.reference_data == {"answer": "4"}
        assert saved.skipped_reason is None
        assert saved.input == "What is 2+2?"

    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_skip_persists_skipped(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
        data_source,
    ):
        ei = mock_eval_inputs[1]
        fresh_task_run = TaskRun(
            input="Say hello",
            output=TaskOutput(output="hi there", source=data_source),
            parent=mock_v2_ei_tr_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=ei,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = SkippingStubV2Eval(mock_v2_ei_tr_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_ei_tr_runner.run_job(job)

        assert result is True
        runs = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.eval_config_eval is False
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        assert saved.output is None
        assert saved.scores == {}
        assert saved.reference_data == {"answer": "hello"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stub_cls", [StubV2Eval, SkippingStubV2Eval])
    async def test_eval_input_task_run_eval_persists_trace(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
        data_source,
        stub_cls,
    ):
        """A traced fresh generation from an EvalInput lands its conversation
        on the record, scored or skipped — the run is transient, so the
        record is the only place the conversation survives."""
        single_turn_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        ei = mock_eval_inputs[0]
        fresh_task_run = TaskRun(
            input="What is 2+2?",
            output=TaskOutput(output="4", source=data_source),
            trace=single_turn_trace,
            parent=mock_v2_ei_tr_runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=ei,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        stub = stub_cls(mock_v2_ei_tr_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await mock_v2_ei_tr_runner.run_job(job)

        assert result is True
        runs = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == ei.id
        assert saved.task_run_trace is not None
        assert json.loads(saved.task_run_trace) == single_turn_trace
        # Single-turn records are never driven, so no fingerprint.
        assert saved.drive_fingerprint is None
        if stub_cls is SkippingStubV2Eval:
            assert saved.skipped_reason == SkippedReason.extraction_failed.value
            assert saved.output is None

    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_no_reference(
        self,
        mock_task,
        mock_v2_ei_tr_eval_config,
        mock_run_config,
        data_source,
    ):
        ei_no_ref = EvalInput(
            id="ei_no_ref",
            data=SingleTurnEvalInputData(
                user_message=UserMessage(text="no ref input"),
            ),
            reference=None,
            parent=mock_task,
        )
        ei_no_ref.save_to_file()

        runner = EvalRunner(
            eval_configs=[mock_v2_ei_tr_eval_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )

        fresh_task_run = TaskRun(
            input="no ref input",
            output=TaskOutput(output="4", source=data_source),
            parent=runner.task,
        )
        fresh_task_run.save_to_file()

        job = EvalJob(
            item=ei_no_ref,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = StubV2Eval(mock_v2_ei_tr_eval_config)
        with (
            patch.object(stub, "run_task", return_value=fresh_task_run),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
        ):
            result = await runner.run_job(job)

        assert result is True
        runs = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.reference_data is None
        assert saved.eval_input_id == "ei_no_ref"


class TestCollectTasksEvalInputTaskRunEval:
    def test_crosses_eval_inputs_x_eval_configs_x_run_configs(
        self,
        mock_v2_ei_tr_runner,
        mock_eval_inputs,
        mock_run_config,
    ):
        jobs = mock_v2_ei_tr_runner.collect_tasks()
        assert len(jobs) == 2
        for job in jobs:
            assert isinstance(job.item, EvalInput)
            assert job.type == "task_run_eval"
            assert job.task_run_config == mock_run_config

    def test_multiple_run_configs(
        self,
        mock_task,
        mock_v2_eval_input_task_run_eval,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
    ):
        rc1 = TaskRunConfig(
            name="config1",
            description="first",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            parent=mock_task,
        )
        rc1.save_to_file()
        rc2 = TaskRunConfig(
            name="config2",
            description="second",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4o",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            parent=mock_task,
        )
        rc2.save_to_file()
        runner = EvalRunner(
            eval_configs=[mock_v2_ei_tr_eval_config],
            run_configs=[rc1, rc2],
            eval_run_type="task_run_eval",
        )
        jobs = runner.collect_tasks()
        assert len(jobs) == 4
        config_pairs = {(j.item.id, j.task_run_config.id) for j in jobs}
        for ei in mock_eval_inputs:
            assert (ei.id, rc1.id) in config_pairs
            assert (ei.id, rc2.id) in config_pairs

    def test_dedup_already_run_task_run_eval(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
    ):
        run = EvalRun(
            parent=mock_v2_ei_tr_eval_config,
            eval_input_id="ei_1",
            task_run_config_id=mock_run_config.id,
            eval_config_eval=False,
            scores={"accuracy": 1.0},
            input="What is 2+2?",
            output="4",
        )
        run.save_to_file()
        jobs = mock_v2_ei_tr_runner.collect_tasks()
        assert len(jobs) == 1
        assert jobs[0].item.id == "ei_2"

    def test_dedup_does_not_cross_run_configs(
        self,
        mock_task,
        mock_v2_eval_input_task_run_eval,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
    ):
        rc1 = TaskRunConfig(
            name="rc_a",
            description="a",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            parent=mock_task,
        )
        rc1.save_to_file()
        rc2 = TaskRunConfig(
            name="rc_b",
            description="b",
            run_config_properties=KilnAgentRunConfigProperties(
                model_name="gpt-4o",
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            parent=mock_task,
        )
        rc2.save_to_file()
        run = EvalRun(
            parent=mock_v2_ei_tr_eval_config,
            eval_input_id="ei_1",
            task_run_config_id=rc1.id,
            eval_config_eval=False,
            scores={"accuracy": 1.0},
            input="What is 2+2?",
            output="4",
        )
        run.save_to_file()
        runner = EvalRunner(
            eval_configs=[mock_v2_ei_tr_eval_config],
            run_configs=[rc1, rc2],
            eval_run_type="task_run_eval",
        )
        jobs = runner.collect_tasks()
        assert len(jobs) == 3
        remaining = {(j.item.id, j.task_run_config.id) for j in jobs}
        assert (mock_eval_inputs[0].id, rc1.id) not in remaining
        assert (mock_eval_inputs[0].id, rc2.id) in remaining
        assert (mock_eval_inputs[1].id, rc1.id) in remaining
        assert (mock_eval_inputs[1].id, rc2.id) in remaining


class TestRunTaskFromEvalInput:
    @pytest.mark.asyncio
    async def test_run_task_extracts_eval_input_user_message(
        self,
        mock_v2_ei_tr_eval_config,
        mock_run_config,
    ):
        ei = EvalInput(
            id="ei_rt",
            data=SingleTurnEvalInputData(
                user_message=UserMessage(text="What is 2+2?"),
            ),
        )
        stub = StubV2Eval(
            mock_v2_ei_tr_eval_config,
            run_config=mock_run_config.run_config_properties,
        )
        mock_output = TaskRun(
            input="What is 2+2?",
            output=TaskOutput(
                output="4",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test",
                    },
                ),
            ),
        )
        with patch(
            "kiln_ai.adapters.eval.base_eval.adapter_for_task"
        ) as mock_adapter_for_task:
            mock_adapter = AsyncMock()
            mock_adapter.invoke = AsyncMock(return_value=mock_output)
            mock_adapter_for_task.return_value = mock_adapter
            result = await stub.run_task(ei)

        assert result == mock_output
        mock_adapter.invoke.assert_awaited_once_with("What is 2+2?")

    @pytest.mark.asyncio
    async def test_run_task_extracts_eval_input_with_json_schema(
        self,
        mock_task,
        mock_run_config,
    ):
        mock_task.input_json_schema = '{"type": "object"}'
        mock_task.save_to_file()

        eval = Eval(
            id="v2_json_eval",
            name="json eval",
            description="json eval desc",
            eval_input_filter_id="all",
            eval_configs_filter_id="all",
            output_scores=[
                EvalOutputScore(
                    name="Accuracy",
                    instruction="Check",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            parent=mock_task,
        )
        eval.save_to_file()
        ec = EvalConfig(
            name="json config",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="4"),
            parent=eval,
        )
        ec.save_to_file()

        ei = EvalInput(
            id="ei_json",
            data=SingleTurnEvalInputData(
                user_message=UserMessage(text='{"question": "2+2"}'),
            ),
        )
        stub = StubV2Eval(
            ec,
            run_config=mock_run_config.run_config_properties,
        )
        mock_output = TaskRun(
            input='{"question": "2+2"}',
            output=TaskOutput(
                output="4",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test",
                    },
                ),
            ),
        )
        with patch(
            "kiln_ai.adapters.eval.base_eval.adapter_for_task"
        ) as mock_adapter_for_task:
            mock_adapter = AsyncMock()
            mock_adapter.invoke = AsyncMock(return_value=mock_output)
            mock_adapter_for_task.return_value = mock_adapter
            result = await stub.run_task(ei)

        assert result == mock_output
        mock_adapter.invoke.assert_awaited_once_with({"question": "2+2"})

    @pytest.mark.asyncio
    async def test_run_task_still_works_with_task_run(
        self,
        mock_v2_ei_tr_eval_config,
        mock_run_config,
        data_source,
    ):
        tr = TaskRun(
            input="test input",
            output=TaskOutput(output="test output", source=data_source),
        )
        stub = StubV2Eval(
            mock_v2_ei_tr_eval_config,
            run_config=mock_run_config.run_config_properties,
        )
        mock_output = TaskRun(
            input="test input",
            output=TaskOutput(output="fresh output", source=data_source),
        )
        with patch(
            "kiln_ai.adapters.eval.base_eval.adapter_for_task"
        ) as mock_adapter_for_task:
            mock_adapter = AsyncMock()
            mock_adapter.invoke = AsyncMock(return_value=mock_output)
            mock_adapter_for_task.return_value = mock_adapter
            result = await stub.run_task(tr)

        assert result == mock_output
        mock_adapter.invoke.assert_awaited_once_with("test input")


# -------------------------------------------------------------------
# SkippedReason validity: all runner skip paths emit valid enum values
# -------------------------------------------------------------------
class TestRunnerSkipReasonsAreValidEnumMembers:
    """Verify every hardcoded ``skipped_reason=`` value in ``eval_runner.py``
    is a valid ``SkippedReason`` member.

    The runner stores ``skipped_reason`` as a plain ``str`` on ``EvalRun``.
    This test catches any future hardcoded string that falls outside the
    ``SkippedReason`` enum.
    """

    def test_all_hardcoded_skip_reasons_are_valid(self):
        import ast
        import inspect

        from kiln_ai.adapters.eval import eval_runner

        source = inspect.getsource(eval_runner)
        tree = ast.parse(source)

        valid_values = {member.value for member in SkippedReason}
        found_reasons: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword):
                continue
            if node.arg != "skipped_reason":
                continue
            value_node = node.value
            # Catch SkippedReason.<member>.value patterns
            if isinstance(value_node, ast.Attribute) and isinstance(
                value_node.attr, str
            ):
                if value_node.attr == "value":
                    if isinstance(value_node.value, ast.Attribute):
                        reason_name = value_node.value.attr
                        found_reasons.append(reason_name)
                        assert reason_name in SkippedReason.__members__, (
                            f"eval_runner uses SkippedReason.{reason_name} "
                            f"which is not a valid SkippedReason member"
                        )
            # Catch raw string literals like skipped_reason="some_string"
            elif isinstance(value_node, ast.Constant) and isinstance(
                value_node.value, str
            ):
                literal = value_node.value
                found_reasons.append(literal)
                assert literal in valid_values, (
                    f'eval_runner uses raw string skipped_reason="{literal}" '
                    f"which is not a valid SkippedReason value — "
                    f"use SkippedReason.<member>.value instead"
                )

        assert len(found_reasons) > 0, (
            "Expected at least one hardcoded SkippedReason usage in eval_runner. "
            "Test may need updating if runner was refactored."
        )


# ── V1 Legacy Runner Coexistence Guards ──────────────────────────────


class TestV1LegacyRunnerCoexistence:
    """Verify V1 eval configs dispatch through the legacy runner path.

    Guards against V2 additions accidentally misrouting V1 configs.
    Complements the model-layer tests in TestV1EvalConfigCoexistence (42050a2).
    """

    @pytest.mark.asyncio
    async def test_v1_g_eval_dispatches_through_legacy_runner(
        self,
        mock_eval_runner,
        mock_task,
        mock_eval_config,
        mock_run_config,
        data_source,
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

        assert mock_eval_config.config_type == EvalConfigType.g_eval

        mock_scores: EvalScores = {"accuracy": 0.9}

        class LegacyStubEval(BaseEval):
            async def run_task_and_eval(self, eval_job_item: TaskRun):
                return (
                    TaskRun(
                        input=eval_job_item.input,
                        input_source=data_source,
                        output=TaskOutput(output="legacy output"),
                    ),
                    mock_scores,
                    None,
                )

        with patch(
            "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
            return_value=lambda *args, **kwargs: LegacyStubEval(*args, **kwargs),
        ) as mock_dispatch:
            success = await mock_eval_runner.run_job(job)

        assert success is True
        mock_dispatch.assert_called_once_with(mock_eval_config)

        runs = mock_eval_config.runs()
        assert len(runs) == 1
        saved = runs[0]
        assert saved.dataset_id == task_run.id
        assert saved.eval_input_id is None
        assert saved.skipped_reason is None
        assert saved.reference_data is None
        assert saved.scores == mock_scores
        assert saved.output == "legacy output"
        assert saved.eval_config_eval is False

    @pytest.mark.asyncio
    async def test_v1_config_without_config_type_key_runs_through_legacy_runner(
        self, mock_eval_runner, mock_task, mock_eval, mock_run_config, data_source
    ):
        raw = {
            "name": "No Config Type Key",
            "model_name": "gpt-4",
            "model_provider": "openai",
            "properties": {"eval_steps": ["step1"]},
        }
        config = EvalConfig.model_validate(raw)
        config.parent = mock_eval
        config.save_to_file()

        assert config.config_type == EvalConfigType.g_eval

        task_run = TaskRun(
            parent=mock_task,
            input="hello",
            input_source=data_source,
            output=TaskOutput(output="world"),
        )
        task_run.save_to_file()

        job = EvalJob(
            item=task_run,
            task_run_config=mock_run_config,
            type="task_run_eval",
            eval_config=config,
        )

        mock_scores: EvalScores = {"accuracy": 0.85}

        class LegacyStubEval(BaseEval):
            async def run_task_and_eval(self, eval_job_item: TaskRun):
                return (
                    TaskRun(
                        input=eval_job_item.input,
                        input_source=data_source,
                        output=TaskOutput(output="from default config_type"),
                    ),
                    mock_scores,
                    None,
                )

        with patch(
            "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
            return_value=lambda *args, **kwargs: LegacyStubEval(*args, **kwargs),
        ) as mock_dispatch:
            success = await mock_eval_runner.run_job(job)

        assert success is True
        mock_dispatch.assert_called_once_with(config)

        runs = config.runs()
        assert len(runs) == 1
        saved = runs[0]
        assert saved.dataset_id == task_run.id
        assert saved.eval_input_id is None
        assert saved.output == "from default config_type"
        assert saved.skipped_reason is None

    @pytest.mark.asyncio
    async def test_v1_config_with_type_key_in_properties_not_misrouted_at_runner(
        self, mock_eval_runner, mock_task, mock_eval, mock_run_config, data_source
    ):
        config = EvalConfig(
            name="Type Key Collision",
            config_type=EvalConfigType.g_eval,
            model_name="gpt-4",
            model_provider="openai",
            properties={"eval_steps": ["s1"], "type": "exact_match"},
            parent=mock_eval,
        )
        config.save_to_file()

        assert config.config_type == EvalConfigType.g_eval
        assert isinstance(config.properties, dict)
        assert config.properties["type"] == "exact_match"

        task_run = TaskRun(
            parent=mock_task,
            input="collision input",
            input_source=data_source,
            output=TaskOutput(output="collision output"),
        )
        task_run.save_to_file()

        job = EvalJob(
            item=task_run,
            task_run_config=mock_run_config,
            type="task_run_eval",
            eval_config=config,
        )

        mock_scores: EvalScores = {"accuracy": 0.75}

        class LegacyStubEval(BaseEval):
            async def run_task_and_eval(self, eval_job_item: TaskRun):
                return (
                    TaskRun(
                        input=eval_job_item.input,
                        input_source=data_source,
                        output=TaskOutput(output="legacy, not v2"),
                    ),
                    mock_scores,
                    None,
                )

        with patch(
            "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
            return_value=lambda *args, **kwargs: LegacyStubEval(*args, **kwargs),
        ) as mock_dispatch:
            success = await mock_eval_runner.run_job(job)

        assert success is True
        mock_dispatch.assert_called_once_with(config)

        runs = config.runs()
        assert len(runs) == 1
        saved = runs[0]
        assert saved.output == "legacy, not v2"
        assert saved.eval_input_id is None
        assert saved.skipped_reason is None


# -------------------------------------------------------------------
# V2 multi-turn synthetic re-drive tests
# -------------------------------------------------------------------


@pytest.fixture
def mock_v2_redrive_eval(mock_task):
    """EvalInput-sourced full_trace eval with a drive config — the shape the
    builder saves for multi-turn."""
    eval = Eval(
        id="v2_redrive_eval",
        name="v2 redrive eval",
        description="multi-turn re-drive eval",
        eval_input_filter_id="all",
        eval_configs_filter_id="all",
        evaluation_data_type=EvalDataType.full_trace,
        multi_turn_drive_config=MultiTurnDriveConfig(
            model_name="claude_4_5_haiku",
            model_provider="openrouter",
            turns=3,
        ),
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
def mock_v2_redrive_config(mock_v2_redrive_eval):
    eval_config = EvalConfig(
        name="v2 redrive config",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="reply"),
        parent=mock_v2_redrive_eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def multi_turn_eval_input(mock_task):
    ei = EvalInput(
        id="ei_redrive",
        data=MultiTurnSyntheticEvalInputData(
            first_message=UserMessage(text="opening message"),
            synthetic_user_info=SyntheticUserInfo(
                persona="frustrated customer",
                goal="get a refund",
                behavior_guidance="be polite then escalate",
            ),
        ),
        parent=mock_task,
    )
    ei.save_to_file()
    return ei


def _fresh_leaf(task: Task, data_source: DataSource) -> TaskRun:
    """The in-memory leaf drive_case_for_eval would return: id-less,
    trace-carrying, never saved."""
    leaf = TaskRun(
        input="opening message",
        input_source=data_source,
        output=TaskOutput(output="fresh reply", source=data_source),
        trace=MULTI_TURN_TRACE,
        parent=task,
    )
    leaf.id = None
    return leaf


class TestRunV2MultiTurnRedrive:
    @pytest.mark.asyncio
    async def test_redrives_and_judges_fresh_trace(
        self,
        mock_task,
        mock_run_config,
        mock_v2_redrive_config,
        multi_turn_eval_input,
        data_source,
    ):
        runner = EvalRunner(
            eval_configs=[mock_v2_redrive_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        stub = RecordingStubV2Eval(mock_v2_redrive_config)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            result = await runner.run_job(job)

        assert result is True
        # The drive got the seed, the typed persona, the eval's drive config
        # as the customer, and the job's run config as the agent.
        drive_kwargs = mock_drive.await_args.kwargs
        assert drive_kwargs["seed_prompt"] == "opening message"
        assert drive_kwargs["synthetic_user_info"].persona == "frustrated customer"
        assert drive_kwargs["turns"] == 3
        assert drive_kwargs["su_driver_config"].model_name == "claude_4_5_haiku"
        assert (
            drive_kwargs["target_run_config"].model_name
            == mock_run_config.run_config_properties.model_name
        )

        # The judge saw the FRESH conversation, not stored data.
        assert len(stub.seen_inputs) == 1
        assert stub.seen_inputs[0].final_message == "fresh reply"
        assert stub.seen_inputs[0].trace == MULTI_TURN_TRACE
        assert stub.seen_inputs[0].task_input == "opening message"

        runs = mock_v2_redrive_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.eval_input_id == "ei_redrive"
        assert saved.dataset_id is None
        assert saved.eval_config_eval is False
        assert saved.task_run_config_id == mock_run_config.id
        assert saved.scores == {"accuracy": 1.0}
        assert saved.input == "opening message"
        assert saved.output == "fresh reply"
        assert saved.skipped_reason is None
        # The scored conversation and its drive identity ride the record.
        assert saved.task_run_trace is not None
        assert json.loads(saved.task_run_trace) == MULTI_TURN_TRACE
        assert saved.drive_fingerprint is not None
        assert saved.drive_fingerprint.startswith("v1:")

    @pytest.mark.asyncio
    async def test_missing_drive_config_skips(
        self,
        mock_task,
        mock_run_config,
        multi_turn_eval_input,
    ):
        """An eval without multi_turn_drive_config has no customer to
        re-drive with — clean typed skip, no drive attempted."""
        eval = Eval(
            id="v2_no_drive_eval",
            name="no drive config",
            description="missing drive config",
            eval_input_filter_id="all",
            eval_configs_filter_id="all",
            evaluation_data_type=EvalDataType.full_trace,
            output_scores=[
                EvalOutputScore(
                    name="Accuracy",
                    instruction="Check",
                    type=TaskOutputRatingType.pass_fail,
                ),
            ],
            parent=mock_task,
        )
        eval.save_to_file()
        config = EvalConfig(
            name="no drive cfg",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="x"),
            parent=eval,
        )
        config.save_to_file()
        runner = EvalRunner(
            eval_configs=[config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            result = await runner.run_job(job)

        assert result is True
        mock_drive.assert_not_awaited()
        runs = config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.skipped_reason == SkippedReason.missing_drive_config.value
        assert saved.eval_input_id == "ei_redrive"
        assert saved.scores == {}
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_missing_first_message_skips(
        self,
        mock_task,
        mock_run_config,
        mock_v2_redrive_config,
    ):
        """No seed message → nothing to open the conversation with."""
        ei = EvalInput(
            id="ei_no_seed",
            data=MultiTurnSyntheticEvalInputData(
                synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            ),
            parent=mock_task,
        )
        ei.save_to_file()
        runner = EvalRunner(
            eval_configs=[mock_v2_redrive_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(mock_v2_redrive_config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            result = await runner.run_job(job)

        assert result is True
        mock_drive.assert_not_awaited()
        runs = mock_v2_redrive_config.runs(readonly=True)
        saved = next(r for r in runs if r.eval_input_id == "ei_no_seed")
        assert saved.skipped_reason == SkippedReason.incompatible_input_shape.value
        assert "first_message" in saved.skipped_detail

    @pytest.mark.asyncio
    async def test_adapter_skip_keeps_trace(
        self,
        mock_task,
        mock_run_config,
        mock_v2_redrive_config,
        multi_turn_eval_input,
        data_source,
    ):
        """A judge-side skip after the drive keeps the full-cost conversation
        on the skip record (with its fingerprint) — only scores are absent."""
        runner = EvalRunner(
            eval_configs=[mock_v2_redrive_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=SkippingStubV2Eval(mock_v2_redrive_config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ),
        ):
            result = await runner.run_job(job)

        assert result is True
        runs = mock_v2_redrive_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.output is None
        assert saved.task_run_trace is not None
        assert json.loads(saved.task_run_trace) == MULTI_TURN_TRACE
        assert saved.drive_fingerprint is not None
        assert saved.drive_fingerprint.startswith("v1:")

    @pytest.mark.asyncio
    async def test_transient_drive_error_classifies_retryable(
        self,
        mock_task,
        mock_run_config,
        mock_v2_redrive_config,
        multi_turn_eval_input,
    ):
        """A provider rate limit mid-conversation arrives wrapped in
        KilnRunError (whose own message is genericized user-facing text).
        run_job must unwrap it, classify the failure as transient so the
        job runner retries the re-drive, keep the provider detail for the
        error log, and persist nothing for the failed attempt."""
        runner = EvalRunner(
            eval_configs=[mock_v2_redrive_config],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        mid_drive_error = wrapped_rate_limit_error(
            "rate limit exceeded, please try again later"
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=RecordingStubV2Eval(mock_v2_redrive_config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(side_effect=mid_drive_error),
            ),
        ):
            with pytest.raises(RetryableError) as exc_info:
                await runner.run_job(job)

        assert "rate limit exceeded, please try again later" in str(exc_info.value)
        assert "Wait a moment" not in str(exc_info.value)
        assert len(mock_v2_redrive_config.runs(readonly=True)) == 0


# -------------------------------------------------------------------
# Trace reuse: drive once, judge with every sibling config
# -------------------------------------------------------------------
@pytest.fixture
def reuse_eval(mock_task):
    """EvalInput-sourced eval whose drive turns match MULTI_TURN_TRACE's two
    user/assistant exchanges, so stored copies of that trace are healthy."""
    eval = Eval(
        id="reuse_eval",
        name="reuse eval",
        description="trace reuse eval",
        eval_input_filter_id="all",
        eval_configs_filter_id="all",
        multi_turn_drive_config=MultiTurnDriveConfig(
            model_name="claude_4_5_haiku",
            model_provider="openrouter",
            turns=2,
        ),
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


def make_reuse_config(reuse_eval: Eval, config_id: str) -> EvalConfig:
    config = EvalConfig(
        id=config_id,
        name=f"cfg {config_id}",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="reply"),
        parent=reuse_eval,
    )
    config.save_to_file()
    return config


def make_cross_eval(task, eval_id: str, su_model: str = "claude_4_5_haiku") -> Eval:
    """A SEPARATE Eval on the same task sharing reuse_eval's drive setup —
    the two-judges-two-evals shape the task-wide reuse scan exists for."""
    eval = Eval(
        id=eval_id,
        name=f"cross eval {eval_id}",
        description="separate eval sharing the drive setup",
        eval_input_filter_id="all",
        eval_configs_filter_id="all",
        multi_turn_drive_config=MultiTurnDriveConfig(
            model_name=su_model,
            model_provider="openrouter",
            turns=2,
        ),
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check if the output is accurate",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def cross_eval(mock_task):
    # Id sorts before reuse_eval's so the deterministic-pick test below can
    # prove cross-eval records participate in the (eval, config, run) order.
    return make_cross_eval(mock_task, "aaa_cross_eval")


@pytest.fixture
def cross_eval_config(cross_eval):
    return make_reuse_config(cross_eval, "cross_config")


@pytest.fixture
def reuse_config_a(reuse_eval):
    return make_reuse_config(reuse_eval, "config_a")


@pytest.fixture
def reuse_config_b(reuse_eval):
    return make_reuse_config(reuse_eval, "config_b")


def serialized_trace(trace: list[ChatCompletionMessageParam]) -> str:
    """The exact bytes the runner writes for a trace, for byte-equality asserts."""
    return json.dumps(trace, indent=2, ensure_ascii=False)


def reuse_fingerprint(
    eval: Eval, eval_input: EvalInput, run_config: TaskRunConfig
) -> str:
    assert eval.multi_turn_drive_config is not None
    assert isinstance(eval_input.data, MultiTurnSyntheticEvalInputData)
    return compute_drive_fingerprint(
        eval.multi_turn_drive_config,
        run_config.run_config_properties,
        eval_input.data,
    )


def seed_driven_run(
    config: EvalConfig,
    eval_input: EvalInput,
    run_config: TaskRunConfig,
    fingerprint: str | None,
    trace_json: str | None,
    run_id: str | None = None,
) -> EvalRun:
    """Persist an EvalRun shaped like a prior driven+judged record."""
    run = EvalRun(
        parent=config,
        task_run_config_id=run_config.id,
        dataset_id=None,
        eval_input_id=eval_input.id,
        eval_config_eval=False,
        scores={"accuracy": 1.0},
        input="opening message",
        output="reply",
        task_run_trace=trace_json,
        drive_fingerprint=fingerprint,
    )
    if run_id is not None:
        run.id = run_id
    run.save_to_file()
    return run


def make_reuse_job(
    eval_input: EvalInput, config: EvalConfig, run_config: TaskRunConfig
) -> EvalJob:
    return EvalJob(
        item=eval_input,
        eval_config=config,
        type="task_run_eval",
        task_run_config=run_config,
    )


@pytest.fixture
def second_run_config(mock_task):
    """Same resolved properties as mock_run_config, different id — the shape
    where fingerprints collide but the reuse key must still separate them."""
    rc = TaskRunConfig(
        name="test twin",
        description="identical properties, distinct config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=mock_task,
    )
    rc.save_to_file()
    return rc


class TestTraceReuse:
    @pytest.mark.asyncio
    async def test_reuse_hit_skips_drive_and_persists_identical_trace(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
    ):
        """A sibling config's healthy driven record satisfies a later
        invocation's job: no drive, judge sees the stored conversation, and
        the new record re-persists trace + fingerprint byte-identically."""
        fingerprint = reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        seeded_trace = serialized_trace(MULTI_TURN_TRACE)
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            seeded_trace,
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        stub = RecordingStubV2Eval(reuse_config_b)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            result = await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        assert result is True
        mock_drive.assert_not_awaited()

        # The judge scored the stored conversation with the input's own data.
        assert len(stub.seen_inputs) == 1
        judged = stub.seen_inputs[0]
        assert judged.trace == MULTI_TURN_TRACE
        assert judged.final_message == "reply"
        assert judged.task_input == "opening message"

        runs = reuse_config_b.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.scores == {"accuracy": 1.0}
        assert saved.output == "reply"
        assert saved.task_run_trace == seeded_trace
        assert saved.drive_fingerprint == fingerprint
        # Reuse writes no TaskRuns: the driven dataset stays transient.
        assert len(mock_task.runs(readonly=True)) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_trace_json",
        [
            None,  # tombstone: skip record that never got a conversation
            "[]",  # empty conversation
            serialized_trace(
                [
                    {"role": "user", "content": "turn 1"},
                    {"role": "assistant", "content": "hi"},
                ]
            ),  # one turn where the drive config demands two
            serialized_trace(
                [
                    {"role": "user", "content": "turn 1"},
                    {"role": "assistant", "content": None, "tool_calls": []},
                    {"role": "user", "content": "turn 2"},
                    {"role": "assistant", "content": None, "tool_calls": []},
                ]
            ),  # full turn count but no assistant text to judge
            serialized_trace(
                [
                    {"role": "user", "content": "turn 1"},
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "turn 2"},
                ]
            ),  # full user count but the final reply is missing
            serialized_trace(
                [
                    {"role": "user", "content": "turn 1"},
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "turn 2"},
                    {"role": "assistant", "content": None, "tool_calls": [{"id": "t"}]},
                ]
            ),  # ends mid tool call: reusing it would promote turn 1's reply
            "not json at all",
        ],
    )
    async def test_unhealthy_records_never_satisfy_reuse(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
        bad_trace_json,
    ):
        fingerprint = reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            bad_trace_json,
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            result = await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        assert result is True
        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fingerprint_mismatch_redrives(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
    ):
        """A healthy record under a different fingerprint (edited drive or
        scenario) never matches — content identity is the whole key."""
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            "v1:" + "0" * 64,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_legacy_records_without_fingerprint_never_reused(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
    ):
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            None,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reuse_never_crosses_run_configs(
        self,
        mock_task,
        mock_run_config,
        second_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
    ):
        """Two run configs with identical properties fingerprint identically,
        but a job for one must never consume the other's conversation."""
        fingerprint = reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        assert fingerprint == reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, second_run_config
        )
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[second_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, second_run_config)
            )

        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_invocation_siblings_share_one_drive(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
    ):
        """Within one runner invocation the first drive is published in
        memory, so the sibling config's job reuses it before it hits disk."""
        runner = EvalRunner(
            eval_configs=[reuse_config_a, reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                side_effect=lambda config, *_: StubV2Eval(config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            for config in (reuse_config_a, reuse_config_b):
                assert await runner.run_job(
                    make_reuse_job(multi_turn_eval_input, config, mock_run_config)
                )

        assert mock_drive.await_count == 1
        run_a = reuse_config_a.runs(readonly=True)[0]
        run_b = reuse_config_b.runs(readonly=True)[0]
        assert run_a.task_run_trace == run_b.task_run_trace
        assert run_a.task_run_trace is not None
        assert run_a.drive_fingerprint == run_b.drive_fingerprint

    @pytest.mark.asyncio
    async def test_deterministic_pick_across_racing_writers(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        multi_turn_eval_input,
    ):
        """When racing drives left two healthy records for one key, every
        later read picks the same one (lowest config id, run id)."""
        fingerprint = reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        first_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": "first writer"},
            {"role": "user", "content": "turn 2"},
            {"role": "assistant", "content": "first writer final"},
        ]
        second_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": "second writer"},
            {"role": "user", "content": "turn 2"},
            {"role": "assistant", "content": "second writer final"},
        ]
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(first_trace),
            run_id="run_1",
        )
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(second_trace),
            run_id="run_2",
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        stub = RecordingStubV2Eval(reuse_config_b)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        mock_drive.assert_not_awaited()
        assert stub.seen_inputs[0].trace == first_trace

    @pytest.mark.asyncio
    async def test_cross_eval_reuse_hit_skips_drive(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_b,
        cross_eval,
        cross_eval_config,
        multi_turn_eval_input,
    ):
        """A healthy driven record under a DIFFERENT eval on the same task
        satisfies this eval's job: the fingerprint is content-keyed, so two
        judges forced onto separate Evals still score one conversation."""
        fingerprint = reuse_fingerprint(
            cross_eval, multi_turn_eval_input, mock_run_config
        )
        # Identical drive configs fingerprint identically from either eval.
        assert fingerprint == reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        seeded_trace = serialized_trace(MULTI_TURN_TRACE)
        seed_driven_run(
            cross_eval_config,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            seeded_trace,
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        stub = RecordingStubV2Eval(reuse_config_b)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            result = await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        assert result is True
        mock_drive.assert_not_awaited()
        assert stub.seen_inputs[0].trace == MULTI_TURN_TRACE

        # The reused record is self-contained: byte-identical trace + the
        # shared fingerprint persist under THIS eval's config.
        saved = reuse_config_b.runs(readonly=True)[0]
        assert saved.task_run_trace == seeded_trace
        assert saved.drive_fingerprint == fingerprint
        assert len(mock_task.runs(readonly=True)) == 0

    @pytest.mark.asyncio
    async def test_cross_eval_different_drive_config_never_reused(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_b,
        multi_turn_eval_input,
        data_source,
    ):
        """Another eval driving with a different SU model (same turns, so its
        trace is healthy) fingerprints differently — never reused here."""
        other_eval = make_cross_eval(mock_task, "other_su_eval", su_model="gpt_4o")
        other_config = make_reuse_config(other_eval, "other_su_config")
        other_fingerprint = reuse_fingerprint(
            other_eval, multi_turn_eval_input, mock_run_config
        )
        assert other_fingerprint != reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        seed_driven_run(
            other_config,
            multi_turn_eval_input,
            mock_run_config,
            other_fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cross_eval_never_crosses_run_configs(
        self,
        mock_task,
        mock_run_config,
        second_run_config,
        reuse_eval,
        reuse_config_b,
        cross_eval,
        cross_eval_config,
        multi_turn_eval_input,
        data_source,
    ):
        """Widening the scan across evals must not loosen the run-config
        boundary: another eval's record for run config A never serves B."""
        fingerprint = reuse_fingerprint(
            cross_eval, multi_turn_eval_input, mock_run_config
        )
        seed_driven_run(
            cross_eval_config,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[second_run_config],
            eval_run_type="task_run_eval",
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_leaf(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, second_run_config)
            )

        mock_drive.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cross_eval_deterministic_pick(
        self,
        mock_task,
        mock_run_config,
        reuse_eval,
        reuse_config_a,
        reuse_config_b,
        cross_eval,
        cross_eval_config,
        multi_turn_eval_input,
    ):
        """With healthy records under TWO evals for one key, every reader
        picks by (eval id, config id, run id) — here the cross eval's record,
        whose eval id sorts first."""
        fingerprint = reuse_fingerprint(
            reuse_eval, multi_turn_eval_input, mock_run_config
        )
        cross_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "turn 1"},
            {"role": "assistant", "content": "cross-eval writer"},
            {"role": "user", "content": "turn 2"},
            {"role": "assistant", "content": "cross-eval final"},
        ]
        seed_driven_run(
            cross_eval_config,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(cross_trace),
        )
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = EvalRunner(
            eval_configs=[reuse_config_b],
            run_configs=[mock_run_config],
            eval_run_type="task_run_eval",
        )
        stub = RecordingStubV2Eval(reuse_config_b)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )

        mock_drive.assert_not_awaited()
        assert stub.seen_inputs[0].trace == cross_trace
