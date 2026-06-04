from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.desktop.studio_server.chat.stream_session import ToolCallInfo
from pydantic import BaseModel, Field

_RUN_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_RUN_ID_LENGTH = 12


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    """Mint a run id like ``ar_<base32>`` (mirrors jobs' ``_new_job_id``)."""
    suffix = "".join(secrets.choice(_RUN_ID_ALPHABET) for _ in range(_RUN_ID_LENGTH))
    return f"ar_{suffix}"


class AutoRunStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"  # assistant asked the user / finished naturally
    USER_STOPPED = "stopped"  # user hit Stop
    ERROR = "error"  # unrecoverable runner/upstream error
    MAX_ROUNDS = "max_rounds"

    @property
    def is_terminal(self) -> bool:
        return self is not AutoRunStatus.RUNNING


class AutoChatSeed(BaseModel):
    """Everything needed to begin (or resume into) an auto run as a fresh
    upstream continuation."""

    trace_id: str
    # Resolve this enable_auto_mode call as "enabled" before the first round.
    enable_tool_call_id: str | None = None
    # Sibling client tools to auto-execute first (usually empty — the model is
    # instructed to call enable_auto_mode alone).
    pending_tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    # Extra messages to prepend (e.g. a new user message on the manual idle path).
    extra_messages: list[dict[str, Any]] = Field(default_factory=list)


class AutoRunRecord(BaseModel):
    """Serializable view of an auto run's lifecycle state (in-memory only)."""

    run_id: str
    status: AutoRunStatus
    # Latest persisted leaf the runner has seen.
    current_trace_id: str
    # Whole chain this run has touched (for history correlation).
    seen_trace_ids: list[str] = Field(default_factory=list)
    # Model-supplied reason from enable_auto_mode.
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
