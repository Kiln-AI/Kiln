from __future__ import annotations

import json

from app.desktop.studio_server.chat.constants import (
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
    """reason ∈ {done, asked_user, user_stopped, error, max_rounds}."""
    return _encode({"type": SSE_TYPE_AUTO_MODE_OFF, "run_id": run_id, "reason": reason})


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
