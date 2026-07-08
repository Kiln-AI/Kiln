from __future__ import annotations

import secrets
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

_SUBAGENT_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_SUBAGENT_ID_LENGTH = 12


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_subagent_id() -> str:
    """Mint a sub-agent id like ``sa_<base32>`` (mirrors auto's ``_new_run_id``)."""
    suffix = "".join(
        secrets.choice(_SUBAGENT_ID_ALPHABET) for _ in range(_SUBAGENT_ID_LENGTH)
    )
    return f"sa_{suffix}"


class SubAgentStatus(str, Enum):
    """One-shot lifecycle — unlike auto mode there is no IDLE re-arm: a
    sub-agent runs to a terminal state exactly once, and COMPLETED is the
    success case."""

    RUNNING = "running"
    COMPLETED = "completed"  # natural finish: final plain-text turn = the report
    FAILED = "failed"  # unrecoverable error (retries exhausted / exception)
    STOPPED = "stopped"  # user or parent called stop
    TIMEOUT = "timeout"  # round cap or wall-clock cap exceeded

    @property
    def is_terminal(self) -> bool:
        return self is not SubAgentStatus.RUNNING


class SubAgentSeed(BaseModel):
    """Everything needed to start a sub-agent session upstream.

    ``prompt`` becomes the backend-side seed prompt (appended to the agent
    task's instruction as the operator briefing); ``parent_trace_id`` is the
    parent conversation's leaf trace id at spawn time, resolved server-side
    into durable lineage on the child's session meta.
    """

    agent_type: str
    name: str
    prompt: str
    parent_key: str
    parent_trace_id: str | None = None


class SubAgentRecord(BaseModel):
    """Serializable view of a sub-agent's lifecycle state (in-memory only).

    The durable facts (agent type, lineage) also live upstream in the child
    session's ``session_meta``; this record adds the runtime-only state — live
    status, the report-delivery bookkeeping, and the parent key used for
    completion injection.
    """

    subagent_id: str = Field(default_factory=_new_subagent_id)
    name: str
    agent_type: str
    status: SubAgentStatus = SubAgentStatus.RUNNING
    # ``auto:<run_id>`` for an auto-mode parent, ``trace:<leaf-at-spawn>`` for an
    # interactive parent (the registry aliases later leaves to the same key as
    # the parent's trace chain advances).
    parent_key: str
    parent_trace_id_at_spawn: str | None = None
    # Latest persisted leaf of the CHILD session (rotates every turn); the whole
    # chain is kept for the sessions join.
    current_trace_id: str | None = None
    seen_trace_ids: list[str] = Field(default_factory=list)
    # The child's final plain-text turn (its report). Synthesized with a status
    # note for FAILED/STOPPED/TIMEOUT so the parent always learns the outcome.
    final_report: str | None = None
    # True once the report reached the parent through ANY channel (wait result,
    # status tool with include_report, auto-run injection, next-turn injection).
    report_delivered: bool = False
    rounds_used: int = 0
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


def format_subagent_report(record: SubAgentRecord) -> str:
    """The framed report injected into the parent conversation as a user-role
    message. The frame is stripped/specialized on hydration client-side and the
    skill teaches the model it is machinery, not the user speaking."""
    body = record.final_report or "(no report produced)"
    return (
        f'<subagent_report id="{record.subagent_id}" '
        f'agent_type="{record.agent_type}" '
        f'status="{record.status.value}" '
        f'title="{_escape_attr(record.name)}">\n'
        f"{body}\n"
        f"</subagent_report>"
    )


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
