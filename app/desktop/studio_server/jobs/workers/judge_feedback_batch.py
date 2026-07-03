from __future__ import annotations

import asyncio

from app.desktop.git_sync.save_context import save_context_for_project
from kiln_ai.adapters.eval.judge_feedback_batch_runner import (
    JudgeFeedbackBatchItemError,
    JudgeFeedbackBatchRunner,
)
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.usage import Usage
from kiln_server.task_api import task_from_id
from pydantic import BaseModel, Field

from ...judge_feedback_batch_api import (
    eval_config_from_id,
    judge_feedback_batch_from_id,
    validate_judge_eval,
    validate_run_config_id,
)
from ..models import (
    JOB_TRANSIENT_ERROR_MAX_RETRIES,
    JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS,
    JobContext,
    JobWorker,
)


class JudgeFeedbackBatchJobParams(BaseModel):
    """Run an existing judge feedback batch as a background job.

    The batch config is created first via `POST .../judge_feedback_batches` (which
    returns its id); the job just runs it — mirroring how `EvalJobParams` runs a
    pre-existing eval. Because the id is carried in params (not minted inside
    run()), it's retrievable via `GET /api/jobs/{id}` even if the run fails.
    """

    project_id: str = Field(description="The ID of the project the task belongs to.")
    task_id: str = Field(description="The ID of the task the batch belongs to.")
    judge_feedback_batch_id: str = Field(
        description="The ID of the judge feedback batch to run. Create it first via "
        "POST /api/projects/{project_id}/tasks/{task_id}/judge_feedback_batches."
    )
    concurrency: int | None = Field(
        default=None,
        ge=1,
        description="Max items judged in parallel by the runner. Leave null to use the runner's "
        "default (5 when generating fresh outputs, 25 when judging existing ones).",
    )


class JudgeFeedbackBatchJobResult(BaseModel):
    """Aggregate summary of a judge feedback batch run.

    The bulky per-item arrays (judged_runs / failing_runs, each with the judge's
    feedback) are NOT returned here — they're persisted as children of the batch.
    Use `judge_feedback_batch_id` to fetch them via
    `GET /judge_feedback_batches/{id}/runs` (pair them across runs by task_run_id
    for a val gate). The scores/usage/latency below mirror the synchronous run
    response's aggregate fields.
    """

    judge_feedback_batch_id: str = Field(
        description="The ID of the judge feedback batch this job ran (echoes the id from params). "
        "Fetch its per-item runs (with feedback) via GET /judge_feedback_batches/{id}/runs."
    )
    num_judged: int = Field(
        description="How many items were examined (judged) during the run."
    )
    failing_count: int = Field(
        description="How many judged items failed the judge (scored below the threshold)."
    )
    train_set_size: int = Field(
        description="Total number of dataset items matching the target tags (before max_samples)."
    )
    hit_cap: bool = Field(
        description="True if coverage was capped: max_samples was reached before "
        "stop_after_failures, or the matching set exceeded max_samples."
    )
    error_count: int = Field(
        description="Number of per-item judge/save errors collected during the run. The messages "
        "are in the job's error log (GET /api/jobs/{id}/errors)."
    )
    mean_normalized_scores: dict[str, float] = Field(
        description="Mean normalized (0-1, higher = better) score per output-score dimension over "
        "the judged items."
    )
    mean_normalized_score: float | None = Field(
        default=None,
        description="Mean of mean_normalized_scores across dimensions (null if nothing was judged).",
    )
    total_usage: Usage | None = Field(
        default=None,
        description="Summed token usage, cost (USD), and LLM latency for generating the judged "
        "outputs (generate_outputs mode only; null when existing outputs were judged).",
    )
    mean_cost: float | None = Field(
        default=None,
        description="Mean generation cost (USD) per judged item, over items that reported cost "
        "(generate_outputs mode only; null otherwise).",
    )
    mean_latency_ms: float | None = Field(
        default=None,
        description="Mean generation LLM latency (ms) per judged item, over items that reported "
        "latency (generate_outputs mode only; null otherwise).",
    )


class JudgeFeedbackBatchJobProperties(BaseModel):
    """Static, descriptive info about a judge feedback batch job, for the jobs UI.

    Mirrors EvalJobProperties: which judge (eval config) scores the items, the run
    config (present only when generating fresh outputs), and the batch's sampling
    scope. Model/provider fields carry raw ids; the frontend resolves them to
    display names with its model-name helpers.
    """

    batch_name: str
    eval_name: str
    judge_name: str
    judge_algorithm: str
    judge_model_name: str
    judge_model_provider: str
    generate_outputs: bool
    run_config_name: str
    run_config_model_name: str
    run_config_model_provider: str
    target_tags: list[str]
    max_samples: int
    stop_after_failures: int | None = None


