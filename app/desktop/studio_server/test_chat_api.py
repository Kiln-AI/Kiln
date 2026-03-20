import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from app.desktop.studio_server.api_client.kiln_ai_server_client.api.health import (
    ping_ping_get,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_kiln_server_client,
)
from app.desktop.studio_server.chat_api import (
    _build_continuation_body,
    _execute_client_tool,
    _parse_sse_events,
    connect_chat_api,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config
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
        lines, tool_event, fin_tool = _parse_sse_events(raw)
        assert tool_event is None
        assert fin_tool is False
        assert any(b"text-delta" in line for line in lines)

    def test_detects_client_tool_call(self):
        raw = (
            b'data: {"type":"text-delta","delta":"hi"}\n'
            b'data: {"type":"client-tool-call","toolCallId":"tc1","toolName":"read_task_run","input":{"path":"/x"}}\n\n'
        )
        lines, tool_event, fin_tool = _parse_sse_events(raw)
        assert tool_event is not None
        assert fin_tool is False
        assert tool_event["toolName"] == "read_task_run"
        assert tool_event["toolCallId"] == "tc1"
        assert not any(b"client-tool-call" in line for line in lines)

    def test_detects_ai_sdk_tool_calls_finish(self):
        raw = b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n'
        lines, tool_event, fin_tool = _parse_sse_events(raw)
        assert tool_event is None
        assert fin_tool is True
        assert any(b"finish" in line for line in lines)

    def test_handles_empty_input(self):
        lines, tool_event, fin_tool = _parse_sse_events(b"")
        assert tool_event is None
        assert fin_tool is False


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

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"

        parts = result["messages"][1]["parts"]
        assert result["messages"][1]["role"] == "assistant"
        assert len(parts) == 2
        assert parts[0]["toolCallId"] == "tc1"
        assert parts[0]["state"] == "call"
        assert parts[0]["input"] == {"path": "/x"}
        assert parts[1]["state"] == "output-available"
        assert parts[1]["output"] == '{"data": "result"}'
        assert "input" not in parts[1]

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
        assert len(continuation_body["messages"]) == 2


_MAX_TOOL_ROUNDS_INTEGRATION = 5


def _sse_json_from_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    payload = line[6:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        out = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


def _finish_reason_is_tool_calls(event: dict[str, Any]) -> bool:
    meta = event.get("messageMetadata") or {}
    return meta.get("finishReason") == "tool-calls"


def _execute_math_tool_for_integration(
    tool_name: str, arguments: dict[str, Any]
) -> str:
    """Mirror libs/core paid litellm streaming tests: built-in math tool names and {a,b} args."""
    base = tool_name.split("::")[-1]
    aliases = {
        "multiply_numbers": "multiply",
        "add_numbers": "add",
        "subtract_numbers": "subtract",
        "divide_numbers": "divide",
    }
    name = aliases.get(base, tool_name)
    a, b = float(arguments.get("a", 0)), float(arguments.get("b", 0))
    if name == "add":
        result = a + b
    elif name == "subtract":
        result = a - b
    elif name == "multiply":
        result = a * b
    elif name == "divide":
        result = a / b
    else:
        return json.dumps(
            {"error": f"integration test: unsupported tool {tool_name!r}"}
        )
    text = str(int(result)) if result == int(result) else str(result)
    return text


def _openai_assistant_and_tool_messages(
    assistant_text: str,
    tool_input_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    tool_messages: list[dict[str, Any]] = []
    for ev in tool_input_events:
        tc_id = ev["toolCallId"]
        tname = ev["toolName"]
        inp = ev.get("input")
        if inp is None:
            inp = {}
        if isinstance(inp, str):
            arg_str = inp
            try:
                raw_args = json.loads(inp)
            except json.JSONDecodeError:
                raw_args = {}
        else:
            arg_str = json.dumps(inp)
            raw_args = inp if isinstance(inp, dict) else {}
        tool_calls.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": tname, "arguments": arg_str},
            }
        )
        if not isinstance(raw_args, dict):
            raw_args = {}
        result_str = _execute_math_tool_for_integration(tname, raw_args)
        tool_messages.append(
            {"role": "tool", "tool_call_id": tc_id, "content": result_str}
        )

    text = assistant_text.strip()
    assistant: dict[str, Any] = {
        "role": "assistant",
        "content": text if text else None,
        "tool_calls": tool_calls,
    }
    return [assistant, *tool_messages]


def _kiln_copilot_api_key_for_integration() -> str | None:
    """Resolve the Copilot API key for paid tests.

    Unit tests patch Config.settings_path to an empty temp file, so keys stored
    only in the real user settings.yaml are invisible to Config unless we read
    that file or the key is in the environment.
    """
    if key := os.environ.get("KILN_COPILOT_API_KEY"):
        return key.strip() or None
    settings_file = Path(Config.settings_dir(create=False)) / "settings.yaml"
    if not settings_file.is_file():
        return None
    data = yaml.safe_load(settings_file.read_text()) or {}
    raw = data.get("kiln_copilot_api_key")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


@pytest.mark.paid
def test_api_integration():
    kiln_client = get_kiln_server_client()
    assert ping_ping_get.sync(client=kiln_client) == "pong"


@pytest.mark.paid
def test_chat_api_integration(app):
    api_key = _kiln_copilot_api_key_for_integration()
    if not api_key:
        pytest.skip(
            "No Kiln Copilot API key: set KILN_COPILOT_API_KEY or kiln_copilot_api_key "
            f"in {Path(Config.settings_dir(create=False)) / 'settings.yaml'}"
        )
    client = TestClient(app)
    collected = bytearray()
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "hi - my name is bob. Can you compute 2 * 8 for me? "
                "Use the multiply tool if available."
            ),
        }
    ]

    with patch.dict(os.environ, {"KILN_COPILOT_API_KEY": api_key}, clear=False):
        for round_i in range(_MAX_TOOL_ROUNDS_INTEGRATION):
            pending_tool_inputs: list[dict[str, Any]] = []
            assistant_chunks: list[str] = []
            stop_with_tool_calls = False

            with client.stream(
                "POST",
                "/api/chat",
                json={"messages": messages},
                timeout=httpx.Timeout(120.0, connect=30.0),
            ) as response:
                assert response.status_code == 200
                ctype = response.headers.get("content-type", "")
                assert ctype.startswith("text/event-stream")
                for line in response.iter_lines():
                    text = line or ""
                    print(text, flush=True)
                    collected.extend(text.encode("utf-8"))
                    collected.extend(b"\n")

                    ev = _sse_json_from_line(text)
                    if not ev:
                        continue
                    et = ev.get("type")
                    if et == "text-delta":
                        delta = ev.get("delta")
                        if isinstance(delta, str):
                            assistant_chunks.append(delta)
                    elif et == "tool-input-available":
                        pending_tool_inputs.append(ev)
                    elif et == "finish" and _finish_reason_is_tool_calls(ev):
                        stop_with_tool_calls = True

            if not stop_with_tool_calls:
                break

            assert pending_tool_inputs, (
                "finishReason tool-calls but no tool-input-available events"
            )
            continuation = _openai_assistant_and_tool_messages(
                "".join(assistant_chunks), pending_tool_inputs
            )
            messages = messages + continuation
        else:
            pytest.fail(
                f"Exceeded {_MAX_TOOL_ROUNDS_INTEGRATION} tool rounds without finishing"
            )

    content = bytes(collected)
    assert len(content) > 0
    assert b"data:" in content
    assert b"16" in content or b'"16"' in content
