from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from app.desktop.studio_server.jobs.workers.judge_feedback_batch import (
    JudgeFeedbackBatchJobParams,
    JudgeFeedbackBatchJobResult,
    JudgeFeedbackBatchJobWorker,
)
from kiln_ai.adapters.eval.judge_feedback_batch_runner import (
    JudgeFeedbackBatchItemError,
    JudgeFeedbackBatchRunResult,
)
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    Project,
    Task,
    TaskOutputRatingType,
)
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalOutputScore
from kiln_ai.datamodel.judge_feedback_batch import JudgeFeedbackBatch
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import StructuredOutputMode, TaskRunConfig


@pytest.fixture
def project(tmp_path):
    project = Project(
        id="project1", name="Test Project", path=tmp_path / "project.kiln"
    )
    project.save_to_file()
    return project


@pytest.fixture
def task(project):
    task = Task(
        id="task1",
        name="Test Task",
        description="test",
        instruction="do the thing",
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def eval(task):
    eval = Eval(
        id="eval1",
        name="Test Eval",
        description="test",
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
        output_scores=[
            EvalOutputScore(
                name="Accuracy",
                instruction="Check accuracy",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        parent=task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def eval_config(eval):
    eval_config = EvalConfig(
        id="eval_config1",
        name="Test Eval Config",
        model_name="gpt-4",
        model_provider="openai",
        properties={"eval_steps": ["step1"]},
        parent=eval,
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def run_config(task):
    run_config = TaskRunConfig(
        id="run_config1",
        name="Test Run Config",
        description="test",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=task,
    )
    run_config.save_to_file()
    return run_config


@pytest.fixture
def params():
    return JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        target_tags=["train_set"],
        eval_config_id="eval_config1",
        run_config_id="run_config1",
        generate_outputs=True,
        max_samples=50,
    )


@pytest.fixture
def resolve_project(project):
    """Make the entity helpers resolve the on-disk project by id (task_from_id
    binds project_from_id into kiln_server.task_api)."""
    with patch("kiln_server.task_api.project_from_id", return_value=project):
        yield project


class _FakeCtx:
    """Records report_progress / report_error calls so we can assert on them."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, dict]] = []
        self.progress: list[tuple[int, int, int | None]] = []

    async def report_error(self, error_message: str, **extra) -> None:
        self.errors.append((error_message, extra))

    async def report_progress(
        self, success: int, error: int = 0, total: int | None = None, message=None
    ) -> None:
        self.progress.append((success, error, total))


def _fake_result() -> JudgeFeedbackBatchRunResult:
    return JudgeFeedbackBatchRunResult(
        failing_runs=[],
        judged_runs=[],
        num_judged=5,
        failing_count=2,
        train_set_size=10,
        hit_cap=False,
        errors=[JudgeFeedbackBatchItemError(task_run_id="tr1", error="boom")],
        mean_normalized_scores={"accuracy": 0.8},
        mean_normalized_score=0.8,
        total_usage=None,
        mean_cost=0.01,
        mean_latency_ms=120.0,
    )


@contextmanager
def _stub_runner(result: JudgeFeedbackBatchRunResult):
    async def fake_run(self, progress_callback=None) -> JudgeFeedbackBatchRunResult:
        # Mimic the real runner streaming one progress tick before returning, so
        # the worker's live-progress wiring is exercised.
        if progress_callback is not None:
            planned = min(result.train_set_size, self.judge_feedback_batch.max_samples)
            await progress_callback(result.num_judged, len(result.errors), planned)
        return result

    with (
        patch(
            "kiln_ai.adapters.eval.judge_feedback_batch_runner.JudgeFeedbackBatchRunner.run",
            new=fake_run,
        ),
        patch(
            "app.desktop.studio_server.jobs.workers.judge_feedback_batch.save_context_for_project",
            return_value=None,
        ),
    ):
        yield


async def test_run_creates_batch_and_maps_result(
    resolve_project, task, eval_config, run_config, params
):
    ctx = _FakeCtx()
    with _stub_runner(_fake_result()):
        result = await JudgeFeedbackBatchJobWorker().run(params, ctx)

    assert isinstance(result, JudgeFeedbackBatchJobResult)
    assert result.num_judged == 5
    assert result.failing_count == 2
    assert result.train_set_size == 10
    assert result.hit_cap is False
    assert result.error_count == 1
    assert result.mean_normalized_scores == {"accuracy": 0.8}
    assert result.mean_normalized_score == 0.8
    assert result.mean_cost == 0.01
    assert result.mean_latency_ms == 120.0

    # The job created + persisted a batch under the task; its id round-trips.
    batch = JudgeFeedbackBatch.from_id_and_parent_path(
        result.judge_feedback_batch_id, task.path
    )
    assert batch is not None
    assert batch.target_tags == ["train_set"]
    assert batch.eval_config_id == "eval_config1"
    assert batch.generate_outputs is True


async def test_run_reports_progress_and_per_item_errors(
    resolve_project, task, eval_config, run_config, params
):
    ctx = _FakeCtx()
    with _stub_runner(_fake_result()):
        await JudgeFeedbackBatchJobWorker().run(params, ctx)

    # Per-item judge error surfaced to the job error log, keyed by the item.
    assert len(ctx.errors) == 1
    msg, extra = ctx.errors[0]
    assert msg == "boom"
    assert extra["dataset_id"] == "tr1"
    assert extra["run_config_id"] == "run_config1"

    # Progress streams per chunk (via the callback) and a final snapshot is
    # reported. Total is the planned (capped) count = min(train_set_size,
    # max_samples) = min(10, 50) = 10, so success can reach total on full
    # coverage (success=num_judged, error=len(errors), total=planned).
    assert len(ctx.progress) >= 2
    assert ctx.progress[-1] == (5, 1, 10)


async def test_run_progress_total_is_capped_at_max_samples(
    resolve_project, task, eval_config, run_config
):
    """When train_set_size exceeds max_samples, progress totals against the capped
    count (max_samples), not the full matching set — so a fully-judged run reads
    as 100% rather than stalling at max_samples/train_set_size."""
    params = JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        target_tags=["train_set"],
        eval_config_id="eval_config1",
        run_config_id="run_config1",
        generate_outputs=True,
        max_samples=20,
    )
    result = JudgeFeedbackBatchRunResult(
        failing_runs=[],
        judged_runs=[],
        num_judged=20,
        failing_count=0,
        train_set_size=200,
        hit_cap=True,
        errors=[],
    )
    ctx = _FakeCtx()
    with _stub_runner(result):
        await JudgeFeedbackBatchJobWorker().run(params, ctx)

    # planned = min(200, 20) = 20, and all 20 were judged -> success == total.
    success, error, total = ctx.progress[-1]
    assert (success, error, total) == (20, 0, 20)


async def test_describe_publishes_properties(
    resolve_project, task, eval_config, run_config, params
):
    props = await JudgeFeedbackBatchJobWorker().describe(params)

    assert props.batch_name  # generated or provided, never empty
    assert props.eval_name == "Test Eval"
    assert props.judge_name == "Test Eval Config"
    assert props.judge_model_name == "gpt-4"
    assert props.judge_model_provider == "openai"
    assert props.generate_outputs is True
    # generate_outputs mode: the run config is resolved for display.
    assert props.run_config_name == "Test Run Config"
    assert props.run_config_model_name == "gpt-4"
    assert props.target_tags == ["train_set"]
    assert props.max_samples == 50
