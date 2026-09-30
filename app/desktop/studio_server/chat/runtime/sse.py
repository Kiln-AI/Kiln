"""SSE formatters for the unified runtime.

Two families live here:

1. **The unified control event** — ``conversation-state`` — the ONE lifecycle
   event the frontend's conversation store consumes (architecture §6). The
   AI-SDK content vocabulary (text deltas, tool events, ``kiln_chat_trace``,
   tool-exec framing, ``user-message`` echoes, retry, pending/consent events)
   passes through from upstream or is emitted by the shared round primitives.

2. **The generic per-run formatters** (user-message echo, tool-exec framing,
   tool output, error). Their payload shapes are part of the browser protocol
   consumed by the web UI's ``StreamEventProcessor``.

The round-primitive formatters (``format_chat_retry``,
``_format_tool_calls_pending_sse``, ``_format_consent_required_sse``) live in
``chat/stream_session.py`` and are re-exported here so runtime code has one
import site for every event it can emit.
"""

from __future__ import annotations

import json

from app.desktop.studio_server.chat.constants import (
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)

# Re-exports: these formatters belong to the round primitives in
# stream_session.py — reused, never duplicated.
from app.desktop.studio_server.chat.stream_session import (  # noqa: F401
    _format_consent_required_sse as format_consent_required,
)
from app.desktop.studio_server.chat.stream_session import (  # noqa: F401
    _format_tool_calls_pending_sse as format_tool_calls_pending,
)
from app.desktop.studio_server.chat.stream_session import (  # noqa: F401
    format_chat_retry,
)

from .models import ConversationRecord

# The one lifecycle control event (architecture §6). Emitted by the
# supervisor on every state change and as the on-subscribe marker after the
# replay buffer.
SSE_TYPE_CONVERSATION_STATE = "conversation-state"


def _encode(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def format_conversation_state(record: ConversationRecord) -> bytes:
    """Snapshot of a conversation's lifecycle for observers.

    - state=running, auto_flag=true   → an auto burst is in flight
    - state=idle, auto_flag=true      → auto mode on, between bursts
                                        (idle_reason says why)
    - auto_flag=false + idle_reason   → auto mode just turned off
                                        (user_stopped / user_disabled)
    - state=running ⇔ a turn/burst is working
    """
    payload: dict[str, object] = {
        "type": SSE_TYPE_CONVERSATION_STATE,
        "session_id": record.session_id,
        "kind": record.kind,
        "state": record.state.value,
        "auto_flag": record.auto_flag,
    }
    # Optional fields ride only when meaningful, keeping the event compact.
    if record.idle_reason is not None:
        payload["idle_reason"] = record.idle_reason
    return _encode(payload)


# ── Generic per-run formatters. Shapes are part of the browser protocol — do
#    not change them without updating StreamEventProcessor. ────────────────────


def format_user_message(content: str, message_id: str | None = None) -> bytes:
    """Echo a user message onto the run stream so observers (including the
    sender) render it immediately, consistent with re-attach/replay.
    ``message_id`` is the injected message's stable id, so a client can dedupe
    the echo if a buffer replay re-emits it for a message it already shows.
    """
    payload: dict[str, str] = {"type": "user-message", "content": content}
    if message_id is not None:
        payload["id"] = message_id
    return _encode(payload)


def format_tool_exec_start(tool_count: int) -> bytes:
    return _encode({"type": SSE_TYPE_TOOL_EXEC_START, "tool_count": tool_count})


def format_tool_exec_end(tool_count: int) -> bytes:
    return _encode({"type": SSE_TYPE_TOOL_EXEC_END, "tool_count": tool_count})


def format_tool_output(tool_call_id: str, output: str) -> bytes:
    return _encode(
        {
            "type": "tool-output-available",
            "toolCallId": tool_call_id,
            "output": output,
        }
    )


def format_error(message: str, trace_id: str | None = None) -> bytes:
    payload: dict = {"type": "error", "message": message}
    if trace_id:
        payload["trace_id"] = trace_id
    return _encode(payload)
