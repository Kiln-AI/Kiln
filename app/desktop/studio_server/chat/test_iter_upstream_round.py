"""Golden regression: prove the iter_upstream_round round mechanics leave the
interactive stream output byte-for-byte unchanged.

Originally written against ChatStreamSession.stream() (which inlined the
per-round upstream mechanics before the iter_upstream_round refactor); the
class died in phase 4, so the same fixtures now drive the ConversationEngine
under interactive_policy() — the SAME round primitives, and io.emit is the
old loop's `yield`, so the byte assertions are unchanged. Covers: plain text,
a client-tool round (executed + continuation), an upstream non-200, and a
RemoteProtocolError mid-stream.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from app.desktop.studio_server.chat.constants import (
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine, EngineIO
from app.desktop.studio_server.chat.runtime.models import (
    ConversationRecord,
    interactive_policy,
)

from .test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    error_event,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)


async def _run_turn(client, initial_body: dict | None = None) -> list[bytes]:
    """Drive one interactive turn on the engine, returning the emitted SSE
    payloads — the exact bytes ChatStreamSession.stream() used to yield."""
    emitted: list[bytes] = []
    engine = ConversationEngine("https://example.test/v1/chat", {})
    record = ConversationRecord(kind="interactive")

    async def _decide(batch):  # pragma: no cover — these turns never park
        return {}

    io = EngineIO(emit=emitted.append, await_decisions=_decide)
    with patch.object(httpx, "AsyncClient", return_value=client):
        await engine.run(
            record,
            interactive_policy(),
            io,
            initial_body or {"messages": [{"role": "user", "content": "hi"}]},
        )
    return emitted


@pytest.mark.asyncio
async def test_golden_plain_text_stream_unchanged():
    chunks = [text_delta("Hello "), text_delta("world"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])

    out = await _run_turn(client)

    # Every upstream forward-byte is passed through verbatim. Each `data: ...\n\n`
    # chunk round-trips through the line parser to exactly itself, so the client
    # sees the concatenation of all upstream chunks.
    joined = b"".join(out)
    assert joined == b"".join(chunks)
    # No tool execution events for a text-only turn.
    decoded = joined.decode()
    assert SSE_TYPE_TOOL_EXEC_START not in decoded


@pytest.mark.asyncio
async def test_golden_client_tool_round_executes_and_continues():
    round1 = [
        text_delta("Let me add"),
        tool_input_available("tc1", "add", {"a": 2, "b": 3}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("The answer is 5"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(chunks=round1),
            FakeUpstreamResponse(chunks=round2),
        ]
    )

    out = await _run_turn(client)

    decoded = b"".join(out).decode()
    # Upstream tool-input bytes forwarded verbatim.
    assert '"toolCallId": "tc1"' in decoded
    # Server executed the tool and emitted exec start/output/end.
    assert SSE_TYPE_TOOL_EXEC_START in decoded
    assert '"type": "tool-output-available"' in decoded
    assert '"output": "5"' in decoded
    assert SSE_TYPE_TOOL_EXEC_END in decoded
    # Continued into round 2.
    assert "The answer is 5" in decoded
    # Continuation carried the trace id + tool result.
    assert client.bodies[1]["trace_id"] == "tr-1"


@pytest.mark.asyncio
async def test_golden_non_200_emits_error_and_stops():
    # 400 (non-retryable): surfaces immediately and stops. Retryable statuses
    # (5xx/429) go through the retry loop instead (see test_stream_session.py).
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                status_code=400, body=b'{"message": "boom", "code": "X"}'
            )
        ]
    )
    out = await _run_turn(client, {"trace_id": "tr-known", "messages": []})

    assert len(out) == 1
    decoded = out[0].decode()
    assert '"type": "error"' in decoded
    assert '"message": "boom"' in decoded
    assert '"code": "X"' in decoded
    assert '"trace_id": "tr-known"' in decoded


@pytest.mark.asyncio
async def test_golden_remote_protocol_error_emits_generic_error():
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                chunks=[text_delta("partial")], raise_protocol_error=True
            )
        ]
    )

    out = await _run_turn(client)

    decoded = b"".join(out).decode()
    assert "partial" in decoded
    assert '"message": "Something went wrong."' in decoded


@pytest.mark.asyncio
async def test_golden_upstream_error_event_forwarded_once_then_stream_ends():
    # Upstream emits a non-terminal `error` event mid-round, then closes cleanly
    # (a plain `finish`, no tool-calls boundary). This drives the post-round
    # `seen_upstream_error and not finish_tool_calls` branch
    # (RoundState.is_terminal_upstream_error) added by the refactor: the error
    # bytes must be forwarded verbatim exactly once, and the stream must end
    # without appending a duplicate generic "Something went wrong." error.
    chunks = [
        text_delta("trying"),
        error_event("Upstream blew up"),
        trace("tr-1"),
        finish("stop"),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=chunks)])

    out = await _run_turn(client)

    joined = b"".join(out)
    # The upstream error event is forwarded byte-for-byte (it lives in the
    # forwarded SSE lines; only `seen_upstream_error` is flagged internally).
    assert error_event("Upstream blew up") in joined
    decoded = joined.decode()
    # Forwarded exactly once — no duplicate from the post-round handling.
    assert decoded.count('"errorText": "Upstream blew up"') == 1
    # No generic terminal error was synthesized on top of the forwarded one.
    assert "Something went wrong." not in decoded
    assert "Maximum tool rounds exceeded" not in decoded
    # The stream ended after this single round (no second upstream POST).
    assert len(client.bodies) == 1


@pytest.mark.asyncio
async def test_golden_remote_protocol_error_after_tool_boundary_is_silent():
    # finish=tool-calls then connection drop is the expected AI SDK behavior —
    # no error SSE, the round's tool calls still process.
    round1 = [
        tool_input_available("tc1", "multiply", {"a": 4, "b": 5}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("20"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(chunks=round1, raise_protocol_error=True),
            FakeUpstreamResponse(chunks=round2),
        ]
    )

    out = await _run_turn(client)

    decoded = b"".join(out).decode()
    assert "Something went wrong." not in decoded
    assert '"output": "20"' in decoded
    assert "20" in decoded
