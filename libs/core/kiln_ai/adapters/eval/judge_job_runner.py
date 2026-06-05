"""Execute a JudgeJob: sample dataset items by tag, judge them, persist results + status.

A JudgeJob samples dataset items carrying its target tags, runs the configured judge (eval config)
over each item's existing output, and records pass/fail + the judge's feedback as child JudgeJobRuns
— surfacing a minibatch of failing examples for reflective prompt optimization.

The runner mirrors EvalRunner (eval_runner.py): it judges in "eval_config_eval" mode (no task
re-run), yields Progress for SSE streaming, and persists results as it goes. It also updates the
JudgeJob's latest_status/outcome so a run is a durable, pollable record.
"""

import asyncio
import logging
import random
from typing import AsyncGenerator

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalConfig, EvalOutputScore, EvalScores
from kiln_ai.datamodel.judge_job import (
    JudgeJob,
    JudgeJobOutcome,
    JudgeJobRun,
    JudgeJobStatus,
)
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.async_job_runner import Progress
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context
from kiln_ai.utils.lock import shared_async_lock_manager

logger = logging.getLogger(__name__)

# Default "pass" bar on the normalized 0-1 scale. 0.75 matches the four-star / is_high_quality
# threshold for five_star scores (normalize_rating(4, five_star) == 0.75).
DEFAULT_FAILURE_THRESHOLD = 0.75


def score_passes(
    value: float, score_type: TaskOutputRatingType, threshold: float
) -> bool:
    """Whether an eval score counts as a 'pass' (at/above the bar) on a normalized 0-1 scale."""
    try:
        normalized = normalize_rating(value, score_type)
    except ValueError:
        # Out-of-range or non-normalizable (e.g. custom) scores can't clear the bar.
        return False
    return normalized >= threshold


def example_fails(
    scores: EvalScores, output_scores: list[EvalOutputScore], threshold: float
) -> bool:
    """An example 'fails' only if ALL of the eval's (non-custom) output scores are below the bar."""
    relevant = [s for s in output_scores if s.type != TaskOutputRatingType.custom]
    if not relevant:
        return False
    for score in relevant:
        value = scores.get(score.json_key())
        # A missing score can't be confirmed as a pass, so treat it as failing and keep checking.
        if value is not None and score_passes(value, score.type, threshold):
            return False
    return True


def feedback_from_intermediate_outputs(
    intermediate_outputs: dict[str, str] | None,
) -> str | None:
    """Extract a single plaintext feedback string from a judge's intermediate outputs."""
    if not intermediate_outputs:
        return None
    for key in ("reasoning", "chain_of_thought"):
        value = intermediate_outputs.get(key)
        if value and value.strip():
            return value.strip()
    combined = "\n\n".join(
        f"{key}: {value}"
        for key, value in intermediate_outputs.items()
        if value and value.strip()
    )
    return combined or None


