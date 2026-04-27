import json
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    ChatSnapshot,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.chat_session_list_item import (
    ChatSessionListItem as SdkChatSessionListItem,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as KilnResponse,
)
from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.helpers import (
    PATCH_ASYNC_CLIENT,
    PATCH_EXECUTE_TOOL,
    make_httpx_mock,
    make_n_round_mock_client,
    sse_text_delta,
)
from kiln_server.error_codes import CHAT_CLIENT_VERSION_TOO_OLD


class TestChatStreaming:
    def test_streams_chunks(self, client, mock_api_key):
        chunks = [
            sse_text_delta("hello"),
            b'data: {"type":"finish"}\n\n',
        ]
        mock_class, _, _ = make_httpx_mock(chunks=chunks)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert b"text-delta" in response.content

    def test_forwards_auth_header(self, client, mock_api_key):
        mock_class, mock_client, _ = make_httpx_mock()

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            _ = response.content

        call_kwargs = mock_client.stream.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test_api_key"

    def test_returns_401_when_no_api_key(self, client):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None

            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 401

    def test_handles_upstream_error(self, client, mock_api_key):
        mock_class, _, _ = make_httpx_mock(status_code=500)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert b"error" in response.content


def _make_task_run_dict(**overrides):
    base = {
        "input": "",
        "output": {"output": "", "model_type": "test_model"},
        "model_type": "test_model",
    }
    base.update(overrides)
    return base


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_forwards_to_kiln(
    mock_asyncio_detailed, client, mock_api_key
):
    list_item_dict = {
        "id": "trace-1",
        "title": "Hi",
        "updated_at": "2025-06-15T12:30:00+00:00",
        "task_run": _make_task_run_dict(),
    }
    parsed_item = SdkChatSessionListItem.from_dict(list_item_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[parsed_item],
    )

    r = client.get("/api/chat/sessions")

    assert r.status_code == 200
    assert r.json() == [
        {"id": "trace-1", "title": "Hi", "updated_at": "2025-06-15T12:30:00Z"}
    ]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_forwards_to_kiln(mock_asyncio_detailed, client, mock_api_key):
    snapshot_dict = {
        "id": "trace-abc",
        "task_run": _make_task_run_dict(
            trace=[{"role": "user", "content": "yo"}],
        ),
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-abc")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "trace-abc"
    assert body["task_run"]["trace"] == [{"role": "user", "content": "yo"}]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert call_kwargs["session_id"] == "trace-abc"
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_passes_through_error_status(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=b'{"detail":"not found"}',
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.get("/api/chat/sessions/missing")

    assert r.status_code == 404
    assert r.json()["message"] == "not found"


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_returns_204(mock_asyncio_detailed, client, mock_api_key):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NO_CONTENT,
        content=b"",
        headers={},
        parsed=None,
    )

    r = client.delete("/api/chat/sessions/trace-xyz")

    assert r.status_code == 204
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert call_kwargs["session_id"] == "trace-xyz"
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.delete_session_v1_chat_sessions_session_id_delete.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_delete_chat_session_passes_through_error(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.NOT_FOUND,
        content=b'{"detail":"session not found"}',
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.delete("/api/chat/sessions/missing")

    assert r.status_code == 404
    assert r.json()["message"] == "session not found"


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_passes_through_version_error_code(
    mock_asyncio_detailed, client, mock_api_key
):
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=json.dumps(
            {"message": "Update required", "code": CHAT_CLIENT_VERSION_TOO_OLD}
        ).encode(),
        headers={"content-type": "application/json"},
        parsed=None,
    )

    r = client.get("/api/chat/sessions")

    assert r.status_code == 400
    body = r.json()
    assert body["message"] == {
        "message": "Update required",
        "code": CHAT_CLIENT_VERSION_TOO_OLD,
    }


class TestRemoteToolRoundTrip:
    def test_continues_after_tool_input_available(self, client, mock_api_key):
        """First request returns tool-input-available + finish tool-calls; proxy runs the built-in tool and continues."""
        first_chunks = [
            sse_text_delta("Let me compute that"),
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"call_kiln_api","input":{"method":"GET","url_path":"/api/test"}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [
            sse_text_delta("The answer is 16"),
            b'data: {"type":"finish"}\n\n',
        ]

        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="16")):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute 2*8"}]},
                )

        assert response.status_code == 200
        content = response.content
        assert b"Let me compute that" in content
        assert b"The answer is 16" in content
        assert get_call_count() == 2

        continuation_call = mock_client.stream.call_args_list[1]
        continuation_body = json.loads(continuation_call.kwargs["content"])
        messages = continuation_body["messages"]

        # original user + assistant(tool_calls) + tool result
        assert len(messages) == 3
        assert messages[0]["role"] == "user"

        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "Let me compute that"
        assert len(assistant_msg["tool_calls"]) == 1
        tc = assistant_msg["tool_calls"][0]
        assert tc["id"] == "tc1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "call_kiln_api"

        tool_msg = messages[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "tc1"
        assert tool_msg["content"] == "16"

    def test_openai_tool_continuation_omits_user_when_trace_in_stream(
        self, client, mock_api_key
    ):
        """After kiln_chat_trace, the persisted trace already has user + assistant(tool_calls); send only tool results."""
        trace_tid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        first_chunks = [
            sse_text_delta("Let me compute that"),
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"call_kiln_api","input":{"method":"GET","url_path":"/api/test"}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
            f'data: {{"type":"kiln_chat_trace","trace_id":"{trace_tid}"}}\n\n'.encode(),
        ]
        second_chunks = [
            sse_text_delta("The answer is 16"),
            b'data: {"type":"finish"}\n\n',
        ]

        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="16")):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute 2*8"}]},
                )

        assert response.status_code == 200
        assert get_call_count() == 2

        continuation_body = json.loads(
            mock_client.stream.call_args_list[1].kwargs["content"]
        )
        messages = continuation_body["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["tool"]
        assert continuation_body["trace_id"] == trace_tid
        assert messages[0]["tool_call_id"] == "tc1"
        assert messages[0]["content"] == "16"

    def test_skips_local_execute_tool_when_kiln_metadata_executor_server(
        self, client, mock_api_key
    ):
        first_chunks = [
            sse_text_delta("ok"),
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::multiply_numbers","input":{"a":2,"b":8},"kiln_metadata":{"executor":"server"}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        mock_client, get_call_count = make_n_round_mock_client(first_chunks, [])
        mock_class = MagicMock(return_value=mock_client)
        execute_tool_mock = AsyncMock()

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                )

        assert response.status_code == 200
        execute_tool_mock.assert_not_called()
        assert get_call_count() == 1
        assert mock_client.stream.call_count == 1
        assert b"ok" in response.content
        assert b"tool-output-available" not in response.content

    def test_emits_tool_output_available_to_ui(self, client, mock_api_key):
        """Proxy should emit tool-output-available SSE so the UI can show the result."""
        first_chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"call_kiln_api","input":{"method":"GET","url_path":"/api/test"}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [b'data: {"type":"finish"}\n\n']

        mock_client, _ = make_n_round_mock_client(first_chunks, second_chunks)
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="3")):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "add 1+2"}]},
                )

        content = response.content
        assert b"tool-output-available" in content
        assert b"tc1" in content
        assert b'"output": "3"' in content

    def test_multiple_tool_calls_in_one_round(self, client, mock_api_key):
        """All tools in a single round are handled and forwarded as continuation."""
        first_chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"call_kiln_api","input":{"method":"GET","url_path":"/api/a"}}\n\n',
            b'data: {"type":"tool-input-available","toolCallId":"tc2","toolName":"call_kiln_api","input":{"method":"GET","url_path":"/api/b"}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [b'data: {"type":"finish"}\n\n']

        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        execute_results = iter(["3", "12"])

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(
                PATCH_EXECUTE_TOOL,
                AsyncMock(side_effect=lambda *_: next(execute_results)),
            ):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute"}]},
                )
                _ = response.content

        assert get_call_count() == 2
        continuation_body = json.loads(
            mock_client.stream.call_args_list[1].kwargs["content"]
        )
        messages = continuation_body["messages"]
        # user + assistant(2 tool_calls) + 2 tool messages
        assert len(messages) == 4
        assert len(messages[1]["tool_calls"]) == 2
        assert messages[2]["role"] == "tool"
        assert messages[2]["content"] == "3"
        assert messages[3]["role"] == "tool"
        assert messages[3]["content"] == "12"

    def test_no_continuation_when_finish_not_tool_calls(self, client, mock_api_key):
        """When finish reason is not tool-calls, only one upstream request is made."""
        chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::add_numbers","input":{}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"stop"}}\n\n',
        ]
        mock_class, _, _ = make_httpx_mock(chunks=chunks)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        # Only one stream call
        assert mock_class.return_value.stream.call_count == 1

    def test_requires_approval_emits_tool_calls_pending_and_does_not_execute(
        self, client, mock_api_key
    ):
        first_chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2},"kiln_metadata":{"requires_approval":true}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        mock_client, get_call_count = make_n_round_mock_client(first_chunks, [])
        mock_class = MagicMock(return_value=mock_client)
        execute_tool_mock = AsyncMock(return_value="3")

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                )

        assert response.status_code == 200
        content = response.content
        assert b"tool-calls-pending" in content
        assert b"tool-output-available" not in content
        execute_tool_mock.assert_not_called()
        assert get_call_count() == 1

    def test_requires_approval_pending_payload_lists_tool(self, client, mock_api_key):
        first_chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2},"kiln_metadata":{"requires_approval":true}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        mock_client, _ = make_n_round_mock_client(first_chunks, [])
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        for line in response.content.decode().split("\n"):
            if line.startswith("data: ") and "tool-calls-pending" in line:
                payload = json.loads(line[6:])
                assert payload["type"] == "tool-calls-pending"
                assert len(payload["items"]) == 1
                assert payload["items"][0]["toolCallId"] == "tc1"
                assert payload["items"][0]["requiresApproval"] is True
                break
        else:
            raise AssertionError("tool-calls-pending event not found")

    def test_mixed_auto_and_approval_emits_tool_calls_pending_for_batch(
        self, client, mock_api_key
    ):
        first_chunks = [
            b'data: {"type":"tool-input-available","toolCallId":"tc_auto","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2}}\n\n',
            b'data: {"type":"tool-input-available","toolCallId":"tc_need","toolName":"kiln_tool::multiply_numbers","input":{"a":3,"b":4},"kiln_metadata":{"requires_approval":true}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        mock_client, _ = make_n_round_mock_client(first_chunks, [])
        mock_class = MagicMock(return_value=mock_client)
        execute_tool_mock = AsyncMock(return_value="3")

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "hi"}]},
                )

        assert response.status_code == 200
        assert b"tool-calls-pending" in response.content
        execute_tool_mock.assert_not_called()
        for line in response.content.decode().split("\n"):
            if line.startswith("data: ") and "tool-calls-pending" in line:
                payload = json.loads(line[6:])
                ids = {i["toolCallId"] for i in payload["items"]}
                assert ids == {"tc_auto", "tc_need"}
                break
        else:
            raise AssertionError("tool-calls-pending event not found")


