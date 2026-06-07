from typing import Any

from kiln_ai.adapters.eval.base_v2_eval import BaseV2Eval
from kiln_ai.adapters.eval.eval_utils.v2_eval_helpers import build_binary_scores
from kiln_ai.datamodel.eval import (
    EvalScores,
    EvalTaskInput,
    SkippedReason,
    StepCountCheckProperties,
)


class StepCountCheckEval(BaseV2Eval):
    """V2 adapter for step_count_check: validates the number of steps in the trace.

    count_type determines what is counted:
    - "tool_calls": total number of individual tool call invocations across all assistant messages
    - "model_responses": number of assistant messages, including tool-call-only
    - "turns": number of distinct user/assistant turn pairs (count of user messages)
    """

    def evaluate(
        self, eval_input: EvalTaskInput
    ) -> tuple[EvalScores, SkippedReason | None, str | None]:
        props = self.properties
        assert isinstance(props, StepCountCheckProperties)

        if eval_input.trace is None:
            return (
                {},
                SkippedReason.missing_trace,
                "step_count_check requires a trace",
            )

        count = self._count(eval_input.trace, props.count_type)

        passed = True
        if props.min_count is not None and count < props.min_count:
            passed = False
        if props.max_count is not None and count > props.max_count:
            passed = False

        return build_binary_scores(self.eval_config, passed), None, None

    @staticmethod
    def _count(trace: list[dict[str, Any]], count_type: str) -> int:
        """Count steps in the trace based on count_type."""
        if count_type == "tool_calls":
            total = 0
            for msg in trace:
                if msg.get("role") != "assistant":
                    continue
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    total += len(tool_calls)
            return total
        elif count_type == "model_responses":
            total = 0
            for msg in trace:
                if msg.get("role") == "assistant":
                    total += 1
            return total
        elif count_type == "turns":
            total = 0
            for msg in trace:
                if msg.get("role") == "user":
                    total += 1
            return total
        return 0
