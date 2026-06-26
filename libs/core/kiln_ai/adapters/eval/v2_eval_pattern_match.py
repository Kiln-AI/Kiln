import re

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    PatternMatchProperties,
    SkippedReason,
    V2EvalResult,
)


class PatternMatchEval(BaseV2EvalBridge):
    """V2 adapter for pattern_match: tests an extracted value against a regex pattern."""

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, PatternMatchProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return V2EvalResult(skipped_reason=skip, skipped_detail=detail)

        actual = str(value)

        try:
            match = re.search(props.pattern, actual)
        except re.error as e:
            return V2EvalResult(
                skipped_reason=SkippedReason.extraction_failed,
                skipped_detail=f"Invalid regex pattern '{props.pattern}': {e}",
            )

        if props.mode == "must_match":
            passed = match is not None
        else:
            passed = match is None

        return V2EvalResult(
            scores=build_binary_scores(self._output_scores, passed),
        )
