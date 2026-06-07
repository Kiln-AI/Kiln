import re

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import (
    build_binary_scores,
    extract_value,
)
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    PatternMatchProperties,
    SkippedReason,
)


class PatternMatchEval(BaseV2Eval):
    """V2 adapter for pattern_match: tests an extracted value against a regex pattern."""

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, PatternMatchProperties)

        value, skip, detail = extract_value(props.value_expression, eval_input)
        if skip is not None:
            return {}, skip, detail

        actual = str(value)

        try:
            match = re.search(props.pattern, actual)
        except re.error as e:
            return (
                {},
                SkippedReason.extraction_failed,
                f"Invalid regex pattern '{props.pattern}': {e}",
            )

        if props.mode == "must_match":
            passed = match is not None
        else:
            passed = match is None

        return build_binary_scores(self.eval_config, passed), None, None
