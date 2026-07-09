import json
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

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
from app.desktop.studio_server.chat.routes import ChatSessionSnapshot
from app.desktop.studio_server.chat.helpers import (
    PATCH_ASYNC_CLIENT,
    PATCH_EXECUTE_TOOL,
    make_httpx_mock,
    make_n_round_mock_client,
    sse_text_delta,
)
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse
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
        # 404 (non-retryable) surfaces immediately as an SSE error. Retryable
        # statuses (5xx/429) go through the retry loop instead (covered in
        # test_stream_session.py), so they'd block on backoff here.
        mock_class, _, _ = make_httpx_mock(status_code=404)

        with patch(PATCH_ASYNC_CLIENT, mock_class):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert response.status_code == 200
        assert b"error" in response.content

    def test_uses_cancellable_streaming_response(self, client, mock_api_key):
        mock_class, _, _ = make_httpx_mock()

        with (
            patch(PATCH_ASYNC_CLIENT, mock_class),
            patch(
                "app.desktop.studio_server.chat.routes.CancellableStreamingResponse",
                wraps=CancellableStreamingResponse,
            ) as mock_cls,
        ):
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            _ = response.content

        assert response.status_code == 200
        mock_cls.assert_called_once()

    def test_has_no_write_lock_decorator(self, app):
        for route in app.routes:
            if getattr(route, "path", None) == "/api/chat" and "POST" in getattr(
                route, "methods", set()
            ):
                assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
                    "/api/chat must be @no_write_lock so GitSyncMiddleware does "
                    "not wrap receive/send and break SSE disconnect cancellation"
                )
                return
        raise AssertionError("POST /api/chat route not found")


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
        {
            "id": "trace-1",
            "title": "Hi",
            "updated_at": "2025-06-15T12:30:00Z",
            "auto_active": False,
            "auto_run_id": None,
            "agent_type": None,
            "root_id": None,
            "parent_root_id": None,
            "is_subagent": False,
            "subagent_id": None,
            "subagent_status": None,
        }
    ]
    mock_asyncio_detailed.assert_called_once()
    call_kwargs = mock_asyncio_detailed.call_args[1]
    assert "client" in call_kwargs


