"""Execute a JudgeJob: sample dataset items by tag, judge them, persist per-item results.

A JudgeJob samples dataset items carrying its target tags, runs the configured judge (eval config)
over each item's existing output, and records pass/fail + the judge's feedback as child JudgeJobRuns
— surfacing a minibatch of failing examples for reflective prompt optimization.

The run is synchronous: it judges in "eval_config_eval" mode (no task re-run), persists each result
as a child run, and returns a summary (the failing runs + counts + any per-item errors). The counts
and errors are returned as FYI for the caller's loop decisions; the durable record is the persisted
JudgeJobRun children. Per-item judge/save errors don't abort the run — they're collected and returned
so the caller can see partial failures, and re-running the job retries only the un-persisted items.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalConfig, EvalOutputScore, EvalScores
from kiln_ai.datamodel.judge_job import JudgeJob, JudgeJobRun
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context

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
    except (ValueError, TypeError):
        # Out-of-range, non-numeric, or non-normalizable (e.g. custom) scores can't clear the bar.
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
        if isinstance(value, str) and value.strip():
            return value.strip()
    combined = "\n\n".join(
        f"{key}: {value}"
        for key, value in intermediate_outputs.items()
        if isinstance(value, str) and value.strip()
    )
    return combined or None


class JudgeJobItemError(BaseModel):
    """An error judging or persisting a single item. Surfaced so the caller can see partial failures."""

    task_run_id: str = Field(
        description="The ID of the task run (dataset item) that errored."
    )
    error: str = Field(description="The error message.")


@dataclass
class JudgeJobRunResult:
    """The result of running a JudgeJob. Counts and errors are FYI for the caller; not persisted."""

    failing_runs: list[JudgeJobRun]
    num_judged: int
    failing_count: int
    train_set_size: int
    hit_cap: bool
    errors: list[JudgeJobItemError] = field(default_factory=list)


@dataclass
class _ScoredItem:
    """The outcome of judging a single item: a run (unless the judge errored), pass/fail, and an
    optional error (judge or save failure) to surface to the caller."""

    run: JudgeJobRun | None = None
    passed: bool = False
    error: JudgeJobItemError | None = None


class JudgeJobRunner:
    """Runs a JudgeJob: judges tagged dataset items and persists per-item results."""

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
        return set(self.judge_job.target_tags or []) <= set(task_run.tags or [])

    async def run(self, concurrency: int = 25) -> JudgeJobRunResult:
        """Judge tagged dataset items until `count` failures are found or `max_samples` are judged.

        Persists each result as a JudgeJobRun child and returns the failing runs + counts + any
        per-item errors. Per-item errors are collected (not raised), so one bad item never aborts
        the run; the item is left un-persisted and a later re-run will retry it.
        """
        job = self.judge_job

        candidates = [
            run for run in self.task.runs(readonly=True) if self._matches_tags(run)
        ]
        train_set_size = len(candidates)
        self._rng.shuffle(candidates)
        candidates = candidates[: job.max_samples]

        # Reuse previously-judged results for this job to avoid re-paying the judge.
        cache: dict[ID_TYPE, JudgeJobRun] = {
            run.task_run_id: run for run in job.runs(readonly=True)
        }

        evaluator = eval_adapter_from_type(self.eval_config.config_type)(
            self.eval_config, None
        )
        if not isinstance(evaluator, BaseEval):
            raise ValueError("Not able to create evaluator from eval config")

        failing_runs: list[JudgeJobRun] = []
        errors: list[JudgeJobItemError] = []
        num_judged = 0

        # Judge in concurrent chunks so we can stop early once we have enough failures
        # (a chunk may over-judge by up to concurrency-1 items past the stopping point).
        for start in range(0, len(candidates), concurrency):
            chunk = candidates[start : start + concurrency]
            results = await asyncio.gather(
                *(self._score_one(evaluator, task_run, cache) for task_run in chunk)
            )
            for scored in results:
                num_judged += 1
                if scored.error is not None:
                    errors.append(scored.error)
                if scored.run is not None and not scored.passed:
                    failing_runs.append(scored.run)
            if len(failing_runs) >= job.count:
                break

        hit_cap = len(failing_runs) < job.count and num_judged >= job.max_samples
        return JudgeJobRunResult(
            failing_runs=failing_runs[: job.count],
            num_judged=num_judged,
            failing_count=len(failing_runs),
            train_set_size=train_set_size,
            hit_cap=hit_cap,
            errors=errors,
        )

    async def _score_one(
        self,
        evaluator: BaseEval,
        task_run: TaskRun,
        cache: dict[ID_TYPE, JudgeJobRun],
    ) -> _ScoredItem:
        """Judge one item (or reuse a cached result) and persist a JudgeJobRun.

        Never raises: a judge or save failure is logged and returned as an error on the result so the
        caller can surface it. A judge error yields no run (the item is skipped and left un-persisted,
        so a later re-run retries it); a save error still returns the in-memory run and pass/fail.
        """
        existing = cache.get(task_run.id)
        if existing is not None:
            return _ScoredItem(run=existing, passed=existing.passed)

        try:
            scores, intermediate_outputs = await evaluator.run_eval(task_run)
        except Exception as e:
            logger.error(
                "Error judging item %s for judge job %s",
                task_run.id,
                self.judge_job.id,
                exc_info=True,
            )
            return _ScoredItem(
                error=JudgeJobItemError(
                    task_run_id=str(task_run.id),
                    error=f"Error judging item: {e}",
                )
            )

        passed = not example_fails(
            scores, self.eval.output_scores, self.judge_job.threshold
        )
        feedback = feedback_from_intermediate_outputs(intermediate_outputs)
        judge_job_run = JudgeJobRun(
            parent=self.judge_job,
            task_run_id=task_run.id,
            scores=scores,
            feedback=feedback,
            passed=passed,
        )

        # Best-effort persistence: a save failure must not crash the whole concurrent batch. We keep
        # the in-memory result (so the failing example is still returned) but report the save error.
        save_error: JudgeJobItemError | None = None
        try:
            async with self._save_context():
                judge_job_run.save_to_file()
        except Exception as e:
            logger.error(
                "Error saving judge job run for item %s in judge job %s",
                task_run.id,
                self.judge_job.id,
                exc_info=True,
            )
            save_error = JudgeJobItemError(
                task_run_id=str(task_run.id),
                error=f"Error saving judge result: {e}",
            )

        return _ScoredItem(run=judge_job_run, passed=passed, error=save_error)
