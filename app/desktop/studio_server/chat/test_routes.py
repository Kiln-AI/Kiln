import json
from http import HTTPStatus
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
from app.desktop.studio_server.chat.helpers import (
    PATCH_ASYNC_CLIENT,
    PATCH_EXECUTE_TOOL,
    make_httpx_mock,
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
    def _make_stream_mock(self, chunks: list[bytes]):
        async def mock_aiter_bytes():
            for chunk in chunks:
                yield chunk

        mock_upstream = MagicMock()
        mock_upstream.status_code = 200
        mock_upstream.aiter_bytes.return_value = mock_aiter_bytes()
        mock_upstream.__aenter__ = AsyncMock(return_value=mock_upstream)
        mock_upstream.__aexit__ = AsyncMock(return_value=None)
        return mock_upstream

    def _make_mock_client(self, first_chunks: list[bytes], second_chunks: list[bytes]):
        call_count = 0
        first_mock = self._make_stream_mock(first_chunks)
        second_mock = self._make_stream_mock(second_chunks)

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count_ref = call_count
            call_count += 1
            return first_mock if call_count_ref == 0 else second_mock

        mock_client = MagicMock()
        mock_client.stream.side_effect = side_effect
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        return mock_client, lambda: call_count

    def test_continues_after_tool_input_available(self, client, mock_api_key):
        """First request returns tool-input-available + finish tool-calls; proxy runs the built-in tool and continues."""
        first_chunks = [
            sse_text_delta("Let me compute that"),
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::multiply_numbers","input":{"a":2,"b":8}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [
            sse_text_delta("The answer is 16"),
            b'data: {"type":"finish"}\n\n',
        ]

        mock_client, get_call_count = self._make_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
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
        assert tc["function"]["name"] == "kiln_tool::multiply_numbers"
        assert json.loads(tc["function"]["arguments"]) == {"a": 2, "b": 8}

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
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::multiply_numbers","input":{"a":2,"b":8}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
            f'data: {{"type":"kiln_chat_trace","trace_id":"{trace_tid}"}}\n\n'.encode(),
        ]
        second_chunks = [
            sse_text_delta("The answer is 16"),
            b'data: {"type":"finish"}\n\n',
        ]

        mock_client, get_call_count = self._make_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
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
        mock_client, get_call_count = self._make_mock_client(first_chunks, [])
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
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [b'data: {"type":"finish"}\n\n']

        mock_client, _ = self._make_mock_client(first_chunks, second_chunks)
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
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
            b'data: {"type":"tool-input-available","toolCallId":"tc1","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2}}\n\n',
            b'data: {"type":"tool-input-available","toolCallId":"tc2","toolName":"kiln_tool::multiply_numbers","input":{"a":3,"b":4}}\n\n',
            b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
        ]
        second_chunks = [b'data: {"type":"finish"}\n\n']

        mock_client, get_call_count = self._make_mock_client(
            first_chunks, second_chunks
        )
        mock_class = MagicMock(return_value=mock_client)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
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
        mock_client, get_call_count = self._make_mock_client(first_chunks, [])
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
        mock_client, _ = self._make_mock_client(first_chunks, [])
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
        mock_client, _ = self._make_mock_client(first_chunks, [])
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
