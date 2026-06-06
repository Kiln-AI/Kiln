"""Standalone scoring functions extracted from GEval.

These can be used by both legacy GEval and future V2 adapters.
"""

from typing import Callable, Dict, List

from kiln_ai.adapters.model_adapters.base_adapter import RunOutput
from kiln_ai.datamodel.eval import EvalScores


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

    for metric, score in run_output.output.items():
        token_score = score_from_token_fn(f"{score}")
        if token_score is None:
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
