import json
from typing import Any

from app.desktop.studio_server.chat import (
    _build_openai_tool_continuation,
    tool_input_executor_is_server,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent


class TestBuildOpenAIToolContinuation:
    def _event(
        self, tc_id: str, tool_name: str, inp: dict[str, Any]
    ) -> ToolInputAvailableEvent:
        return ToolInputAvailableEvent(
            toolCallId=tc_id,
            toolName=tool_name,
            input=inp,
        )

    def test_appends_assistant_and_tool_messages(self):
        original = {"messages": [{"role": "user", "content": "hi"}]}
        events = [self._event("tc1", "multiply", {"a": 2, "b": 8})]
        result = _build_openai_tool_continuation(
            original, "Let me check", events, {"tc1": "16"}
        )

        messages = result["messages"]
        assert len(messages) == 3

        assistant = messages[1]
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "Let me check"
        assert len(assistant["tool_calls"]) == 1
        tc = assistant["tool_calls"][0]
        assert tc["id"] == "tc1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "multiply"
        assert json.loads(tc["function"]["arguments"]) == {"a": 2, "b": 8}

        tool_msg = messages[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "tc1"
        assert tool_msg["content"] == "16"

    def test_null_content_when_no_assistant_text(self):
        original = {"messages": [{"role": "user", "content": "hi"}]}
        result = _build_openai_tool_continuation(
            original, "   ", [self._event("tc1", "add", {})], {"tc1": "0"}
        )
        assert result["messages"][1]["content"] is None

    def test_multiple_tool_calls(self):
        original = {"messages": [{"role": "user", "content": "hi"}]}
        events = [
            self._event("tc1", "add", {"a": 1, "b": 2}),
            self._event("tc2", "multiply", {"a": 3, "b": 4}),
        ]
        result = _build_openai_tool_continuation(
            original, "", events, {"tc1": "3", "tc2": "12"}
        )
        messages = result["messages"]
        assert len(messages) == 4  # user + assistant + 2 tool
        assert messages[1]["role"] == "assistant"
        assert len(messages[1]["tool_calls"]) == 2
        assert messages[2]["role"] == "tool"
        assert messages[2]["tool_call_id"] == "tc1"
        assert messages[2]["content"] == "3"
        assert messages[3]["role"] == "tool"
        assert messages[3]["tool_call_id"] == "tc2"
        assert messages[3]["content"] == "12"

    def test_omits_tool_rows_not_in_results(self):
        original = {"messages": [{"role": "user", "content": "hi"}]}
        events = [
            self._event("tc1", "server_only", {}),
            self._event("tc2", "multiply", {"a": 3, "b": 4}),
        ]
        result = _build_openai_tool_continuation(
            original, "partial", events, {"tc2": "12"}
        )
        messages = result["messages"]
        assert len(messages) == 3
        assistant = messages[1]
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "partial"
        assert len(assistant["tool_calls"]) == 1
        assert assistant["tool_calls"][0]["id"] == "tc2"
        assert messages[2]["role"] == "tool"
        assert messages[2]["tool_call_id"] == "tc2"
        assert messages[2]["content"] == "12"

    def test_preserves_original_body_fields(self):
        original = {"messages": [], "task_id": "t1", "session_id": "s1"}
        result = _build_openai_tool_continuation(
            original, "", [self._event("tc1", "tool", {})], {"tc1": "x"}
        )
        assert result["task_id"] == "t1"
        assert result["session_id"] == "s1"

    def test_trace_id_with_empty_messages_sends_only_tool_results(self):
        original = {
            "trace_id": "tr-1",
            "messages": [],
        }
        events = [self._event("tc1", "call_kiln_api", {"method": "GET"})]
        result = _build_openai_tool_continuation(
            original, "ignored assistant text", events, {"tc1": '{"ok": true}'}
        )
        assert result["messages"] == [
            {
                "role": "tool",
                "tool_call_id": "tc1",
                "content": '{"ok": true}',
            }
        ]


class TestToolInputExecutorServer:
    def test_executor_server_is_true(self):
        event = ToolInputAvailableEvent(
            toolCallId="tc1",
            toolName="some_tool",
            input={},
            kiln_metadata={"executor": "server"},
        )
        assert tool_input_executor_is_server(event) is True

    def test_executor_absent_or_other_is_false(self):
        assert (
            tool_input_executor_is_server(
                ToolInputAvailableEvent(
                    toolCallId="tc1",
                    toolName="some_tool",
                    input={},
                )
            )
            is False
        )
        assert (
            tool_input_executor_is_server(
                ToolInputAvailableEvent(
                    toolCallId="tc1",
                    toolName="some_tool",
                    input={},
                    kiln_metadata={"executor": "client"},
                )
            )
            is False
        )
