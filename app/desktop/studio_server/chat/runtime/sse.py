"""SSE formatters for the unified runtime.

Two families live here:

1. **The unified control event** — ``conversation-state`` — which replaces the
   whole per-kind lifecycle vocabulary (``auto-mode-on`` / ``auto-mode-off`` /
   ``auto-mode-idle`` / ``auto-mode-state`` and ``kiln-subagent-status``) with
   ONE event the frontend's single conversation store consumes (architecture
   §6). The AI-SDK content vocabulary (text deltas, tool events,
   ``kiln_chat_trace``, tool-exec framing, ``user-message`` echoes, retry,
   pending/consent events) is untouched — those bytes pass through or are
   emitted by the shared round primitives exactly as today.

2. **Canonical copies of the generic per-run formatters** that currently live
   in ``chat/auto/sse.py`` (re-exported by ``chat/subagents/sse.py``). Those
   packages are deleted in phases 2–3, so the runtime owns its own copies now;
   the payload shapes are byte-identical so ``StreamEventProcessor`` consumes
   the new streams unchanged.

The surviving round-primitive formatters (``format_chat_retry``,
``_format_tool_calls_pending_sse``, ``_format_consent_required_sse``) stay in
``chat/stream_session.py`` and are re-exported here so runtime code has one
import site for every event it can emit.
"""

from __future__ import annotations

import json

from app.desktop.studio_server.chat.constants import (
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)

# Re-exports: these formatters belong to the surviving round primitives in
# stream_session.py — reused, never duplicated (phase-1 hard constraint).
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
# replay buffer, replacing:
#   auto-mode-on / auto-mode-off / auto-mode-idle / auto-mode-state
#   kiln-subagent-status
SSE_TYPE_CONVERSATION_STATE = "conversation-state"


def _encode(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def format_conversation_state(record: ConversationRecord) -> bytes:
    """Snapshot of a conversation's lifecycle for observers.

    Field mapping from the old vocabulary (so the frontend port in phases 2–4
    is mechanical):

    - old ``auto-mode-on``            → state=running, auto_flag=true
    - old ``auto-mode-idle{reason}``  → state=idle, auto_flag=true, idle_reason
    - old ``auto-mode-off{reason}``   → auto_flag=false, idle_reason carries
                                        user_stopped/user_disabled
    - old ``auto-mode-state{working}``→ state==running ⇔ working
    - old ``kiln-subagent-status``    → kind=subagent + state/name/
                                        report_available (the old trace_id
                                        field is deliberately gone: browsers
                                        never see trace ids in the new world,
                                        functional spec §4)
    """
    payload: dict[str, object] = {
        "type": SSE_TYPE_CONVERSATION_STATE,
        "session_id": record.session_id,
        "kind": record.kind,
        "state": record.state.value,
        "auto_flag": record.auto_flag,
    }
    # Optional fields ride only when meaningful, keeping the event compact and
    # making the per-kind payloads easy to eyeball in transcripts.
    if record.idle_reason is not None:
        payload["idle_reason"] = record.idle_reason
    if record.name is not None:
        payload["name"] = record.name
    # Lineage rides the event so a firehose observer can attribute an unknown
    # child to its parent directly, without a racy list-fetch round trip.
    if record.parent_session_id is not None:
        payload["parent_session_id"] = record.parent_session_id
    if record.kind == "subagent":
        payload["report_available"] = record.final_report is not None
        # Identity rides along too, so a directly-attributed child renders its
        # type badge/tooltip immediately instead of waiting for a list fetch.
        if record.agent_type is not None:
            payload["agent_type"] = record.agent_type
    return _encode(payload)


# ── Canonical copies of the generic per-run formatters (old chat/auto/sse.py,
#    deleted in phase 3). Shapes are part of the browser protocol — do not
#    change them without updating StreamEventProcessor. ────────────────────────


def format_user_message(content: str, message_id: str | None = None) -> bytes:
    """Echo a user message onto the run stream so observers (including the
    sender) render it immediately, consistent with re-attach/replay.
    ``message_id`` is the injected message's stable id, so a client can dedupe
    the echo if a buffer replay re-emits it for a message it already shows.
    (Report-injection echoes carry no id — same as the old interactive path.)
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
