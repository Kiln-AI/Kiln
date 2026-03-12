import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.chat_api import (
    _build_continuation_body,
    _execute_client_tool,
    _parse_sse_events,
    connect_chat_api,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_chat_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


def _make_httpx_mock(status_code: int = 200, chunks: list[bytes] | None = None):
    if chunks is None:
        chunks = [b'data: {"type":"text-delta","delta":"hello"}\n\n']

    async def mock_aiter_bytes():
        for chunk in chunks:
            yield chunk

    mock_upstream = MagicMock()
    mock_upstream.status_code = status_code
    mock_upstream.aiter_bytes.return_value = mock_aiter_bytes()
    mock_upstream.aread = AsyncMock(
        return_value=b'{"message":"upstream error"}' if status_code != 200 else b""
    )
    mock_upstream.__aenter__ = AsyncMock(return_value=mock_upstream)
    mock_upstream.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_upstream
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_async_client_class = MagicMock(return_value=mock_client)
    return mock_async_client_class, mock_client, mock_upstream


# --- SSE passthrough tests ---


class TestChatStreaming:
    def test_streams_chunks(self, client, mock_api_key):
        chunks = [
            b'data: {"type":"text-delta","delta":"hello"}\n\n',
            b'data: {"type":"finish"}\n\n',
        ]
        mock_class, _, _ = _make_httpx_mock(chunks=chunks)

        with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert b"text-delta" in response.content

    def test_forwards_auth_header(self, client, mock_api_key):
        mock_class, mock_client, _ = _make_httpx_mock()

        with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
            client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

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
        mock_class, _, _ = _make_httpx_mock(status_code=500)

        with patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert b"error" in response.content


# --- SSE parsing tests ---


class TestParseSSEEvents:
    def test_passthrough_normal_events(self):
        raw = b'data: {"type":"text-delta","delta":"hi"}\n\n'
        lines, tool_event = _parse_sse_events(raw)
        assert tool_event is None
        assert any(b"text-delta" in line for line in lines)

    def test_detects_client_tool_call(self):
        raw = (
            b'data: {"type":"text-delta","delta":"hi"}\n'
            b'data: {"type":"client-tool-call","toolCallId":"tc1","toolName":"read_task_run","input":{"path":"/x"}}\n\n'
        )
        lines, tool_event = _parse_sse_events(raw)
        assert tool_event is not None
        assert tool_event["toolName"] == "read_task_run"
        assert tool_event["toolCallId"] == "tc1"
        assert not any(b"client-tool-call" in line for line in lines)

    def test_handles_empty_input(self):
        lines, tool_event = _parse_sse_events(b"")
        assert tool_event is None


# --- Client tool execution tests ---


class TestExecuteClientTool:
    def test_read_task_run_success(self):
        mock_run = MagicMock()
        mock_run.model_dump_json.return_value = '{"id": "42", "input": "hello"}'

        with patch(
            "app.desktop.studio_server.chat_api._find_task_run_by_id",
            return_value=mock_run,
        ):
            result = _execute_client_tool("read_task_run", {"task_run_id": "42"})
        assert '"id": "42"' in result

    def test_read_task_run_not_found(self):
        with patch(
            "app.desktop.studio_server.chat_api._find_task_run_by_id",
            return_value=None,
        ):
            result = _execute_client_tool("read_task_run", {"task_run_id": "999"})
        parsed = json.loads(result)
        assert "error" in parsed
        assert "999" in parsed["error"]

    def test_read_task_run_missing_id(self):
        result = _execute_client_tool("read_task_run", {})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_unknown_tool(self):
        result = _execute_client_tool("unknown_tool", {})
        assert "Unknown client tool" in result


# --- Continuation body tests ---


class TestBuildContinuationBody:
    def test_appends_tool_messages(self):
        original = {"messages": [{"role": "user", "content": "hi"}]}
        result = _build_continuation_body(
            original, "tc1", "read_task_run", {"path": "/x"}, '{"data": "result"}'
        )

        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["parts"][0]["toolCallId"] == "tc1"
        assert result["messages"][1]["parts"][0]["state"] == "call"
        assert result["messages"][2]["role"] == "assistant"
        assert result["messages"][2]["parts"][0]["state"] == "output-available"
        assert result["messages"][2]["parts"][0]["output"] == '{"data": "result"}'

    def test_preserves_original_body_fields(self):
        original = {
            "messages": [{"role": "user", "content": "hi"}],
            "task_id": "test_task",
        }
        result = _build_continuation_body(original, "tc1", "tool", {}, "result")
        assert result["task_id"] == "test_task"


# --- Client tool round-trip test ---


class TestClientToolRoundTrip:
    def test_detects_and_continues_after_client_tool(self, client, mock_api_key):
        """First request returns client-tool-call, proxy executes locally and sends continuation."""
        first_response_chunks = [
            b'data: {"type":"text-delta","delta":"Let me read that"}\n\n',
            b'data: {"type":"client-tool-call","toolCallId":"tc1","toolName":"read_task_run","input":{"path":"/fake"}}\n\n',
            b'data: {"type":"finish"}\n\n',
        ]
        second_response_chunks = [
            b'data: {"type":"text-delta","delta":"Here is the result"}\n\n',
            b'data: {"type":"finish"}\n\n',
        ]

        call_count = 0

        def make_stream_mock(chunks):
            async def mock_aiter_bytes():
                for chunk in chunks:
                    yield chunk

            mock_upstream = MagicMock()
            mock_upstream.status_code = 200
            mock_upstream.aiter_bytes.return_value = mock_aiter_bytes()
            mock_upstream.__aenter__ = AsyncMock(return_value=mock_upstream)
            mock_upstream.__aexit__ = AsyncMock(return_value=None)
            return mock_upstream

        def side_effect_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_stream_mock(first_response_chunks)
            return make_stream_mock(second_response_chunks)

        mock_client = MagicMock()
        mock_client.stream.side_effect = side_effect_stream
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_class = MagicMock(return_value=mock_client)

        with (
            patch("app.desktop.studio_server.chat_api.httpx.AsyncClient", mock_class),
            patch(
                "app.desktop.studio_server.chat_api._execute_client_tool",
                return_value='{"data": "mock result"}',
            ),
        ):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "read my task run"}]},
            )

        assert response.status_code == 200
        content = response.content
        assert b"Let me read that" in content
        assert b"Here is the result" in content
        assert call_count == 2

        continuation_call = mock_client.stream.call_args_list[1]
        continuation_body = json.loads(continuation_call.kwargs["content"])
        assert len(continuation_body["messages"]) == 3
