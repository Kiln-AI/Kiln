"""Standalone scoring functions extracted from GEval.

These can be used by both legacy GEval and V2 adapters.
"""

import math
from typing import Callable, Dict, List, Tuple

from kiln_ai.adapters.model_adapters.base_adapter import RunOutput
from kiln_ai.datamodel.eval import EvalScores
from litellm.types.utils import ChatCompletionTokenLogprob

TOKEN_TO_SCORE_MAP: Dict[str, float] = {
    "1": 1.0,
    "2": 2.0,
    "3": 3.0,
    "4": 4.0,
    "5": 5.0,
    "pass": 1.0,
    "fail": 0.0,
    "critical": -1.0,
}


def score_from_token_string(token: str) -> float | None:
    """Look up a token string in TOKEN_TO_SCORE_MAP with cleanup.

    Handles variations like upper case, whitespace, quotes, and numeric strings.
    """
    if token in TOKEN_TO_SCORE_MAP:
        return TOKEN_TO_SCORE_MAP[token]

    unquoted_token = token.strip().strip('"').lower()
    if unquoted_token in TOKEN_TO_SCORE_MAP:
        return TOKEN_TO_SCORE_MAP[unquoted_token]

    try:
        float_value = float(token)
        if float_value.is_integer():
            str_token = str(int(float_value))
            if str_token in TOKEN_TO_SCORE_MAP:
                return TOKEN_TO_SCORE_MAP[str_token]
    except ValueError:
        pass

    return None


def raw_output_from_logprobs(run_output: RunOutput) -> str:
    """Build the raw output string from logprobs.

    Generated from logprobs so it is guaranteed to match logprob offsets.
    """
    if run_output.output_logprobs is None or run_output.output_logprobs.content is None:
        raise RuntimeError("No logprobs found for output - can not calculate g-eval")

    raw = ""
    for chat_logprob in run_output.output_logprobs.content:
        raw += chat_logprob.token
    return raw


def metric_offsets(raw_output: str, metrics: List[str]) -> Dict[str, int]:
    """Find the character offset of each quoted metric name in raw JSON output.

    For example, for ``{"overall_rating": 1}`` the offset of ``overall_rating``
    is 1 (the position of the opening quote).
    """
    offsets: Dict[str, int] = {}
    for m in metrics:
        metric_name = f'"{m}"'
        count = raw_output.count(metric_name)
        if count != 1:
            raise ValueError(
                f"Metric {m} should appear exactly once in the output. Found {count} times"
            )
        offset = raw_output.find(metric_name)
        if offset == -1:
            raise ValueError(f"Metric {m} not found in raw output")
        offsets[m] = offset
    return offsets


def token_search_range(
    raw_output: str, metric: str, offsets: Dict[str, int]
) -> Tuple[int, int]:
    """Find the start and end character offsets for scanning a metric's rating token.

    Start after the target metric's key and stop before the next metric's key.
    """
    start_offset = offsets[metric] + len(metric)

    end_offset = len(raw_output)
    for v in list(offsets.values()):
        if v < end_offset and v > start_offset:
            end_offset = v

    return start_offset, end_offset


def rating_token_to_score(
    token_logprob: ChatCompletionTokenLogprob,
) -> float | None:
    """Convert a rating token to a score using weighted average of top logprobs.

    Only includes tokens that have valid scores. Handles the OpenAI 4o bug
    where the primary token may or may not appear in top_logprobs.
    """
    primary_token_score = score_from_token_string(token_logprob.token)
    if primary_token_score is None:
        return None

    total_score = 0.0
    total_probability = 0.0
    top_logprobs_contains_primary_token = False

    for top_logprob in token_logprob.top_logprobs:
        if top_logprob.token == token_logprob.token:
            top_logprobs_contains_primary_token = True
        token_score = score_from_token_string(top_logprob.token)
        if token_score is not None:
            probability = math.exp(top_logprob.logprob)
            total_score += token_score * probability
            total_probability += probability

    if not top_logprobs_contains_primary_token:
        if token_logprob.logprob == -9999.0:
            total_score += primary_token_score * 1.0
            total_probability += 1.0
        else:
            probability = math.exp(token_logprob.logprob)
            total_score += primary_token_score * probability
            total_probability += probability

    if total_probability <= 0.0:
        raise RuntimeError(
            f"No valid scoring tokens found for {token_logprob.token}. This should never happen as the token has a valid score (so it must be excluded from top logprobs). Please file a bug if you see this."
        )

    weighted_score = total_score / total_probability

    return weighted_score


def g_eval_single_metric(
    run_output: RunOutput,
    metric: str,
    offsets: Dict[str, int],
    raw_output: str,
) -> float | None:
    """Compute the G-Eval weighted score for a single metric.

    Scans logprobs in the token range for the metric and returns the
    probability-weighted score of the first valid rating token found.
    """
    start_offset, end_offset = token_search_range(raw_output, metric, offsets)

    offset = 0

    if run_output.output_logprobs is None or run_output.output_logprobs.content is None:
        raise RuntimeError("No logprobs found for output - can not calculate g-eval")

    for _, chat_logprob in enumerate(run_output.output_logprobs.content):
        if offset >= end_offset:
            break
        if offset >= start_offset:
            score = rating_token_to_score(chat_logprob)
            if score is not None:
                return score
        offset += len(chat_logprob.token)

    return None


def build_llm_as_judge_score(
    run_output: RunOutput,
    score_from_token_fn: Callable[[str], float | None],
) -> EvalScores:
    """Convert discrete LLM judge output to float scores.

    Args:
        run_output: The run output containing the LLM's structured dict output.
        score_from_token_fn: Function mapping a token string to a float score,
            or None if the token is not a valid score.
    """
    scores: EvalScores = {}
    if not isinstance(run_output.output, dict):
        raise ValueError("LLM as Judge output must be a dictionary")

    for metric, value in run_output.output.items():
        if isinstance(value, (int, float)):
            scores[metric] = float(value)
            continue
        token_score = score_from_token_fn(f"{value}")
        if token_score is None:
            try:
                scores[metric] = float(value)
                continue
            except (ValueError, TypeError):
                pass
            raise ValueError(
                f"No score found for metric: {metric}. The LLM failed to follow the scoring rubric/instructions/schema."
            )
        scores[metric] = token_score
    return scores


def build_g_eval_score(
    run_output: RunOutput,
    raw_output_from_logprobs_fn: Callable[[RunOutput], str],
    metric_offsets_fn: Callable[[str, List[str]], Dict[str, int]],
    g_eval_single_metric_fn: Callable[
        [RunOutput, str, Dict[str, int], str], float | None
    ],
) -> EvalScores:
    """Build G-Eval weighted scores from logprobs.

    Args:
        run_output: The run output with logprobs.
        raw_output_from_logprobs_fn: Function to build raw output string from logprobs.
        metric_offsets_fn: Function to find metric name offsets in raw JSON.
        g_eval_single_metric_fn: Function to compute a single metric's weighted score.
    """
    outputs = run_output.output
    if not isinstance(outputs, dict):
        raise ValueError("G-Eval output must be a dictionary")

    raw_output = raw_output_from_logprobs_fn(run_output)

    metrics: List[str] = list(outputs.keys())
    metric_offsets = metric_offsets_fn(raw_output, metrics)

    final_scores: EvalScores = {}
    for metric in metrics:
        score = g_eval_single_metric_fn(run_output, metric, metric_offsets, raw_output)
        if score is None:
            raise ValueError(
                f"No score found for metric: {metric}. The LLM failed to follow the scoring rubric/instructions/schema."
            )
        final_scores[metric] = score

    return final_scores
