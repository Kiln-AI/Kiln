import json

from kiln_ai.adapters.eval.base_eval import BaseV2EvalBridge
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    SetCheckProperties,
    V2EvalResult,
)


class SetCheckEval(BaseV2EvalBridge):
    """V2 adapter for set_check: compares an extracted set against an expected set.

    The extracted value is coerced to a set of strings:
    - If it's a list, each element is stringified.
    - If it's a dict, use ``set(dict.keys())``.
    - If it's a string, attempt ``json.loads``; if the result is a list,
      stringify each element. Otherwise wrap the original string as a
      single-element set ``{the_string}``.
    - Any other type: wrap as a single-element set via ``{str(value)}``.
    """

    async def evaluate(self, eval_input: EvalTaskInput) -> V2EvalResult:
        props = self.properties
        assert isinstance(props, SetCheckProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return V2EvalResult(skipped_reason=skip, skipped_detail=detail)

        actual_set = self._coerce_to_set(value)

        if props.reference_key is not None:
            expected_raw, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return V2EvalResult(skipped_reason=skip, skipped_detail=detail)
            expected_set = self._coerce_to_set(expected_raw)
        else:
            assert props.expected_set is not None
            expected_set = set(props.expected_set)

        if props.mode == "subset":
            passed = actual_set.issubset(expected_set)
        elif props.mode == "superset":
            passed = actual_set.issuperset(expected_set)
        else:
            passed = actual_set == expected_set

        return V2EvalResult(
            scores=build_binary_scores(self._output_scores, passed),
        )

    @staticmethod
    def _coerce_to_set(value: object) -> set[str]:
        """Coerce a value to a set of strings."""
        if isinstance(value, list):
            return {str(item) for item in value}
        if isinstance(value, set):
            return {str(item) for item in value}
        if isinstance(value, dict):
            return {str(k) for k in value.keys()}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return {str(item) for item in parsed}
            except (json.JSONDecodeError, TypeError):
                pass
            return {value}
        return {str(value)}
