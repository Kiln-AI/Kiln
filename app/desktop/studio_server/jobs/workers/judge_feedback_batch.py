from __future__ import annotations

from app.desktop.git_sync.save_context import save_context_for_project
from kiln_ai.adapters.eval.judge_feedback_batch_runner import JudgeFeedbackBatchRunner
from kiln_ai.datamodel.usage import Usage
from kiln_server.task_api import task_from_id
from pydantic import BaseModel

from ...judge_feedback_batch_api import (
    CreateJudgeFeedbackBatchRequest,
    _build_judge_feedback_batch,
    eval_config_from_id,
    validate_judge_eval,
    validate_run_config_id,
)
from ..models import JobContext, JobWorker


class JudgeFeedbackBatchJobParams(CreateJudgeFeedbackBatchRequest):
    """Create-and-run a judge feedback batch as a background job.

    Inherits every CreateJudgeFeedbackBatchRequest field (and its validation) and
    adds the project/task scope, so the body is the same as the synchronous
    create-and-run endpoint plus project_id/task_id.
    """

    project_id: str
    task_id: str


class JudgeFeedbackBatchJobResult(BaseModel):
    """Aggregate summary of a judge feedback batch run.

    The bulky per-item arrays (judged_runs / failing_runs, each with the judge's
    feedback) are NOT returned here — they're persisted as children of the batch.
    Use `judge_feedback_batch_id` to fetch them via
    `GET /judge_feedback_batches/{id}/runs` (pair them across runs by task_run_id
    for a val gate). The scores/usage/latency below mirror the synchronous run
    response's aggregate fields.
    """

    judge_feedback_batch_id: str
    num_judged: int
    failing_count: int
    train_set_size: int
    hit_cap: bool
    error_count: int
    mean_normalized_scores: dict[str, float]
    mean_normalized_score: float | None = None
    total_usage: Usage | None = None
    mean_cost: float | None = None
    mean_latency_ms: float | None = None


class JudgeFeedbackBatchJobWorker(
    JobWorker[JudgeFeedbackBatchJobParams, JudgeFeedbackBatchJobResult]
):
    """Background worker that creates and runs a judge feedback batch.

    Wraps `JudgeFeedbackBatchRunner` unchanged (mirrors `EvalJobWorker` wrapping
    `EvalRunner`). Making the judge run job-backed lets an agent fire many gates
    at once and `POST /api/jobs/wait` on all of them together, instead of blocking
    on each synchronous call serially. The runner is single-shot (no incremental
    progress), so progress is reported once on completion and `supports_pause`
    stays False. Re-running creates a fresh batch, so there's nothing to resume —
    `compute_state` keeps its default (None).
    """

    type_name = "judge_feedback_batch"
    params_model = JudgeFeedbackBatchJobParams
    result_model = JudgeFeedbackBatchJobResult
    supports_pause = False

    async def run(
        self, params: JudgeFeedbackBatchJobParams, ctx: JobContext
    ) -> JudgeFeedbackBatchJobResult:
        # params IS a CreateJudgeFeedbackBatchRequest (plus project/task scope), so
        # the existing validators + builder accept it directly.
        task = task_from_id(params.project_id, params.task_id)
        eval_config = eval_config_from_id(task, params.eval_config_id)
        validate_judge_eval(eval_config, params.generate_outputs)
        validate_run_config_id(task, params.run_config_id)

        judge_feedback_batch = _build_judge_feedback_batch(task, params)
        judge_feedback_batch.save_to_file()
        batch_id = judge_feedback_batch.id
        if batch_id is None:
            raise ValueError("Judge feedback batch was not assigned an id")

        runner = JudgeFeedbackBatchRunner(
            judge_feedback_batch,
            eval_config,
            save_context=save_context_for_project(
                params.project_id,
                context=f"judge feedback batch {judge_feedback_batch.id}",
            ),
        )
        result = await runner.run()

        # Single-shot runner: surface any per-item judge/save errors to the job's
        # error log, then report final progress once (0 -> done).
        for item_error in result.errors:
            await ctx.report_error(
                item_error.error,
                dataset_id=item_error.task_run_id,
                run_config_id=params.run_config_id,
            )
        await ctx.report_progress(
            success=result.num_judged,
            error=len(result.errors),
            total=result.train_set_size or result.num_judged,
        )

        return JudgeFeedbackBatchJobResult(
            judge_feedback_batch_id=batch_id,
            num_judged=result.num_judged,
            failing_count=result.failing_count,
            train_set_size=result.train_set_size,
            hit_cap=result.hit_cap,
            error_count=len(result.errors),
            mean_normalized_scores=result.mean_normalized_scores,
            mean_normalized_score=result.mean_normalized_score,
            total_usage=result.total_usage,
            mean_cost=result.mean_cost,
            mean_latency_ms=result.mean_latency_ms,
        )
