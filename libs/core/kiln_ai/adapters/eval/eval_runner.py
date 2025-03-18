import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Literal, Set

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.dataset_filters import dataset_filter_from_id
from kiln_ai.datamodel.eval import EvalConfig, EvalRun, EvalScores
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_run import TaskRun

logger = logging.getLogger(__name__)


@dataclass
class EvalJob:
    item: TaskRun
    type: Literal["task_run_eval", "eval_config_eval"]
    # If type == "task_run_eval", both of these should be set. If type == "eval_config_eval", only eval_config should be set.
    eval_config: EvalConfig
    task_run_config: TaskRunConfig | None = None


@dataclass
class EvalProgress:
    complete: int | None = None
    total: int | None = None
    errors: int | None = None


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

        self.eval_run_type = eval_run_type
        self.eval_configs = eval_configs
        self.run_configs = run_configs
        self.task = target_task
        self.eval = target_eval

    def collect_tasks(self) -> List[EvalJob]:
        if self.eval_run_type == "eval_config_eval":
            return self.collect_tasks_for_eval_config_eval()
        else:
            return self.collect_tasks_for_task_run_eval()

    def collect_tasks_for_eval_config_eval(self) -> List[EvalJob]:
        """
        Collect all jobs for this run, excluding any that have already been run.

        This variant is used for mode "eval_config_eval", using existing dataset run data (input/output).

        The tasks:
        - should be in the eval config set filter
        - should not have already been run for this eval config + dataset item pair
        """
        filter = dataset_filter_from_id(self.eval.eval_configs_filter_id)

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
        - should be in the eval set filter
        - should not have already been run for this eval config + run config + dataset item
        """
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

    async def run(self, concurrency: int = 25) -> AsyncGenerator[EvalProgress, None]:
        """
        Runs the configured eval run with parallel workers and yields progress updates.
        """
        jobs = self.collect_tasks()

        complete = 0
        errors = 0
        total = len(jobs)

        # Send initial status
        yield EvalProgress(complete=complete, total=total, errors=errors)

        worker_queue: asyncio.Queue[EvalJob] = asyncio.Queue()
        for job in jobs:
            worker_queue.put_nowait(job)

        # simple status queue to return progress. True=success, False=error
        status_queue: asyncio.Queue[bool] = asyncio.Queue()

        workers = []
        for i in range(concurrency):
            task = asyncio.create_task(self.run_worker(worker_queue, status_queue))
            workers.append(task)

        # Send status updates until workers are done, and they are all sent
        while not status_queue.empty() or not all(worker.done() for worker in workers):
            try:
                # Use timeout to prevent hanging if all workers complete
                # between our while condition check and get()
                success = await asyncio.wait_for(status_queue.get(), timeout=0.1)
                if success:
                    complete += 1
                else:
                    errors += 1

                yield EvalProgress(complete=complete, total=total, errors=errors)
            except asyncio.TimeoutError:
                # Timeout is expected, just continue to recheck worker status
                # Don't love this but beats sentinels for reliability
                continue

        # These are redundant, but keeping them will catch async errors
        await asyncio.gather(*workers)
        await worker_queue.join()

    async def run_worker(
        self, worker_queue: asyncio.Queue[EvalJob], status_queue: asyncio.Queue[bool]
    ):
        while True:
            try:
                job = worker_queue.get_nowait()
            except asyncio.QueueEmpty:
                # worker can end when the queue is empty
                break
            try:
                success = await self.run_job(job)
                await status_queue.put(success)
            finally:
                # Always mark the dequeued task as done, even on exceptions
                worker_queue.task_done()

    async def run_job(self, job: EvalJob) -> bool:
        try:
            # Create the evaluator for this eval config/run config pair
            evaluator = eval_adapter_from_type(job.eval_config.config_type)(
                job.eval_config,
                job.task_run_config.run_config() if job.task_run_config else None,
            )
            if not isinstance(evaluator, BaseEval):
                raise ValueError("Not able to create evaluator from eval config")

            task_output: str | None = None
            scores: EvalScores | None = None
            intermediate_outputs: Dict[str, str] | None = None
            if job.type == "eval_config_eval":
                # Eval config eval, we use the saved input from the task run, not invoking the task again
                scores, intermediate_outputs = await evaluator.run_eval(job.item)
                task_output = job.item.output.output
            else:
                # Task run eval, we invoke the task again to get a fresh output
                (
                    result_task_run,
                    scores,
                    intermediate_outputs,
                ) = await evaluator.run_task_and_eval(job.item.input)
                task_output = result_task_run.output.output

            # Save the job result
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
                intermediate_outputs=intermediate_outputs,
            )
            eval_run.save_to_file()

            return True
        except Exception as e:
            logger.error(f"Error running eval job for dataset item {job.item.id}: {e}")
            return False
