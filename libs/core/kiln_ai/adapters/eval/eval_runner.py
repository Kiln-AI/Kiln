import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Literal, Set, Tuple

import litellm

from kiln_ai.adapters.adapter_registry import load_skills_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval, BaseV2EvalBridge
from kiln_ai.adapters.eval.drive_fingerprint import compute_drive_fingerprint
from kiln_ai.adapters.eval.registry import legacy_eval_adapter_from_type
from kiln_ai.adapters.eval.trace_index import TraceIndex, TraceKey, trace_key
from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
from kiln_ai.datamodel.basemodel import ID_TYPE, generate_model_id
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
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
from kiln_ai.datamodel.run_config import (
    KilnAgentRunConfigProperties,
    as_kiln_agent_run_config,
)
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_run import EvalItemSource, TaskRun, Usage
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.run_context import clear_eval_input_id, set_eval_input_id
from kiln_ai.synthetic_user import drive_case_for_eval
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.utils.async_job_runner import (
    AsyncJobRunner,
    AsyncJobRunnerObserver,
    Progress,
    RetryableError,
)
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam, serialize_trace

logger = logging.getLogger(__name__)

# Default number of dataset items evaluated in parallel when a caller doesn't specify one.
DEFAULT_EVAL_CONCURRENCY = 25


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


