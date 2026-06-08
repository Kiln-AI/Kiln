"""Tests for ToolCallCheckEval adapter."""

import json
from unittest.mock import Mock

import pytest

from kiln_ai.adapters.eval.v2_eval_tool_call_check import ToolCallCheckEval
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import (
    ArgMatch,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalTaskInput,
    SkippedReason,
    ToolCallCheckProperties,
    ToolCallSpec,
)


def _make_config(props: ToolCallCheckProperties) -> EvalConfig:
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


def _trace_with_tool_calls(
    *calls: tuple[str, dict],
) -> list[dict]:
    """Build a trace with assistant tool calls. Each call is (name, args_dict)."""
    tool_calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
        for i, (name, args) in enumerate(calls)
    ]
    return [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "tool_calls": tool_calls},
    ]


class TestToolCallCheckAllMode:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
            )
        )
        trace = _trace_with_tool_calls(("search", {"q": "hi"}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
            )
        )
        trace = _trace_with_tool_calls(("search", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestToolCallCheckAnyMode:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
                match_mode="any",
            )
        )
        trace = _trace_with_tool_calls(("search", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
                match_mode="any",
            )
        )
        trace = _trace_with_tool_calls(("unrelated", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestToolCallCheckOrderedMode:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
                match_mode="ordered",
            )
        )
        trace = _trace_with_tool_calls(("search", {}), ("other", {}), ("fetch", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
                match_mode="ordered",
            )
        )
        trace = _trace_with_tool_calls(("fetch", {}), ("search", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestToolCallCheckNeverMode:
    @pytest.mark.asyncio
    async def test_pass(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="delete")],
                match_mode="never",
            )
        )
        trace = _trace_with_tool_calls(("search", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="delete")],
                match_mode="never",
            )
        )
        trace = _trace_with_tool_calls(("delete", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None


class TestToolCallCheckNeverModeWithArgs:
    @pytest.mark.asyncio
    async def test_never_with_matching_args_fails(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="delete_database",
                        expected_args={
                            "force": ArgMatch(value=True, match_mode="exact")
                        },
                    )
                ],
                match_mode="never",
            )
        )
        trace = _trace_with_tool_calls(("delete_database", {"force": True}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_never_with_non_matching_args_passes(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="delete_database",
                        expected_args={
                            "force": ArgMatch(value=True, match_mode="exact")
                        },
                    )
                ],
                match_mode="never",
            )
        )
        trace = _trace_with_tool_calls(("delete_database", {"force": False}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_never_with_args_different_tool_passes(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="delete_database",
                        expected_args={
                            "force": ArgMatch(value=True, match_mode="exact")
                        },
                    )
                ],
                match_mode="never",
            )
        )
        trace = _trace_with_tool_calls(("search", {"q": "hi"}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None


class TestToolCallCheckUnexpectedTools:
    @pytest.mark.asyncio
    async def test_on_unexpected_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
                on_unexpected_tools="fail",
            )
        )
        trace = _trace_with_tool_calls(("search", {}), ("other", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_on_unexpected_fail_with_args_mismatch(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={
                            "query": ArgMatch(value="foo", match_mode="exact")
                        },
                    )
                ],
                on_unexpected_tools="fail",
            )
        )
        trace = _trace_with_tool_calls(
            ("search", {"query": "foo"}), ("search", {"query": "bar"})
        )
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_on_unexpected_fail_all_args_match(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={
                            "query": ArgMatch(value="foo", match_mode="exact")
                        },
                    )
                ],
                on_unexpected_tools="fail",
            )
        )
        trace = _trace_with_tool_calls(("search", {"query": "foo"}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_on_unexpected_ignore(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
                on_unexpected_tools="ignore",
            )
        )
        trace = _trace_with_tool_calls(("search", {}), ("other", {}))
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None


class TestToolCallCheckArgMatch:
    @pytest.mark.asyncio
    async def test_exact(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={"query": ArgMatch(value="test")},
                    )
                ],
            )
        )
        trace = _trace_with_tool_calls(("search", {"query": "test"}))
        scores, _skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_contains(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={
                            "query": ArgMatch(value="test", match_mode="contains")
                        },
                    )
                ],
            )
        )
        trace = _trace_with_tool_calls(("search", {"query": "this is a test query"}))
        scores, _skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_regex(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={
                            "query": ArgMatch(value=r"\d+", match_mode="regex")
                        },
                    )
                ],
            )
        )
        trace = _trace_with_tool_calls(("search", {"query": "item 42"}))
        scores, _skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}

    @pytest.mark.asyncio
    async def test_fail(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(
                        tool_name="search",
                        expected_args={"query": ArgMatch(value="test")},
                    )
                ],
            )
        )
        trace = _trace_with_tool_calls(("search", {"query": "other"}))
        scores, _skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 0.0}


class TestToolCallCheckEdgeCases:
    @pytest.mark.asyncio
    async def test_missing_trace_skips(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
            )
        )
        scores, skip, detail = await ToolCallCheckEval(cfg).evaluate(_inp(trace=None))
        assert scores == {}
        assert skip == SkippedReason.missing_trace
        assert detail is not None

    @pytest.mark.asyncio
    async def test_empty_trace(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
            )
        )
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=[]))
        assert scores == {"score_a": 0.0}
        assert skip is None

    @pytest.mark.asyncio
    async def test_multiple_assistant_messages(self):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[
                    ToolCallSpec(tool_name="search"),
                    ToolCallSpec(tool_name="fetch"),
                ],
            )
        )
        trace = [
            {"role": "user", "content": "msg1"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": json.dumps({}),
                        },
                    }
                ],
            },
            {"role": "user", "content": "msg2"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "fetch",
                            "arguments": json.dumps({}),
                        },
                    }
                ],
            },
        ]
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "args_str",
        ["not valid json", "", None],
        ids=["invalid_json", "empty_string", "none"],
    )
    async def test_malformed_arguments_handled(self, args_str: str | None):
        cfg = _make_config(
            ToolCallCheckProperties(
                expected_tools=[ToolCallSpec(tool_name="search")],
            )
        )
        trace = [
            {"role": "user", "content": "msg"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search", "arguments": args_str},
                    }
                ],
            },
        ]
        scores, skip, _ = await ToolCallCheckEval(cfg).evaluate(_inp(trace=trace))
        assert scores == {"score_a": 1.0}
        assert skip is None