class JudgeFeedbackBatchJobWorker(
    JobWorker[JudgeFeedbackBatchJobParams, JudgeFeedbackBatchJobResult]
):
    """Background worker that runs a pre-existing judge feedback batch.

    Wraps `JudgeFeedbackBatchRunner` unchanged (mirrors `EvalJobWorker` wrapping
    `EvalRunner`). The batch config is created first via the synchronous create
    endpoint; this job only runs it (the id is in params). Making the judge run
    job-backed lets an agent fire many gates at once and `POST /api/jobs/wait` on
    all of them together, instead of blocking on each synchronous call serially.
    The runner streams progress per judged chunk. `supports_pause` stays False and
    `compute_state` keeps its default (None) for now — the runner already reuses
    cached child runs, so a re-run is idempotent, but deriving progress from disk
    is left as a follow-up.
    """

    type_name = "judge_feedback_batch"
    params_model = JudgeFeedbackBatchJobParams
    result_model = JudgeFeedbackBatchJobResult
    properties_model = JudgeFeedbackBatchJobProperties
    supports_pause = False

    async def describe(
        self, params: JudgeFeedbackBatchJobParams
    ) -> JudgeFeedbackBatchJobProperties:
        # Loads entities off disk; offload the blocking IO to a thread so create()
        # stays responsive (mirrors EvalJobWorker.describe).
        return await asyncio.to_thread(self._describe_sync, params)

    def _describe_sync(
        self, params: JudgeFeedbackBatchJobParams
    ) -> JudgeFeedbackBatchJobProperties:
        task = task_from_id(params.project_id, params.task_id)
        batch = judge_feedback_batch_from_id(
            params.project_id, params.task_id, params.judge_feedback_batch_id, task=task
        )
        eval_config = eval_config_from_id(task, batch.eval_config_id)
        eval = eval_config.parent_eval()

        # The run config only matters when generating fresh outputs; and only the
        # kiln_agent variant carries a model. Leave the fields blank otherwise so
        # the judge/batch info still renders.
        run_config_name = ""
        run_config_model_name = ""
        run_config_model_provider = ""
        if batch.run_config_id is not None:
            run_config = next(
                (
                    rc
                    for rc in task.run_configs(readonly=True)
                    if rc.id == batch.run_config_id
                ),
                None,
            )
            if run_config is not None:
                run_config_name = run_config.name
                run_config_properties = run_config.run_config_properties
                if isinstance(run_config_properties, KilnAgentRunConfigProperties):
                    run_config_model_name = run_config_properties.model_name
                    run_config_model_provider = (
                        run_config_properties.model_provider_name
                    )

        return JudgeFeedbackBatchJobProperties(
            batch_name=batch.name,
            eval_name=eval.name if eval is not None else "",
            judge_name=eval_config.name,
            judge_algorithm=eval_config.config_type.value,
            judge_model_name=eval_config.model_name,
            judge_model_provider=eval_config.model_provider,
            generate_outputs=batch.generate_outputs,
            run_config_name=run_config_name,
            run_config_model_name=run_config_model_name,
            run_config_model_provider=run_config_model_provider,
            target_tags=list(batch.target_tags or []),
            max_samples=batch.max_samples,
            stop_after_failures=batch.stop_after_failures,
        )

    async def run(
        self, params: JudgeFeedbackBatchJobParams, ctx: JobContext
    ) -> JudgeFeedbackBatchJobResult:
        # Load the pre-created batch config (the create endpoint already persisted it under the
        # git-sync write lock), then run it. Nothing is created here, so there is no config write to
        # wrap — only the runner's per-item child writes, which it wraps in its own save_context.
        task = task_from_id(params.project_id, params.task_id)
        judge_feedback_batch = judge_feedback_batch_from_id(
            params.project_id, params.task_id, params.judge_feedback_batch_id, task=task
        )
        eval_config = eval_config_from_id(task, judge_feedback_batch.eval_config_id)
        validate_judge_eval(eval_config, judge_feedback_batch.generate_outputs)
        validate_run_config_id(task, judge_feedback_batch.run_config_id)

        runner = JudgeFeedbackBatchRunner(
            judge_feedback_batch,
            eval_config,
            save_context=save_context_for_project(
                params.project_id,
                context=f"judge feedback batch {params.judge_feedback_batch_id}",
            ),
            max_retries=JOB_TRANSIENT_ERROR_MAX_RETRIES,
            retry_delay=JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS,
        )

        async def report_progress(
            num_judged: int, error_count: int, planned_total: int
        ) -> None:
            # num_judged counts every attempted item (errors included), so subtract the errors to
            # keep success and error disjoint — the job progress contract is processed = success +
            # error. Otherwise an errored item is counted in both and the bar overshoots 100%.
            await ctx.report_progress(
                success=num_judged - error_count,
                error=error_count,
                total=planned_total,
            )

        async def report_item_error(item_error: JudgeFeedbackBatchItemError) -> None:
            # Write each per-item error to the job's error log the moment it happens (not batched to
            # the end), so "View Errors" shows messages live — the streamed progress error count
            # gates the button mid-run, and this keeps the log in step with it.
            await ctx.report_error(
                item_error.error,
                dataset_id=item_error.task_run_id,
                run_config_id=judge_feedback_batch.run_config_id,
            )

        result = await runner.run(
            concurrency=params.concurrency,
            progress_callback=report_progress,
            error_callback=report_item_error,
        )

        # Final snapshot against the planned (capped) count = min(train_set_size, max_samples), the
        # number of items the run judges in gate mode (so success + error reaches total on full
        # coverage). In train-signal mode the run stops early once enough failures are found, so the
        # bar can legitimately end below total — the job still succeeds. success excludes errors to
        # keep success + error <= total (see report_progress above).
        error_count = len(result.errors)
        planned_total = min(result.train_set_size, judge_feedback_batch.max_samples)
        await ctx.report_progress(
            success=result.num_judged - error_count,
            error=error_count,
            total=planned_total or result.num_judged,
        )

        return JudgeFeedbackBatchJobResult(
            judge_feedback_batch_id=params.judge_feedback_batch_id,
            num_judged=result.num_judged,
            failing_count=result.failing_count,
            train_set_size=result.train_set_size,
            hit_cap=result.hit_cap,
            error_count=error_count,
            mean_normalized_scores=result.mean_normalized_scores,
            mean_normalized_score=result.mean_normalized_score,
            total_usage=result.total_usage,
            mean_cost=result.mean_cost,
            mean_latency_ms=result.mean_latency_ms,
        )
