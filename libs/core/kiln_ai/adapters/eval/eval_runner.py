import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Literal, Set, Tuple

import litellm

from kiln_ai.adapters.adapter_registry import load_skills_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval, BaseV2EvalBridge
from kiln_ai.adapters.eval.registry import legacy_eval_adapter_from_type
from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilterId,
    dataset_filter_from_id,
    eval_input_filter_from_id,
)
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalRun,
    EvalScores,
    EvalTaskInput,
    MultiTurnSyntheticEvalInputData,
    SingleTurnEvalInputData,
    SkippedReason,
)
from kiln_ai.datamodel.run_config import as_kiln_agent_run_config
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_run import TaskRun, Usage
from kiln_ai.datamodel.usage import MessageUsage
from kiln_ai.synthetic_user import drive_case_for_eval
from kiln_ai.synthetic_user.models import SyntheticUserDriverConfig
from kiln_ai.utils.async_job_runner import AsyncJobRunner, Progress, RetryableError
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context

logger = logging.getLogger(__name__)


@dataclass
class EvalJob:
    item: TaskRun | EvalInput
    type: Literal["task_run_eval", "eval_config_eval"]
    eval_config: EvalConfig
    task_run_config: TaskRunConfig | None = None


class EvalRunner:
    """
    Runs an eval. Async execution is supported to make it faster when using remote/fast model providers.

    Can run an eval in 2 modes:
    1) eval_config_eval: evaluate an eval config (judge quality) against the
       golden set — human-rated TaskRuns selected by eval_configs_filter_id.
    2) task_run_eval: evaluate a range of task run configs, generating fresh
       output per run config. Inputs come from stored TaskRuns
       (eval_set_filter_id) or EvalInput items (eval_input_filter_id).
       Multi-turn synthetic EvalInputs are re-driven as a full conversation
       per run config using the eval's multi_turn_drive_config; stored
       multi-turn TaskRun chains are judged on their stored trace instead.
    """

    def __init__(
        self,
        eval_configs: List[EvalConfig],
        run_configs: List[TaskRunConfig] | None,
        eval_run_type: Literal["eval_config_eval", "task_run_eval"],
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

        # Check that run_configs is compatible
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
        else:
            if run_configs is not None:
                raise ValueError("Mode 'eval_config_eval' does not support run configs")

        self._source_mode: Literal["task_run", "eval_input"] = "task_run"
        if target_eval.eval_input_filter_id is not None:
            self._source_mode = "eval_input"

        self.eval_run_type = eval_run_type
        self.eval_configs = eval_configs
        self.run_configs = run_configs
        self.task = target_task
        self.eval = target_eval
        self._skills: SkillsDict = self._preload_skills()
        self._save_context: SaveContext = save_context or default_save_context
        # Single-flight guard for multi-turn drives: concurrent jobs for the
        # same (eval_input, run_config) pair (e.g. two eval configs scoring
        # the same input) must not both drive the conversation.
        self._drive_locks: Dict[Tuple[str, str], asyncio.Lock] = {}

    def collect_tasks(self) -> List[EvalJob]:
        if self.eval_run_type == "eval_config_eval":
            # Judge calibration runs against the golden set (human-rated
            # TaskRuns) regardless of _source_mode: judge validation needs
            # stored, human-rated outputs, and eval_configs_filter_id is a
            # TaskRun dataset filter.
            if self.eval.eval_configs_filter_id is not None:
                return self.collect_tasks_for_eval_config_eval(
                    self.eval.eval_configs_filter_id
                )
            else:
                raise ValueError(
                    "Eval configs filter ID is required for eval runs of type 'eval_config_eval'"
                )
        elif self._source_mode == "eval_input":
            return self.collect_tasks_for_eval_input()
        else:
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

    def collect_tasks_for_eval_input(self) -> List[EvalJob]:
        """Collect jobs from EvalInput items under the task.

        task_run_eval only: eval_config_eval always collects golden TaskRuns
        (see collect_tasks) since EvalInput items carry no stored output to
        judge.
        """
        if self.eval_run_type != "task_run_eval":
            raise ValueError(
                "EvalInput collection only supports task_run_eval; "
                "eval_config_eval uses eval_configs_filter_id over TaskRuns"
            )
        filter_id = self.eval.eval_input_filter_id
        if filter_id is None:
            raise ValueError(
                "eval_input_filter_id is required for eval_input source mode"
            )
        input_filter = eval_input_filter_from_id(filter_id)

        already_run: Dict[ID_TYPE, Dict[ID_TYPE, Set[ID_TYPE]]] = {}
        for eval_config in self.eval_configs:
            already_run[eval_config.id] = {}
            for run_config in self.run_configs or []:
                already_run[eval_config.id][run_config.id] = set()
            for run in eval_config.runs(readonly=True):
                if (
                    run.eval_input_id is not None
                    and run.task_run_config_id is not None
                    and run.task_run_config_id in already_run[eval_config.id]
                ):
                    already_run[eval_config.id][run.task_run_config_id].add(
                        run.eval_input_id
                    )

        jobs: List[EvalJob] = []
        for eval_input in self.task.eval_inputs(readonly=True):
            if not input_filter(eval_input):
                continue
            for eval_config in self.eval_configs:
                for run_config in self.run_configs or []:
                    if eval_input.id in already_run[eval_config.id][run_config.id]:
                        continue
                    jobs.append(
                        EvalJob(
                            item=eval_input,
                            eval_config=eval_config,
                            type="task_run_eval",
                            task_run_config=run_config,
                        )
                    )
        return jobs

    def collect_tasks_for_task_run_eval(self) -> List[EvalJob]:
        """
        Collect all jobs for this run, excluding any that have already been run.

        This variant is used for mode "task_run_eval", generating new run output using existing dataset item input.

        The tasks:
        - should be in the eval set filter
        - should not have already been run for this eval config + run config + dataset item
        """
        if self.eval.eval_set_filter_id is None:
            raise ValueError("eval_set_filter_id is required for task_run_eval mode")
        filter = dataset_filter_from_id(self.eval.eval_set_filter_id)

        # already_run[eval_config_id][run_config_id][dataset_id]
        already_run: Dict[ID_TYPE, Dict[ID_TYPE, Set[ID_TYPE]]] = {}
        for eval_config in self.eval_configs:
            already_run[eval_config.id] = {}
            for run_config in self.run_configs or []:
                already_run[eval_config.id][run_config.id] = set()
            for run in eval_config.runs(readonly=True):
                if (
                    run.task_run_config_id is not None
                    and run.task_run_config_id in already_run[eval_config.id]
                ):
                    already_run[eval_config.id][run.task_run_config_id].add(
                        run.dataset_id
                    )

        return [
            EvalJob(
                item=task_run,
                task_run_config=run_config,
                type="task_run_eval",
                eval_config=eval_config,
            )
            for task_run in self.task.runs(readonly=True)
            if filter(task_run)
            for eval_config in self.eval_configs
            for run_config in self.run_configs or []
            if task_run.id not in already_run[eval_config.id][run_config.id]
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
                trace = json.dumps(result_task_run.trace, indent=2)

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

        if isinstance(job.item, TaskRun):
            early_input_str = job.item.input
        elif isinstance(job.item, EvalInput) and isinstance(
            job.item.data, SingleTurnEvalInputData
        ):
            early_input_str = job.item.data.user_message.text
        elif isinstance(job.item, EvalInput) and isinstance(
            job.item.data, MultiTurnSyntheticEvalInputData
        ):
            early_input_str = (
                job.item.data.first_message.text if job.item.data.first_message else ""
            )
        else:
            early_input_str = ""

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
            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=job.item.id if isinstance(job.item, TaskRun) else None,
                    eval_input_id=job.item.id
                    if isinstance(job.item, EvalInput)
                    else None,
                    eval_config_eval=job.type == "eval_config_eval",
                    scores={},
                    input=early_input_str,
                    output=None,
                    skipped_reason=SkippedReason.type_not_available.value,
                    skipped_detail="V2 eval type not yet implemented",
                )
                eval_run.save_to_file()
            return True

        if (
            isinstance(job.item, EvalInput)
            and isinstance(job.item.data, MultiTurnSyntheticEvalInputData)
            and job.type == "task_run_eval"
        ):
            # Multi-turn synthetic input: re-drive the conversation fresh
            # for this run config, then judge the new trace. The job.type
            # guard is defensive — collect_tasks never pairs eval_config_eval
            # with EvalInput items (judge calibration uses golden TaskRuns);
            # a hand-built job of that shape hits the EvalInput skip below.
            return await self._run_v2_multi_turn_synthetic_job(
                job, evaluator, job.item, job.item.data, early_input_str
            )

        if isinstance(job.item, TaskRun) and job.item.parent_task_run_id is not None:
            # Multi-turn chain leaf: a conversation can't be regenerated in
            # a single model call, so both run modes evaluate the stored
            # trace. In task_run_eval mode the scores are therefore a property
            # of the stored conversation, identical across run configs —
            # re-driving per run config needs a synthetic-user seed + persona,
            # which EvalInput-sourced cases carry (branch above) but stored
            # TaskRun chains do not.
            leaf = job.item
            if not leaf.trace:
                async with self._save_context():
                    eval_run = EvalRun(
                        parent=job.eval_config,
                        task_run_config_id=job.task_run_config.id
                        if job.task_run_config
                        else None,
                        dataset_id=leaf.id,
                        eval_input_id=None,
                        eval_config_eval=job.type == "eval_config_eval",
                        scores={},
                        input=leaf.input,
                        output=None,
                        skipped_reason=SkippedReason.missing_trace.value,
                        skipped_detail="Multi-turn task run has no stored trace to evaluate",
                    )
                    eval_run.save_to_file()
                return True

            eval_task_input = EvalTaskInput.from_task_run(leaf)
            result = await evaluator.evaluate(eval_task_input)

            # Like the legacy runner, only successful task-run-eval records of
            # a full_trace eval carry the serialized trace.
            trace_json: str | None = None
            if (
                job.type == "task_run_eval"
                and result.skipped_reason is None
                and self.eval.evaluation_data_type == EvalDataType.full_trace
            ):
                trace_json = json.dumps(
                    eval_task_input.trace,
                    indent=2,
                    ensure_ascii=False,
                    default=_trace_json_default,
                )

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=leaf.id,
                    eval_input_id=None,
                    eval_config_eval=job.type == "eval_config_eval",
                    scores=result.scores,
                    input=leaf.input,
                    output=leaf.output.output
                    if result.skipped_reason is None
                    else None,
                    reference_data=eval_task_input.reference_data,
                    skipped_reason=result.skipped_reason.value
                    if result.skipped_reason
                    else None,
                    skipped_detail=result.skipped_detail,
                    intermediate_outputs=result.intermediate_outputs,
                    task_run_trace=trace_json,
                )
                eval_run.save_to_file()
            return True

        if isinstance(job.item, EvalInput):
            if job.type == "eval_config_eval":
                async with self._save_context():
                    eval_run = EvalRun(
                        parent=job.eval_config,
                        task_run_config_id=job.task_run_config.id
                        if job.task_run_config
                        else None,
                        dataset_id=None,
                        eval_input_id=job.item.id,
                        eval_config_eval=True,
                        scores={},
                        input=early_input_str,
                        output=None,
                        skipped_reason=SkippedReason.incompatible_input_shape.value,
                        skipped_detail="EvalInput source has no stored output; eval_config_eval over EvalInput is deferred in V2.0 (golden subsets use TaskRun sources)",
                    )
                    eval_run.save_to_file()
                return True

            run_output = await evaluator.run_task(job.item)
            eval_task_input = EvalTaskInput.from_eval_input(job.item, run_output)
            result = await evaluator.evaluate(eval_task_input)

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=None,
                    eval_input_id=job.item.id,
                    eval_config_eval=False,
                    scores=result.scores,
                    input=early_input_str,
                    output=run_output.output.output
                    if result.skipped_reason is None
                    else None,
                    reference_data=job.item.reference,
                    skipped_reason=result.skipped_reason.value
                    if result.skipped_reason
                    else None,
                    skipped_detail=result.skipped_detail,
                    intermediate_outputs=result.intermediate_outputs,
                )
                eval_run.save_to_file()
            return True

        if job.type == "task_run_eval":
            run_output = await evaluator.run_task(job.item)
            eval_task_input = EvalTaskInput.from_task_run(run_output)
            result = await evaluator.evaluate(eval_task_input)
            task_output = run_output.output.output
            task_input_str = run_output.input
            dataset_id = run_output.id

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=dataset_id,
                    eval_input_id=None,
                    eval_config_eval=False,
                    scores=result.scores,
                    input=task_input_str,
                    output=task_output if result.skipped_reason is None else None,
                    reference_data=eval_task_input.reference_data,
                    skipped_reason=result.skipped_reason.value
                    if result.skipped_reason
                    else None,
                    skipped_detail=result.skipped_detail,
                    intermediate_outputs=result.intermediate_outputs,
                )
                eval_run.save_to_file()
            return True
        else:
            eval_task_input = EvalTaskInput.from_task_run(job.item)
            dataset_id = job.item.id
            task_input_str = job.item.input
            task_output = job.item.output.output

            result = await evaluator.evaluate(eval_task_input)

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=dataset_id,
                    eval_input_id=None,
                    eval_config_eval=True,
                    scores=result.scores,
                    input=task_input_str,
                    output=task_output if result.skipped_reason is None else None,
                    reference_data=eval_task_input.reference_data,
                    skipped_reason=result.skipped_reason.value
                    if result.skipped_reason
                    else None,
                    skipped_detail=result.skipped_detail,
                    intermediate_outputs=result.intermediate_outputs,
                )
                eval_run.save_to_file()
            return True

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
        multi_turn_drive_config plays the synthetic user, so each run config
        gets its own conversation — the property that makes run-config
        comparison meaningful for multi-turn. Driven conversations persist as
        real TaskRuns keyed by (eval_input, run_config): the leaf carries a
        `sei_<eval_input_id>` tag and the adapter stamps
        `output.source.run_config_id`, so any eval scoring the same pair
        reuses the stored conversation instead of re-driving it (KIL-761).
        For full_trace evals the EvalRun record additionally carries the
        serialized conversation when scoring succeeds.
        """
        drive_config = self.eval.multi_turn_drive_config
        if drive_config is None:
            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=None,
                    eval_input_id=eval_input.id,
                    eval_config_eval=False,
                    scores={},
                    input=seed,
                    output=None,
                    skipped_reason=SkippedReason.missing_drive_config.value,
                    skipped_detail="Eval has no multi_turn_drive_config; "
                    "re-driving a multi-turn synthetic input requires one",
                )
                eval_run.save_to_file()
            return True

        if not seed:
            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=None,
                    eval_input_id=eval_input.id,
                    eval_config_eval=False,
                    scores={},
                    input=seed,
                    output=None,
                    skipped_reason=SkippedReason.incompatible_input_shape.value,
                    skipped_detail="Multi-turn synthetic input has no "
                    "first_message to open the conversation",
                )
                eval_run.save_to_file()
            return True

        if job.task_run_config is None:
            raise ValueError("Task run eval requires a run config")

        # Reuse a conversation another eval already drove for this
        # (eval_input, run_config) pair: the drive tags its leaf
        # sei_<eval_input_id> and the adapter stamps
        # output.source.run_config_id. Conversations are plain persisted
        # TaskRuns any number of evals can score. The per-pair lock
        # single-flights scan+drive+tag so concurrent jobs for the same pair
        # (e.g. two eval configs over one input) reuse the first drive
        # instead of racing into duplicates.
        pair_tag = f"sei_{eval_input.id}"
        pair_key = (str(eval_input.id), str(job.task_run_config.id))
        pair_lock = self._drive_locks.setdefault(pair_key, asyncio.Lock())
        async with pair_lock:
            leaf: TaskRun | None = None
            for run in self.task.runs(readonly=True):
                if (
                    pair_tag in (run.tags or [])
                    and run.trace
                    and run.output is not None
                    and run.output.source is not None
                    and run.output.source.run_config_id == job.task_run_config.id
                ):
                    leaf = run
                    break

            if leaf is None:
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

                leaf = await drive_case_for_eval(
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
                    task_run_config_id=job.task_run_config.id,
                )
                # The pair tag makes the leaf discoverable for reuse; the
                # eval-scoped tag lets cleanup sweeps find driven
                # conversations.
                new_tags = {pair_tag, f"synthetic_eval_drive_{self.eval.id}"}
                if not new_tags.issubset(leaf.tags or []):
                    async with self._save_context():
                        leaf.tags = sorted(set(leaf.tags or []) | new_tags)
                        leaf.save_to_file()

        eval_task_input = EvalTaskInput.from_eval_input(eval_input, leaf)
        result = await evaluator.evaluate(eval_task_input)

        # Like the stored-trace path, only successful records of a full_trace
        # eval carry the serialized conversation.
        trace_json: str | None = None
        if (
            result.skipped_reason is None
            and self.eval.evaluation_data_type == EvalDataType.full_trace
        ):
            trace_json = json.dumps(
                eval_task_input.trace,
                indent=2,
                ensure_ascii=False,
                default=_trace_json_default,
            )

        async with self._save_context():
            eval_run = EvalRun(
                parent=job.eval_config,
                task_run_config_id=job.task_run_config.id,
                dataset_id=None,
                eval_input_id=eval_input.id,
                eval_config_eval=False,
                scores=result.scores,
                input=seed,
                output=leaf.output.output if result.skipped_reason is None else None,
                reference_data=eval_input.reference,
                skipped_reason=result.skipped_reason.value
                if result.skipped_reason
                else None,
                skipped_detail=result.skipped_detail,
                intermediate_outputs=result.intermediate_outputs,
                task_run_trace=trace_json,
            )
            eval_run.save_to_file()
        return True


def _trace_json_default(obj: object) -> object:
    """json.dumps `default` for stored traces: in-memory assistant turns carry
    MessageUsage (Pydantic). The whitelist stays narrow so any new non-JSON
    type fails loudly instead of leaking through a blanket str() fallback."""
    if isinstance(obj, MessageUsage):
        return obj.model_dump(mode="json")
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


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
