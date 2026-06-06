from typing import Any

from jinja2 import Undefined
from kiln_ai.datamodel.eval import EvalTaskInput, SkippedReason
from kiln_ai.utils.jinja_engine import extract


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
    if isinstance(result, Undefined):
        return (
            None,
            SkippedReason.extraction_failed,
            f"Expression '{expression}' resolved to undefined",
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
    return eval_input.reference_data[reference_key], None, None


def check_required_vars(
    required_vars: list[str],
    eval_input: EvalTaskInput,
) -> tuple[SkippedReason | None, str | None]:
    """Check that all required_var expressions resolve to non-Undefined values."""
    data = eval_input.model_dump()
    for var_expr in required_vars:
        result = extract(var_expr, data)
        if isinstance(result, Undefined):
            return (
                SkippedReason.extraction_failed,
                f"required_var '{var_expr}' resolved to undefined",
            )
    return None, None
