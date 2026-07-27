from __future__ import annotations

import asyncio

from app.desktop.git_sync.save_context import save_context_for_project
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.eval_runner import (
    DEFAULT_EVAL_CONCURRENCY,
    EvalJob,
    EvalRunner,
)
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilterId,
    dataset_filter_from_id,
    eval_input_filter_from_id,
)
from kiln_ai.datamodel.eval import Eval, EvalConfig, EvalSplitName
from kiln_ai.datamodel.prompt_type import generator_label
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import Task, TaskRunConfig
from kiln_ai.datamodel.tool_id import SKILL_TOOL_ID_PREFIX
from kiln_ai.utils.async_job_runner import AsyncJobRunnerObserver
from pydantic import BaseModel, Field

from ...eval_api import (
    eval_config_from_id,
    split_filter_id_from_eval,
    task_run_config_from_id,
)
from ..models import (
    JOB_TRANSIENT_ERROR_MAX_RETRIES,
    JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS,
    JobContext,
    JobDerivedState,
    JobWorker,
)


def _safe_str(exc: Exception) -> str:
    """str(exc), falling back to the class name when it's empty or __str__ raises.

    This runs in the error-logging path, which must never itself crash the run:
    AsyncJobRunner awaits the observer's on_error unguarded, so a buggy __str__
    here would take down the whole eval. Mirrors errors._safe_str, but prefers
    the class name over a generic message since this log is developer-facing.
    """
    try:
        result = str(exc)
    except Exception:
        return type(exc).__name__
    return result or type(exc).__name__


def _error_detail(error: Exception) -> str:
    """The most informative message for a failed dataset item's error log.

    The model adapter wraps failures in `KilnRunError`, whose own message is the
    user-friendly `format_error_message` text — often the generic "An unexpected
    error occurred." for exception types it doesn't recognize. The original
    exception survives on `.original`, so for the developer-facing eval error log
    we surface that underlying detail instead of the genericized wrapper message.
    """
    if isinstance(error, KilnRunError) and error.original is not None:
        return _safe_str(error.original)
    return _safe_str(error)


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
            _error_detail(error),
            dataset_id=job.item.id,
            run_config_id=job.task_run_config.id if job.task_run_config else None,
        )


class EvalJobParams(BaseModel):
    project_id: str = Field(description="Id of the project the eval belongs to.")
    task_id: str = Field(description="Id of the task the eval belongs to.")
    eval_id: str = Field(description="Id of the eval to run.")
    eval_config_id: str = Field(
        description="Id of the eval config (judge) to evaluate the run's output with."
    )
    run_config_id: str = Field(
        description="Id of the task run config whose outputs are being evaluated."
    )
    concurrency: int | None = Field(
        default=None,
        ge=1,
        description="Max dataset items evaluated in parallel by the runner. Leave null to use the "
        f"runner's default ({DEFAULT_EVAL_CONCURRENCY}).",
    )
    split: EvalSplitName | None = Field(
        default=None,
        description="Which of the eval's dataset splits to run: train, val, or test. "
        "Fails with 422 if the eval has no filter configured for the split. Leave "
        "null to run the eval set (the test set — today's default behavior).",
    )


class EvalJobResult(BaseModel):
    total: int = Field(description="Total number of dataset items the eval processed.")
    success: int = Field(description="Number of dataset items evaluated successfully.")
    error: int = Field(description="Number of dataset items that failed to evaluate.")


