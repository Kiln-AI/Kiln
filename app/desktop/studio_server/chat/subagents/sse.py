from __future__ import annotations

import json

# The sub-agent stream reuses the exact chat SSE vocabulary the interactive and
# auto streams emit (so StreamEventProcessor consumes it unchanged), plus one
# control event for lifecycle status. The generic tool-exec/user-message/error
# formatters are shared with the auto stream.
from app.desktop.studio_server.chat.auto.sse import (  # noqa: F401
    format_error,
    format_tool_exec_end,
    format_tool_exec_start,
    format_tool_output,
    format_user_message,
)

from .models import SubAgentRecord

SSE_TYPE_SUBAGENT_STATUS = "kiln-subagent-status"


def format_subagent_status(record: SubAgentRecord) -> bytes:
    """Lifecycle status event, published on spawn / trace advance / terminal.

    Consumed by the per-run observer stream (also emitted as the on-subscribe
    liveness marker) and by the registry-level firehose the UI store watches.
    """
    payload = {
        "type": SSE_TYPE_SUBAGENT_STATUS,
        "subagent_id": record.subagent_id,
        "name": record.name,
        "agent_type": record.agent_type,
        "status": record.status.value,
        "trace_id": record.current_trace_id,
        "report_available": record.final_report is not None,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