class JudgeJobRunner:
    """Runs a JudgeJob: judges tagged dataset items and persists results + status."""

    def __init__(
        self,
        judge_job: JudgeJob,
        eval_config: EvalConfig,
        save_context: SaveContext | None = None,
        rng: random.Random | None = None,
    ):
        task = judge_job.parent_task()
        if task is None:
            raise ValueError("Judge job must have a parent task")
        eval = eval_config.parent_eval()
        if eval is None:
            raise ValueError("Eval config must have a parent eval")

        self.judge_job = judge_job
        self.eval_config = eval_config
        self.task = task
        self.eval = eval
        self._save_context: SaveContext = save_context or default_save_context
        self._rng = rng or random.Random()

    def _matches_tags(self, task_run: TaskRun) -> bool:
        # AND semantics: the item must carry every target tag.
        return set(self.judge_job.target_tags) <= set(task_run.tags)

    async def run(self, concurrency: int = 25) -> AsyncGenerator[Progress, None]:
        """Run the judge job, yielding Progress updates and persisting results + status."""
        job = self.judge_job
        train_set_size = 0
        num_judged = 0
        failures = 0
        errors = 0

        try:
            await self._set_status(JudgeJobStatus.running)

            candidates = [
                run for run in self.task.runs(readonly=True) if self._matches_tags(run)
            ]
            train_set_size = len(candidates)
            self._rng.shuffle(candidates)
            candidates = candidates[: job.max_samples]

            # Reuse previously-judged results for this job to avoid re-paying the judge.
            cache: dict[ID_TYPE, JudgeJobRun] = {
                run.dataset_id: run for run in job.runs(readonly=True)
            }

            evaluator = eval_adapter_from_type(self.eval_config.config_type)(
                self.eval_config, None
            )
            if not isinstance(evaluator, BaseEval):
                raise ValueError("Not able to create evaluator from eval config")

            total = len(candidates)
            yield Progress(complete=0, total=total, errors=0)

            # Judge in concurrent chunks so we can stop early once we have enough failures
            # (a chunk may over-judge by up to concurrency-1 items past the stopping point).
            for start in range(0, len(candidates), concurrency):
                chunk = candidates[start : start + concurrency]
                results = await asyncio.gather(
                    *(self._score_one(evaluator, task_run, cache) for task_run in chunk)
                )
                for scored in results:
                    num_judged += 1
                    if scored is None:
                        errors += 1
                    elif not scored:  # passed == False
                        failures += 1
                    yield Progress(complete=num_judged, total=total, errors=errors)
                if failures >= job.count:
                    break

            hit_cap = failures < job.count and num_judged >= job.max_samples
            await self._finish(
                JudgeJobStatus.succeeded,
                JudgeJobOutcome(
                    train_set_size=train_set_size,
                    num_judged=num_judged,
                    failing_count=failures,
                    hit_cap=hit_cap,
                ),
            )
        except Exception as e:
            logger.error("Judge job %s failed: %s", job.id, e, exc_info=True)
            await self._finish(
                JudgeJobStatus.failed,
                JudgeJobOutcome(
                    train_set_size=train_set_size,
                    num_judged=num_judged,
                    failing_count=failures,
                    hit_cap=False,
                    error=str(e),
                ),
            )

    async def _score_one(
        self,
        evaluator: BaseEval,
        task_run: TaskRun,
        cache: dict[ID_TYPE, JudgeJobRun],
    ) -> bool | None:
        """Judge one item (or reuse a cached result), persist a JudgeJobRun, return `passed`.

        Returns None if the judge errored on this item (logged + skipped by the caller).
        """
        existing = cache.get(task_run.id)
        if existing is not None:
            return existing.passed

        try:
            scores, intermediate_outputs = await evaluator.run_eval(task_run)
        except Exception:
            logger.error(
                "Error judging item %s for judge job %s",
                task_run.id,
                self.judge_job.id,
                exc_info=True,
            )
            return None

        passed = not example_fails(
            scores, self.eval.output_scores, self.judge_job.threshold
        )
        feedback = feedback_from_intermediate_outputs(intermediate_outputs)

        # Best-effort persistence: a save failure must not crash the whole concurrent batch.
        try:
            async with self._save_context():
                JudgeJobRun(
                    parent=self.judge_job,
                    dataset_id=task_run.id,
                    scores=scores,
                    feedback=feedback,
                    passed=passed,
                ).save_to_file()
        except Exception:
            logger.error(
                "Error saving judge job run for item %s in judge job %s",
                task_run.id,
                self.judge_job.id,
                exc_info=True,
            )

        return passed

    async def _set_status(self, status: JudgeJobStatus) -> None:
        async with shared_async_lock_manager.acquire(str(self.judge_job.id)):
            self.judge_job.latest_status = status
            async with self._save_context():
                self.judge_job.save_to_file()

    async def _finish(self, status: JudgeJobStatus, outcome: JudgeJobOutcome) -> None:
        async with shared_async_lock_manager.acquire(str(self.judge_job.id)):
            self.judge_job.latest_status = status
            self.judge_job.outcome = outcome
            async with self._save_context():
                self.judge_job.save_to_file()
