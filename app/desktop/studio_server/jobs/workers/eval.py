from __future__ import annotations

import asyncio

from app.desktop.git_sync.save_context import save_context_for_project
from kiln_ai.adapters.eval.eval_runner import EvalJob, EvalRunner
from kiln_ai.datamodel.dataset_filters import dataset_filter_from_id
from kiln_ai.datamodel.eval import Eval, EvalConfig
from kiln_ai.datamodel.task import Task
from kiln_ai.utils.async_job_runner import AsyncJobRunnerObserver
from pydantic import BaseModel

from ...eval_api import eval_config_from_id, task_run_config_from_id
from ..models import JobContext, JobDerivedState, JobWorker


class _EvalErrorLogObserver(AsyncJobRunnerObserver[EvalJob]):
    """Writes each failed dataset item's exception to the job's error log.

    EvalRunner's Progress only carries an error COUNT; without this the
    /api/jobs/{id}/errors endpoint would report "no errors" even when every
    item failed. The observer fires once per item, only after retries are
    exhausted (a final failure), so it logs real failures, not transient retries.
    """

    def __init__(self, ctx: JobContext) -> None:
        self._ctx = ctx

    async def on_error(self, job: EvalJob, error: Exception) -> None:
        await self._ctx.report_error(
            str(error) or error.__class__.__name__,
            dataset_id=job.item.id,
            run_config_id=job.task_run_config.id if job.task_run_config else None,
        )


class EvalJobParams(BaseModel):
    project_id: str
    task_id: str
    eval_id: str
    eval_config_id: str
    run_config_id: str


class EvalJobResult(BaseModel):
    total: int
    success: int
    error: int


class EvalJobWorker(JobWorker[EvalJobParams, EvalJobResult]):
    """Background worker that runs an eval against a single run config.

    Wraps the existing EvalRunner unchanged. Idempotent: EvalRunner excludes
    already-run (eval_config, run_config, dataset) triples, so a paused-then-
    resumed (or re-triggered) job skips completed items and writes no duplicate
    EvalRun entities — hence supports_pause = True.
    """

    type_name = "eval"
    params_model = EvalJobParams
    result_model = EvalJobResult
    supports_pause = True

    async def compute_state(self, params: EvalJobParams) -> JobDerivedState:
        # _compute_state_sync loads entities and enumerates runs/ directories
        # (os.scandir + open/read/json.loads per child) synchronously. The
        # registry awaits this on the event loop, so offload the blocking IO to
        # a thread to keep progress/SSE updates flowing for large eval sets.
        return await asyncio.to_thread(self._compute_state_sync, params)

    def _compute_state_sync(self, params: EvalJobParams) -> JobDerivedState:
        eval_config = eval_config_from_id(
            params.project_id,
            params.task_id,
            params.eval_id,
            params.eval_config_id,
        )
        eval, task = self._eval_and_task(eval_config)

        # The eval-set filter defines the universe of dataset items in scope.
        # EvalRunner only works items that BOTH pass this filter AND lack a
        # matching EvalRun, so progress must be measured against this set.
        filter = dataset_filter_from_id(eval.eval_set_filter_id)
        in_filter_ids = {
            task_run.id for task_run in task.runs(readonly=True) if filter(task_run)
        }
        total = len(in_filter_ids)

        # Count only scored items that are still in the filter set. Items that
        # were scored but later drifted out of the filter must not be counted,
        # or success/is_complete would overcount and a resume could short-circuit
        # to succeeded while real work remains.
        scored_ids = {
            run.dataset_id
            for run in eval_config.runs(readonly=True)
            if run.task_run_config_id == params.run_config_id
        }
        success = len(scored_ids & in_filter_ids)

        # error is left None: failed items leave no EvalRun to count, so they
        # are not derivable from disk. The registry keeps the live error count
        # reported during run() rather than resetting it to 0 on reconcile.
        return JobDerivedState(
            total=total,
            success=success,
            is_complete=success >= total,
        )

    async def run(self, params: EvalJobParams, ctx: JobContext) -> EvalJobResult:
        # Baseline: items already scored (and still in-filter) before this run.
        # EvalRunner only works the unfinished remainder, so its Progress counts
        # are relative to that remainder. We add the baseline back so progress
        # and the returned result are reported against the FULL eval-set size,
        # not just the work left for this run.
        baseline = await self.compute_state(params)
        baseline_success = baseline.success

        eval_runner = self._build_eval_runner(params)

        success = baseline_success
        total = baseline.total if baseline.total is not None else baseline_success
        error = 0
        async for progress in eval_runner.run(observers=[_EvalErrorLogObserver(ctx)]):
            # progress.total = full - baseline_success (the unfinished remainder),
            # so baseline_success + progress.total = the full eval-set size.
            success = baseline_success + progress.complete
            total = baseline_success + progress.total
            error = progress.errors
            await ctx.report_progress(
                success=success,
                error=error,
                total=total,
            )

        return EvalJobResult(total=total, success=success, error=error)

    def _build_eval_runner(self, params: EvalJobParams) -> EvalRunner:
        eval_config = eval_config_from_id(
            params.project_id,
            params.task_id,
            params.eval_id,
            params.eval_config_id,
        )
        run_config = task_run_config_from_id(
            params.project_id,
            params.task_id,
            params.run_config_id,
        )
        save_context = save_context_for_project(
            params.project_id,
            context=f"eval job {params.eval_id}/{params.run_config_id}",
        )
        return EvalRunner(
            eval_configs=[eval_config],
            run_configs=[run_config],
            eval_run_type="task_run_eval",
            save_context=save_context,
        )

    def _eval_and_task(self, eval_config: EvalConfig) -> tuple[Eval, Task]:
        eval = eval_config.parent_eval()
        if eval is None:
            raise ValueError("Eval config has no parent eval")
        task = eval.parent_task()
        if task is None:
            raise ValueError("Eval has no parent task")
        return eval, task
