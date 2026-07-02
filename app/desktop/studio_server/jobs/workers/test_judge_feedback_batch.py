from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
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
def batch(task, eval_config, run_config):
    """A pre-created judge feedback batch on disk — the job runs an existing one."""
    batch = JudgeFeedbackBatch(
        id="batch1",
        name="Test Batch",
        target_tags=["train_set"],
        eval_config_id="eval_config1",
        run_config_id="run_config1",
        generate_outputs=True,
        max_samples=50,
        parent=task,
    )
    batch.save_to_file()
    return batch


@pytest.fixture
def params(batch):
    return JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        judge_feedback_batch_id=batch.id,
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
    async def fake_run(
        self, concurrency=None, progress_callback=None, error_callback=None
    ) -> JudgeFeedbackBatchRunResult:
        # Mimic the real runner: surface each per-item error live via error_callback, then stream one
        # progress tick before returning, so the worker's live error + progress wiring is exercised.
        if error_callback is not None:
            for item_error in result.errors:
                await error_callback(item_error)
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


async def test_run_loads_existing_batch_and_maps_result(
    resolve_project, task, eval_config, run_config, batch, params
):
    ctx = _FakeCtx()
    with _stub_runner(_fake_result()):
        result = await JudgeFeedbackBatchJobWorker().run(params, ctx)

    assert isinstance(result, JudgeFeedbackBatchJobResult)
    # The job runs the PRE-EXISTING batch named in params; the id round-trips into the result.
    assert result.judge_feedback_batch_id == batch.id
    assert result.num_judged == 5
    assert result.failing_count == 2
    assert result.train_set_size == 10
    assert result.hit_cap is False
    assert result.error_count == 1
    assert result.mean_normalized_scores == {"accuracy": 0.8}
    assert result.mean_normalized_score == 0.8
    assert result.mean_cost == 0.01
    assert result.mean_latency_ms == 120.0


@pytest.mark.parametrize("concurrency", [None, 3, 25])
async def test_run_forwards_concurrency_to_runner(
    resolve_project, task, eval_config, run_config, batch, concurrency
):
    # The job's concurrency param (None -> runner default) flows straight to runner.run.
    received: dict[str, int | None] = {}

    async def fake_run(
        self, concurrency=None, progress_callback=None, error_callback=None
    ) -> JudgeFeedbackBatchRunResult:
        received["concurrency"] = concurrency
        return _fake_result()

    params = JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        judge_feedback_batch_id=batch.id,
        concurrency=concurrency,
    )
    ctx = _FakeCtx()
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
        await JudgeFeedbackBatchJobWorker().run(params, ctx)

    assert received["concurrency"] == concurrency


@pytest.mark.parametrize("concurrency", [0, -1])
def test_concurrency_below_one_rejected(concurrency):
    # concurrency must be >= 1: Pydantic rejects invalid input up front (422) rather than
    # relying on the runner to clamp it.
    with pytest.raises(ValidationError):
        JudgeFeedbackBatchJobParams(
            project_id="project1",
            task_id="task1",
            judge_feedback_batch_id="batch1",
            concurrency=concurrency,
        )


async def test_run_missing_batch_raises(resolve_project, task, eval_config):
    # No batch persisted for this id -> the run fails cleanly (the registry marks the job failed).
    ctx = _FakeCtx()
    params = JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        judge_feedback_batch_id="does_not_exist",
    )
    with pytest.raises(HTTPException) as exc_info:
        await JudgeFeedbackBatchJobWorker().run(params, ctx)
    assert exc_info.value.status_code == 404


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
    # max_samples) = min(10, 50) = 10. success excludes errors so success + error
    # stays <= total: 5 judged, 1 errored -> success=4, error=1, total=10.
    assert len(ctx.progress) >= 2
    assert ctx.progress[-1] == (4, 1, 10)


async def test_run_progress_total_is_capped_at_max_samples(
    resolve_project, task, eval_config, run_config
):
    """When train_set_size exceeds max_samples, progress totals against the capped
    count (max_samples), not the full matching set — so a fully-judged run reads
    as 100% rather than stalling at max_samples/train_set_size."""
    capped_batch = JudgeFeedbackBatch(
        id="batch_capped",
        name="Capped Batch",
        target_tags=["train_set"],
        eval_config_id="eval_config1",
        run_config_id="run_config1",
        generate_outputs=True,
        max_samples=20,
        parent=task,
    )
    capped_batch.save_to_file()
    params = JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        judge_feedback_batch_id=capped_batch.id,
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
    resolve_project, task, eval_config, run_config, batch, params
):
    props = await JudgeFeedbackBatchJobWorker().describe(params)

    # Derived from the persisted batch, not from params.
    assert props.batch_name == "Test Batch"
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


async def test_describe_judge_only_mode_leaves_run_config_blank(
    resolve_project, task, eval_config, run_config
):
    # Judge-only mode (generate_outputs=False, no run_config_id): the run-config display fields are
    # left blank, but the judge/eval/batch info still resolves.
    judge_only_batch = JudgeFeedbackBatch(
        id="batch_judge_only",
        name="Judge Only Batch",
        target_tags=["train_set"],
        eval_config_id="eval_config1",
        generate_outputs=False,
        parent=task,
    )
    judge_only_batch.save_to_file()
    params = JudgeFeedbackBatchJobParams(
        project_id="project1",
        task_id="task1",
        judge_feedback_batch_id=judge_only_batch.id,
    )
    props = await JudgeFeedbackBatchJobWorker().describe(params)

    assert props.generate_outputs is False
    assert props.run_config_name == ""
    assert props.run_config_model_name == ""
    assert props.run_config_model_provider == ""
    assert props.judge_name == "Test Eval Config"
    assert props.eval_name == "Test Eval"
