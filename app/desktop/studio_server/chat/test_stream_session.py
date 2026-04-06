import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.desktop.studio_server.chat import _build_openai_tool_continuation, execute_tool
from app.desktop.studio_server.chat.constants import SSE_TYPE_TOOL_CALLS_PENDING
from app.desktop.studio_server.chat.stream_session import (
    ChatStreamSession,
    ToolCallInfo,
    _format_tool_calls_pending_sse,
    execute_tool_batch,
)
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent
from kiln_server.error_codes import CHAT_CLIENT_VERSION_TOO_OLD


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_runs_multiply_builtin(self):
        assert (
            await execute_tool("kiln_tool::multiply_numbers", {"a": 2, "b": 8}) == "16"
        )

    @pytest.mark.asyncio
    async def test_runs_add_builtin(self):
        assert await execute_tool("kiln_tool::add_numbers", {"a": 1, "b": 2}) == "3"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_json_error(self):
        out = await execute_tool("nonexistent_tool_xyz", {})
        data = json.loads(out)
        assert "error" in data
        assert "nonexistent_tool_xyz" in data["error"]


def _make_session():
    return ChatStreamSession(
        upstream_url="https://example.test/v1/chat",
        headers={},
        initial_body={"messages": []},
    )


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    async def aread(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def stream(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_stream_error_includes_code_field():
    error_body = json.dumps(
        {"message": "Update required", "code": CHAT_CLIENT_VERSION_TOO_OLD}
    ).encode()
    fake_resp = _FakeResponse(400, error_body)
    fake_client = _FakeClient(fake_resp)

    session = _make_session()

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        chunks = []
        async for chunk in session.stream():
            chunks.append(chunk)

    assert len(chunks) == 1
    payload = json.loads(chunks[0].decode().removeprefix("data: ").strip())
    assert payload["type"] == "error"
    assert payload["message"] == "Update required"
    assert payload["code"] == CHAT_CLIENT_VERSION_TOO_OLD


@pytest.mark.asyncio
async def test_stream_error_without_code_omits_code_field():
    error_body = json.dumps({"message": "Something failed"}).encode()
    fake_resp = _FakeResponse(500, error_body)
    fake_client = _FakeClient(fake_resp)

    session = _make_session()

    with patch.object(httpx, "AsyncClient", return_value=fake_client):
        chunks = []
        async for chunk in session.stream():
            chunks.append(chunk)

    assert len(chunks) == 1
    payload = json.loads(chunks[0].decode().removeprefix("data: ").strip())
    assert payload["type"] == "error"
    assert payload["message"] == "Something failed"
    assert "code" not in payload


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


class TestToolCallsPendingSse:
    def test_format_tool_calls_pending_sse_shape(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="tc1",
            toolName="call_kiln_api",
            input={"method": "GET"},
            kiln_metadata={
                "requires_approval": True,
                "permission": "api",
                "approval_description": "Do the thing",
            },
        )
        raw = _format_tool_calls_pending_sse([ev])
        line = raw.decode().strip()
        assert line.startswith("data: ")
        payload = json.loads(line[6:])
        assert payload["type"] == SSE_TYPE_TOOL_CALLS_PENDING
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["toolCallId"] == "tc1"
        assert item["toolName"] == "call_kiln_api"
        assert item["input"] == {"method": "GET"}
        assert item["requiresApproval"] is True
        assert item["permission"] == "api"
        assert item["approvalDescription"] == "Do the thing"


class TestExecuteToolBatch:
    @pytest.mark.asyncio
    async def test_execute_tool_batch_mixed(self):
        calls = [
            ToolCallInfo.model_validate(
                {
                    "toolCallId": "a",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                    "requiresApproval": False,
                }
            ),
            ToolCallInfo.model_validate(
                {
                    "toolCallId": "b",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 3, "b": 4},
                    "requiresApproval": True,
                }
            ),
        ]
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            AsyncMock(side_effect=["3", "7"]),
        ) as m:
            out = await execute_tool_batch(
                calls,
                {"b": True},
            )
        assert out == {"a": "3", "b": "7"}
        assert m.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_tool_batch_denies_when_not_approved(self):
        calls = [
            ToolCallInfo.model_validate(
                {
                    "toolCallId": "b",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                    "requiresApproval": True,
                }
            ),
        ]
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            AsyncMock(return_value="3"),
        ) as m:
            out = await execute_tool_batch(calls, {"b": False})
        assert "error" in json.loads(out["b"])
        m.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_tool_batch_denies_when_missing_decision(self):
        calls = [
            ToolCallInfo.model_validate(
                {
                    "toolCallId": "b",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                    "requiresApproval": True,
                }
            ),
        ]
        with patch(
            "app.desktop.studio_server.chat.stream_session.execute_tool",
            AsyncMock(return_value="3"),
        ) as m:
            out = await execute_tool_batch(calls, {})
        assert "error" in json.loads(out["b"])
        m.assert_not_called()