@patch(
    "app.desktop.studio_server.chat.routes.list_sessions_v1_chat_sessions_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_list_chat_sessions_auto_join_reads_supervisor(
    mock_asyncio_detailed, client, mock_api_key, monkeypatch
):
    # Phase 3: the auto_active/auto_run_id join reads the conversation
    # supervisor (the old AutoChatRegistry is gone). auto_run_id carries the
    # auto conversation's SESSION id, and the join keys on flag-on records —
    # the green dot persists while IDLE, disappears once stopped/disabled
    # (old AutoRunStatus.flag_on semantics).
    from app.desktop.studio_server.chat import routes as routes_module
    from app.desktop.studio_server.chat.runtime.supervisor import (
        ConversationSupervisor,
    )

    sup = ConversationSupervisor()
    monkeypatch.setattr(routes_module, "conversation_supervisor", sup)
    record = sup.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    # Adopt the row's leaf like enable_auto does (whole-chain index).
    record.current_leaf_trace_id = "t1"
    record.seen_trace_ids.append("t1")
    sup._trace_index["t1"] = record.session_id

    parsed_item = SdkChatSessionListItem.from_dict(
        {
            "id": "t1",
            "title": "Active one",
            "updated_at": "2025-06-15T12:30:00+00:00",
            "task_run": _make_task_run_dict(),
        }
    )
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"[]",
        headers={"content-type": "application/json"},
        parsed=[parsed_item],
    )

    r = client.get("/api/chat/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["auto_active"] is True
    assert body[0]["auto_run_id"] == record.session_id

    # Flag off → the join drops it (no green dot after stop/disable).
    record.auto_flag = False
    r = client.get("/api/chat/sessions")
    assert r.json()[0]["auto_active"] is False
    assert r.json()[0]["auto_run_id"] is None


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
def test_get_chat_session_round_trips_context_usage(
    mock_asyncio_detailed, client, mock_api_key
):
    # Upstream now emits a top-level ``context_usage`` alongside ``id`` /
    # ``task_run``. The generated SDK model only declares id + task_run and
    # stashes extras in ``additional_properties``, which ``to_dict()`` re-emits,
    # so the field survives into ``ChatSessionSnapshot`` once the field exists.
    snapshot_dict = {
        "id": "trace-ctx",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
        "context_usage": {
            "context_tokens": 1234,
            "context_limit": 150000,
            "context_percent": 0.0082,
            "compacted": True,
        },
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-ctx")

    assert r.status_code == 200
    body = r.json()
    assert body["context_usage"] == {
        "context_tokens": 1234,
        "context_limit": 150000,
        "context_percent": 0.0082,
        "compacted": True,
    }


def test_chat_session_snapshot_drops_unknown_keys_invariant():
    # Pin the containment invariant at the model level, independent of the route
    # round-trip: a valid snapshot carrying the server-only ``compacted_trace``
    # validates successfully (no 500) AND the unknown key is dropped, so it can
    # never reach the client (functional_spec.md §7.3). This guards against a
    # maintainer "tightening" the config to ``extra="forbid"`` (which would raise
    # instead of drop) or relying on an unstated default.
    snapshot = ChatSessionSnapshot.model_validate(
        {
            "id": "trace-invariant",
            "task_run": {"trace": [{"role": "user", "content": "hi"}]},
            "context_usage": {
                "context_tokens": 1,
                "context_limit": 2,
                "context_percent": 0.5,
                "compacted": False,
            },
            "compacted_trace": [{"role": "system", "content": "secret"}],
        }
    )

    assert not hasattr(snapshot, "compacted_trace")
    assert "compacted_trace" not in snapshot.model_dump()
    assert snapshot.id == "trace-invariant"
    assert snapshot.context_usage is not None


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_drops_compacted_trace(
    mock_asyncio_detailed, client, mock_api_key
):
    # Defense in depth (functional_spec.md §7.3): even if a regressed upstream
    # leaked the server-only ``compacted_trace``, ``ChatSessionSnapshot``'s
    # ``extra="ignore"`` config must drop it at the client boundary. The full
    # ``task_run.trace`` and the gauge numbers still come through.
    snapshot_dict = {
        "id": "trace-leak",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "hi"}]),
        "compacted_trace": [{"role": "system", "content": "<compaction_summary>..."}],
        "context_usage": {
            "context_tokens": 99,
            "context_limit": 150000,
            "context_percent": 0.0007,
            "compacted": True,
        },
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-leak")

    assert r.status_code == 200
    body = r.json()
    assert "compacted_trace" not in body
    assert body["task_run"]["trace"] == [{"role": "user", "content": "hi"}]
    assert body["context_usage"]["compacted"] is True


@patch(
    "app.desktop.studio_server.chat.routes.get_session_v1_chat_sessions_session_id_get.asyncio_detailed",
    new_callable=AsyncMock,
)
def test_get_chat_session_tolerates_missing_context_usage(
    mock_asyncio_detailed, client, mock_api_key
):
    # Backward compatibility: an older upstream that omits ``context_usage`` must
    # not 500 the proxy. ``response_model_exclude_none`` drops the absent field.
    snapshot_dict = {
        "id": "trace-old",
        "task_run": _make_task_run_dict(trace=[{"role": "user", "content": "yo"}]),
    }
    parsed = ChatSnapshot.from_dict(snapshot_dict)
    mock_asyncio_detailed.return_value = KilnResponse(
        status_code=HTTPStatus.OK,
        content=b"{}",
        headers={"content-type": "application/json"},
        parsed=parsed,
    )

    r = client.get("/api/chat/sessions/trace-old")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "trace-old"
    assert "context_usage" not in body


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


def test_execute_tools_uses_cancellable_streaming_response(client, mock_api_key):
    mock_class, _, _ = make_httpx_mock(
        chunks=[sse_text_delta("ok"), b'data: {"type":"finish"}\n\n']
    )
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

    with (
        patch(PATCH_ASYNC_CLIENT, mock_class),
        patch(PATCH_EXECUTE_TOOL, AsyncMock(return_value="3")),
        patch(
            "app.desktop.studio_server.chat.routes.CancellableStreamingResponse",
            wraps=CancellableStreamingResponse,
        ) as mock_cls,
    ):
        response = client.post("/api/chat/execute-tools", json=body)
        _ = response.content

    assert response.status_code == 200
    mock_cls.assert_called_once()


def test_execute_tools_has_no_write_lock_decorator(app):
    for route in app.routes:
        if getattr(
            route, "path", None
        ) == "/api/chat/execute-tools" and "POST" in getattr(route, "methods", set()):
            assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
                "/api/chat/execute-tools must be @no_write_lock so "
                "GitSyncMiddleware does not wrap receive/send and break "
                "SSE disconnect cancellation"
            )
            return
    raise AssertionError("POST /api/chat/execute-tools route not found")


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


