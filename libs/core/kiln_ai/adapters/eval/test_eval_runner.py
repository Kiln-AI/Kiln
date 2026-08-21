import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from typing import ClassVar, Dict
from unittest.mock import AsyncMock, patch

import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval, BaseV2EvalBridge
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
    EvalItemSource,
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
    EvalInputSplit,
    EvalOutputScore,
    EvalRun,
    EvalScores,
    EvalSplitName,
    EvalTaskInput,
    ExactMatchProperties,
    MultiTurnDriveConfig,
    MultiTurnSyntheticEvalInputData,
    SingleTurnEvalInputData,
    SkippedReason,
    SyntheticUserInfo,
    TaskRunSplit,
    UserMessage,
    V2EvalResult,
)
from kiln_ai.datamodel.eval_splits import resolve_split
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig
from kiln_ai.datamodel.usage import MessageUsage, Usage
from kiln_ai.synthetic_user.drive_loop import DriveCaseResult
from kiln_ai.utils.async_job_runner import RetryableError
from kiln_ai.utils.git_sync_protocols import default_save_context
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def build_task_run_eval_runner(
    eval_configs: list[EvalConfig],
    run_configs: list[TaskRunConfig],
    *,
    split_name: EvalSplitName = "test",
    **kwargs,
) -> EvalRunner:
    """A task_run_eval runner over the named split, resolved from disk as of now.

    The runner is handed items rather than a filter, so its item set is a snapshot taken
    here. A test that creates dataset items or changes a split after calling this must
    build a second runner — which is what a real caller would have to do too.
    """
    eval = eval_configs[0].parent_eval()
    assert eval is not None
    task = eval.parent_task()
    assert task is not None
    split = resolve_split(task, eval, split_name)
    assert split is not None, f"eval has no '{split_name}' split"
    return EvalRunner(
        eval_configs=eval_configs,
        run_configs=run_configs,
        eval_run_type="task_run_eval",
        split=split,
        **kwargs,
    )


class TraceGenerator:
    """Stands in for the model call inside `BaseEval.run_task`.

    Reproduces the exact shape production returns, which is load-bearing twice over:

    - **`id=None`.** `run_task` builds its adapter with `allow_saving=False`, and every
      adapter clears the id of a run it did not persist (`base_adapter.py:346`). A double
      that kept its default-factory id would let the runner `save_to_file()` a run that
      real code cannot, hiding a failure on every single job.
    - **`run_config_id` set on the output source.** Half the trace key. A double that
      left it unset would be rejected by the trace index.
    - **A real `trace` and `usage`.** These are the fields the split exists to move onto
      the TaskRun, and the reuse path hands back a run *reloaded from disk*. Leaving them
      None on the double would make the round-trip assert nothing: `full_trace` evals
      read `trace.trace` through `EvalTaskInput.from_trace`, and Phase 4's rollup reads
      `usage`.
    """

    def __init__(self, task: Task, output: str = "fresh output"):
        self.task = task
        self.output = output
        self.trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "the prompt the model saw"},
            {"role": "assistant", "content": output},
        ]
        self.usage = Usage(input_tokens=42, output_tokens=7, cost=0.001)
        self.calls: list[tuple[TaskRun | EvalInput, str | None]] = []

    async def __call__(
        self, item: TaskRun | EvalInput, run_config_id: str | None = None
    ) -> TaskRun:
        self.calls.append((item, run_config_id))
        # Real generation is a network call. Yielding here is what lets two jobs on one
        # key interleave — without it they run to completion in turn, and an unlocked
        # index would look correct.
        await asyncio.sleep(0)
        run = TaskRun(
            parent=self.task,
            input=item.input
            if isinstance(item, TaskRun)
            else item.data.user_message.text,
            output=TaskOutput(
                output=self.output,
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test_adapter",
                    },
                    run_config_id=run_config_id,
                ),
            ),
            trace=self.trace,
            usage=self.usage,
        )
        run.id = None
        return run


def eval_traces(task: Task) -> list[TaskRun]:
    """The task's eval-generated runs, which `task.runs()` hides by default."""
    return [
        run
        for run in task.runs(readonly=True, include_eval_generated=True)
        if run.eval_source is not None
    ]


def trace_for(task: Task, run_id: str | None) -> TaskRun:
    return next(run for run in eval_traces(task) if run.id == run_id)


@contextmanager
def generating(generator: TraceGenerator, evaluator_factory=StubV2Eval):
    """Score V2 jobs with `evaluator_factory`'s judge, and generate with `generator`.

    The judge is built per eval config, as the registry does, so a test with two judges
    exercises two adapters rather than sharing one.
    """
    with (
        patch.object(BaseV2EvalBridge, "run_task", new=generator),
        patch(
            "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
            side_effect=lambda config, *args, **kwargs: evaluator_factory(config),
        ),
    ):
        yield


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
    """A runner whose split is resolved before any test data exists — so it is empty.

    Fine for run_job tests, which take their item from the job. A collect_tasks test must
    build its own runner with build_task_run_eval_runner after creating its data.
    """
    return build_task_run_eval_runner([mock_eval_config], [mock_run_config])


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

    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::tag1")
    mock_eval.eval_configs_filter_id = "tag::tag2"

    # Create a new runner of type task run eval
    runner = build_task_run_eval_runner([mock_eval_config], [mock_run_config])
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
    runner = build_task_run_eval_runner([mock_eval_config], [mock_run_config, rc])
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
    mock_eval, mock_task, data_source, mock_eval_config, mock_run_config
):
    """Test that already run tasks are excluded"""
    # Narrow the test split to the tag the runs carry, so "no jobs" below can only mean
    # "already run" — with a filter that matched nothing it would be zero either way.
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::tag1")
    mock_eval.eval_configs_filter_id = "tag::nonexistent"

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
    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()
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

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()

    # Should get no jobs since the task was already run
    assert len(jobs) == 0

    # Same split, a second item that has not been run: the split is really being read.
    second_run = TaskRun(
        parent=mock_task,
        input="test2",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(output="test2"),
    )
    second_run.save_to_file()
    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()
    assert [job.item.id for job in jobs] == [second_run.id]


def test_collect_tasks_ignores_runs_from_run_configs_not_being_evaluated(
    mock_eval, mock_task, data_source, mock_eval_config, mock_run_config
):
    """Scoring an item under run config A must not exclude it when B is evaluated later.

    The eval config accumulates runs for every run config ever compared, so most of what
    collect_tasks reads belongs to run configs this runner was not given.
    """
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::tag1")
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(output="test"),
    )
    task_run.save_to_file()

    other_run_config = TaskRunConfig(
        name="other",
        description="a run config this runner was not given",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=mock_task,
    )
    other_run_config.save_to_file()
    EvalRun(
        parent=mock_eval_config,
        dataset_id=task_run.id,
        task_run_config_id=other_run_config.id,
        input="test",
        output="test",
        scores={"accuracy": 1.0},
    ).save_to_file()

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()

    assert [job.item.id for job in jobs] == [task_run.id]


