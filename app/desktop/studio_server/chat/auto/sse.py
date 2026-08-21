from __future__ import annotations

import json

from app.desktop.studio_server.chat.constants import (
    SSE_TYPE_AUTO_MODE_IDLE,
    SSE_TYPE_AUTO_MODE_STATE,
    SSE_TYPE_TOOL_EXEC_END,
    SSE_TYPE_TOOL_EXEC_START,
)

# Control-event types unique to the auto stream. The rest of the auto stream
# reuses the exact chat SSE vocabulary the interactive stream emits, so the
# existing StreamEventProcessor consumes it unchanged.
SSE_TYPE_AUTO_MODE_ON = "auto-mode-on"
SSE_TYPE_AUTO_MODE_OFF = "auto-mode-off"


def _encode(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def format_auto_mode_on(run_id: str) -> bytes:
    return _encode({"type": SSE_TYPE_AUTO_MODE_ON, "run_id": run_id})


def format_auto_mode_off(run_id: str, reason: str) -> bytes:
    """Published only on explicit disable. reason ∈ {user_stopped, user_disabled}."""
    return _encode({"type": SSE_TYPE_AUTO_MODE_OFF, "run_id": run_id, "reason": reason})


def format_auto_mode_idle(run_id: str, reason: str) -> bytes:
    """Revision R1: a burst settled but the conversation flag stays on.
    reason ∈ {asked_user, done, error, max_rounds}."""
    return _encode(
        {"type": SSE_TYPE_AUTO_MODE_IDLE, "run_id": run_id, "reason": reason}
    )


def format_auto_mode_state(run_id: str, *, flag_on: bool, working: bool) -> bytes:
    """Phase 9: on-subscribe snapshot of the run's CURRENT liveness.

    Emitted once when an observer subscribes (after the buffer replay) so a
    re-attaching client immediately reflects working-vs-idle — instead of looking
    fully loaded/idle until the next event happens to arrive. ``working`` is true
    iff a burst is actively running (status RUNNING); ``flag_on`` carries the
    conversation auto-mode flag. Uses the existing on/idle/off vocabulary by
    semantics (working ⇒ thinking indicator, idle ⇒ "· waiting for you")."""
    return _encode(
        {
            "type": SSE_TYPE_AUTO_MODE_STATE,
            "run_id": run_id,
            "flag_on": flag_on,
            "working": working,
        }
    )


def format_user_message(content: str, message_id: str | None = None) -> bytes:
    """Echo a user message onto the run stream so observers (including the
    sender) render it immediately, consistent with re-attach/replay. ``message_id``
    is the injected message's stable id, so a client can dedupe the echo if a
    buffer replay re-emits it for a message it already shows."""
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
