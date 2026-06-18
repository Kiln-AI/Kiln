from typing import Any

from jinja2 import Undefined
from kiln_ai.datamodel.eval import EvalConfig, EvalScores, EvalTaskInput, SkippedReason
from kiln_ai.utils.jinja_engine import extract


def build_binary_scores(eval_config: EvalConfig, passed: bool) -> EvalScores:
    """Build an EvalScores dict with the same binary value for all declared score keys.

    Reads output_scores from the parent Eval via eval_config.parent_eval().
    Returns {} if no parent eval or no output_scores are declared.
    """
    parent = eval_config.parent_eval()
    if parent is None or not parent.output_scores:
        return {}
    value = 1.0 if passed else 0.0
    return {score.json_key(): value for score in parent.output_scores}


def extract_value(
    expression: str | None,
    eval_input: EvalTaskInput,
) -> tuple[Any, SkippedReason | None, str | None]:
    """Extract a value from eval_input using a Jinja2 expression.

    If expression is None, defaults to eval_input.final_message.
    Returns (value, skip_reason, skip_detail).
    """
    if expression is None:
        return eval_input.final_message, None, None
    data = eval_input.model_dump()
    result = extract(expression, data)
    if isinstance(result, Undefined) or result is None:
        return (
            None,
            SkippedReason.extraction_failed,
            f"Expression '{expression}' resolved to {'undefined' if isinstance(result, Undefined) else 'None'}",
        )
    return result, None, None


def check_reference_key(
    reference_key: str,
    eval_input: EvalTaskInput,
) -> tuple[Any, SkippedReason | None, str | None]:
    """Look up a key in eval_input.reference_data.

    Returns (value, skip_reason, skip_detail).
    """
    if eval_input.reference_data is None:
        return (
            None,
            SkippedReason.missing_reference_key,
            f"No reference_data; need key '{reference_key}'",
        )
    if reference_key not in eval_input.reference_data:
        return (
            None,
            SkippedReason.missing_reference_key,
            f"reference_data missing key '{reference_key}'",
        )
    value = eval_input.reference_data[reference_key]
    if value is None:
        return (
            None,
            SkippedReason.missing_reference_key,
            f"reference_data key '{reference_key}' is None",
        )
    return value, None, None


def check_required_vars(
    required_vars: list[str],
    eval_input: EvalTaskInput,
) -> tuple[SkippedReason | None, str | None]:
    """Check that all required_var expressions resolve to non-Undefined/non-None values."""
    data = eval_input.model_dump()
    for var_expr in required_vars:
        result = extract(var_expr, data)
        if isinstance(result, Undefined) or result is None:
            return (
                SkippedReason.extraction_failed,
                f"required_var '{var_expr}' resolved to {'undefined' if isinstance(result, Undefined) else 'None'}",
            )
    return None, None