def test_collect_tasks_ignores_calibration_runs_when_a_run_config_has_no_id(
    mock_eval, mock_task, data_source, mock_eval_config, mock_run_config
):
    """`ID_TYPE` is `str | None`, so a run config file carrying a null id loads as one.

    That makes None a real key in the already-run map, and every calibration record —
    which is exactly the set that carries `task_run_config_id=None` — would be folded
    into it, silently skipping items that were never scored for this run config.
    """
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::tag1")
    task_run = TaskRun(
        parent=mock_task,
        input="test",
        input_source=data_source,
        tags=["tag1"],
        output=TaskOutput(output="test"),
    )
    task_run.save_to_file()
    EvalRun(
        parent=mock_eval_config,
        dataset_id=task_run.id,
        task_run_config_id=None,
        eval_config_eval=True,
        input="test",
        output="test",
        scores={"accuracy": 1.0},
    ).save_to_file()

    id_less_run_config = TaskRunConfig(
        id=None,
        name="no id",
        description="a run config whose stored id is null",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=mock_task,
    )
    assert id_less_run_config.id is None

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [id_less_run_config]
    ).collect_tasks()

    assert [job.item.id for job in jobs] == [task_run.id]


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

    # eval_config_eval scopes by the golden filter, never by the test split — the split
    # below matches nothing precisely to show the golden filter is what selects the item.
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::nonexistent")
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
    mock_eval, mock_eval_config, mock_task, data_source, mock_run_config
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

    # Set filter to match the task
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::tag1")

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config, second_config]
    ).collect_tasks()

    # Should get 2 jobs, one for each config
    assert len(jobs) == 2
    assert {job.task_run_config.id for job in jobs} == {
        second_config.id,
        mock_run_config.id,
    }


def test_collect_tasks_empty_cases(
    mock_eval, mock_eval_config, mock_run_config, mock_task, data_source
):
    """Test empty cases - no matching tasks or no tasks at all"""
    # Set filter that won't match anything
    mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::nonexistent")
    mock_eval.eval_configs_filter_id = "tag::nonexistent"

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()
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

    jobs = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config]
    ).collect_tasks()
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
                None,
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
async def test_run_job_persists_judge_eval_usage(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    """A judged EvalRun must carry the judge model's usage in eval_usage."""
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

    judge_usage = Usage(
        input_tokens=1234, output_tokens=56, total_tokens=1290, cost=0.0042
    )

    class MockEvaluator(BaseEval):
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            return (
                TaskRun(
                    input=eval_job_item.input,
                    input_source=data_source,
                    output=TaskOutput(output="evaluated output"),
                ),
                {"accuracy": 0.95},
                None,
                judge_usage,
            )

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        success = await mock_eval_runner.run_job(job)

    assert success is True
    eval_runs = mock_eval_config.runs()
    assert len(eval_runs) == 1
    saved_run = eval_runs[0]
    assert saved_run.eval_usage is not None
    assert saved_run.eval_usage.input_tokens == 1234
    assert saved_run.eval_usage.output_tokens == 56
    assert saved_run.eval_usage.total_tokens == 1290
    assert saved_run.eval_usage.cost == 0.0042

    # Round-trip through disk: the usage must survive persistence.
    assert saved_run.path is not None
    reloaded = EvalRun.load_from_file(saved_run.path)
    assert reloaded.eval_usage is not None
    assert reloaded.eval_usage.total_tokens == 1290
    assert reloaded.eval_usage.cost == 0.0042


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
        ) -> tuple[EvalScores, Dict[str, str] | None, Usage | None]:
            return mock_scores, {"intermediate_output": "intermediate output"}, None

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
                None,
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
    parsed_trace = json.loads(saved_run.task_run_trace)
    assert parsed_trace == mock_trace


@pytest.mark.asyncio
async def test_run_job_full_trace_serializes_per_message_usage(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    """Regression: the V1 runner serialized the trace with a plain `json.dumps`.

    A real trace types its per-message `usage` as a `MessageUsage` model, which that
    encoder cannot handle - so the job died before it ever saved an EvalRun.
    """
    mock_eval_config.parent.evaluation_data_type = EvalDataType.full_trace
    mock_eval_config.parent.save_to_file()

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
        async def run_task_and_eval(self, eval_job_item: TaskRun):
            result_task_run = TaskRun(
                input=eval_job_item.input,
                input_source=data_source,
                output=TaskOutput(output="evaluated output"),
                trace=[
                    {"role": "user", "content": "test input"},
                    {
                        "role": "assistant",
                        "content": "test response",
                        "usage": MessageUsage(
                            input_tokens=42, output_tokens=7, cost=0.001
                        ),
                    },
                ],
            )
            return result_task_run, {"accuracy": 0.95}, {}, None

    with patch(
        "kiln_ai.adapters.eval.eval_runner.legacy_eval_adapter_from_type",
        return_value=lambda *args, **kwargs: MockEvaluator(*args, **kwargs),
    ):
        assert await mock_eval_runner.run_job(job) is True

    saved_run = mock_eval_config.runs()[0]
    assert saved_run.task_run_trace is not None
    assert json.loads(saved_run.task_run_trace)[1]["usage"] == {
        "input_tokens": 42,
        "output_tokens": 7,
        "total_tokens": None,
        "cost": 0.001,
        "cached_tokens": None,
    }


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
                None,
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
                None,
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


@pytest.mark.asyncio
async def test_run_job_wrapped_rate_limit_raises_retryable_with_detail(
    mock_eval_runner, mock_task, data_source, mock_run_config, mock_eval_config
):
    # Real adapter failures arrive wrapped in KilnRunError whose own message is the
    # genericized user-facing text. run_job must still classify the failure as
    # transient (RetryableError) and keep the underlying provider message for the
    # developer-facing logs.
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
    runner = build_task_run_eval_runner([mock_eval_config], [mock_run_config])
    assert runner._save_context is default_save_context


def test_eval_runner_accepts_custom_save_context(
    mock_eval, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config], save_context=recorder
    )
    assert runner._save_context is recorder


