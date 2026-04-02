import json
from unittest.mock import AsyncMock, patch

import pytest
from app.desktop.studio_server.chat.constants import SSE_TYPE_TOOL_CALLS_PENDING
from app.desktop.studio_server.chat.stream_session import (
    ToolCallInfo,
    _format_tool_calls_pending_sse,
    execute_tool_batch,
)
from app.desktop.studio_server.chat.tool_metadata import tool_requires_user_approval
from kiln_ai.adapters.model_adapters.stream_events import ToolInputAvailableEvent


class TestToolApprovalHelpers:
    def test_tool_requires_user_approval_accepts_bool_metadata(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": True},
        )
        assert tool_requires_user_approval(ev) is True
        ev2 = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": False},
        )
        assert tool_requires_user_approval(ev2) is False

    def test_tool_requires_user_approval_rejects_non_bool_requires_approval(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={"requires_approval": "true"},
        )
        assert tool_requires_user_approval(ev) is False

    def test_kiln_metadata_extra_keys_do_not_break_parsing(self):
        ev = ToolInputAvailableEvent(
            type="tool-input-available",
            toolCallId="x",
            toolName="t",
            input={},
            kiln_metadata={
                "requires_approval": True,
                "future_flag": 1,
            },
        )
        assert tool_requires_user_approval(ev) is True

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


def test_post_execute_tools_runs_and_continues(client, mock_api_key):
    from app.desktop.studio_server.test_chat.helpers import (
        PATCH_ASYNC_CLIENT,
        PATCH_EXECUTE_TOOL,
        make_httpx_mock,
        sse_text_delta,
    )

    second_chunks = [
        sse_text_delta("ok"),
        b'data: {"type":"finish"}\n\n',
    ]
    mock_class, mock_client, _ = make_httpx_mock(chunks=second_chunks)

    body = {
        "trace_id": "tr-exec-1",
        "tool_calls": [
            {
                "toolCallId": "tc1",
                "toolName": "kiln_tool::add_numbers",
                "input": {"a": 1, "b": 2},
                "requiresApproval": True,
            }
        ],
        "decisions": {"tc1": True},
    }

    with patch(PATCH_ASYNC_CLIENT, mock_class):
        with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="3")):
            response = client.post("/api/chat/execute-tools", json=body)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    content = response.content
    assert b"tool-output-available" in content
    assert b'"output": "3"' in content
    assert b"ok" in content
    continuation = json.loads(mock_client.stream.call_args.kwargs["content"])
    assert continuation["trace_id"] == "tr-exec-1"
    assert len(continuation["messages"]) == 1
    assert continuation["messages"][0]["role"] == "tool"
    assert continuation["messages"][0]["tool_call_id"] == "tc1"
    assert continuation["messages"][0]["content"] == "3"
