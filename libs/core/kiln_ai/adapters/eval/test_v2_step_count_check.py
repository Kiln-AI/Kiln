"""Tests for StepCountCheckEval adapter."""

from unittest.mock import Mock

from kiln_ai.adapters.eval.v2_eval_step_count_check import StepCountCheckEval
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
    StepCountCheckProperties,
)


def _make_config(props: StepCountCheckProperties) -> EvalConfig:
    parent = Mock()
    parent.output_scores = [
        EvalOutputScore(
            name="score_a", instruction="a", type=TaskOutputRatingType.pass_fail
        ),
    ]
    cfg = Mock(spec=EvalConfig)
    cfg.config_type = EvalConfigType.v2
    cfg.properties = props
    cfg.parent_eval.return_value = parent
    return cfg


def _inp(**overrides: object) -> EvalTaskInput:
    defaults: dict = {
        "final_message": "hello",
        "trace": None,
        "reference_data": None,
        "task_input": None,
    }
    defaults.update(overrides)
    return EvalTaskInput(**defaults)


def _multi_turn_trace(
    n_user: int = 2, n_assistant: int = 2, tools_per_assistant: int = 0
) -> list[dict]:
    """Build a multi-turn trace with optional tool calls per assistant message."""
    trace: list[dict] = []
    for i in range(max(n_user, n_assistant)):
        if i < n_user:
            trace.append({"role": "user", "content": f"user msg {i}"})
        if i < n_assistant:
            msg: dict = {"role": "assistant", "content": f"response {i}"}
            if tools_per_assistant > 0:
                msg["tool_calls"] = [
                    {
                        "id": f"call_{i}_{j}",
                        "type": "function",
                        "function": {"name": f"tool_{j}", "arguments": "{}"},
                    }
                    for j in range(tools_per_assistant)
                ]
            trace.append(msg)
    return trace


class TestStepCountToolCalls:
    def test_within_range_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=1, max_count=4)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2, tools_per_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_below_min_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=5)
        )
        trace = _multi_turn_trace(n_user=1, n_assistant=1, tools_per_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None

    def test_above_max_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", max_count=1)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2, tools_per_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestStepCountModelResponses:
    def test_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="model_responses", min_count=2)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="model_responses", min_count=5)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestStepCountTurns:
    def test_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="turns", min_count=1, max_count=3)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_fail(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", max_count=1))
        trace = _multi_turn_trace(n_user=3, n_assistant=3)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestStepCountEdgeCases:
    def test_missing_trace_skips(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=1)
        )
        scores, skip, detail = StepCountCheckEval(cfg).evaluate(_inp(trace=None))
        assert scores == {}
        assert skip == SkippedReason.missing_trace
        assert detail is not None

    def test_empty_trace(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=0, max_count=0)
        )
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=[]))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_only_min_bound(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", min_count=1))
        trace = _multi_turn_trace(n_user=10, n_assistant=10)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_only_max_bound(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", max_count=5))
        trace = _multi_turn_trace(n_user=3, n_assistant=3)
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    def test_tool_call_only_assistant_counted_as_model_response(self):
        """A tool-call-only assistant message (no content) must count as a model_response."""
        trace = [
            {"role": "user", "content": "do something"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "my_tool", "arguments": "{}"},
                    }
                ],
            },
        ]
        cfg = _make_config(
            StepCountCheckProperties(
                count_type="model_responses", min_count=1, max_count=1
            )
        )
        scores, skip, _ = StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None