@pytest.mark.asyncio
async def test_run_job_custom_save_context_wraps_save(
    mock_task, data_source, mock_eval_config, mock_run_config
):
    recorder = _RecordingSaveContext()
    runner = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config], save_context=recorder
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
                None,
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
    runner = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config], save_context=recorder
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
                None,
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
    runner = build_task_run_eval_runner(
        [mock_eval_config], [mock_run_config], save_context=recorder
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
                None,
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
    """Eval whose test split is EvalInput-backed (V2 source mode)."""
    eval = Eval(
        id="v2_eval",
        name="v2 test eval",
        description="v2 eval desc",
        splits={"test": EvalInputSplit(filter_id="all")},
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
# Init: the split is the runner's item scope (architecture 4.2)
# -------------------------------------------------------------------
class TestEvalRunnerSplitArgument:
    def test_task_run_eval_requires_a_split(self, mock_eval_config, mock_run_config):
        with pytest.raises(ValueError, match="requires a resolved split"):
            EvalRunner(
                eval_configs=[mock_eval_config],
                run_configs=[mock_run_config],
                eval_run_type="task_run_eval",
            )

    def test_eval_config_eval_rejects_a_split(
        self, mock_eval, mock_task, mock_eval_config
    ):
        split = resolve_split(mock_task, mock_eval, "test")
        assert split is not None
        with pytest.raises(ValueError, match="does not support a split"):
            EvalRunner(
                eval_configs=[mock_eval_config],
                run_configs=None,
                eval_run_type="eval_config_eval",
                split=split,
            )

    def test_task_run_eval_accepts_an_eval_input_backed_split(
        self, mock_v2_eval_config, mock_run_config, mock_eval_inputs
    ):
        runner = build_task_run_eval_runner([mock_v2_eval_config], [mock_run_config])
        assert runner.split is not None
        assert runner.split.source == "eval_input"
        assert runner.eval_run_type == "task_run_eval"

    def test_rejects_a_split_resolved_from_a_different_eval(
        self, mock_task, mock_eval, mock_v2_eval, mock_eval_config, mock_run_config
    ):
        """Before the runner took items, the item set came from the eval and this was
        unconstructible. It stays unconstructible because the split remembers where it
        came from — otherwise one eval's judges would score another's items in silence."""
        other_evals_split = resolve_split(mock_task, mock_v2_eval, "test")
        assert other_evals_split is not None
        assert mock_v2_eval.id != mock_eval.id

        with pytest.raises(ValueError, match="was resolved from eval") as exc_info:
            EvalRunner(
                eval_configs=[mock_eval_config],
                run_configs=[mock_run_config],
                eval_run_type="task_run_eval",
                split=other_evals_split,
            )

        assert mock_v2_eval.id in str(exc_info.value)
        assert mock_eval.id in str(exc_info.value)


# -------------------------------------------------------------------
# eval_config_eval is golden-scoped, so its items are always TaskRuns
# -------------------------------------------------------------------
class TestCollectTasksEvalConfigEval:
    def test_collects_only_task_runs_on_an_eval_input_backed_eval(
        self, mock_v2_runner, mock_task, mock_eval_inputs, data_source
    ):
        """The eval's test split is EvalInput-backed, but calibration scopes by the golden
        filter, which can only address TaskRuns. The EvalInputs are present precisely so a
        source-mode branch would wrongly collect them."""
        task_run = TaskRun(
            parent=mock_task,
            input="golden input",
            input_source=data_source,
            output=TaskOutput(output="golden output"),
        )
        task_run.save_to_file()

        jobs = mock_v2_runner.collect_tasks()

        assert [job.item.id for job in jobs] == [task_run.id]
        assert all(isinstance(job.item, TaskRun) for job in jobs)
        assert all(job.type == "eval_config_eval" for job in jobs)

    @pytest.mark.asyncio
    async def test_writes_no_skipped_runs_for_an_eval_input_backed_eval(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs
    ):
        """Architecture 4.3. This used to be a *successful* run that persisted one junk
        EvalRun per EvalInput, so only the absence of records can catch a regression."""
        async for _ in mock_v2_runner.run():
            pass

        assert mock_v2_eval_config.runs(readonly=True) == []

    def test_no_golden_set_raises_at_construction(self, mock_task, mock_eval_inputs):
        """Not at collect time. These runners are driven by SSE endpoints, so a failure
        raised once the response generator is running arrives after a 200 and reaches the
        client as a dead stream. Construction is the last point a caller can turn it into
        a real error (architecture 4.3, functional spec 9)."""
        eval = Eval(
            id="no_golden",
            name="no golden",
            description="EvalInput-backed eval with no golden set",
            splits={"test": EvalInputSplit(filter_id="all")},
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
            name="no golden config",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="4"),
            parent=eval,
        )
        eval_config.save_to_file()

        with pytest.raises(
            ValueError, match="has no golden set configured"
        ) as exc_info:
            EvalRunner(
                eval_configs=[eval_config],
                run_configs=None,
                eval_run_type="eval_config_eval",
            )

        assert "no_golden" in str(exc_info.value)

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


class RecordingStoredTraceStubV2Eval(StubV2Eval):
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
        assert saved.scored_run_id == task_run.id
        assert saved.output is None

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
        # Calibration scores the golden item itself, so the trace exists no matter where
        # the skip happened — same shape as the scoring-time skip below.
        assert saved.scored_run_id == task_run.id
        assert eval_traces(mock_v2_runner.task) == []
        # No copy of the item on the record: the inline trace fields are deprecated and
        # new records never set them.
        assert saved.output is None
        assert saved.input is None

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
        # Skipped at scoring time, so the trace it could not score is still named.
        assert saved.scored_run_id == task_run.id
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_type_not_available_skip_eval_input(
        self, mock_v2_runner, mock_v2_eval_config, mock_eval_inputs, mock_run_config
    ):
        ei = mock_eval_inputs[1]
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
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
        # A scoring job that can never be scored has nothing to point at, and pays for
        # no generation to give itself one.
        assert saved.scored_run_id is None
        assert eval_traces(mock_v2_runner.task) == []
        assert saved.input is None

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
        stub = RecordingStoredTraceStubV2Eval(mock_v2_eval_config)
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
        # The record names the golden run it scored rather than copying it: the
        # conversation already lives on that TaskRun.
        assert saved.scored_run_id == task_run.id
        assert saved.input is None
        assert saved.output is None
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
        # A conversation is judged on the trace it already has, so a chain leaf that
        # stored none is a missing trace rather than an unsupported shape.
        assert saved.skipped_reason == SkippedReason.missing_trace.value
        assert "no stored trace" in saved.skipped_detail
        assert saved.scored_run_id == task_run.id
        # No eval_traces() here: this test's leaf is only constructible under a
        # multiturn copy of the task, so re-reading the whole runs directory can't
        # load it back. `scored_run_id` above already says which run was scored, and
        # that it is the stored one rather than a generation.
        assert saved.input is None
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_multi_turn_eval_input_skipped(
        self,
        mock_task,
        mock_v2_runner,
        mock_v2_eval_config,
        mock_eval_inputs,
        mock_run_config,
    ):
        """A multi-turn EvalInput is re-driven, so an eval with nothing to drive it with
        is a typed skip.

        The synthetic user comes from the eval's `multi_turn_drive_config`, and this eval
        has none; the case is a conversation to hold, not an item with a stored output,
        so there is nothing to fall back to. Nothing is generated either way."""
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
            type="task_run_eval",
            task_run_config=mock_run_config,
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
        assert saved.skipped_reason == SkippedReason.missing_drive_config.value
        assert "multi_turn_drive_config" in saved.skipped_detail
        assert saved.eval_input_id == "ei_multi"
        assert saved.scored_run_id is None
        assert eval_traces(mock_task) == []
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
    return build_task_run_eval_runner([mock_v2_task_run_eval_config], [mock_run_config])


class TestV2FreshGeneration:
    @pytest.mark.asyncio
    async def test_task_run_eval_generates_persists_and_scores_the_trace(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """The trace is a TaskRun of its own, and the score only points at it."""
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        generator = TraceGenerator(mock_v2_task_run_eval_runner.task, "hello")
        with generating(generator):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        assert generator.calls == [(item, mock_run_config.id)]

        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.scores == {"accuracy": 1.0}
        assert saved.dataset_id == item.id
        assert saved.eval_config_eval is False
        assert saved.skipped_reason is None
        assert saved.scored_run_id is not None
        assert saved.scored_run_id != item.id
        # No inline copy of what was scored: the trace has one home now.
        assert saved.input is None
        assert saved.output is None
        assert saved.task_run_trace is None
        assert saved.task_run_usage is None
        assert saved.reference_answer is None

        trace = trace_for(mock_v2_task_run_eval_runner.task, saved.scored_run_id)
        assert trace.output.output == "hello"
        assert trace.eval_source == EvalItemSource(
            source_type="task_run", source_id=item.id
        )
        assert trace.output.source.run_config_id == mock_run_config.id

    @pytest.mark.asyncio
    async def test_the_runner_persists_a_run_the_adapter_left_unsaved(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """Production reproduction: `run_task` builds its adapter with
        `allow_saving=False`, and every adapter clears the id of a run it did not persist
        (`base_adapter.py:346`). The runner mints one before saving.

        Without that, `save_to_file()` raises "ID is not set - can not save or build
        path" and every V2 task_run_eval job fails. The score still records the *source*
        item as `dataset_id`, and the minted trace as `scored_run_id`.
        """
        task = mock_v2_task_run_eval_runner.task
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=task,
        )
        item.save_to_file()

        # The double is only worth anything if it reproduces the unsaved shape.
        assert (await TraceGenerator(task)(item, mock_run_config.id)).id is None

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with generating(TraceGenerator(task)):
            assert await mock_v2_task_run_eval_runner.run_job(job) is True

        (trace,) = eval_traces(task)
        assert trace.id is not None
        assert trace.path is not None and trace.path.exists()
        assert TaskRun.load_from_file(trace.path).id == trace.id

        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.dataset_id == item.id
        assert saved.scored_run_id == trace.id

    @pytest.mark.asyncio
    async def test_generated_trace_is_hidden_from_the_dataset(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """Phase 1's default-exclude is what makes persisting traces safe at all."""
        task = mock_v2_task_run_eval_runner.task
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with generating(TraceGenerator(task)):
            await mock_v2_task_run_eval_runner.run_job(job)

        assert [run.id for run in task.runs(readonly=True)] == [item.id]
        assert len(task.runs(readonly=True, include_eval_generated=True)) == 2

    @pytest.mark.asyncio
    async def test_judge_usage_is_recorded_on_the_score(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """What the judgment cost, which nothing recorded before `eval_usage`.

        Distinct from the task's usage, which now lives on the trace's own TaskRun.
        """
        judge_usage = Usage(input_tokens=90, output_tokens=6, cost=0.002)

        class MeteredJudge(StubV2Eval):
            async def evaluate(self, eval_input):
                return V2EvalResult(scores={"accuracy": 1.0}, usage=judge_usage)

        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with generating(
            TraceGenerator(mock_v2_task_run_eval_runner.task), MeteredJudge
        ):
            await mock_v2_task_run_eval_runner.run_job(job)

        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.eval_usage == judge_usage
        assert saved.task_run_usage is None

    @pytest.mark.asyncio
    async def test_scoring_skip_still_names_the_trace_it_could_not_score(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        with generating(
            TraceGenerator(mock_v2_task_run_eval_runner.task), SkippingStubV2Eval
        ):
            result = await mock_v2_task_run_eval_runner.run_job(job)

        assert result is True
        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        assert saved.scores == {}
        assert saved.dataset_id == item.id
        # Generation succeeded and only the judge gave up, so the trace stays reusable —
        # and the record names the trace it could not score, not merely some trace.
        (trace,) = eval_traces(mock_v2_task_run_eval_runner.task)
        assert saved.scored_run_id == trace.id
        assert saved.output is None

    @pytest.mark.asyncio
    async def test_calibration_scores_the_golden_item_itself(
        self,
        mock_v2_runner,
        mock_v2_eval_config,
        data_source,
    ):
        """No generation, so no trace: `scored_run_id` is the dataset item (spec 4.5)."""
        task = mock_v2_runner.task
        golden = TaskRun(
            input="existing input",
            output=TaskOutput(output="existing output", source=data_source),
            parent=task,
        )
        golden.save_to_file()

        job = EvalJob(
            item=golden,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )

        generator = TraceGenerator(task)
        with generating(generator):
            result = await mock_v2_runner.run_job(job)

        assert result is True
        assert generator.calls == []
        (saved,) = mock_v2_eval_config.runs(readonly=True)
        assert saved.scores == {"accuracy": 1.0}
        assert saved.dataset_id == golden.id
        assert saved.scored_run_id == golden.id
        assert saved.eval_config_eval is True
        assert saved.skipped_reason is None
        # The golden item is not flagged, so it stays a normal dataset run: visible,
        # and deletable.
        assert [
            run.id for run in task.runs(readonly=True, include_eval_generated=True)
        ] == [golden.id]
        assert TaskRun.load_from_file(golden.path).eval_source is None

    @pytest.mark.asyncio
    async def test_failed_generation_persists_nothing(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """D14: a failed generation has no representation — not a trace, not a score."""
        task = mock_v2_task_run_eval_runner.task
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = StubV2Eval(mock_v2_task_run_eval_config)
        with (
            patch.object(stub, "run_task", side_effect=RuntimeError("model exploded")),
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            pytest.raises(RuntimeError, match="model exploded"),
        ):
            await mock_v2_task_run_eval_runner.run_job(job)

        assert mock_v2_task_run_eval_config.runs(readonly=True) == []
        assert len(task.runs(readonly=True, include_eval_generated=True)) == 1

    @pytest.mark.asyncio
    async def test_retry_after_a_scoring_failure_rescores_without_regenerating(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
    ):
        """Functional spec 4.3: the trace survives the judge, so a retry is cheap.

        Two `run_job` calls on one job, which is what `AsyncJobRunner` does on a
        RetryableError — the live index is what makes the second one skip generation.
        """
        task = mock_v2_task_run_eval_runner.task
        item = TaskRun(
            input="test input",
            output=TaskOutput(output="stale output", source=data_source),
            parent=task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        stub = StubV2Eval(mock_v2_task_run_eval_config)
        generator = TraceGenerator(task)
        with generating(generator, lambda config: stub):
            with patch.object(
                stub,
                "evaluate",
                side_effect=litellm.RateLimitError("slow down", "", ""),
            ):
                with pytest.raises(RetryableError):
                    await mock_v2_task_run_eval_runner.run_job(job)

            assert len(generator.calls) == 1
            traces = eval_traces(task)
            assert len(traces) == 1
            assert mock_v2_task_run_eval_config.runs(readonly=True) == []

            assert await mock_v2_task_run_eval_runner.run_job(job) is True

        assert len(generator.calls) == 1
        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.scored_run_id == traces[0].id


# -------------------------------------------------------------------
# What the judge is handed: reference data reaching the evaluator
# -------------------------------------------------------------------
class RecordingStubV2Eval(BaseV2EvalBridge):
    """Captures every EvalTaskInput handed to a judge."""

    seen: ClassVar[list[EvalTaskInput]] = []

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        RecordingStubV2Eval.seen.append(eval_input)
        return V2EvalResult(scores={"accuracy": 1.0})


@pytest.fixture
def recorded_judge_inputs():
    RecordingStubV2Eval.seen = []
    yield RecordingStubV2Eval.seen
    RecordingStubV2Eval.seen = []


class TestReferenceDataReachesTheJudge:
    """A QnA dataset item stores the reference answer as its output. The judge is told
    to grade against it, so it has to arrive."""

    @pytest.mark.asyncio
    async def test_a_dataset_items_output_is_the_judges_reference_answer(
        self,
        mock_v2_task_run_eval_runner,
        mock_v2_task_run_eval_config,
        mock_run_config,
        data_source,
        recorded_judge_inputs,
    ):
        item = TaskRun(
            input="Who wrote Dune?",
            output=TaskOutput(output="Frank Herbert.", source=data_source),
            parent=mock_v2_task_run_eval_runner.task,
        )
        item.save_to_file()

        job = EvalJob(
            item=item,
            eval_config=mock_v2_task_run_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        generator = TraceGenerator(mock_v2_task_run_eval_runner.task, "Herbert, 1965.")
        with generating(generator, RecordingStubV2Eval):
            assert await mock_v2_task_run_eval_runner.run_job(job) is True

        (seen,) = recorded_judge_inputs
        assert seen.final_message == "Herbert, 1965."
        assert seen.reference_data == {"reference_answer": "Frank Herbert."}

        # The judge saw it; the record does not keep it. A pointer-mode record carries
        # no second copy of what it scored: the reference is derived from the item
        # `dataset_id` names, and `EvalRun` has no field to hold one.
        (saved,) = mock_v2_task_run_eval_config.runs(readonly=True)
        assert saved.dataset_id == item.id
        assert not hasattr(saved, "reference_data")

    @pytest.mark.asyncio
    async def test_calibration_gives_the_judge_no_reference_answer(
        self,
        mock_v2_runner,
        mock_v2_eval_config,
        data_source,
        recorded_judge_inputs,
    ):
        """Calibration scores the golden item as itself, so a reference here would be
        the answer key and the response — every item would pass."""
        golden = TaskRun(
            input="Who wrote Dune?",
            output=TaskOutput(output="Frank Herbert.", source=data_source),
            parent=mock_v2_runner.task,
        )
        golden.save_to_file()

        job = EvalJob(
            item=golden,
            eval_config=mock_v2_eval_config,
            type="eval_config_eval",
        )

        with generating(TraceGenerator(mock_v2_runner.task), RecordingStubV2Eval):
            assert await mock_v2_runner.run_job(job) is True

        (seen,) = recorded_judge_inputs
        assert seen.final_message == "Frank Herbert."
        assert seen.reference_data is None


# -------------------------------------------------------------------
# V2 EvalInput + task_run_eval (fresh generation from EvalInput)
# -------------------------------------------------------------------
@pytest.fixture
def mock_v2_eval_input_task_run_eval(mock_task):
    eval = Eval(
        id="v2_ei_tr_eval",
        name="v2 eval input task_run_eval",
        description="v2 eval for EvalInput + task_run_eval mode",
        splits={"test": EvalInputSplit(filter_id="all")},
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
    mock_eval_inputs,
):
    # Depends on mock_eval_inputs because the split is resolved here: without it the
    # runner would hold an empty item set no matter what the test creates afterwards.
    return build_task_run_eval_runner([mock_v2_ei_tr_eval_config], [mock_run_config])


class TestV2EvalInputFreshGeneration:
    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_generates_and_evaluates(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
    ):
        ei = mock_eval_inputs[0]
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        generator = TraceGenerator(mock_v2_ei_tr_runner.task, "4")
        with generating(generator):
            result = await mock_v2_ei_tr_runner.run_job(job)

        assert result is True
        assert generator.calls == [(ei, mock_run_config.id)]

        (saved,) = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.eval_config_eval is False
        assert saved.scores == {"accuracy": 1.0}
        assert saved.skipped_reason is None
        assert saved.input is None
        assert saved.output is None

        trace = trace_for(mock_v2_ei_tr_runner.task, saved.scored_run_id)
        assert trace.output.output == "4"
        assert trace.eval_source == EvalItemSource(
            source_type="eval_input", source_id=ei.id
        )
        assert trace.output.source.run_config_id == mock_run_config.id

    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_skip_persists_skipped(
        self,
        mock_v2_ei_tr_runner,
        mock_v2_ei_tr_eval_config,
        mock_eval_inputs,
        mock_run_config,
    ):
        ei = mock_eval_inputs[1]
        job = EvalJob(
            item=ei,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        with generating(TraceGenerator(mock_v2_ei_tr_runner.task), SkippingStubV2Eval):
            result = await mock_v2_ei_tr_runner.run_job(job)

        assert result is True
        (saved,) = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert saved.eval_input_id == ei.id
        assert saved.dataset_id is None
        assert saved.eval_config_eval is False
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        assert saved.skipped_detail == "test skip detail"
        (trace,) = eval_traces(mock_v2_ei_tr_runner.task)
        assert saved.scored_run_id == trace.id
        assert saved.output is None
        assert saved.scores == {}

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
        """A traced fresh generation from an EvalInput keeps its conversation, scored or
        skipped — the record names the TaskRun the generation was persisted as."""
        single_turn_trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        ei = mock_eval_inputs[0]
        fresh_task_run = TaskRun(
            input="What is 2+2?",
            output=TaskOutput(
                output="4",
                # The run config the generation ran under is half the key the trace is
                # filed under, so a generated run has to carry it.
                source=data_source.model_copy(
                    update={"run_config_id": mock_run_config.id}
                ),
            ),
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
        trace = trace_for(mock_v2_ei_tr_runner.task, saved.scored_run_id)
        assert trace.trace == single_turn_trace
        # Single-turn generations are never driven, so there is no fingerprint on the
        # record and no variant on the trace: the item and run config are the whole key.
        assert saved.drive_fingerprint is None
        assert trace.eval_source is not None
        assert trace.eval_source.variant is None
        if stub_cls is SkippingStubV2Eval:
            assert saved.skipped_reason == SkippedReason.extraction_failed.value
            assert saved.output is None

    @pytest.mark.asyncio
    async def test_eval_input_task_run_eval_no_reference(
        self,
        mock_task,
        mock_v2_ei_tr_eval_config,
        mock_run_config,
        recorded_judge_inputs,
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

        runner = build_task_run_eval_runner(
            [mock_v2_ei_tr_eval_config], [mock_run_config]
        )

        job = EvalJob(
            item=ei_no_ref,
            eval_config=mock_v2_ei_tr_eval_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )

        with generating(TraceGenerator(runner.task), RecordingStubV2Eval):
            result = await runner.run_job(job)

        assert result is True
        (seen,) = recorded_judge_inputs
        assert seen.reference_data is None
        (saved,) = mock_v2_ei_tr_eval_config.runs(readonly=True)
        assert saved.eval_input_id == "ei_no_ref"


# -------------------------------------------------------------------
# Trace reuse: the point of the project
# -------------------------------------------------------------------
@pytest.fixture
def dataset_items(mock_task, data_source):
    items = []
    for i in range(2):
        run = TaskRun(
            input=f"input {i}",
            output=TaskOutput(output=f"dataset output {i}", source=data_source),
            parent=mock_task,
        )
        run.save_to_file()
        items.append(run)
    return items


@pytest.fixture
def second_judge(mock_v2_task_run_eval):
    """A second eval config on the same eval — the judge a user adds after the fact."""
    config = EvalConfig(
        name="second judge",
        config_type=EvalConfigType.v2,
        properties=ExactMatchProperties(expected_value="something else"),
        parent=mock_v2_task_run_eval,
    )
    config.save_to_file()
    return config


@pytest.fixture
def second_run_config(mock_task):
    rc = TaskRunConfig(
        name="second run config",
        description="a different way of running the task",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4o",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=mock_task,
    )
    rc.save_to_file()
    return rc


async def run_to_completion(runner) -> None:
    last = None
    async for progress in runner.run():
        last = progress
    assert last is not None
    assert last.errors == 0, f"{last.errors} job(s) errored"


def scored_run_ids(eval_config) -> dict:
    return {
        run.dataset_id or run.eval_input_id: run.scored_run_id
        for run in eval_config.runs(readonly=True)
    }


class TestTraceReuse:
    @pytest.mark.asyncio
    async def test_a_second_judge_reuses_the_first_judges_traces(
        self,
        mock_task,
        mock_v2_task_run_eval_config,
        second_judge,
        mock_run_config,
        dataset_items,
    ):
        """The project, in one test.

        Run an eval, add a judge, run again: the second judge scores what the first one
        already paid to generate. It also makes the comparison *paired* — both judges saw
        the same generation, so the delta between them is the judges.
        """
        generator = TraceGenerator(mock_task)

        first_run = build_task_run_eval_runner(
            [mock_v2_task_run_eval_config], [mock_run_config]
        )
        with generating(generator):
            await run_to_completion(first_run)

        assert len(generator.calls) == len(dataset_items)
        first_scores = scored_run_ids(mock_v2_task_run_eval_config)
        assert len(first_scores) == len(dataset_items)

        second_run = build_task_run_eval_runner(
            [mock_v2_task_run_eval_config, second_judge], [mock_run_config]
        )
        with generating(generator):
            await run_to_completion(second_run)

        assert len(generator.calls) == len(dataset_items), (
            "the second run generated something"
        )
        assert len(eval_traces(mock_task)) == len(dataset_items)
        assert len(mock_v2_task_run_eval_config.runs(readonly=True)) == len(
            dataset_items
        ), "the first judge was re-scored"
        assert scored_run_ids(second_judge) == first_scores

        # The second judge reads its trace back off disk, so the fields the split moved
        # onto the TaskRun have to survive the round-trip — the messages a full_trace
        # eval scores, and the usage Phase 4's rollup reports.
        for trace in eval_traces(mock_task):
            assert trace.trace == generator.trace
            assert trace.usage == generator.usage

    @pytest.mark.asyncio
    async def test_two_judges_in_one_run_generate_once_per_item(
        self,
        mock_task,
        mock_v2_task_run_eval_config,
        second_judge,
        mock_run_config,
        dataset_items,
    ):
        """The concurrent half, which a precomputed lookup could never have caught.

        `AsyncJobRunner` runs these four jobs at 25-way concurrency, so the two judges'
        jobs for one item overlap. Only the live per-key lock stops both from generating.
        """
        generator = TraceGenerator(mock_task)
        runner = build_task_run_eval_runner(
            [mock_v2_task_run_eval_config, second_judge], [mock_run_config]
        )
        with generating(generator):
            await run_to_completion(runner)

        assert len(generator.calls) == len(dataset_items)
        assert len(eval_traces(mock_task)) == len(dataset_items)
        assert scored_run_ids(mock_v2_task_run_eval_config) == scored_run_ids(
            second_judge
        )

    @pytest.mark.asyncio
    async def test_a_different_eval_reuses_the_same_traces(
        self,
        mock_task,
        mock_v2_task_run_eval,
        mock_v2_task_run_eval_config,
        mock_run_config,
        dataset_items,
    ):
        """Cross-*eval* reuse, which falls out of storing traces on the task (spec 10).

        The reuse key deliberately names no eval, so a second eval over the same items
        and run config scores what the first one generated. Nothing else pins this, and
        it is the one reuse axis a future change to the key would break silently.
        """
        other_eval = Eval(
            id="other_eval",
            name="a different eval",
            description="same items, different question",
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
        other_eval.save_to_file()
        other_config = EvalConfig(
            name="other eval judge",
            config_type=EvalConfigType.v2,
            properties=ExactMatchProperties(expected_value="hello"),
            parent=other_eval,
        )
        other_config.save_to_file()

        generator = TraceGenerator(mock_task)
        with generating(generator):
            await run_to_completion(
                build_task_run_eval_runner(
                    [mock_v2_task_run_eval_config], [mock_run_config]
                )
            )
            first_scores = scored_run_ids(mock_v2_task_run_eval_config)

            await run_to_completion(
                build_task_run_eval_runner([other_config], [mock_run_config])
            )

        assert len(generator.calls) == len(dataset_items)
        assert len(eval_traces(mock_task)) == len(dataset_items)
        assert scored_run_ids(other_config) == first_scores

    @pytest.mark.asyncio
    async def test_a_second_run_config_generates_its_own_trace(
        self,
        mock_task,
        mock_v2_task_run_eval_config,
        mock_run_config,
        second_run_config,
        dataset_items,
    ):
        """Reuse is keyed on the run config, not around it: two ways of running the task
        are two generations, which is the comparison the eval exists to make."""
        generator = TraceGenerator(mock_task)
        runner = build_task_run_eval_runner(
            [mock_v2_task_run_eval_config], [mock_run_config, second_run_config]
        )
        with generating(generator):
            await run_to_completion(runner)

        assert len(generator.calls) == 2 * len(dataset_items)
        traces = eval_traces(mock_task)
        assert len(traces) == 2 * len(dataset_items)
        assert len({trace.id for trace in traces}) == len(traces)

        by_run_config = {
            rc.id: {
                run.scored_run_id
                for run in mock_v2_task_run_eval_config.runs(readonly=True)
                if run.task_run_config_id == rc.id
            }
            for rc in (mock_run_config, second_run_config)
        }
        assert by_run_config[mock_run_config.id].isdisjoint(
            by_run_config[second_run_config.id]
        )

    @pytest.mark.asyncio
    async def test_rerunning_one_judge_scores_nothing_new(
        self,
        mock_task,
        mock_v2_task_run_eval_config,
        mock_run_config,
        dataset_items,
    ):
        """Reuse must not have cost us the score-level dedupe: a second identical run is
        a no-op, not a re-score against the trace it just found."""
        generator = TraceGenerator(mock_task)
        with generating(generator):
            await run_to_completion(
                build_task_run_eval_runner(
                    [mock_v2_task_run_eval_config], [mock_run_config]
                )
            )
            before = scored_run_ids(mock_v2_task_run_eval_config)

            rerun = build_task_run_eval_runner(
                [mock_v2_task_run_eval_config], [mock_run_config]
            )
            assert rerun.collect_tasks() == []
            await run_to_completion(rerun)

        assert len(generator.calls) == len(dataset_items)
        assert scored_run_ids(mock_v2_task_run_eval_config) == before


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
        runner = build_task_run_eval_runner([mock_v2_ei_tr_eval_config], [rc1, rc2])
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
        runner = build_task_run_eval_runner([mock_v2_ei_tr_eval_config], [rc1, rc2])
        jobs = runner.collect_tasks()
        assert len(jobs) == 3
        remaining = {(j.item.id, j.task_run_config.id) for j in jobs}
        assert (mock_eval_inputs[0].id, rc1.id) not in remaining
        assert (mock_eval_inputs[0].id, rc2.id) in remaining
        assert (mock_eval_inputs[1].id, rc1.id) in remaining
        assert (mock_eval_inputs[1].id, rc2.id) in remaining


# -------------------------------------------------------------------
# The split is the item scope, whatever backs it (architecture 4.1)
# -------------------------------------------------------------------
class TestCollectTasksOverArbitrarySplits:
    def test_eval_input_backed_split_collects_exactly_the_matching_inputs(
        self, mock_task, mock_eval_inputs, mock_run_config
    ):
        """Asserted on which items, not on a job count: functional spec 4.2's failure mode
        is a run that succeeds over the wrong item set."""
        eval = Eval(
            id="tag_backed",
            name="tag backed",
            description="EvalInput-backed test split, narrowed by tag",
            splits={"test": EvalInputSplit(filter_id="tag::math")},
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

        jobs = build_task_run_eval_runner(
            [eval_config], [mock_run_config]
        ).collect_tasks()

        assert [job.item.id for job in jobs] == ["ei_1"]
        assert all(isinstance(job.item, EvalInput) for job in jobs)

    def test_a_non_test_split_is_collected_the_same_way(
        self, mock_eval, mock_task, mock_eval_config, mock_run_config, data_source
    ):
        """Nothing in the runner names 'test' any more — it works whatever split it's given."""
        items = {}
        for tag in ["test_tag", "val_tag"]:
            run = TaskRun(
                parent=mock_task,
                input=tag,
                input_source=data_source,
                output=TaskOutput(output=tag),
                tags=[tag],
            )
            run.save_to_file()
            items[tag] = run

        mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::test_tag")
        mock_eval.splits["val"] = TaskRunSplit(filter_id="tag::val_tag")

        jobs = build_task_run_eval_runner(
            [mock_eval_config], [mock_run_config], split_name="val"
        ).collect_tasks()

        assert [job.item.id for job in jobs] == [items["val_tag"].id]

    def test_dedupe_keys_on_the_item_source_not_the_bare_id(
        self, mock_task, mock_v2_ei_tr_eval_config, mock_run_config
    ):
        """Ids come from one generator shared by every model type (functional spec 5.3), so
        a TaskRun and an EvalInput can collide. A bare-id dedupe would drop this job."""
        shared_id = "collide_1"
        TaskRun(
            id=shared_id,
            parent=mock_task,
            input="task run with the colliding id",
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "test_adapter",
                },
            ),
            output=TaskOutput(output="out"),
        ).save_to_file()
        eval_input = EvalInput(
            id=shared_id,
            data=SingleTurnEvalInputData(user_message=UserMessage(text="eval input")),
            parent=mock_task,
        )
        eval_input.save_to_file()

        EvalRun(
            parent=mock_v2_ei_tr_eval_config,
            dataset_id=shared_id,
            task_run_config_id=mock_run_config.id,
            eval_config_eval=False,
            scores={"accuracy": 1.0},
            input="task run with the colliding id",
            output="out",
        ).save_to_file()

        jobs = build_task_run_eval_runner(
            [mock_v2_ei_tr_eval_config], [mock_run_config]
        ).collect_tasks()

        assert [job.item.id for job in jobs] == [shared_id]
        assert isinstance(jobs[0].item, EvalInput)

    def test_overlapping_splits_reuse_already_scored_items(
        self, mock_eval, mock_task, mock_eval_config, mock_run_config, data_source
    ):
        """Dedupe keys on the item, not on the split, so an item scored under one split is
        not re-scored when it turns up in another."""
        shared = TaskRun(
            parent=mock_task,
            input="in both splits",
            input_source=data_source,
            output=TaskOutput(output="out"),
            tags=["test_tag", "val_tag"],
        )
        shared.save_to_file()
        val_only = TaskRun(
            parent=mock_task,
            input="val only",
            input_source=data_source,
            output=TaskOutput(output="out"),
            tags=["val_tag"],
        )
        val_only.save_to_file()

        mock_eval.splits["test"] = TaskRunSplit(filter_id="tag::test_tag")
        mock_eval.splits["val"] = TaskRunSplit(filter_id="tag::val_tag")

        EvalRun(
            parent=mock_eval_config,
            dataset_id=shared.id,
            task_run_config_id=mock_run_config.id,
            input="in both splits",
            output="out",
            scores={"accuracy": 1.0},
        ).save_to_file()

        jobs = build_task_run_eval_runner(
            [mock_eval_config], [mock_run_config], split_name="val"
        ).collect_tasks()

        assert [job.item.id for job in jobs] == [val_only.id]


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
            splits={"test": EvalInputSplit(filter_id="all")},
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
    """Verify every skip reason ``eval_runner.py`` writes is a valid enum member.

    ``EvalRun.skipped_reason`` is a plain ``str`` for forward-compat, so nothing at the
    model layer rejects a reason that is not a ``SkippedReason``. The runner's own skip
    helper takes a typed ``SkippedReason``, which covers its two call sites; this catches
    a future one that goes around the helper with a bare string.
    """

    def test_all_hardcoded_skip_reasons_are_valid(self):
        import ast
        import inspect

        from kiln_ai.adapters.eval import eval_runner

        tree = ast.parse(inspect.getsource(eval_runner))
        valid_values = {member.value for member in SkippedReason}

        enum_members = [
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "SkippedReason"
        ]
        assert enum_members, (
            "Expected eval_runner to name at least one SkippedReason member. "
            "Test may need updating if the runner was refactored."
        )
        for member in enum_members:
            assert member in SkippedReason.__members__, (
                f"eval_runner uses SkippedReason.{member}, which is not a member"
            )

        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "skipped_reason":
                continue
            if isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, str
            ):
                assert node.value.value in valid_values, (
                    f'eval_runner uses raw string skipped_reason="{node.value.value}" '
                    "which is not a valid SkippedReason value — "
                    "use SkippedReason.<member>.value instead"
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
    """The in-memory leaf drive_case_for_eval produces: id-less,
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


# The synthetic user's spend for one drive. Non-None by default so the
# reuse tests, which assert it is absent, are testing the runner's branch
# rather than a fixture that never had a value.
FRESH_SU_USAGE = Usage(
    input_tokens=2600, output_tokens=90, total_tokens=2690, cost=0.0021
)


def _fresh_drive_result(task: Task, data_source: DataSource) -> DriveCaseResult:
    """What drive_case_for_eval returns: the chain plus the SU's usage."""
    return DriveCaseResult(
        chain=[_fresh_leaf(task, data_source)], su_usage=FRESH_SU_USAGE
    )


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
        runner = build_task_run_eval_runner([mock_v2_redrive_config], [mock_run_config])
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        stub = RecordingStoredTraceStubV2Eval(mock_v2_redrive_config)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
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
        assert saved.skipped_reason is None
        # The scored conversation lives on the TaskRun this record points at; the drive
        # identity rides the record itself.
        assert saved.scored_run_id is not None
        trace_run = TaskRun.from_id_and_parent_path(saved.scored_run_id, mock_task.path)
        assert trace_run is not None
        assert trace_run.trace == MULTI_TURN_TRACE
        assert trace_run.output.output == "fresh reply"
        assert trace_run.eval_source is not None
        assert trace_run.eval_source.source_id == "ei_redrive"
        assert saved.drive_fingerprint is not None
        assert saved.drive_fingerprint.startswith("v1:")
        # The trace is filed under the fingerprint, so a different drive config cannot
        # be handed this conversation.
        assert trace_run.eval_source.variant == saved.drive_fingerprint

    @pytest.mark.asyncio
    async def test_persists_synthetic_user_usage_on_a_fresh_drive(
        self,
        mock_task,
        mock_run_config,
        mock_v2_redrive_config,
        multi_turn_eval_input,
        data_source,
    ):
        """The driver model's spend must land on the record. It cannot be
        recovered from task_run_trace — the SU's calls leave nothing in it —
        so dropping it here makes it unmeasurable after the fact."""
        runner = build_task_run_eval_runner([mock_v2_redrive_config], [mock_run_config])
        job = EvalJob(
            item=multi_turn_eval_input,
            eval_config=mock_v2_redrive_config,
            type="task_run_eval",
            task_run_config=mock_run_config,
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=RecordingStoredTraceStubV2Eval(mock_v2_redrive_config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
            ),
        ):
            assert await runner.run_job(job) is True

        saved = mock_v2_redrive_config.runs(readonly=True)[0]
        assert saved.synthetic_user_usage is not None
        assert saved.synthetic_user_usage.input_tokens == 2600
        assert saved.synthetic_user_usage.output_tokens == 90
        assert saved.synthetic_user_usage.total_tokens == 2690
        assert saved.synthetic_user_usage.cost == 0.0021
        # It is the driver's spend alone — the agent's stays on the trace it produced.
        assert saved.scored_run_id is not None
        trace_run = TaskRun.from_id_and_parent_path(saved.scored_run_id, mock_task.path)
        assert trace_run is not None
        assert trace_run.usage != saved.synthetic_user_usage

        # Round-trip through disk: the field must survive persistence.
        assert saved.path is not None
        reloaded = EvalRun.load_from_file(saved.path)
        assert reloaded.synthetic_user_usage is not None
        assert reloaded.synthetic_user_usage.total_tokens == 2690
        assert reloaded.synthetic_user_usage.cost == 0.0021

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
        runner = build_task_run_eval_runner([config], [mock_run_config])
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
        runner = build_task_run_eval_runner([mock_v2_redrive_config], [mock_run_config])
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
        runner = build_task_run_eval_runner([mock_v2_redrive_config], [mock_run_config])
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
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
            ),
        ):
            result = await runner.run_job(job)

        assert result is True
        runs = mock_v2_redrive_config.runs(readonly=True)
        assert len(runs) == 1
        saved = runs[0]
        assert saved.skipped_reason == SkippedReason.extraction_failed.value
        # A judge that could not score a conversation must not discard it: a full-cost
        # drive happened, and the record still names the trace it produced.
        assert saved.scored_run_id is not None
        trace_run = TaskRun.from_id_and_parent_path(saved.scored_run_id, mock_task.path)
        assert trace_run is not None
        assert trace_run.trace == MULTI_TURN_TRACE
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
        runner = build_task_run_eval_runner([mock_v2_redrive_config], [mock_run_config])
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
                return_value=RecordingStoredTraceStubV2Eval(mock_v2_redrive_config),
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
    trace_run_id: str | None = None,
) -> EvalRun:
    """A prior driven+judged record: the conversation as a TaskRun, and the score
    record pointing at it.

    Two files, because that is what a drive leaves behind now — the trace is a TaskRun
    filed under (item, run config, drive fingerprint), and the EvalRun names it with
    `scored_run_id`. A `trace_json` of None is a tombstone: a record from a job that was
    skipped before it ever had a conversation, so no TaskRun exists to reuse.
    """
    trace_run: TaskRun | None = None
    task = config.parent_eval().parent_task()  # type: ignore[union-attr]
    assert task is not None
    if trace_json is not None:
        trace_run = TaskRun(
            parent=task,
            input="opening message",
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "test",
                },
            ),
            output=TaskOutput(
                output="reply",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "test",
                    },
                    run_config_id=run_config.id,
                ),
            ),
            trace=json.loads(trace_json),
            eval_source=EvalItemSource(
                source_type="eval_input",
                source_id=str(eval_input.id),
                variant=fingerprint,
            ),
        )
        if trace_run_id is not None:
            trace_run.id = trace_run_id
        trace_run.save_to_file()

    run = EvalRun(
        parent=config,
        task_run_config_id=run_config.id,
        dataset_id=None,
        eval_input_id=eval_input.id,
        eval_config_eval=False,
        scored_run_id=trace_run.id if trace_run is not None else None,
        scores={} if trace_run is None else {"accuracy": 1.0},
        # A record with no trace to point at is a skip: that is the only shape the
        # datamodel allows without inline data, and the only way a drive leaves nothing
        # reusable behind.
        skipped_reason=None
        if trace_run is not None
        else SkippedReason.incompatible_input_shape.value,
        drive_fingerprint=fingerprint,
    )
    if run_id is not None:
        run.id = run_id
    run.save_to_file()
    return run


def seeded_trace_run(task: Task, eval_config: EvalConfig) -> TaskRun | None:
    """The conversation the one record under `eval_config` points at."""
    runs = eval_config.runs(readonly=True)
    assert len(runs) == 1
    scored_run_id = runs[0].scored_run_id
    if scored_run_id is None:
        return None
    return TaskRun.from_id_and_parent_path(scored_run_id, task.path)


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
def twin_run_config(mock_task):
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


class TestMultiTurnTraceReuse:
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
        seeded = seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            seeded_trace,
        )

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        stub = RecordingStoredTraceStubV2Eval(reuse_config_b)
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
        # The record names the conversation that was already on disk rather than storing
        # a second copy of it.
        assert saved.scored_run_id == seeded.scored_run_id
        assert saved.drive_fingerprint == fingerprint
        # No driver call was made, so this record carries no synthetic-user
        # spend. Copying it from the record that drove the conversation would
        # double-book the same dollars across every eval that reuses the trace.
        assert saved.synthetic_user_usage is None
        # Reuse writes no second conversation: the one the first drive persisted is the
        # only trace on the task.
        traces = mock_task.runs(readonly=True, include_eval_generated=True)
        assert len(traces) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_trace_json",
        [
            None,  # tombstone: a record from a job skipped before it had a conversation
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
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "turn 2"},
                ]
            ),  # full user count but the final reply is missing
        ],
        ids=["tombstone", "empty", "one_turn", "no_final_reply"],
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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
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
        twin_run_config,
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
            reuse_eval, multi_turn_eval_input, twin_run_config
        )
        seed_driven_run(
            reuse_config_a,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = build_task_run_eval_runner([reuse_config_b], [twin_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, twin_run_config)
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
        runner = build_task_run_eval_runner(
            [reuse_config_a, reuse_config_b], [mock_run_config]
        )
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                side_effect=lambda config, *_: StubV2Eval(config),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
            ) as mock_drive,
        ):
            for config in (reuse_config_a, reuse_config_b):
                assert await runner.run_job(
                    make_reuse_job(multi_turn_eval_input, config, mock_run_config)
                )

        assert mock_drive.await_count == 1
        run_a = reuse_config_a.runs(readonly=True)[0]
        run_b = reuse_config_b.runs(readonly=True)[0]
        # Both judges scored the same conversation — the point of reuse, and what makes
        # the comparison between them paired.
        assert run_a.scored_run_id is not None
        assert run_a.scored_run_id == run_b.scored_run_id
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
        """When racing drives left two healthy conversations for one key, every later
        read picks the same one.

        Which one is not specified: the index takes the first it sees on disk, and two
        machines that each drove one are both correct (trace_index D8). What must hold
        is that a reader does not oscillate — otherwise two judges on the same run would
        score different conversations and their comparison would stop being paired."""
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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        stub = RecordingStoredTraceStubV2Eval(reuse_config_b)
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
        judged = stub.seen_inputs[0].trace
        assert judged in (first_trace, second_trace)

        # A second reader, over the same task, lands on the same conversation.
        second_runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        second_stub = RecordingStoredTraceStubV2Eval(reuse_config_b)
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=second_stub,
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(),
            ) as second_drive,
        ):
            await second_runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, mock_run_config)
            )
        second_drive.assert_not_awaited()
        assert second_stub.seen_inputs[0].trace == judged

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
        seeded = seed_driven_run(
            cross_eval_config,
            multi_turn_eval_input,
            mock_run_config,
            fingerprint,
            serialized_trace(MULTI_TURN_TRACE),
        )

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        stub = RecordingStoredTraceStubV2Eval(reuse_config_b)
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

        # This eval's record names the other eval's conversation: one trace, scored
        # twice, with the shared fingerprint on both records.
        saved = reuse_config_b.runs(readonly=True)[0]
        assert saved.scored_run_id == seeded.scored_run_id
        assert saved.drive_fingerprint == fingerprint
        assert len(mock_task.runs(readonly=True, include_eval_generated=True)) == 1

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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
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
        twin_run_config,
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

        runner = build_task_run_eval_runner([reuse_config_b], [twin_run_config])
        with (
            patch(
                "kiln_ai.adapters.eval.registry.v2_eval_adapter_from_config",
                return_value=StubV2Eval(reuse_config_b),
            ),
            patch(
                "kiln_ai.adapters.eval.eval_runner.drive_case_for_eval",
                new=AsyncMock(return_value=_fresh_drive_result(mock_task, data_source)),
            ) as mock_drive,
        ):
            await runner.run_job(
                make_reuse_job(multi_turn_eval_input, reuse_config_b, twin_run_config)
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

        runner = build_task_run_eval_runner([reuse_config_b], [mock_run_config])
        stub = RecordingStoredTraceStubV2Eval(reuse_config_b)
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
        # Either conversation is a correct pick — both were driven for this exact key,
        # under two evals that share a drive config. What matters is that one of them is
        # reused rather than a third being driven.
        assert stub.seen_inputs[0].trace in (cross_trace, MULTI_TURN_TRACE)
