from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    ExactMatchProperties,
    SkippedReason,
)


class ExactMatchEval(BaseV2EvalBridge):
    """V2 adapter for exact_match: compares an extracted value against an expected string."""

    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, ExactMatchProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        if props.reference_key is not None:
            expected, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return {}, skip, detail
            expected = str(expected)
        else:
            expected = props.expected_value

        actual = str(value)
        assert expected is not None
        if props.case_sensitive:
            passed = actual == expected
        else:
            passed = actual.lower() == expected.lower()

        return build_binary_scores(self.eval_config, passed), None, None
