from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    ExactMatchProperties,
    V2EvalResult,
)


class ExactMatchEval(BaseV2EvalBridge):
    """V2 adapter for exact_match: compares an extracted value against an expected string."""

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, ExactMatchProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return V2EvalResult(skipped_reason=skip, skipped_detail=detail)

        if props.reference_key is not None:
            expected, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return V2EvalResult(skipped_reason=skip, skipped_detail=detail)
            expected = str(expected)
        else:
            expected = props.expected_value

        actual = str(value)
        assert expected is not None
        if props.case_sensitive:
            passed = actual == expected
        else:
            passed = actual.lower() == expected.lower()

        return V2EvalResult(
            scores=build_binary_scores(self._output_scores, passed),
        )