def _multi_turn_synthetic_case(
    job: EvalJob,
) -> Tuple[EvalInput, MultiTurnSyntheticEvalInputData] | None:
    """The synthetic multi-turn case this job re-drives, if it is one.

    task_run_eval only: calibration scores golden TaskRuns, and an EvalInput carries no
    stored output to judge, so a hand-built job of that shape falls through to the skip
    rather than paying for a drive.
    """
    if job.type != "task_run_eval":
        return None
    if not isinstance(job.item, EvalInput):
        return None
    if not isinstance(job.item.data, MultiTurnSyntheticEvalInputData):
        return None
    return job.item, job.item.data


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
        eval_set_filter_id_override: DatasetFilterId | None = None,
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
        self.eval_set_filter_id_override = eval_set_filter_id_override
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

    async def run(
        self,
        concurrency: int | None = None,
        observers: list[AsyncJobRunnerObserver[EvalJob]] | None = None,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> AsyncGenerator[Progress, None]:
        """
        Runs the configured eval run with parallel workers and yields progress updates.

        Pass `observers` to be notified per-item (e.g. to surface the exception of
        a failed dataset item — `Progress.errors` is only a count). Optional so the
        streaming UI paths can keep calling `run()` with no observer.

        `concurrency` bounds how many items run in parallel; None uses the default.

        `max_retries` re-attempts items that fail with a transient error (rate limit,
        connection blip) with exponential backoff starting at `retry_delay` seconds,
        only surfacing the error if every attempt fails. Background jobs override the
        defaults with a more patient schedule.
        """
        if concurrency is None:
            concurrency = DEFAULT_EVAL_CONCURRENCY
        jobs = self.collect_tasks()

        runner = AsyncJobRunner(
            concurrency=concurrency,
            jobs=jobs,
            run_job_fn=self.run_job,
            max_retries=max_retries,
            retry_delay=retry_delay,
            observers=observers,
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
                # Warning, not error: this fires per attempt, and the runner may
                # still retry. A final failure is reported via the runner's observers.
                logger.warning(
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
        eval_usage: Usage | None = None
        if job.type == "eval_config_eval":
            scores, intermediate_outputs, eval_usage = await evaluator.run_eval(
                job.item
            )
            task_output = job.item.output.output
            task_run_usage = job.item.usage
        else:
            (
                result_task_run,
                scores,
                intermediate_outputs,
                eval_usage,
            ) = await evaluator.run_task_and_eval(job.item)
            task_output = result_task_run.output.output
            task_run_usage = result_task_run.usage

            parent_eval = job.eval_config.parent_eval()
            if (
                parent_eval
                and parent_eval.evaluation_data_type == EvalDataType.full_trace
                and result_task_run.trace
            ):
                trace = serialize_trace(result_task_run.trace)

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
                eval_usage=eval_usage,
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

        # The two multi-turn lanes come before `_resolve_trace`: neither is a single
        # generation, so neither can go through it.
        multi_turn_case = _multi_turn_synthetic_case(job)
        if multi_turn_case is not None:
            eval_input, data = multi_turn_case
            return await self._run_v2_multi_turn_synthetic_job(
                job,
                evaluator,
                eval_input,
                data,
                data.first_message.text if data.first_message else "",
            )

        if isinstance(job.item, TaskRun) and job.item.parent_task_run_id is not None:
            # A stored conversation, not a case to re-drive: a chain leaf carries no
            # synthetic-user persona, so there is nothing to drive it with and both run
            # modes judge the trace it already has. Its scores are therefore a property
            # of the stored conversation and identical across run configs.
            leaf = job.item
            if not leaf.trace:
                return await self._persist_skip(
                    job,
                    SkippedReason.missing_trace,
                    "Multi-turn task run has no stored trace to evaluate",
                )
            eval_task_input = EvalTaskInput.from_task_run(leaf)
            result = await evaluator.evaluate(eval_task_input)
            return await self._persist_judgment(job, leaf, result)

        # Any other multi-turn shape can never be scored, and the skip comes before
        # `_resolve_trace` so it never pays for a generation.
        if _is_multi_turn(job.item):
            return await self._persist_skip(
                job,
                SkippedReason.incompatible_input_shape,
                "V2 evals do not yet support multi-turn inputs",
            )

        trace = await self._resolve_trace(job, evaluator)
        eval_task_input = EvalTaskInput.from_trace(trace, job.item)
        result = await evaluator.evaluate(eval_task_input)
        return await self._persist_judgment(job, trace, result)

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
        source_type, source_id, run_config_id, variant = key
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
        trace.eval_source = EvalItemSource(
            source_type=source_type, source_id=source_id, variant=variant or None
        )
        async with self._save_context():
            trace.save_to_file()
        return trace

    async def _persist_score(
        self,
        job: EvalJob,
        *,
        scored_run_id: ID_TYPE = None,
        scores: EvalScores | None = None,
        skipped_reason: str | None = None,
        skipped_detail: str | None = None,
        intermediate_outputs: Dict[str, str] | None = None,
        eval_usage: Usage | None = None,
        synthetic_user_usage: Usage | None = None,
        drive_fingerprint: str | None = None,
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
                skipped_reason=skipped_reason,
                skipped_detail=skipped_detail,
                intermediate_outputs=intermediate_outputs,
                eval_usage=eval_usage,
                # Both are multi-turn only, and both describe the drive rather than the
                # judgment: the synthetic user's spend (which surfaces nowhere else —
                # its turns are not persisted as runs) and the inputs the conversation
                # was driven from.
                synthetic_user_usage=synthetic_user_usage,
                drive_fingerprint=drive_fingerprint,
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
            skipped_reason=result.skipped_reason.value
            if result.skipped_reason
            else None,
            skipped_detail=result.skipped_detail,
            intermediate_outputs=result.intermediate_outputs,
            eval_usage=result.usage,
        )

    async def _run_v2_multi_turn_synthetic_job(
        self,
        job: EvalJob,
        evaluator: BaseV2EvalBridge,
        eval_input: EvalInput,
        data: MultiTurnSyntheticEvalInputData,
        seed: str,
    ) -> bool:
        """task_run_eval over a multi-turn synthetic input.

        The run config under evaluation drives the agent while the eval's
        multi_turn_drive_config plays the synthetic user, so each run config gets its own
        conversation — the property that makes run-config comparison meaningful for
        multi-turn. The conversation is persisted as a TaskRun and reached through
        `TraceIndex` like any other eval trace, so a second judge scores what the first
        one paid for, across evals as well as within one.

        Reuse is keyed on the drive fingerprint as well as the item and run config: two
        evals driving the same case with different drive settings produce genuinely
        different conversations, and the fingerprint is what keeps them apart.
        """
        drive_config = self.eval.multi_turn_drive_config
        if drive_config is None:
            return await self._persist_skip(
                job,
                SkippedReason.missing_drive_config,
                "Eval has no multi_turn_drive_config; re-driving a multi-turn "
                "synthetic input requires one",
            )

        if not seed:
            return await self._persist_skip(
                job,
                SkippedReason.incompatible_input_shape,
                "Multi-turn synthetic input has no first_message to open the "
                "conversation",
            )

        if job.task_run_config is None:
            raise ValueError("Task run eval requires a run config")
        try:
            agent_run_config = as_kiln_agent_run_config(
                job.task_run_config.run_config_properties
            )
        except ValueError as e:
            raise ValueError(
                "Multi-turn re-drive requires a Kiln agent run config; "
                f"run config '{job.task_run_config.name}' is a different type"
            ) from e
        try:
            su_provider = ModelProviderName(drive_config.model_provider)
        except ValueError as e:
            raise ValueError(
                "Invalid synthetic-user model provider on the eval's "
                f"multi_turn_drive_config: {drive_config.model_provider}"
            ) from e

        fingerprint = compute_drive_fingerprint(
            drive_config, job.task_run_config.run_config_properties, data
        )
        # Synthetic-user spend for THIS record. Stays None when the conversation was
        # reused: no driver call was made, and the spend is already booked on the record
        # that drove it. Unlike the agent's usage it cannot be recovered from the trace,
        # because the synthetic user's calls leave nothing in it.
        driven_su_usage: List[Usage | None] = []

        key = trace_key(item_key(job.item), job.task_run_config.id, fingerprint)
        trace, was_generated = await self._trace_index.get_or_create(
            key,
            lambda: self._drive_and_persist(
                job,
                eval_input,
                data,
                seed,
                agent_run_config,
                su_provider,
                key,
                driven_su_usage,
            ),
        )

        if not was_generated and not _trace_is_complete_drive(
            trace.trace, drive_config.turns
        ):
            # A partial conversation is a degraded sample, not a cheaper one: re-judging
            # it would quietly score every later judge against a drive that fell over.
            # Driving again under a variant nothing else can name keeps the fresh
            # conversation out of the way of the indexed (broken) one, which stays where
            # it is as the record of what the first judge actually scored.
            logger.info(
                "Indexed multi-turn trace %s for %s is incomplete; re-driving",
                trace.id,
                key,
            )
            retry_key = trace_key(
                item_key(job.item),
                job.task_run_config.id,
                f"{fingerprint}:redrive:{job.eval_config.id}",
            )
            trace, _ = await self._trace_index.get_or_create(
                retry_key,
                lambda: self._drive_and_persist(
                    job,
                    eval_input,
                    data,
                    seed,
                    agent_run_config,
                    su_provider,
                    retry_key,
                    driven_su_usage,
                ),
            )

        eval_task_input = EvalTaskInput.from_trace(trace, eval_input)
        result = await evaluator.evaluate(eval_task_input)
        return await self._persist_score(
            job,
            scored_run_id=trace.id,
            scores=result.scores,
            skipped_reason=result.skipped_reason.value
            if result.skipped_reason
            else None,
            skipped_detail=result.skipped_detail,
            intermediate_outputs=result.intermediate_outputs,
            eval_usage=result.usage,
            synthetic_user_usage=driven_su_usage[0] if driven_su_usage else None,
            drive_fingerprint=fingerprint,
        )

    async def _drive_and_persist(
        self,
        job: EvalJob,
        eval_input: EvalInput,
        data: MultiTurnSyntheticEvalInputData,
        seed: str,
        agent_run_config: KilnAgentRunConfigProperties,
        su_provider: ModelProviderName,
        key: TraceKey,
        su_usage_out: List[Usage | None] | None = None,
    ) -> TaskRun:
        """Drive one conversation and make it durable before it is scored.

        The `TraceIndex` counterpart to `_generate_and_persist`, for the lane where a
        generation is a whole conversation rather than a single call. Stamped from `key`
        for the same reason: a run that files itself under a different key than the one
        it was generated for is never found again.
        """
        drive_config = self.eval.multi_turn_drive_config
        assert drive_config is not None, "the caller checks this before driving"
        source_type, source_id, run_config_id, variant = key

        # Scope the eval-input id to the drive: every turn's tool calls see which
        # EvalInput produced them (run_context contextvar).
        if eval_input.id:
            set_eval_input_id(eval_input.id)
        try:
            drive_result = await drive_case_for_eval(
                seed_prompt=seed,
                synthetic_user_info=data.synthetic_user_info,
                target_task=self.task,
                target_run_config=agent_run_config,
                su_driver_config=SyntheticUserDriverConfig(
                    model_name=drive_config.model_name,
                    model_provider_name=su_provider,
                ),
                turns=drive_config.turns,
                skills=self._skills,
            )
        finally:
            clear_eval_input_id()

        if su_usage_out is not None:
            su_usage_out.append(drive_result.su_usage)

        leaf = drive_result.chain[-1]
        # The leaf carries the whole conversation on `.trace`, and its ancestors are
        # never saved. Keeping a pointer to them would read as a broken chain in the
        # dataset UI, and would hide this trace from the index, which does not look at
        # runs that are somebody's parent.
        leaf.parent_task_run_id = None
        if leaf.usage is None:
            leaf.usage = _usage_from_trace(leaf.trace)
        if leaf.id is None:
            # Driven with allow_saving=False, so nothing has minted an id; the runner is
            # the one persisting, exactly as in `_generate_and_persist`.
            leaf.id = generate_model_id()
        if leaf.output.source is not None:
            # Half the key a later index rebuilds from is read off here.
            leaf.output.source.run_config_id = run_config_id
        leaf.eval_source = EvalItemSource(
            source_type=source_type, source_id=source_id, variant=variant or None
        )
        async with self._save_context():
            leaf.save_to_file()
        return leaf


def _usage_from_trace(trace: list[ChatCompletionMessageParam] | None) -> Usage | None:
    """Aggregate per-message usage and latency into run-level Usage.

    A driven conversation's leaf reaches the runner unsaved and without run-level
    usage of its own, so it is derived from the trace before the leaf is persisted.
    Latency is the sum of per-call latency_ms:
    calls within one conversation run sequentially, so the sum is the real
    time spent waiting on the model."""
    if not trace:
        return None
    message_usage = MessageUsage()
    latency = 0
    for message in trace:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        raw_usage = message.get("usage")
        if isinstance(raw_usage, MessageUsage):
            message_usage = message_usage + raw_usage
        elif isinstance(raw_usage, dict):
            message_usage = message_usage + MessageUsage.model_validate(raw_usage)
        latency += message.get("latency_ms") or 0
    if message_usage == MessageUsage() and not latency:
        return None
    return Usage(**message_usage.model_dump(), total_llm_latency_ms=latency or None)


def _trace_is_complete_drive(
    trace: list[ChatCompletionMessageParam] | None, expected_turns: int
) -> bool:
    """A complete drive has exactly one user message per turn (assistant
    messages can be several per turn when tools fire, so they can't be
    counted) and ends with assistant text — the judges' final_message.
    Requiring the LAST message to be assistant text keeps a degraded record
    from promoting a mid-conversation reply to the final answer."""
    if not trace:
        return False
    user_turns = sum(1 for msg in trace if msg.get("role") == "user")
    if user_turns != expected_turns:
        return False
    last = trace[-1] if trace else None
    if last is None:
        return False
    content = last.get("content")
    return (
        last.get("role") == "assistant" and isinstance(content, str) and bool(content)
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