# --- GET /api/chat/version_policy proxy ---

PATCH_ROUTES_ASYNC_CLIENT = "app.desktop.studio_server.chat.routes.httpx.AsyncClient"


def _mock_version_policy_client(*, json_body=None, status_code=200):
    """Build a mock httpx.AsyncClient whose async .get() returns a fake response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=http_client)


def test_version_policy_forwards_and_parses(client, mock_api_key):
    mock_class = _mock_version_policy_client(
        json_body={"required": False, "upgrade_nudge_version": "1.0.5"}
    )
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": "1.0.5"}


def test_version_policy_degrades_on_non_200(client, mock_api_key):
    mock_class = _mock_version_policy_client(json_body={}, status_code=503)
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


def test_version_policy_degrades_on_invalid_upstream_body(client, mock_api_key):
    # Pydantic v2 ValidationError is not a ValueError; ensure it's caught and we
    # degrade to "no banner" rather than 500.
    mock_class = _mock_version_policy_client(json_body={"required": "not-a-bool"})
    with patch(PATCH_ROUTES_ASYNC_CLIENT, mock_class):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


def test_version_policy_degrades_on_transport_error(client, mock_api_key):
    http_client = MagicMock()
    http_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    with patch(PATCH_ROUTES_ASYNC_CLIENT, MagicMock(return_value=http_client)):
        r = client.get("/api/chat/version_policy")
    assert r.status_code == 200
    assert r.json() == {"required": False, "upgrade_nudge_version": None}


# ── Auto-mode interception on the interactive stream (port of the old
#    chat/auto/test_api.py /api/chat coverage; the interactive loop still
#    hosts these interceptions until phase 4). ─────────────────────────────────


def test_enable_auto_mode_emits_consent_required(client, mock_api_key):
    chunks = [
        b'data: {"type":"kiln_chat_trace","trace_id":"t1"}\n\n',
        sse_text_delta("I can run this for you"),
        b'data: {"type":"tool-input-available","toolCallId":"tc_enable","toolName":"enable_auto_mode","input":{"reason":"run the full eval"}}\n\n',
        b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
    ]
    mock_client, get_call_count = make_n_round_mock_client(chunks, [])
    execute_tool_mock = AsyncMock()

    with patch(PATCH_ASYNC_CLIENT, MagicMock(return_value=mock_client)):
        with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
            r = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "run my eval"}]},
            )

    assert r.status_code == 200
    consent = [
        e
        for e in _parse_sse_events(r.content)
        if e.get("type") == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["enable_tool_call_id"] == "tc_enable"
    assert consent[0]["trace_id"] == "t1"
    assert consent[0]["reason"] == "run the full eval"
    assert consent[0]["sibling_tool_calls"] == []
    # enable_auto_mode is never executed and the loop returns (single round).
    execute_tool_mock.assert_not_called()
    assert get_call_count() == 1


def test_enable_auto_mode_carries_sibling_tool_calls(client, mock_api_key):
    chunks = [
        sse_text_delta("here we go"),
        b'data: {"type":"tool-input-available","toolCallId":"tc_enable","toolName":"enable_auto_mode","input":{}}\n\n',
        b'data: {"type":"tool-input-available","toolCallId":"tc_sib","toolName":"kiln_tool::add_numbers","input":{"a":1,"b":2}}\n\n',
        b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
    ]
    mock_client, _ = make_n_round_mock_client(chunks, [])
    with patch(PATCH_ASYNC_CLIENT, MagicMock(return_value=mock_client)):
        r = client.post(
            "/api/chat", json={"messages": [{"role": "user", "content": "go"}]}
        )

    assert r.status_code == 200
    consent = [
        e
        for e in _parse_sse_events(r.content)
        if e.get("type") == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["reason"] is None
    assert {s["toolCallId"] for s in consent[0]["sibling_tool_calls"]} == {"tc_sib"}


def _seed_live_auto_conversation(monkeypatch, trace_id: str = "t1"):
    """A fresh supervisor holding a flag-on IDLE auto conversation indexed
    under ``trace_id``, patched over the singleton the interception path
    (stream_session._clear_auto_mode_flag) resolves lazily."""
    from app.desktop.studio_server.chat.runtime import supervisor as supervisor_module
    from app.desktop.studio_server.chat.runtime.supervisor import (
        ConversationSupervisor,
    )

    sup = ConversationSupervisor(terminal_ttl_seconds=60.0)
    monkeypatch.setattr(supervisor_module, "conversation_supervisor", sup)
    record = sup.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    record.current_leaf_trace_id = trace_id
    record.seen_trace_ids.append(trace_id)
    sup._trace_index[trace_id] = record.session_id
    return sup, record


def test_disable_auto_mode_intercepted_and_continues_interactively(
    client, mock_api_key, monkeypatch
):
    # The model calls disable_auto_mode on the interactive stream → it is
    # intercepted (never executed), the SUPERVISOR conversation's flag clears
    # with reason user_disabled (phase 3 retargeted the cascade from the old
    # auto registry), the call resolves {"status":"disabled"}, and the stream
    # continues interactively (a second upstream round runs).
    sup, record = _seed_live_auto_conversation(monkeypatch)
    round1 = [
        b'data: {"type":"kiln_chat_trace","trace_id":"t1"}\n\n',
        sse_text_delta("turning auto mode off"),
        b'data: {"type":"tool-input-available","toolCallId":"tc_disable","toolName":"disable_auto_mode","input":{}}\n\n',
        b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
    ]
    round2 = [
        sse_text_delta("back to interactive"),
        b'data: {"type":"finish","messageMetadata":{"finishReason":"stop"}}\n\n',
    ]
    mock_client, get_call_count = make_n_round_mock_client(round1, round2)
    execute_tool_mock = AsyncMock()

    with patch(PATCH_ASYNC_CLIENT, MagicMock(return_value=mock_client)):
        with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
            r = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "stop auto mode"}]},
            )

    assert r.status_code == 200
    events = _parse_sse_events(r.content)
    # disable_auto_mode is never executed.
    execute_tool_mock.assert_not_called()
    # The flag cleared on the live supervisor record with the disable reason.
    assert record.auto_flag is False
    assert record.idle_reason == "user_disabled"
    # The interactive stream resolved the call as disabled…
    disabled_outputs = [
        json.loads(e["output"])
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_disable"
    ]
    assert disabled_outputs == [{"status": "disabled"}]
    # …and continued interactively (two upstream rounds).
    assert any(
        e.get("type") == "text-delta" and e.get("delta") == "back to interactive"
        for e in events
    )
    assert get_call_count() == 2


def test_disable_auto_mode_interactive_sibling_requiring_approval_is_denied(
    client, mock_api_key, monkeypatch
):
    # On the INTERACTIVE disable path, a sibling bundled in the same turn as
    # disable_auto_mode goes through the normal approval gate, NOT
    # auto-approval: with no decision available on this path it is denied
    # (DENIED_TOOL_OUTPUT) rather than run without consent.
    _seed_live_auto_conversation(monkeypatch)
    round1 = [
        b'data: {"type":"kiln_chat_trace","trace_id":"t1"}\n\n',
        b'data: {"type":"tool-input-available","toolCallId":"tc_disable","toolName":"disable_auto_mode","input":{}}\n\n',
        b'data: {"type":"tool-input-available","toolCallId":"tc_sibling","toolName":"call_kiln_api","input":{"x":1},"kiln_metadata":{"requires_approval":true}}\n\n',
        b'data: {"type":"finish","messageMetadata":{"finishReason":"tool-calls"}}\n\n',
    ]
    round2 = [
        sse_text_delta("back to interactive"),
        b'data: {"type":"finish","messageMetadata":{"finishReason":"stop"}}\n\n',
    ]
    mock_client, _ = make_n_round_mock_client(round1, round2)
    execute_tool_mock = AsyncMock()

    with patch(PATCH_ASYNC_CLIENT, MagicMock(return_value=mock_client)):
        with patch(PATCH_EXECUTE_TOOL, execute_tool_mock):
            r = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "stop auto mode"}]},
            )

    assert r.status_code == 200
    events = _parse_sse_events(r.content)
    execute_tool_mock.assert_not_called()
    sibling_outputs = [
        e["output"]
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_sibling"
    ]
    assert sibling_outputs == [DENIED_TOOL_OUTPUT]
    disabled_outputs = [
        json.loads(e["output"])
        for e in events
        if e.get("type") == "tool-output-available"
        and e.get("toolCallId") == "tc_disable"
    ]
    assert disabled_outputs == [{"status": "disabled"}]
