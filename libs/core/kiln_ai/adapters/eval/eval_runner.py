import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Literal, Set

import litellm

from kiln_ai.adapters.adapter_registry import load_skills_for_task
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
from kiln_ai.datamodel.basemodel import ID_TYPE
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
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_run import TaskRun, Usage
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
    1) eval_config_eval: evaluate an eval config using existing dataset items.
    2) task_run_eval: evaluate a range of task run configs, generating new run output using existing dataset item input.
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

    def collect_tasks(self) -> List[EvalJob]:
        if self._source_mode == "eval_input":
            return self.collect_tasks_for_eval_input()
        elif self.eval_run_type == "eval_config_eval":
            if self.eval.eval_configs_filter_id is not None:
                return self.collect_tasks_for_eval_config_eval(
                    self.eval.eval_configs_filter_id
                )
            else:
                raise ValueError(
                    "Eval configs filter ID is required for eval runs of type 'eval_config_eval'"
                )
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
        """Collect jobs from EvalInput items under the task."""
        filter_id = self.eval.eval_input_filter_id
        if filter_id is None:
            raise ValueError(
                "eval_input_filter_id is required for eval_input source mode"
            )
        input_filter = eval_input_filter_from_id(filter_id)

        if self.eval_run_type == "task_run_eval":
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
        else:
            already_run_ec: Dict[ID_TYPE, Set[ID_TYPE]] = {}
            for eval_config in self.eval_configs:
                already_run_ec[eval_config.id] = set()
                for run in eval_config.runs(readonly=True):
                    if run.eval_input_id is not None:
                        already_run_ec[eval_config.id].add(run.eval_input_id)

            jobs_ec: List[EvalJob] = []
            for eval_input in self.task.eval_inputs(readonly=True):
                if not input_filter(eval_input):
                    continue
                for eval_config in self.eval_configs:
                    if eval_input.id in already_run_ec[eval_config.id]:
                        continue
                    jobs_ec.append(
                        EvalJob(
                            item=eval_input,
                            eval_config=eval_config,
                            type=self.eval_run_type,
                        )
                    )
            return jobs_ec

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
                raise RetryableError(str(e)) from e
            logger.error(
                f"Error running eval job for dataset item {job.item.id}: {e}",
                exc_info=True,
            )
            raise

    async def _run_legacy_job(self, job: EvalJob) -> bool:
        if not isinstance(job.item, TaskRun):
            raise ValueError("Legacy eval jobs require a TaskRun item")

        evaluator = eval_adapter_from_type(job.eval_config)(
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

        is_multi_turn = (
            isinstance(job.item, TaskRun) and job.item.parent_task_run_id is not None
        ) or (
            isinstance(job.item, EvalInput)
            and isinstance(job.item.data, MultiTurnSyntheticEvalInputData)
        )
        if is_multi_turn:
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
                    skipped_reason=SkippedReason.incompatible_input_shape.value,
                    skipped_detail="V2 evals do not yet support multi-turn inputs",
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
            scores, skipped_reason, skipped_detail = await evaluator.evaluate(
                eval_task_input
            )

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=None,
                    eval_input_id=job.item.id,
                    eval_config_eval=False,
                    scores=scores,
                    input=early_input_str,
                    output=run_output.output.output if skipped_reason is None else None,
                    reference_data=job.item.reference,
                    skipped_reason=skipped_reason.value if skipped_reason else None,
                    skipped_detail=skipped_detail,
                )
                eval_run.save_to_file()
            return True

        if job.type == "task_run_eval":
            run_output = await evaluator.run_task(job.item)
            eval_task_input = EvalTaskInput.from_task_run(run_output)
            scores, skipped_reason, skipped_detail = await evaluator.evaluate(
                eval_task_input
            )
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
                    scores=scores,
                    input=task_input_str,
                    output=task_output if skipped_reason is None else None,
                    reference_data=eval_task_input.reference_data,
                    skipped_reason=skipped_reason.value if skipped_reason else None,
                    skipped_detail=skipped_detail,
                )
                eval_run.save_to_file()
            return True
        else:
            eval_task_input = EvalTaskInput.from_task_run(job.item)
            dataset_id = job.item.id
            task_input_str = job.item.input
            task_output = job.item.output.output

            scores, skipped_reason, skipped_detail = await evaluator.evaluate(
                eval_task_input
            )

            async with self._save_context():
                eval_run = EvalRun(
                    parent=job.eval_config,
                    task_run_config_id=job.task_run_config.id
                    if job.task_run_config
                    else None,
                    dataset_id=dataset_id,
                    eval_input_id=None,
                    eval_config_eval=True,
                    scores=scores,
                    input=task_input_str,
                    output=task_output if skipped_reason is None else None,
                    reference_data=eval_task_input.reference_data,
                    skipped_reason=skipped_reason.value if skipped_reason else None,
                    skipped_detail=skipped_detail,
                )
                eval_run.save_to_file()
            return True


def _is_retryable_error(e: BaseException) -> bool:
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
