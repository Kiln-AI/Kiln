"""Fake upstream + SSE fixture builders shared by the auto-mode unit tests.

These let the tests drive ``iter_upstream_round`` / ``AutoChatRunner`` /
``ChatStreamSession`` against a stubbed upstream without any network or backend.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

# ── SSE line builders (mirror the AI SDK / backend wire format) ──────────────


def sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


def text_delta(delta: str, id: str = "t1") -> bytes:
    return sse({"type": "text-delta", "id": id, "delta": delta})


def trace(trace_id: str) -> bytes:
    return sse({"type": "kiln_chat_trace", "trace_id": trace_id})


def tool_input_available(
    tool_call_id: str,
    tool_name: str,
    input: dict[str, Any] | None = None,
    kiln_metadata: dict[str, Any] | None = None,
) -> bytes:
    event: dict[str, Any] = {
        "type": "tool-input-available",
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "input": input or {},
    }
    if kiln_metadata is not None:
        event["kiln_metadata"] = kiln_metadata
    return sse(event)


def finish(reason: str | None = None) -> bytes:
    event: dict[str, Any] = {"type": "finish"}
    if reason is not None:
        event["messageMetadata"] = {"finishReason": reason}
    return sse(event)


def finish_tool_calls() -> bytes:
    return finish("tool-calls")


def error_event(error_text: str = "An internal error occurred.") -> bytes:
    return sse({"type": "error", "errorText": error_text, "kiln_metadata": {}})


# ── Fake httpx response / client ─────────────────────────────────────────────


class FakeUpstreamResponse:
    """One upstream round: a status code and a sequence of byte chunks.

    Set ``raise_protocol_error`` to simulate the server dropping the connection
    after emitting ``chunks``."""

    def __init__(
        self,
        chunks: list[bytes] | None = None,
        status_code: int = 200,
        body: bytes = b"",
        raise_protocol_error: bool = False,
        raise_connect_error: bool = False,
        raise_transport_error_after_chunks: bool = False,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks or []
        self._body = body
        self._raise_protocol_error = raise_protocol_error
        self._raise_connect_error = raise_connect_error
        self._raise_transport_error_after_chunks = raise_transport_error_after_chunks

    async def aread(self) -> bytes:
        return self._body

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk
        if self._raise_protocol_error:
            raise httpx.RemoteProtocolError("Server disconnected")
        if self._raise_transport_error_after_chunks:
            # A mid-stream transport failure that is NOT a RemoteProtocolError
            # (e.g. a read timeout), so it propagates out of iter_upstream_round
            # for the runner to classify — after content was already forwarded.
            raise httpx.ReadError("Connection dropped mid-stream")

    async def __aenter__(self):
        # Simulate a pre-response connection failure (raised before any status /
        # bytes), distinct from a mid-stream RemoteProtocolError.
        if self._raise_connect_error:
            raise httpx.ConnectError("connection refused")
        return self

    async def __aexit__(self, *args):
        pass


class FakeUpstreamClient:
    """Stand-in for ``httpx.AsyncClient`` that returns queued responses in order
    and records the request bodies it was POSTed."""

    def __init__(self, responses: list[FakeUpstreamResponse]) -> None:
        self._responses = list(responses)
        self.bodies: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, *, content: bytes, headers: dict):
        self.bodies.append(json.loads(content.decode()))
        if not self._responses:
            raise AssertionError("FakeUpstreamClient ran out of queued responses")
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass
