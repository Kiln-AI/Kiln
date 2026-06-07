from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    check_reference_key,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    ContainsProperties,
    EvalScores,
    EvalTaskInput,
    SkippedReason,
)


class ContainsEval(BaseV2Eval):
    """V2 adapter for contains: checks whether the extracted value contains a substring."""

    async def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, ContainsProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        if props.reference_key is not None:
            substring, skip, detail = check_reference_key(
                props.reference_key, eval_input
            )
            if skip is not None:
                return {}, skip, detail
            substring = str(substring)
        else:
            substring = props.substring
            assert substring is not None

        actual = str(value)
        if props.case_sensitive:
            found = substring in actual
        else:
            found = substring.lower() in actual.lower()

        if props.mode == "must_contain":
            passed = found
        else:
            passed = not found

        return build_binary_scores(self.eval_config, passed), None, None
