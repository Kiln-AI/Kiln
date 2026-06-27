from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
    stringify_for_match,
)
from kiln_ai.datamodel.eval import (
    ContainsProperties,
    EvalTaskInput,
    V2EvalResult,
)


class ContainsEval(BaseV2EvalBridge):
    """V2 adapter for contains: checks whether the extracted value contains a substring."""

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, ContainsProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return V2EvalResult(skipped_reason=skip, skipped_detail=detail)

        if props.reference_key is not None:
            substring, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return V2EvalResult(skipped_reason=skip, skipped_detail=detail)
            substring = stringify_for_match(substring)
        else:
            substring = props.substring
            assert substring is not None

        actual = stringify_for_match(value)
        if props.case_sensitive:
            found = substring in actual
        else:
            found = substring.lower() in actual.lower()

        if props.mode == "must_contain":
            passed = found
        else:
            passed = not found

        return V2EvalResult(
            scores=build_binary_scores(self._output_scores, passed),
        )
