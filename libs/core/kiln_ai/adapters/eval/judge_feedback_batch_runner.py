# TODO (merge blocker — do not merge toward main until resolved): this runner is under design
# review. Concerns 3–5 are implemented here — the parallel eval-result store (JudgeFeedbackBatchRun
# vs EvalRun), the cache bypass on identical re-runs, and the paired-gate logic retrofitted onto
# tag-based sampling. Full write-up and rationale in the header of
# kiln_ai/datamodel/judge_feedback_batch.py. Resolve there before merging toward main.

"""Execute a JudgeFeedbackBatch: sample dataset items by tag, judge them, persist per-item results.

A JudgeFeedbackBatch samples dataset items carrying its target tags, runs the configured judge (eval config)
over each item's existing output, and records pass/fail + the judge's feedback as child JudgeFeedbackBatchRuns
— surfacing a minibatch of failing examples for reflective prompt optimization.

The run is synchronous: it judges in "eval_config_eval" mode (no task re-run), persists each result
as a child run, and returns a summary (the failing runs + counts + any per-item errors). The counts
and errors are returned as FYI for the caller's loop decisions; the durable record is the persisted
JudgeFeedbackBatchRun children. Per-item judge/save errors don't abort the run — they're collected and returned
so the caller can see partial failures, and re-running the job retries only the un-persisted items.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from kiln_ai.adapters.adapter_registry import load_skills_for_task
from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.eval_runner import _is_retryable_error
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.adapters.model_adapters.base_adapter import SkillsDict
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalDataType,
    EvalOutputScore,
    EvalScores,
)
from kiln_ai.datamodel.judge_feedback_batch import (
    JudgeFeedbackBatch,
    JudgeFeedbackBatchRun,
)
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.datamodel.usage import Usage
from kiln_ai.utils.async_job_runner import jittered_backoff_delay
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context

logger = logging.getLogger(__name__)

# Default "pass" bar on the normalized 0-1 scale. 0.75 matches the four-star / is_high_quality
# threshold for five_star scores (normalize_rating(4, five_star) == 0.75).
DEFAULT_FAILURE_THRESHOLD = 0.75


def _error_detail(error: BaseException) -> str:
    """The most informative message for a failed item's error log.

    The model adapter wraps failures in `KilnRunError`, whose own message is the user-friendly
    (often generic) `format_error_message` text; the underlying cause survives on `.original`, so
    surface that for the developer-facing error log. Mirrors `EvalJobWorker._error_detail`.
    """
    if isinstance(error, KilnRunError) and error.original is not None:
        return str(error.original)
    return str(error)


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


def aggregate_normalized_scores(
    runs: list[JudgeFeedbackBatchRun], output_scores: list[EvalOutputScore]
) -> dict[str, float]:
    """Mean normalized (0-1, higher = better) score per non-custom dimension over the judged runs.

    This is the continuous signal that the binary pass/fail collapses away — usable directly as a
    gate / loss metric (e.g. compare a candidate's mean against the baseline's) instead of just a
    failure count, so a 2★→3★ improvement is visible rather than reading as zero gradient.
    """
    aggregated: dict[str, float] = {}
    for score in output_scores:
        if score.type == TaskOutputRatingType.custom:
            continue
        key = score.json_key()
        values: list[float] = []
        for run in runs:
            value = run.scores.get(key)
            if value is None:
                continue
            try:
                values.append(normalize_rating(value, score.type))
            except (ValueError, TypeError):
                continue
        if values:
            aggregated[key] = sum(values) / len(values)
    return aggregated


def aggregate_usage(
    runs: list[JudgeFeedbackBatchRun],
) -> tuple[Usage | None, float | None, float | None]:
    """Sum token/cost/latency across the runs that carried usage (generate_outputs mode).

    The deterministic counterpart to ``aggregate_normalized_scores`` — lets the caller weigh a
    candidate's quality against its cost/latency (a Pareto axis) instead of quality alone. Returns
    ``(total_usage, mean_cost, mean_latency_ms)``. ``total_usage`` is the field-wise sum (via
    ``Usage.__add__``) over runs whose ``usage`` is set; the means divide only by the runs that
    actually reported that field. All three are ``None`` when no run carried usage (judge-only mode).
    """
    usages = [run.usage for run in runs if run.usage is not None]
    if not usages:
        return None, None, None

    total: Usage = Usage()
    for usage in usages:
        total = total + usage

    costs = [u.cost for u in usages if u.cost is not None]
    mean_cost = sum(costs) / len(costs) if costs else None
    latencies = [
        u.total_llm_latency_ms for u in usages if u.total_llm_latency_ms is not None
    ]
    mean_latency_ms = sum(latencies) / len(latencies) if latencies else None
    return total, mean_cost, mean_latency_ms


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


class JudgeFeedbackBatchItemError(BaseModel):
    """An error judging or persisting a single item. Surfaced so the caller can see partial failures."""

    task_run_id: str = Field(
        description="The ID of the task run (dataset item) that errored."
    )
    error: str = Field(description="The error message.")


@dataclass
class JudgeFeedbackBatchRunResult:
    """The result of running a JudgeFeedbackBatch. Counts and errors are FYI for the caller; not persisted."""

    failing_runs: list[JudgeFeedbackBatchRun]
    judged_runs: list[JudgeFeedbackBatchRun]
    # num_judged counts every item ATTEMPTED this run (errored and cached items included), so it can
    # exceed len(judged_runs) when items errored. For a scored-item count (e.g. a fail rate), use
    # failing_count / len(judged_runs), NOT failing_count / num_judged.
    num_judged: int
    failing_count: int
    train_set_size: int
    hit_cap: bool
    errors: list[JudgeFeedbackBatchItemError] = field(default_factory=list)
    # Continuous signal (P1): mean normalized score per dimension over judged_runs, and overall.
    mean_normalized_scores: dict[str, float] = field(default_factory=dict)
    mean_normalized_score: float | None = None
    # Deterministic signal: token/cost/latency for generating the judged outputs (generate_outputs
    # mode only — None when existing dataset outputs were judged, since nothing was generated). The
    # total is the sum across judged_runs; the means divide by the count that actually carried usage.
    total_usage: Usage | None = None
    mean_cost: float | None = None
    mean_latency_ms: float | None = None


@dataclass
class _ScoredItem:
    """The outcome of judging a single item: a run (unless the judge errored), pass/fail, and an
    optional error (judge or save failure) to surface to the caller."""

    run: JudgeFeedbackBatchRun | None = None
    passed: bool = False
    error: JudgeFeedbackBatchItemError | None = None


# Called after each judged chunk with (num_judged, error_count, planned_total), where
# planned_total is the number of items this run will judge (the tag-matched set capped at
# max_samples). Lets a background job stream live progress instead of only a final snapshot.
JudgeProgressCallback = Callable[[int, int, int], Awaitable[None]]

# Called once per item error the moment it's collected (not batched to the end), so a background
# job can write it to its error log live — otherwise the "View Errors" button appears mid-run (the
# streamed error count is non-zero) but the log is still empty until the run finishes.
JudgeErrorCallback = Callable[["JudgeFeedbackBatchItemError"], Awaitable[None]]


class JudgeFeedbackBatchRunner:
    """Runs a JudgeFeedbackBatch: judges tagged dataset items and persists per-item results."""

    def __init__(
        self,
        judge_feedback_batch: JudgeFeedbackBatch,
        eval_config: EvalConfig,
        save_context: SaveContext | None = None,
        rng: random.Random | None = None,
        max_retries: int = 2,
        retry_delay: float = 2.0,
    ):
        task = judge_feedback_batch.parent_task()
        if task is None:
            raise ValueError("Judge feedback batch must have a parent task")
        eval = eval_config.parent_eval()
        if eval is None:
            raise ValueError("Eval config must have a parent eval")

        # Reference-answer evals compare a generated output against the dataset reference; judging an
        # existing output has nothing to compare against (run_eval would raise per item). Reject it
        # here too (the API validates upstream) as a last line of defense.
        if (
            eval.evaluation_data_type == EvalDataType.reference_answer
            and not judge_feedback_batch.generate_outputs
        ):
            raise ValueError(
                "Reference-answer evals can't judge existing outputs (no reference to compare "
                "against). Set generate_outputs=true."
            )

        self.judge_feedback_batch = judge_feedback_batch
        self.eval_config = eval_config
        self.task = task
        self.eval = eval
        self._save_context: SaveContext = save_context or default_save_context
        self._rng = rng or random.Random()
        self._max_retries = max_retries
        self._retry_delay = retry_delay

        # In generate mode we run a candidate config to produce the output before judging it, so we
        # resolve its RunConfigProperties (the evaluator's 2nd arg) and preload its skills.
        self._run_config_properties: RunConfigProperties | None = None
        self._skills: SkillsDict = {}
        if judge_feedback_batch.generate_outputs:
            run_config = next(
                (
                    rc
                    for rc in task.run_configs()
                    if rc.id == judge_feedback_batch.run_config_id
                ),
                None,
            )
            if run_config is None:
                raise ValueError(
                    f"Run config not found for generate mode: {judge_feedback_batch.run_config_id}"
                )
            self._run_config_properties = run_config.run_config_properties
            self._skills = load_skills_for_task(task, run_config.run_config_properties)

    def _matches_tags(self, task_run: TaskRun) -> bool:
        # AND semantics: the item must carry every target tag.
        return set(self.judge_feedback_batch.target_tags or []) <= set(
            task_run.tags or []
        )

    async def run(
        self,
        concurrency: int | None = None,
        progress_callback: JudgeProgressCallback | None = None,
        error_callback: JudgeErrorCallback | None = None,
    ) -> JudgeFeedbackBatchRunResult:
        """Judge tagged dataset items and persist each result as a JudgeFeedbackBatchRun child.

        Two modes, set by `stop_after_failures`:
        - None (gate): judge the WHOLE matching set up to `max_samples` — full coverage, so the
          caller can pair `judged_runs` by task_run_id against another run.
        - set (train signal): stop early once that many failures are found (a cheap minibatch).

        `progress_callback`, if given, is awaited after each judged chunk with
        (num_judged, error_count, planned_total) so a background job can stream live progress;
        the synchronous endpoint leaves it None. `error_callback`, if given, is awaited once per
        item error the moment it's collected, so a job can log errors live (they still appear in the
        returned result too); the synchronous endpoint leaves it None and reads result.errors.

        Returns the failing runs, all judged runs, counts, and any per-item errors. Per-item errors
        are collected (not raised), so one bad item never aborts the run; the item is left
        un-persisted and a later re-run will retry it.
        """
        job = self.judge_feedback_batch
        stop_after = job.stop_after_failures
        # Generating runs a model per item (heavier than judging an existing output), so default to
        # a smaller concurrency in that mode.
        if concurrency is None:
            concurrency = 5 if job.generate_outputs else 25
        # A caller-supplied concurrency of 0 would make range() raise; negatives would mis-chunk.
        concurrency = max(1, concurrency)

        candidates = [
            run for run in self.task.runs(readonly=True) if self._matches_tags(run)
        ]
        train_set_size = len(candidates)
        if stop_after is None:
            # Gate mode: select deterministically (sorted by id) before capping, so two runs over
            # the same tag set (e.g. candidate vs baseline batch) cover the SAME task_run_ids and can
            # be paired. A random sample would pick disjoint subsets whenever the matching set
            # exceeds max_samples, silently defeating the pairing this mode exists for.
            candidates.sort(key=lambda run: str(run.id))
        else:
            # Train-signal mode: a random minibatch is fine (and desirable for variety), since the
            # caller only wants some failing examples, not a stable paired subset.
            self._rng.shuffle(candidates)
        candidates = candidates[: job.max_samples]

        # Reuse previously-judged results to avoid re-paying the judge — but only when judging
        # existing outputs. Generation is non-deterministic, so a cached result would be stale.
        cache: dict[ID_TYPE, JudgeFeedbackBatchRun] = (
            {}
            if job.generate_outputs
            else {run.task_run_id: run for run in job.runs(readonly=True)}
        )

        evaluator = eval_adapter_from_type(self.eval_config.config_type)(
            self.eval_config, self._run_config_properties, skills=self._skills
        )
        if not isinstance(evaluator, BaseEval):
            raise ValueError("Not able to create evaluator from eval config")

        failing_runs: list[JudgeFeedbackBatchRun] = []
        judged_runs: list[JudgeFeedbackBatchRun] = []
        errors: list[JudgeFeedbackBatchItemError] = []
        num_judged = 0

        # Judge in concurrent chunks. In train-signal mode we can stop early once we have enough
        # failures (a chunk may over-judge by up to concurrency-1 items past the stopping point).
        for start in range(0, len(candidates), concurrency):
            chunk = candidates[start : start + concurrency]
            # return_exceptions=True so one item's unexpected throw can't discard the rest of the
            # chunk's results. _score_one is written not to raise, but post-judge processing (or a
            # bug) could; we convert any escaped exception into a per-item error below.
            results = await asyncio.gather(
                *(self._score_one(evaluator, task_run, cache) for task_run in chunk),
                return_exceptions=True,
            )
            for task_run, scored in zip(chunk, results):
                num_judged += 1
                if isinstance(scored, BaseException):
                    logger.error(
                        "Unexpected error judging item %s for judge feedback batch %s",
                        task_run.id,
                        self.judge_feedback_batch.id,
                        exc_info=scored,
                    )
                    unexpected_error = JudgeFeedbackBatchItemError(
                        task_run_id=str(task_run.id),
                        error=f"Unexpected error judging item: {_error_detail(scored)}",
                    )
                    errors.append(unexpected_error)
                    if error_callback is not None:
                        await error_callback(unexpected_error)
                    continue
                if scored.error is not None:
                    errors.append(scored.error)
                    if error_callback is not None:
                        await error_callback(scored.error)
                if scored.run is not None:
                    judged_runs.append(scored.run)
                    if not scored.passed:
                        failing_runs.append(scored.run)
            # Stream live progress against the planned (capped) count so a background job's bar
            # advances per chunk and reaches 100% on full coverage.
            if progress_callback is not None:
                await progress_callback(num_judged, len(errors), len(candidates))
            # Gate mode (stop_after is None) judges the whole set; only the train signal stops early.
            if stop_after is not None and len(failing_runs) >= stop_after:
                break

        failing_count = len(failing_runs)
        if stop_after is not None:
            returned_failing = failing_runs[:stop_after]
            hit_cap = failing_count < stop_after and num_judged >= job.max_samples
        else:
            returned_failing = failing_runs
            # In gate mode we judge everything; "capped" means the matching set exceeded max_samples.
            hit_cap = train_set_size > job.max_samples

        per_dimension = aggregate_normalized_scores(
            judged_runs, self.eval.output_scores
        )
        # Mean-of-means: each dimension is weighted equally regardless of how many runs carried a
        # value for it (a dimension scored on 2 runs counts as much as one scored on 50). This is a
        # simple overall gate signal, not a flat mean over every individual score.
        overall = (
            sum(per_dimension.values()) / len(per_dimension) if per_dimension else None
        )
        total_usage, mean_cost, mean_latency_ms = aggregate_usage(judged_runs)

        return JudgeFeedbackBatchRunResult(
            failing_runs=returned_failing,
            judged_runs=judged_runs,
            num_judged=num_judged,
            failing_count=failing_count,
            train_set_size=train_set_size,
            hit_cap=hit_cap,
            errors=errors,
            mean_normalized_scores=per_dimension,
            mean_normalized_score=overall,
            total_usage=total_usage,
            mean_cost=mean_cost,
            mean_latency_ms=mean_latency_ms,
        )

    async def _score_one(
        self,
        evaluator: BaseEval,
        task_run: TaskRun,
        cache: dict[ID_TYPE, JudgeFeedbackBatchRun],
    ) -> _ScoredItem:
        """Judge one item (or reuse a cached result) and persist a JudgeFeedbackBatchRun.

        Never raises: a judge or save failure is logged and returned as an error on the result so the
        caller can surface it. A judge error yields no run (the item is skipped and left un-persisted,
        so a later re-run retries it); a save error still returns the in-memory run and pass/fail.
        """
        existing = cache.get(task_run.id)
        if existing is not None:
            return _ScoredItem(run=existing, passed=existing.passed)

        try:
            scores, intermediate_outputs, usage = await self._judge_with_retry(
                evaluator, task_run
            )
        except Exception as e:
            logger.error(
                "Error judging item %s for judge feedback batch %s",
                task_run.id,
                self.judge_feedback_batch.id,
                exc_info=True,
            )
            return _ScoredItem(
                error=JudgeFeedbackBatchItemError(
                    task_run_id=str(task_run.id),
                    error=f"Error judging item: {_error_detail(e)}",
                )
            )

        passed = not example_fails(
            scores, self.eval.output_scores, self.judge_feedback_batch.threshold
        )
        feedback = feedback_from_intermediate_outputs(intermediate_outputs)
        judge_feedback_batch_run = JudgeFeedbackBatchRun(
            parent=self.judge_feedback_batch,
            task_run_id=task_run.id,
            run_config_id=(
                self.judge_feedback_batch.run_config_id
                if self.judge_feedback_batch.generate_outputs
                else None
            ),
            scores=scores,
            feedback=feedback,
            passed=passed,
            usage=usage,
        )

        # Best-effort persistence: a save failure must not crash the whole concurrent batch. We keep
        # the in-memory result (so the failing example is still returned) but report the save error.
        save_error: JudgeFeedbackBatchItemError | None = None
        try:
            async with self._save_context():
                judge_feedback_batch_run.save_to_file()
        except Exception as e:
            logger.error(
                "Error saving judge feedback batch run for item %s in judge feedback batch %s",
                task_run.id,
                self.judge_feedback_batch.id,
                exc_info=True,
            )
            save_error = JudgeFeedbackBatchItemError(
                task_run_id=str(task_run.id),
                error=f"Error saving judge result: {_error_detail(e)}",
            )

        return _ScoredItem(
            run=judge_feedback_batch_run, passed=passed, error=save_error
        )

    async def _judge_with_retry(
        self, evaluator: BaseEval, task_run: TaskRun
    ) -> tuple[EvalScores, dict[str, str] | None, Usage | None]:
        """Judge one item, retrying transient (rate-limit / connection) errors.

        Generating or judging invokes a model, so transient failures are expected; without a retry
        they'd be collected as per-item errors and silently shrink coverage (skewing a gate). Reuses
        the eval runner's transient-error classification. Raises on a non-transient error or once
        retries are exhausted — the caller turns that into a collected JudgeFeedbackBatchItemError.
        Background jobs override the constructor's retry defaults with a more patient schedule.

        Returns the judge's scores, its intermediate outputs, and — in generate_outputs mode — the
        generation's token/cost/latency Usage (None when an existing output was judged, since nothing
        was generated). The fresh TaskRun is still discarded (never persisted); only its usage is kept.
        """
        last_error: Exception | None = None
        for attempt in range(1 + self._max_retries):
            try:
                if self.judge_feedback_batch.generate_outputs:
                    # Run the candidate config to produce a fresh output, then judge it. The fresh
                    # TaskRun is returned un-saved (allow_saving=False) and not persisted — we keep
                    # only the JudgeFeedbackBatchRun (and the run's usage), never polluting the
                    # dataset.
                    (
                        fresh_run,
                        scores,
                        intermediate,
                    ) = await evaluator.run_task_and_eval(task_run)
                    return scores, intermediate, fresh_run.usage
                scores, intermediate = await evaluator.run_eval(task_run)
                return scores, intermediate, None
            except Exception as e:
                last_error = e
                if not (_is_retryable_error(e) and attempt < self._max_retries):
                    break
                await asyncio.sleep(jittered_backoff_delay(self._retry_delay, attempt))
        assert last_error is not None  # the loop runs at least once
        raise last_error
