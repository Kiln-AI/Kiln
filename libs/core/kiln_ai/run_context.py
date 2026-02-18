"""Agent run context management using contextvars.

The agent run ID propagates automatically through async call chains,
including asyncio.gather and sub-agent calls via KilnTaskTool.

This is a general-purpose ID for scoping work to a single agent run,
usable for logging, caching, metrics, or any run-scoped operations.
"""

import uuid
from contextvars import ContextVar

_agent_run_id: ContextVar[str | None] = ContextVar("agent_run_id", default=None)


def get_agent_run_id() -> str | None:
    return _agent_run_id.get()


def set_agent_run_id(run_id: str) -> None:
    _agent_run_id.set(run_id)


def clear_agent_run_id() -> None:
    _agent_run_id.set(None)


def generate_agent_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:16]}"
