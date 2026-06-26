"""Tests for StepCountCheckEval adapter."""

import pytest

from kiln_ai.adapters.eval.conftest import make_eval_task_input, make_v2_eval_config
from kiln_ai.adapters.eval.v2_eval_step_count_check import StepCountCheckEval
from kiln_ai.datamodel.eval import (
    EvalTaskInput,
    SkippedReason,
    StepCountCheckProperties,
)

_make_config = make_v2_eval_config


def _inp(**overrides: object) -> EvalTaskInput:
    final_message = overrides.pop("final_message", "hello")
    return make_eval_task_input(final_message=str(final_message), **overrides)


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
    @pytest.mark.asyncio
    async def test_within_range_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=1, max_count=4)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2, tools_per_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_below_min_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=5)
        )
        trace = _multi_turn_trace(n_user=1, n_assistant=1, tools_per_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_above_max_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", max_count=1)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2, tools_per_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None


class TestStepCountModelResponses:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="model_responses", min_count=2)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="model_responses", min_count=5)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None


class TestStepCountTurns:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="turns", min_count=1, max_count=3)
        )
        trace = _multi_turn_trace(n_user=2, n_assistant=2)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", max_count=1))
        trace = _multi_turn_trace(n_user=3, n_assistant=3)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 0.0}
        assert result.skipped_reason is None


class TestStepCountEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_trace_skips(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=1)
        )
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=None))
        assert result.scores == {}
        assert result.skipped_reason == SkippedReason.missing_trace
        assert result.skipped_detail is not None

    @pytest.mark.asyncio
    async def test_empty_trace(self):
        cfg = _make_config(
            StepCountCheckProperties(count_type="tool_calls", min_count=0, max_count=0)
        )
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=[]))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_only_min_bound(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", min_count=1))
        trace = _multi_turn_trace(n_user=10, n_assistant=10)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_only_max_bound(self):
        cfg = _make_config(StepCountCheckProperties(count_type="turns", max_count=5))
        trace = _multi_turn_trace(n_user=3, n_assistant=3)
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_tool_call_only_assistant_counted_as_model_response(self):
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
        result = await StepCountCheckEval(cfg).evaluate(_inp(trace=trace))
        assert result.scores == {"score_a": 1.0}
        assert result.skipped_reason is None
