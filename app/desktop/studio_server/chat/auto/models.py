from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

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


def _new_message_id() -> str:
    """Mint an injected-message id like ``am_<base32>``. Echoed to observers so
    the client can render the message idempotently (a buffer replay on re-attach
    re-emits the echo for an in-flight message the transcript already shows)."""
    suffix = "".join(secrets.choice(_RUN_ID_ALPHABET) for _ in range(_RUN_ID_LENGTH))
    return f"am_{suffix}"


class AutoRunStatus(str, Enum):
    RUNNING = "running"  # a burst is actively driving the loop
    # Revision R1: a burst settled but the conversation auto-mode flag stays ON
    # (the entry is not evicted). The conversation is idle awaiting the user.
    IDLE = "idle"
    USER_STOPPED = "stopped"  # user hit Stop — flag off
    USER_DISABLED = "disabled"  # disable_auto_mode tool intercepted — flag off

    @property
    def is_terminal(self) -> bool:
        """Terminal == the conversation auto-mode flag is OFF and the entry is
        slated for GC. Under Revision R1 a settled burst goes IDLE (flag still
        on), so IDLE is NOT terminal."""
        return self in _OFF_STATUSES

    @property
    def flag_on(self) -> bool:
        """Whether the conversation-scoped auto-mode flag is on (RUNNING or
        IDLE). Drives the green-dot/auto_active join, which must persist while a
        run is idle between bursts."""
        return self in _FLAG_ON_STATUSES


_FLAG_ON_STATUSES = frozenset({AutoRunStatus.RUNNING, AutoRunStatus.IDLE})
_OFF_STATUSES = frozenset({AutoRunStatus.USER_STOPPED, AutoRunStatus.USER_DISABLED})


class InboundMessage(BaseModel):
    """A user message sent into an auto-mode conversation via ``/message``.

    When a burst is active it is queued and drained at the next round boundary
    (appended to the continuation as a ``role:"user"`` message); when the run is
    idle it seeds a fresh burst."""

    # Stable id minted server-side, echoed to observers (see _new_message_id) so
    # the client can dedupe the echo on a buffer replay / re-attach.
    id: str = Field(default_factory=_new_message_id)
    # Fixed to the user role: /message is documented as user-message input only,
    # so the schema enforces it rather than trusting a client-supplied role.
    role: Literal["user"] = "user"
    content: str
    trace_id: str | None = None

    def as_chat_message(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


class AutoChatSeed(BaseModel):
    """Everything needed to begin (or resume into) an auto run as a fresh
    upstream continuation."""

    # The conversation's current leaf trace id. Optional (Revision R2): a
    # brand-new conversation has no trace yet, so the seed carries only the
    # first user message in ``extra_messages`` and the backend starts a fresh
    # conversation, minting the first trace on the opening turn.
    trace_id: str | None = None
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
    # Latest persisted leaf the runner has seen. Optional (Revision R2): a
    # no-trace seed (brand-new conversation) has no leaf until the backend emits
    # the first kiln_chat_trace, at which point _on_trace populates it.
    current_trace_id: str | None = None
    # Whole chain this run has touched (for history correlation).
    seen_trace_ids: list[str] = Field(default_factory=list)
    # Model-supplied reason from enable_auto_mode.
    reason: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
