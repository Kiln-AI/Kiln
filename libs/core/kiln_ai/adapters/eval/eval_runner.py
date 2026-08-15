import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Literal, Set

import litellm
from pydantic import JsonValue

from kiln_ai.adapters.adapter_registry import load_skills_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval, BaseV2EvalBridge
from kiln_ai.adapters.eval.registry import legacy_eval_adapter_from_type
from kiln_ai.adapters.eval.trace_index import TraceIndex, TraceKey, trace_key
from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
from kiln_ai.datamodel.basemodel import ID_TYPE, generate_model_id
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilterId,
    dataset_filter_from_id,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalRun,
    EvalScores,
    EvalTaskInput,
    MultiTurnSyntheticEvalInputData,
    SkippedReason,
    V2EvalResult,
)
from kiln_ai.datamodel.eval_splits import (
    ItemKey,
    ResolvedSplit,
    eval_run_item_key,
    item_key,
)
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun, Usage
from kiln_ai.utils.async_job_runner import AsyncJobRunner, Progress, RetryableError
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context

logger = logging.getLogger(__name__)


@dataclass
class EvalJob:
    item: TaskRun | EvalInput
    type: Literal["task_run_eval", "eval_config_eval"]
    eval_config: EvalConfig
    task_run_config: TaskRunConfig | None = None


def _calibration_item(job: EvalJob) -> TaskRun | None:
    """The golden TaskRun a calibration job scores, or None if this isn't calibration.

    Calibration generates nothing: the human-rated dataset item *is* what gets scored
    (functional spec 4.5). So the trace is known before the job starts, and stays known
    even for a job that is skipped before it reaches the judge — which is why both the
    scoring path and the skip path ask here rather than each deciding for themselves.
    """
    if job.type != "eval_config_eval":
        return None
    if not isinstance(job.item, TaskRun):
        raise ValueError("Calibration items are always TaskRuns")
    return job.item


def _is_multi_turn(item: TaskRun | EvalInput) -> bool:
    """Whether this item is a conversation rather than a single exchange.

    Multi-turn items are skipped by V2 evals, which also keeps eval traces childless —
    a property `TraceIndex._seed` relies on to find them.
    """
    if isinstance(item, TaskRun):
        return item.parent_task_run_id is not None
    return isinstance(item.data, MultiTurnSyntheticEvalInputData)


def no_golden_set_message(eval: Eval) -> str:
    """Why judge comparison can't run without a golden set. One wording, two raisers.

    Shared with the API layer so the 4xx a user sees and the ValueError a library caller
    sees say the same thing (functional spec 9, architecture 4.3).
    """
    return (
        f"Eval '{eval.id}' has no golden set configured. Comparing judges scores them "
        "against a set of human-rated dataset items, so the eval needs one before a "
        "comparison can run."
    )


