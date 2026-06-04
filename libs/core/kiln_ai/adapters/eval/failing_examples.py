"""Sample an Eval's train set, run its judge (EvalConfig), and return failing examples.

This is the local, in-loop building block for GEPA-style reflective optimization: draw datapoints
from the Eval's train set, score them with the judge, and surface the ones that fail (with the
judge's plaintext feedback) so an LLM can reflect on the failures and propose prompt improvements.

It uses the same scoring path as ``EvalRunner`` in "eval_config_eval" mode (judging an existing
dataset item without re-running the task), and persists/reuses each result as an ``EvalRun`` so
repeated calls don't re-pay the judge for the same item.
"""

import asyncio
import logging
import random
from dataclasses import dataclass

from kiln_ai.adapters.eval.base_eval import BaseEval
from kiln_ai.adapters.eval.registry import eval_adapter_from_type
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.dataset_filters import dataset_filter_from_id
from kiln_ai.datamodel.eval import EvalConfig, EvalOutputScore, EvalRun, EvalScores
from kiln_ai.datamodel.task_output import normalize_rating
from kiln_ai.datamodel.task_run import TaskRun
from kiln_ai.utils.git_sync_protocols import SaveContext, default_save_context

logger = logging.getLogger(__name__)

# Default "pass" bar on the normalized 0-1 scale. 0.75 matches the four-star / is_high_quality
# threshold for five_star scores (normalize_rating(4, five_star) == 0.75).
DEFAULT_FAILURE_THRESHOLD = 0.75


@dataclass
class FailingExample:
    dataset_id: ID_TYPE
    scores: EvalScores
    feedback: str | None


@dataclass
class FindFailingResult:
    examples: list[FailingExample]
    num_judged: int
    train_set_size: int
    hit_cap: bool


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


async def _score_one(
    evaluator: BaseEval,
    eval_config: EvalConfig,
    task_run: TaskRun,
    cached: dict[ID_TYPE, EvalRun],
    save_context: SaveContext,
) -> tuple[EvalScores, dict[str, str] | None] | None:
    """Score a single train item, reusing a cached EvalRun or judging + persisting a new one.

    Returns ``(scores, intermediate_outputs)`` or ``None`` if the judge errored (logged + skipped).
    """
    existing = cached.get(task_run.id)
    if existing is not None:
        return existing.scores, existing.intermediate_outputs

    try:
        scores, intermediate_outputs = await evaluator.run_eval(task_run)
    except Exception:
        logger.error(
            "Error judging train item %s for eval config %s",
            task_run.id,
            eval_config.id,
            exc_info=True,
        )
        return None

    # Persist as an eval_config_eval run, mirroring EvalRunner.run_job's eval_config_eval branch.
    async with save_context():
        eval_run = EvalRun(
            parent=eval_config,
            task_run_config_id=None,
            dataset_id=task_run.id,
            eval_config_eval=True,
            scores=scores,
            input=task_run.input,
            output=task_run.output.output,
            intermediate_outputs=intermediate_outputs,
            task_run_usage=task_run.usage,
        )
        eval_run.save_to_file()

    return scores, intermediate_outputs


async def find_failing_train_examples(
    eval_config: EvalConfig,
    *,
    count: int,
    max_samples: int,
    threshold: float = DEFAULT_FAILURE_THRESHOLD,
    concurrency: int = 25,
    reuse_cached: bool = True,
    rng: random.Random | None = None,
    save_context: SaveContext | None = None,
) -> FindFailingResult:
    """Sample the parent Eval's train set, judge items, and return up to ``count`` failing examples.

    Shuffles the train set and judges items (up to ``max_samples``) until ``count`` failures are
    collected or the cap is reached. An item fails only if all of the eval's output scores fall
    below ``threshold`` (normalized 0-1). Results are persisted as EvalRuns and reused on later
    calls when ``reuse_cached`` is set.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if max_samples < count:
        raise ValueError("max_samples must be >= count")

    eval = eval_config.parent_eval()
    if eval is None:
        raise ValueError("Eval config must have a parent eval")
    task = eval.parent_task()
    if task is None:
        raise ValueError("Eval must have a parent task")
    if eval.train_set_filter_id is None:
        raise ValueError("Eval does not have a train set filter (train_set_filter_id)")

    rng = rng or random.Random()
    save_context = save_context or default_save_context

    # Collect the train set. Same logic as runs_in_filter, inlined to avoid a server-layer import.
    dataset_filter = dataset_filter_from_id(eval.train_set_filter_id)
    candidates = [run for run in task.runs(readonly=True) if dataset_filter(run)]
    train_set_size = len(candidates)
    rng.shuffle(candidates)
    candidates = candidates[:max_samples]

    # Reuse previously-judged results for this eval config to avoid re-paying the judge.
    cached: dict[ID_TYPE, EvalRun] = {}
    if reuse_cached:
        cached = {
            run.dataset_id: run
            for run in eval_config.runs(readonly=True)
            if run.eval_config_eval
        }

    evaluator = eval_adapter_from_type(eval_config.config_type)(eval_config, None)
    if not isinstance(evaluator, BaseEval):
        raise ValueError("Not able to create evaluator from eval config")

    failures: list[FailingExample] = []
    num_judged = 0

    # Judge in chunks so the judge runs concurrently, but we can stop early once we have enough
    # failures (a chunk may over-judge by up to concurrency-1 items past the stopping point).
    for start in range(0, len(candidates), concurrency):
        chunk = candidates[start : start + concurrency]
        results = await asyncio.gather(
            *(
                _score_one(evaluator, eval_config, task_run, cached, save_context)
                for task_run in chunk
            )
        )
        for task_run, scored in zip(chunk, results):
            num_judged += 1
            if scored is None:
                # Judge errored on this item; it still counts as examined.
                continue
            scores, intermediate_outputs = scored
            if example_fails(scores, eval.output_scores, threshold):
                failures.append(
                    FailingExample(
                        dataset_id=task_run.id,
                        scores=scores,
                        feedback=feedback_from_intermediate_outputs(
                            intermediate_outputs
                        ),
                    )
                )
        if len(failures) >= count:
            break

    hit_cap = len(failures) < count and num_judged >= max_samples
    return FindFailingResult(
        examples=failures[:count],
        num_judged=num_judged,
        train_set_size=train_set_size,
        hit_cap=hit_cap,
    )