class EvalJobProperties(BaseModel):
    """Static, descriptive info about an eval job, for display in the jobs UI.

    Mirrors the run-config summary and judge info shown elsewhere in the app:
    which eval, the run config (name, model, prompt, tool/skill counts), and the
    judge (eval config) algorithm and model. Model/provider fields carry raw ids;
    the frontend resolves them to display names with its model-name helpers.
    """

    eval_name: str = Field(description="Display name of the eval being run.")
    run_config_name: str = Field(
        description="Display name of the run config whose outputs are being evaluated."
    )
    run_config_model_name: str = Field(
        description="Raw model id used by the run config. The frontend resolves it to a display name."
    )
    run_config_model_provider: str = Field(
        description="Raw model provider id used by the run config. The frontend resolves it to a display name."
    )
    run_config_prompt_name: str = Field(
        description="Display name of the prompt the run config uses."
    )
    run_config_tools_count: int = Field(
        description="Number of tools available to the run config."
    )
    run_config_skills_count: int = Field(
        description="Number of skills available to the run config."
    )
    judge_name: str = Field(
        description="Display name of the judge (eval config) doing the evaluation."
    )
    judge_algorithm: str = Field(
        description="Algorithm the judge (eval config) uses to score outputs."
    )
    judge_model_name: str = Field(
        description="Raw model id used by the judge. The frontend resolves it to a display name."
    )
    judge_model_provider: str = Field(
        description="Raw model provider id used by the judge. The frontend resolves it to a display name."
    )


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
    properties_model = EvalJobProperties
    supports_pause = True

    async def describe(self, params: EvalJobParams) -> EvalJobProperties:
        # Loads entities off disk like _compute_state_sync; offload the blocking
        # IO to a thread so create() stays responsive.
        return await asyncio.to_thread(self._describe_sync, params)

    def _describe_sync(self, params: EvalJobParams) -> EvalJobProperties:
        eval_config = eval_config_from_id(
            params.project_id,
            params.task_id,
            params.eval_id,
            params.eval_config_id,
        )
        eval, task = self._eval_and_task(eval_config)
        run_config = task_run_config_from_id(
            params.project_id,
            params.task_id,
            params.run_config_id,
        )
        # Run configs are a union; only the kiln_agent variant carries a model,
        # prompt, and tools. MCP run configs have none, so leave those fields
        # blank rather than dropping the whole properties block (eval/judge info
        # still renders).
        run_config_properties = run_config.run_config_properties
        if isinstance(run_config_properties, KilnAgentRunConfigProperties):
            run_config_model_name = run_config_properties.model_name
            run_config_model_provider = run_config_properties.model_provider_name
            prompt_name = self._prompt_display_name(
                task, run_config, run_config_properties
            )
            tool_ids = (
                run_config_properties.tools_config.tools
                if run_config_properties.tools_config
                else []
            )
            skills_count = sum(
                1 for t in tool_ids if t.startswith(SKILL_TOOL_ID_PREFIX)
            )
            tools_count = len(tool_ids) - skills_count
        else:
            run_config_model_name = ""
            run_config_model_provider = ""
            prompt_name = ""
            tools_count = 0
            skills_count = 0

        return EvalJobProperties(
            eval_name=eval.name,
            run_config_name=run_config.name,
            run_config_model_name=run_config_model_name,
            run_config_model_provider=run_config_model_provider,
            run_config_prompt_name=prompt_name,
            run_config_tools_count=tools_count,
            run_config_skills_count=skills_count,
            judge_name=eval_config.name,
            judge_algorithm=eval_config.config_type.value,
            # V2 configs have no root-level judge model; leave blank like the
            # MCP run-config fields above.
            judge_model_name=eval_config.model_name or "",
            judge_model_provider=eval_config.model_provider or "",
        )

    def _prompt_display_name(
        self,
        task: Task,
        run_config: TaskRunConfig,
        run_config_properties: KilnAgentRunConfigProperties,
    ) -> str:
        """Resolve a prompt id to a human name, mirroring the frontend's
        prompt_name_from_id: a run config's own frozen prompt carries its name;
        built-in generators map to a label; custom (id::) and reused frozen
        (task_run_config::) prompts resolve their name from the task. Falls back
        to the raw id only when nothing resolves."""
        # A frozen prompt stored on THIS run config carries its saved name.
        if run_config.prompt is not None and run_config.prompt.name:
            return run_config.prompt.name

        prompt_id = run_config_properties.prompt_id

        # Built-in generator (e.g. "few_shot_prompt_builder" -> "Few-Shot").
        label = generator_label(prompt_id)
        if label:
            return label

        if prompt_id.startswith("fine_tune_prompt::"):
            return "Fine-Tune Prompt"

        # Custom prompt saved under the task: "id::<prompt_id>".
        if prompt_id.startswith("id::"):
            target = prompt_id[len("id::") :]
            for prompt in task.prompts(readonly=True):
                if prompt.id == target:
                    return prompt.name

        # Reused frozen prompt referencing another run config's frozen copy:
        # "task_run_config::<project_id>::<task_id>::<run_config_id>".
        if prompt_id.startswith("task_run_config::"):
            target = prompt_id.split("::")[-1]
            for other in task.run_configs(readonly=True):
                if other.id == target and other.prompt is not None:
                    return other.prompt.name

        return prompt_id

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

        # The job's dataset filter defines the universe of dataset items in
        # scope: the requested split's filter, or the eval's own filter — an
        # eval has exactly one of the two filter ids (datamodel invariant),
        # mirroring EvalRunner's two collect paths: TaskRun-backed datasets use
        # eval_set_filter_id; EvalInput-backed datasets use eval_input_filter_id.
        # EvalRunner only works items that BOTH pass this filter AND lack a
        # matching EvalRun, so progress must be measured against this same set.
        #
        # Count only scored items that are still in the filter set. Items that
        # were scored but later drifted out of the filter must not be counted,
        # or success/is_complete would overcount and a resume could short-circuit
        # to succeeded while real work remains.
        if params.split is not None:
            # The requested split's TaskRun dataset filter is the universe.
            # split_filter_id_from_eval rejects EvalInput-backed (V2) evals,
            # which have no TaskRun dataset splits.
            filter = dataset_filter_from_id(
                split_filter_id_from_eval(eval, params.split)
            )
            in_filter_ids = {
                task_run.id for task_run in task.runs(readonly=True) if filter(task_run)
            }
            scored_ids = {
                run.dataset_id
                for run in eval_config.runs(readonly=True)
                if run.task_run_config_id == params.run_config_id
            }
        elif eval.eval_input_filter_id is not None:
            input_filter = eval_input_filter_from_id(eval.eval_input_filter_id)
            in_filter_ids = {
                eval_input.id
                for eval_input in task.eval_inputs(readonly=True)
                if input_filter(eval_input)
            }
            scored_ids = {
                run.eval_input_id
                for run in eval_config.runs(readonly=True)
                if run.task_run_config_id == params.run_config_id
            }
        elif eval.eval_set_filter_id is not None:
            filter = dataset_filter_from_id(eval.eval_set_filter_id)
            in_filter_ids = {
                task_run.id for task_run in task.runs(readonly=True) if filter(task_run)
            }
            scored_ids = {
                run.dataset_id
                for run in eval_config.runs(readonly=True)
                if run.task_run_config_id == params.run_config_id
            }
        else:
            raise ValueError(
                "Eval has neither eval_set_filter_id nor eval_input_filter_id"
            )
        total = len(in_filter_ids)
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
        async for progress in eval_runner.run(
            concurrency=params.concurrency,
            observers=[_EvalErrorLogObserver(ctx)],
            max_retries=JOB_TRANSIENT_ERROR_MAX_RETRIES,
            retry_delay=JOB_TRANSIENT_ERROR_RETRY_DELAY_SECONDS,
        ):
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
        eval, _ = self._eval_and_task(eval_config)
        return EvalRunner(
            eval_configs=[eval_config],
            run_configs=[run_config],
            eval_run_type="task_run_eval",
            save_context=save_context,
            eval_set_filter_id_override=self._split_override(eval, params),
        )

    def _split_override(
        self, eval: Eval, params: EvalJobParams
    ) -> DatasetFilterId | None:
        """The requested split's filter id, or None when no split was requested —
        the single resolution point for a job's split."""
        if params.split is None:
            return None
        return split_filter_id_from_eval(eval, params.split)

    def _eval_and_task(self, eval_config: EvalConfig) -> tuple[Eval, Task]:
        eval = eval_config.parent_eval()
        if eval is None:
            raise ValueError("Eval config has no parent eval")
        task = eval.parent_task()
        if task is None:
            raise ValueError("Eval has no parent task")
        return eval, task