class EvalRunner:
    """
    Runs an eval. Async execution is supported to make it faster when using remote/fast model providers.

    Can run an eval in 2 modes:
    1) eval_config_eval: evaluate an eval config using existing dataset items. Scoped by the
       eval's golden filter, so its items are always TaskRuns.
    2) task_run_eval: evaluate a range of task run configs, generating new run output using
       existing dataset item input. Scoped by the `split` it is given, whose items may come
       from either store.
    """

    def __init__(
        self,
        eval_configs: List[EvalConfig],
        run_configs: List[TaskRunConfig] | None,
        eval_run_type: Literal["eval_config_eval", "task_run_eval"],
        split: ResolvedSplit | None = None,
        save_context: SaveContext | None = None,
    ):
        if len(eval_configs) == 0:
            raise ValueError("Eval runner requires at least one eval config")
        target_eval = eval_configs[0].parent_eval()
        if target_eval is None:
            raise ValueError("Eval config requires a parent eval")
        for eval_config in eval_configs:
            parent_eval = eval_config.parent_eval()
            if parent_eval is None:
                raise ValueError("Eval config requires a parent eval")
            if parent_eval.id != target_eval.id:
                raise ValueError("All eval configs must have the same parent eval")

        target_task = target_eval.parent_task()
        if target_task is None:
            raise ValueError("Eval config requires a (grand)parent task")

        # Both modes settle *what defines* their item scope here rather than at collect
        # time, but to different depths, and the difference is deliberate. task_run_eval
        # takes a ResolvedSplit: the items themselves, fixed now, so a split cannot be
        # accepted and then quietly re-resolved to something else. eval_config_eval takes
        # the golden filter id and still applies it to self.task.runs() at collect time,
        # so items added after construction are picked up — golden is TaskRun-only by
        # definition, so there is no source ambiguity for that to hide.
        self.golden_filter_id: DatasetFilterId | None = None
        if eval_run_type == "task_run_eval":
            if run_configs is None or len(run_configs) == 0:
                raise ValueError("Task run eval requires run configs")
            for run_config in run_configs:
                parent_task = run_config.parent_task()
                if parent_task is None:
                    raise ValueError("All run configs must have a parent task")
                if parent_task.id != target_task.id:
                    raise ValueError(
                        "Run config is not for the same task as the eval configs"
                    )
            if split is None:
                raise ValueError("Task run eval requires a resolved split")
            if split.eval_id != target_eval.id:
                raise ValueError(
                    f"Split '{split.name}' was resolved from eval '{split.eval_id}', not from "
                    f"eval '{target_eval.id}' whose configs are being run"
                )
        else:
            if run_configs is not None:
                raise ValueError("Mode 'eval_config_eval' does not support run configs")
            if split is not None:
                raise ValueError(
                    "Mode 'eval_config_eval' does not support a split: it is scoped by the eval's golden filter"
                )
            if target_eval.eval_configs_filter_id is None:
                raise ValueError(no_golden_set_message(target_eval))
            self.golden_filter_id = target_eval.eval_configs_filter_id

        self.eval_run_type = eval_run_type
        self.eval_configs = eval_configs
        self.run_configs = run_configs
        self.split = split
        self.task = target_task
        self.eval = target_eval
        self._skills: SkillsDict = self._preload_skills()
        self._save_context: SaveContext = save_context or default_save_context
        # Live, not precomputed like `already_run`: a trace persisted by one job has to be
        # visible to the next, whether that next job is running concurrently under a
        # different eval config or is this job's own retry (functional spec 4.2, 4.3).
        self._trace_index = TraceIndex(self.task)

    def collect_tasks(self) -> List[EvalJob]:
        if self.eval_run_type == "eval_config_eval":
            if self.golden_filter_id is None:
                raise ValueError(no_golden_set_message(self.eval))
            return self.collect_tasks_for_eval_config_eval(self.golden_filter_id)
        return self.collect_tasks_for_task_run_eval()

    def collect_tasks_for_eval_config_eval(
        self, eval_configs_filter_id: DatasetFilterId
    ) -> List[EvalJob]:
        """
        Collect all jobs for this run, excluding any that have already been run.

        This variant is used for mode "eval_config_eval", using existing dataset run data (input/output).

        The tasks:
        - should be in the eval config set filter
        - should not have already been run for this eval config + dataset item pair
        """
        filter = dataset_filter_from_id(eval_configs_filter_id)

        # already_run[eval_config_id][dataset_id]
        already_run: Dict[ID_TYPE, Set[ID_TYPE]] = {}
        for eval_config in self.eval_configs:
            already_run[eval_config.id] = set()
            for run in eval_config.runs(readonly=True):
                already_run[eval_config.id].add(run.dataset_id)

        return [
            EvalJob(
                item=task_run,
                eval_config=eval_config,
                type="eval_config_eval",
            )
            for task_run in self.task.runs(readonly=True)
            if filter(task_run)
            for eval_config in self.eval_configs
            if task_run.id not in already_run[eval_config.id]
        ]

    def collect_tasks_for_task_run_eval(self) -> List[EvalJob]:
        """
        Collect all jobs for this run, excluding any that have already been run.

        This variant is used for mode "task_run_eval", generating new run output using existing dataset item input.

        The tasks:
        - are the items of the split this runner was given, from whichever store backs it
        - should not have already been run for this eval config + run config + dataset item
        """
        if self.split is None:
            raise ValueError("Task run eval requires a resolved split")

        # already_run[eval_config_id][run_config_id][item_key]
        already_run: Dict[ID_TYPE, Dict[ID_TYPE, Set[ItemKey]]] = {}
        for eval_config in self.eval_configs:
            already_run[eval_config.id] = {
                run_config.id: set() for run_config in self.run_configs or []
            }
            for run in eval_config.runs(readonly=True):
                # Scopes the dedupe to the run configs actually being evaluated: an eval
                # config accumulates runs for every run config ever compared against it.
                # The `is not None` is not redundant with the membership test — ID_TYPE is
                # `str | None`, so a run config whose file carries a null id would make
                # None a real key and fold every calibration record into its set.
                if (
                    run.task_run_config_id is not None
                    and run.task_run_config_id in already_run[eval_config.id]
                ):
                    already_run[eval_config.id][run.task_run_config_id].add(
                        eval_run_item_key(run)
                    )

        return [
            EvalJob(
                item=item,
                task_run_config=run_config,
                type="task_run_eval",
                eval_config=eval_config,
            )
            for item in self.split.items
            for eval_config in self.eval_configs
            for run_config in self.run_configs or []
            if (self.split.source, item.id)
            not in already_run[eval_config.id][run_config.id]
        ]

    def _preload_skills(self) -> SkillsDict:
        """Collect all skill IDs from run configs and bulk-load them once."""
        if self.run_configs is None:
            return {}
        merged: SkillsDict = {}
        for rc in self.run_configs:
            skills = load_skills_for_task(self.task, rc.run_config_properties)
            merged.update(skills)
        return merged

    async def run(self, concurrency: int = 25) -> AsyncGenerator[Progress, None]:
        """
        Runs the configured eval run with parallel workers and yields progress updates.
        """
        jobs = self.collect_tasks()

        runner = AsyncJobRunner(
            concurrency=concurrency,
            jobs=jobs,
            run_job_fn=self.run_job,
            max_retries=2,
        )
        async for progress in runner.run():
            yield progress

    async def run_job(self, job: EvalJob) -> bool:
        try:
            if job.eval_config.config_type == EvalConfigType.v2:
                return await self._run_v2_job(job)
            else:
                return await self._run_legacy_job(job)
        except Exception as e:
            if _is_retryable_error(e):
                logger.error(
                    f"Transient error running eval job for dataset item {job.item.id}: {e}",
                    exc_info=True,
                )
                # KilnRunError's own message is genericized user-facing text; keep
                # the underlying provider detail for the developer-facing error log.
                raise RetryableError(str(_unwrap_kiln_run_error(e))) from e
            logger.error(
                f"Error running eval job for dataset item {job.item.id}: {e}",
                exc_info=True,
            )
            raise

    async def _run_legacy_job(self, job: EvalJob) -> bool:
        if not isinstance(job.item, TaskRun):
            raise ValueError("Legacy eval jobs require a TaskRun item")

        evaluator = legacy_eval_adapter_from_type(job.eval_config)(
            job.eval_config,
            job.task_run_config.run_config_properties if job.task_run_config else None,
            skills=self._skills,
        )
        if not isinstance(evaluator, BaseEval):
            raise ValueError("Not able to create evaluator from eval config")

        task_output: str | None = None
        reference_answer: str | None = None
        trace: str | None = None
        scores: EvalScores | None = None
        intermediate_outputs: Dict[str, str] | None = None
        task_run_usage: Usage | None = None
        if job.type == "eval_config_eval":
            scores, intermediate_outputs = await evaluator.run_eval(job.item)
            task_output = job.item.output.output
            task_run_usage = job.item.usage
        else:
            (
                result_task_run,
                scores,
                intermediate_outputs,
            ) = await evaluator.run_task_and_eval(job.item)
            task_output = result_task_run.output.output
            task_run_usage = result_task_run.usage

            parent_eval = job.eval_config.parent_eval()
            if (
                parent_eval
                and parent_eval.evaluation_data_type == EvalDataType.full_trace
                and result_task_run.trace
            ):
                trace = json.dumps(result_task_run.trace, indent=2, ensure_ascii=False)

            if (
                parent_eval
                and parent_eval.evaluation_data_type == EvalDataType.reference_answer
            ):
                reference_answer = job.item.output.output

        async with self._save_context():
            eval_run = EvalRun(
                parent=job.eval_config,
                task_run_config_id=job.task_run_config.id
                if job.task_run_config
                else None,
                dataset_id=job.item.id,
                eval_config_eval=job.type == "eval_config_eval",
                scores=scores,
                input=job.item.input,
                output=task_output,
                reference_answer=reference_answer,
                intermediate_outputs=intermediate_outputs,
                task_run_trace=trace,
                task_run_usage=task_run_usage,
            )
            eval_run.save_to_file()

        return True

    async def _run_v2_job(self, job: EvalJob) -> bool:
        from kiln_ai.adapters.eval.registry import v2_eval_adapter_from_config

        try:
            rc_props = (
                job.task_run_config.run_config_properties
                if job.task_run_config
                else None
            )
            evaluator = v2_eval_adapter_from_config(
                job.eval_config, rc_props, self._skills
            )
        except NotImplementedError:
            return await self._persist_skip(
                job,
                SkippedReason.type_not_available,
                "V2 eval type not yet implemented",
            )

        # Both skips come before `_resolve_trace`, so a job that can never be scored
        # never pays for a generation.
        if _is_multi_turn(job.item):
            return await self._persist_skip(
                job,
                SkippedReason.incompatible_input_shape,
                "V2 evals do not yet support multi-turn inputs",
            )

        trace = await self._resolve_trace(job, evaluator)
        eval_task_input = EvalTaskInput.from_trace(trace, job.item)
        result = await evaluator.evaluate(eval_task_input)
        return await self._persist_judgment(job, trace, eval_task_input, result)

    async def _resolve_trace(
        self, job: EvalJob, evaluator: BaseV2EvalBridge
    ) -> TaskRun:
        """The TaskRun this job scores, generating it only if the task has none."""
        golden = _calibration_item(job)
        if golden is not None:
            return golden

        if job.task_run_config is None:
            raise ValueError("A task_run_eval job requires a run config")

        key = trace_key(item_key(job.item), job.task_run_config.id)
        # `TraceIndex` logs both outcomes itself — debug on reuse, info on generation
        # (architecture 8) — so the was_generated bool has no reader here.
        trace, _ = await self._trace_index.get_or_create(
            key, lambda: self._generate_and_persist(job, evaluator, key)
        )
        return trace

    async def _generate_and_persist(
        self, job: EvalJob, evaluator: BaseV2EvalBridge, key: TraceKey
    ) -> TaskRun:
        """Run the task for this job's item, and make the result durable before scoring.

        Stamped from `key` rather than re-derived from the job, so the run files itself
        under exactly the key the index filed it under. A run that disagrees is never
        found again, and the eval regenerates it on every future run.
        """
        source_type, source_id, run_config_id = key
        trace = await evaluator.run_task(job.item, run_config_id=run_config_id)
        if trace.id is None:
            # `run_task` builds its adapter with allow_saving=False, and every adapter
            # clears the id of a run it did not persist (base_adapter.py:346). The runner
            # is the one persisting here, so it mints the id — the same thing
            # data_gen_api.py:474 does with an unsaved adapter run.
            #
            # Deliberately not allow_saving=True instead: the adapter would persist the
            # run before `eval_source` is stamped on it, so a crash in that window would
            # leave an eval trace permanently indistinguishable from a curated dataset
            # row — the contamination Task.runs()' default-exclude exists to prevent.
            trace.id = generate_model_id()
        trace.eval_source = EvalItemSource(source_type=source_type, source_id=source_id)
        async with self._save_context():
            trace.save_to_file()
        return trace

    async def _persist_score(
        self,
        job: EvalJob,
        *,
        scored_run_id: ID_TYPE = None,
        scores: EvalScores | None = None,
        reference_data: dict[str, JsonValue] | None = None,
        skipped_reason: str | None = None,
        skipped_detail: str | None = None,
        intermediate_outputs: Dict[str, str] | None = None,
        eval_usage: Usage | None = None,
    ) -> bool:
        """Write one V2 score record.

        The single place the item-identity fields are filled in, because `collect_tasks`
        dedupes on exactly those: a skip record and a score record that disagreed would
        be two identities for one job. No inline trace field is ever set — they are
        deprecated, and the trace lives on the TaskRun (functional spec 3.2).
        """
        async with self._save_context():
            EvalRun(
                parent=job.eval_config,
                task_run_config_id=job.task_run_config.id
                if job.task_run_config
                else None,
                dataset_id=job.item.id if isinstance(job.item, TaskRun) else None,
                eval_input_id=job.item.id if isinstance(job.item, EvalInput) else None,
                eval_config_eval=job.type == "eval_config_eval",
                scored_run_id=scored_run_id,
                scores=scores or {},
                reference_data=reference_data,
                skipped_reason=skipped_reason,
                skipped_detail=skipped_detail,
                intermediate_outputs=intermediate_outputs,
                eval_usage=eval_usage,
            ).save_to_file()
        return True

    async def _persist_skip(
        self, job: EvalJob, reason: SkippedReason, detail: str
    ) -> bool:
        """A job skipped before it reached the judge.

        Calibration still names its trace: the golden item *is* what would have been
        scored, it is already on disk, and a skip that happens one step later — inside
        `evaluate()` — records it (functional spec 4.6, row 2). Where the failure
        happened shouldn't change the record's shape, and Phase 5 migrates old
        calibration skips to exactly this.

        A scoring job genuinely has nothing to point at. Generating a trace for a job
        that can never be scored is the spend these early skips exist to avoid.
        """
        golden = _calibration_item(job)
        return await self._persist_score(
            job,
            scored_run_id=golden.id if golden is not None else None,
            skipped_reason=reason.value,
            skipped_detail=detail,
        )

    async def _persist_judgment(
        self,
        job: EvalJob,
        trace: TaskRun,
        eval_task_input: EvalTaskInput,
        result: V2EvalResult,
    ) -> bool:
        """The score for one item, pointing at the trace it was computed over.

        Also the home of a scoring-time skip: the trace exists and this judge could not
        score it, so the record carries both `scored_run_id` and `skipped_reason`
        (functional spec 4.6, row 2).
        """
        return await self._persist_score(
            job,
            scored_run_id=trace.id,
            scores=result.scores,
            # From what was handed to the judge, not re-derived from the item: the field
            # records what the scorer actually saw.
            reference_data=eval_task_input.reference_data,
            skipped_reason=result.skipped_reason.value
            if result.skipped_reason
            else None,
            skipped_detail=result.skipped_detail,
            intermediate_outputs=result.intermediate_outputs,
            eval_usage=result.usage,
        )


def _unwrap_kiln_run_error(e: BaseException) -> BaseException:
    """The innermost non-wrapper error.

    The model adapter wraps provider exceptions in KilnRunError (to carry the
    partial trace), whose own message is genericized user-facing text — so both
    retry classification and error detail must use the underlying error. The
    isinstance guard on `original` keeps a (contract-violating) None from
    escaping as the result."""
    while isinstance(e, KilnRunError) and isinstance(e.original, BaseException):
        e = e.original
    return e


def _is_retryable_error(e: BaseException) -> bool:
    e = _unwrap_kiln_run_error(e)

    if isinstance(
        e,
        (
            litellm.RateLimitError,
            litellm.APIConnectionError,
            litellm.InternalServerError,
            litellm.ServiceUnavailableError,
            litellm.BadGatewayError,
            litellm.JSONSchemaValidationError,
        ),
    ):
        return True

    # ValueError thrown by Kiln's adapter when structured output doesn't match schema
    if isinstance(
        e, ValueError
    ) and "This task requires a specific output schema" in str(e):
        return True

    return False
