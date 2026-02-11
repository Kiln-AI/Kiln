"""MCP session context management using contextvars.

The session ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.
"""

import uuid
from contextvars import ContextVar

_mcp_session_id: ContextVar[str | None] = ContextVar("mcp_session_id", default=None)


def get_mcp_session_id() -> str | None:
    return _mcp_session_id.get()


def set_mcp_session_id(session_id: str) -> None:
    _mcp_session_id.set(session_id)


def clear_mcp_session_id() -> None:
    _mcp_session_id.set(None)


def generate_session_id() -> str:
    return f"mcp_{uuid.uuid4().hex[:16]}"