def test_post_execute_tools_runs_and_continues(client, mock_api_key):
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


def _sse_event(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode()


def _parse_sse_events(content: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in content.decode().split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            events.append(ev)
    return events


class TestMockedFlows:
    def test_text_only_chat_no_tools(self, client, mock_api_key):
        trace_id = "trace-text-only-abc"
        chunks = [
            _sse_event({"type": "kiln_chat_trace", "trace_id": trace_id}),
            sse_text_delta("Paris"),
            sse_text_delta(" is the capital."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, get_call_count = make_n_round_mock_client(chunks)
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "capital of France?"}]},
            )

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        text_deltas = [e for e in events if e.get("type") == "text-delta"]
        assert len(text_deltas) >= 1
        assert all(isinstance(e.get("delta"), str) and e["delta"] for e in text_deltas)

        trace_events = [e for e in events if e.get("type") == "kiln_chat_trace"]
        assert len(trace_events) == 1
        assert trace_events[0]["trace_id"] == trace_id

        finish_events = [e for e in events if e.get("type") == "finish"]
        assert any(
            (e.get("messageMetadata") or {}).get("finishReason") == "stop"
            for e in finish_events
        )

        assert not any(e.get("type") == "tool-input-available" for e in events)
        assert not any(e.get("type") == "tool-output-available" for e in events)
        assert not any(e.get("type") == "tool-calls-pending" for e in events)
        assert get_call_count() == 1

    def test_proxy_auto_executes_and_emits_full_flow(self, client, mock_api_key):
        trace_id = "trace-auto-exec-123"
        first_chunks = [
            _sse_event({"type": "kiln_chat_trace", "trace_id": trace_id}),
            sse_text_delta("Computing..."),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc1",
                    "toolName": "kiln_tool::multiply_numbers",
                    "input": {"a": 2, "b": 8},
                }
            ),
            _sse_event(
                {"type": "finish", "messageMetadata": {"finishReason": "tool-calls"}}
            ),
        ]
        second_chunks = [
            sse_text_delta("The result is 16."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="16")):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute 2*8"}]},
                )

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        tool_outputs = [e for e in events if e.get("type") == "tool-output-available"]
        assert len(tool_outputs) == 1
        assert tool_outputs[0]["toolCallId"] == "tc1"
        assert tool_outputs[0]["output"] == "16"

        joined_text = "".join(
            e["delta"] for e in events if e.get("type") == "text-delta"
        )
        assert "16" in joined_text

        assert get_call_count() == 2
        continuation_body = json.loads(
            mock_client.stream.call_args_list[1].kwargs["content"]
        )
        assert continuation_body["trace_id"] == trace_id
        messages = continuation_body["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["tool"]
        assert messages[0]["tool_call_id"] == "tc1"
        assert messages[0]["content"] == "16"

    def test_multi_turn_trace_continuation(self, client, mock_api_key):
        trace_id = "trace-multi-turn-xyz"
        first_chunks = [
            _sse_event({"type": "kiln_chat_trace", "trace_id": trace_id}),
            sse_text_delta("Got it, Bob."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        second_chunks = [
            sse_text_delta("Your name is Bob."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            r1 = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "my name is Bob"}]},
            )
        assert r1.status_code == 200
        assert get_call_count() == 1

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            r2 = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "what's my name?"}],
                    "trace_id": trace_id,
                },
            )
        assert r2.status_code == 200
        assert get_call_count() == 2

        second_body = json.loads(mock_client.stream.call_args_list[1].kwargs["content"])
        assert second_body["trace_id"] == trace_id
        assert len(second_body["messages"]) == 1
        assert second_body["messages"][0]["role"] == "user"
        assert second_body["messages"][0]["content"] == "what's my name?"

        events_r2 = _parse_sse_events(r2.content)
        text = "".join(e["delta"] for e in events_r2 if e.get("type") == "text-delta")
        assert "Bob" in text

    def test_execute_tools_denied_tool(self, client, mock_api_key):
        continuation_chunks = [
            sse_text_delta("Tool was denied."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, get_call_count = make_n_round_mock_client(continuation_chunks)
        mock_class = MagicMock(return_value=mock_client)

        body = {
            "trace_id": "tr-denied-1",
            "tool_calls": [
                {
                    "toolCallId": "tc_deny",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 10, "b": 20},
                    "requiresApproval": True,
                }
            ],
            "decisions": {"tc_deny": False},
        }

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="30")) as exec_mock:
                response = client.post("/api/chat/execute-tools", json=body)

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        tool_outputs = [e for e in events if e.get("type") == "tool-output-available"]
        assert len(tool_outputs) == 1
        assert tool_outputs[0]["toolCallId"] == "tc_deny"
        assert tool_outputs[0]["output"] == DENIED_TOOL_OUTPUT

        exec_mock.assert_not_called()

        continuation_body = json.loads(mock_client.stream.call_args.kwargs["content"])
        assert continuation_body["trace_id"] == "tr-denied-1"
        assert len(continuation_body["messages"]) == 1
        assert continuation_body["messages"][0]["role"] == "tool"
        assert continuation_body["messages"][0]["content"] == DENIED_TOOL_OUTPUT

    def test_execute_tools_mixed_approved_and_denied(self, client, mock_api_key):
        continuation_chunks = [
            sse_text_delta("Done."),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, _ = make_n_round_mock_client(continuation_chunks)
        mock_class = MagicMock(return_value=mock_client)

        body = {
            "trace_id": "tr-mixed-1",
            "tool_calls": [
                {
                    "toolCallId": "tc_yes",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                    "requiresApproval": True,
                },
                {
                    "toolCallId": "tc_no",
                    "toolName": "kiln_tool::multiply_numbers",
                    "input": {"a": 3, "b": 4},
                    "requiresApproval": True,
                },
            ],
            "decisions": {"tc_yes": True, "tc_no": False},
        }

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="3")):
                response = client.post("/api/chat/execute-tools", json=body)

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        tool_outputs = {
            e["toolCallId"]: e["output"]
            for e in events
            if e.get("type") == "tool-output-available"
        }
        assert tool_outputs["tc_yes"] == "3"
        assert tool_outputs["tc_no"] == DENIED_TOOL_OUTPUT

        continuation_body = json.loads(mock_client.stream.call_args.kwargs["content"])
        assert continuation_body["trace_id"] == "tr-mixed-1"
        tool_msgs = continuation_body["messages"]
        assert len(tool_msgs) == 2
        by_id = {m["tool_call_id"]: m["content"] for m in tool_msgs}
        assert by_id["tc_yes"] == "3"
        assert by_id["tc_no"] == DENIED_TOOL_OUTPUT

    def test_mixed_server_and_client_tools_auto_execute(self, client, mock_api_key):
        first_chunks = [
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_srv",
                    "toolName": "server_side_tool",
                    "input": {"x": 1},
                    "kiln_metadata": {"executor": "server"},
                }
            ),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_cli1",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 1, "b": 2},
                }
            ),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_cli2",
                    "toolName": "kiln_tool::multiply_numbers",
                    "input": {"a": 3, "b": 4},
                }
            ),
            _sse_event(
                {"type": "finish", "messageMetadata": {"finishReason": "tool-calls"}}
            ),
        ]
        second_chunks = [
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, get_call_count = make_n_round_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)
        execute_calls: list[tuple[str, dict]] = []
        original_results = {
            "kiln_tool::add_numbers": "3",
            "kiln_tool::multiply_numbers": "12",
        }

        async def mock_execute(tool_name, args):
            execute_calls.append((tool_name, args))
            return original_results.get(tool_name, "unknown")

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, side_effect=mock_execute):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute"}]},
                )

        assert response.status_code == 200
        assert get_call_count() == 2

        executed_names = {name for name, _ in execute_calls}
        assert "kiln_tool::add_numbers" in executed_names
        assert "kiln_tool::multiply_numbers" in executed_names
        assert "server_side_tool" not in executed_names

        events = _parse_sse_events(response.content)
        tool_output_ids = {
            e["toolCallId"] for e in events if e.get("type") == "tool-output-available"
        }
        assert tool_output_ids == {"tc_cli1", "tc_cli2"}
        assert "tc_srv" not in tool_output_ids

        continuation_body = json.loads(
            mock_client.stream.call_args_list[1].kwargs["content"]
        )
        tool_call_ids_in_continuation = {
            m["tool_call_id"]
            for m in continuation_body["messages"]
            if m["role"] == "tool"
        }
        assert tool_call_ids_in_continuation == {"tc_cli1", "tc_cli2"}

    def test_mixed_server_client_approval_emits_pending_for_client_only(
        self, client, mock_api_key
    ):
        first_chunks = [
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_srv",
                    "toolName": "server_side_tool",
                    "input": {"x": 1},
                    "kiln_metadata": {"executor": "server"},
                }
            ),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_auto",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 5, "b": 6},
                }
            ),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_approve",
                    "toolName": "kiln_tool::multiply_numbers",
                    "input": {"a": 7, "b": 8},
                    "kiln_metadata": {"requires_approval": True},
                }
            ),
            _sse_event(
                {"type": "finish", "messageMetadata": {"finishReason": "tool-calls"}}
            ),
        ]
        mock_client, get_call_count = make_n_round_mock_client(first_chunks)
        mock_class = MagicMock(return_value=mock_client)
        execute_tool_mock = AsyncMock()

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "compute"}]},
                )

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        pending = [e for e in events if e.get("type") == "tool-calls-pending"]
        assert len(pending) == 1
        pending_ids = {i["toolCallId"] for i in pending[0]["items"]}
        assert pending_ids == {"tc_auto", "tc_approve"}
        assert "tc_srv" not in pending_ids

        assert not any(e.get("type") == "tool-output-available" for e in events)
        execute_tool_mock.assert_not_called()
        assert get_call_count() == 1

    def test_sse_event_shapes_match_frontend_expectations(self, client, mock_api_key):
        trace_id = "trace-shapes-test"
        first_chunks = [
            _sse_event({"type": "kiln_chat_trace", "trace_id": trace_id}),
            _sse_event(
                {
                    "type": "start",
                    "messageId": "msg-test-123",
                    "kiln_metadata": {},
                }
            ),
            sse_text_delta("Calculating..."),
            _sse_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": "tc_shape",
                    "toolName": "kiln_tool::add_numbers",
                    "input": {"a": 5, "b": 10},
                }
            ),
            _sse_event(
                {"type": "finish", "messageMetadata": {"finishReason": "tool-calls"}}
            ),
        ]
        second_chunks = [
            sse_text_delta("15"),
            _sse_event({"type": "finish", "messageMetadata": {"finishReason": "stop"}}),
        ]
        mock_client, _ = make_n_round_mock_client(first_chunks, second_chunks)
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            with patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="15")):
                response = client.post(
                    "/api/chat",
                    json={"messages": [{"role": "user", "content": "add 5+10"}]},
                )

        assert response.status_code == 200
        events = _parse_sse_events(response.content)

        for ev in events:
            et = ev.get("type")
            if et == "text-delta":
                assert isinstance(ev.get("delta"), str)
                assert ev["delta"]
            elif et == "tool-input-available":
                assert isinstance(ev.get("toolCallId"), str)
                assert isinstance(ev.get("toolName"), str)
                assert "input" in ev
            elif et == "tool-output-available":
                assert isinstance(ev.get("toolCallId"), str)
                assert "output" in ev
            elif et == "kiln_chat_trace":
                assert isinstance(ev.get("trace_id"), str)
                assert ev["trace_id"]
            elif et == "finish":
                meta = ev.get("messageMetadata")
                assert meta is None or isinstance(meta, dict)
                if isinstance(meta, dict) and "finishReason" in meta:
                    assert isinstance(meta["finishReason"], str)

        type_set = {ev.get("type") for ev in events}
        assert "text-delta" in type_set
        assert "tool-input-available" in type_set
        assert "tool-output-available" in type_set
        assert "kiln_chat_trace" in type_set
        assert "finish" in type_set

        tool_outputs = [e for e in events if e.get("type") == "tool-output-available"]
        assert len(tool_outputs) == 1
        assert tool_outputs[0]["toolCallId"] == "tc_shape"
        assert tool_outputs[0]["output"] == "15"


def _find_endpoint_by_path(app, path: str):
    """Locate the endpoint function for a route with exact path match."""
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint  # type: ignore[attr-defined]
    raise AssertionError(f"Route with path {path} not found")


def test_chat_stream_has_no_write_lock(app):
    endpoint = _find_endpoint_by_path(app, "/api/chat")
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True


def test_execute_tools_has_no_write_lock(app):
    endpoint = _find_endpoint_by_path(app, "/api/chat/execute-tools")
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True
