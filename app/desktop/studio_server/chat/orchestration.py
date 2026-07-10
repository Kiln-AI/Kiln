"""Sub-agent orchestration tool executor, targeting the unified runtime.

Relocated from ``chat/subagents/orchestration.py`` in phase 2 (architecture
§1: the executor survives the sub-agent runtime's deletion) and retargeted
from the old ``SubAgentRegistry`` onto the ``ConversationSupervisor``.
Semantics are preserved exactly:

- spawn caps surface as TOOL-RESULT errors (never HTTP) so the model can
  adapt;
- ``wait_for_subagents`` / ``get_subagent_status`` return STATUSES ONLY plus
  a note — reports are delivered exclusively through the
  ``<subagent_report>`` user-message injection channel so they are persisted
  in the parent's trace and rendered as report panels;
- ownership scoping: a conversation can only see/manage its own children;
- an executed spawn marks the conversation spawn-consented (the one-time
  approval downgrade — written by the engine onto
  ``ConversationRecord.spawn_consent_granted``);
- depth ≥ 1 calls are rejected before dispatch (sub-agents cannot manage
  sub-agents).

Phase 4 removed the last old-world identity bridge: EVERY parent is a
supervisor record now, so ``OrchestrationContext`` shrank to
``{parent_session_id, depth}`` and the phase-2/3 ``ParentConversationIndex``
(the ``trace:<leaf>`` alias chain + consent set that stood in for old-loop
interactive parents) is gone — session ids are stable, so no alias chaining
is ever needed, and consent lives on the record. The spawn seed's
``parent_trace_id`` (durable lineage the BACKEND resolves) now reads the
parent record's ``current_leaf_trace_id`` directly — the same value the old
per-round ``ctx.parent_trace_id`` refresh maintained, now with the record as
the single source of truth (single-writer: the run loop's ``on_trace``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.desktop.studio_server.chat.runtime.interceptors import (  # noqa: F401
    GET_SUBAGENT_STATUS_TOOL_NAME,
    ORCHESTRATION_TOOL_NAMES,
    SPAWN_SUBAGENT_TOOL_NAME,
    STOP_SUBAGENT_TOOL_NAME,
    WAIT_FOR_SUBAGENTS_TOOL_NAME,
)
from app.desktop.studio_server.chat.runtime.models import (
    ConversationRecord,
    SubAgentSeed,
)
from app.desktop.studio_server.chat.runtime.supervisor import (
    ConversationCapError,
    conversation_supervisor,
)

logger = logging.getLogger(__name__)

# Matches the backend tool schema; the desktop clamp is authoritative (waits
# must stay bounded so a parent's turn task can always settle).
WAIT_DEFAULT_TIMEOUT_SECONDS = 120.0
WAIT_MAX_TIMEOUT_SECONDS = 300.0


@dataclass
class OrchestrationContext:
    """Identity of the conversation a batch of tool calls belongs to.

    ``parent_session_id`` is the owning conversation's supervisor session id
    (every parent kind lives on the supervisor since phase 4). ``depth`` > 0
    marks a sub-agent's own loop, whose orchestration calls are rejected
    before dispatch. The old ``parent_trace_id`` field is gone: the spawn
    lineage leaf is read from the parent record at spawn time (see the
    module docstring).
    """

    parent_session_id: str | None = None
    depth: int = 0

    def parent_key(self) -> str | None:
        # The session id IS the parent key: stable for the conversation's
        # lifetime, so no trace-alias chaining is needed (this replaced the
        # old ``auto:<run_id>`` / ``trace:<leaf>`` keys as each parent kind
        # moved onto the supervisor in phases 3–4).
        return self.parent_session_id


def _error(message: str) -> str:
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def _record_payload(record: ConversationRecord, include_report: bool) -> dict[str, Any]:
    """The model-visible view of one child. Field names and semantics are the
    OLD wire shape, preserved verbatim (they are persisted into parent traces
    via tool results): ``subagent_id`` is the child handle used for
    wait/stop — now the child's session id — and ``session_id`` is the
    child's current UPSTREAM leaf trace id. The backend's session endpoints
    accept either id kind since phase 6, but the field keeps its name AND its
    leaf value: these payloads are persisted in parent traces, so changing
    the shape would break the "indistinguishable persisted traces" contract
    for zero benefit."""
    payload: dict[str, Any] = {
        "subagent_id": record.session_id,
        "name": record.name,
        "agent_type": record.agent_type,
        "state": record.state.value,
        "rounds": record.rounds_used,
    }
    if record.current_leaf_trace_id is not None:
        payload["session_id"] = record.current_leaf_trace_id
    if include_report and record.state.is_terminal and record.final_report:
        payload["report"] = record.final_report
    return payload


async def execute_orchestration_tool(
    tool_name: str,
    args: dict[str, Any],
    ctx: OrchestrationContext,
) -> str:
    """Execute one orchestration tool call locally; returns the JSON tool result.

    Never raises for domain outcomes (caps, unknown ids, declined) — the model
    gets a structured error result it can react to.
    """
    if ctx.depth > 0:
        return _error("Sub-agents cannot spawn or manage sub-agents.")
    parent_key = ctx.parent_key()
    if parent_key is None:
        return _error("Sub-agent orchestration is unavailable in this context.")

    try:
        if tool_name == SPAWN_SUBAGENT_TOOL_NAME:
            return await _spawn(args, parent_key)
        if tool_name == GET_SUBAGENT_STATUS_TOOL_NAME:
            return _status(args, parent_key)
        if tool_name == WAIT_FOR_SUBAGENTS_TOOL_NAME:
            return await _wait(args, parent_key)
        if tool_name == STOP_SUBAGENT_TOOL_NAME:
            return await _stop(args, parent_key)
    except Exception:
        logger.exception("Orchestration tool %s failed", tool_name)
        return _error("Internal error executing the sub-agent operation.")
    return _error(f"Unknown orchestration tool: {tool_name}")


async def _spawn(args: dict[str, Any], parent_key: str) -> str:
    agent_type = args.get("agent_type")
    name = args.get("name")
    prompt = args.get("prompt")
    if (
        not isinstance(agent_type, str)
        or not isinstance(name, str)
        or not isinstance(prompt, str)
        or not agent_type
        or not name.strip()
        or not prompt.strip()
    ):
        return _error("spawn_subagent requires agent_type, name and prompt strings.")

    # Lazy import: routes imports stream_session which lazily imports this
    # module; by execution time routes is fully loaded.
    from app.desktop.studio_server.chat.routes import (
        _build_upstream_headers,
        _upstream_chat_url,
    )
    from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

    # Durable lineage: the ``agent`` block's ``parent_trace_id`` (which the
    # BACKEND resolves onto the child session's meta) is the parent's CURRENT
    # persisted leaf. The record is the single source — the old runners
    # refreshed a ctx copy per round for exactly this value.
    parent_record = conversation_supervisor.get(parent_key)
    seed = SubAgentSeed(
        agent_type=agent_type,
        name=name.strip()[:80],
        prompt=prompt,
        parent_trace_id=(
            parent_record.current_leaf_trace_id if parent_record else None
        ),
    )
    try:
        record = conversation_supervisor.spawn_subagent(
            seed,
            parent_session_id=parent_key,
            upstream_url=_upstream_chat_url(),
            headers=_build_upstream_headers(get_copilot_api_key()),
        )
    except ConversationCapError as e:
        return _error(str(e))
    return json.dumps(
        {"status": "spawned", "subagent_id": record.session_id, "name": record.name},
        ensure_ascii=False,
    )


def _owned_record(subagent_id: str, parent_key: str) -> ConversationRecord | None:
    """A record visible to this parent — cross-conversation ids are unknown.
    The kind guard is defense in depth: the supervisor also holds
    interactive/auto records, and those must never be addressable as
    sub-agents."""
    record = conversation_supervisor.get(subagent_id)
    if (
        record is None
        or record.kind != "subagent"
        or record.parent_session_id != parent_key
    ):
        return None
    return record


# Appended to wait/status results so the model knows where reports arrive.
_REPORTS_AS_MESSAGES_NOTE = (
    "Final reports are delivered into this conversation as <subagent_report> "
    "user messages when each sub-agent finishes."
)


def _status(args: dict[str, Any], parent_key: str) -> str:
    # ``include_report`` returns the content inline as a convenience, but never
    # consumes the report: delivery stays on the injection channel so the
    # report is always persisted in the parent trace and rendered as a panel.
    include_report = bool(args.get("include_report"))
    subagent_id = args.get("subagent_id")
    if subagent_id:
        record = _owned_record(str(subagent_id), parent_key)
        if record is None:
            return _error(f"Unknown sub-agent id: {subagent_id}")
        payload = _record_payload(record, include_report)
        return json.dumps(
            {"subagents": [payload], "note": _REPORTS_AS_MESSAGES_NOTE},
            ensure_ascii=False,
        )

    records = conversation_supervisor.children_of(parent_key)
    payloads = [_record_payload(r, include_report) for r in records]
    return json.dumps(
        {"subagents": payloads, "note": _REPORTS_AS_MESSAGES_NOTE},
        ensure_ascii=False,
    )


async def _wait(args: dict[str, Any], parent_key: str) -> str:
    raw_ids = args.get("subagent_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return _error("wait_for_subagents requires a non-empty subagent_ids list.")
    ids = [str(sid) for sid in raw_ids]
    unknown = [sid for sid in ids if _owned_record(sid, parent_key) is None]
    if unknown:
        return _error(f"Unknown sub-agent ids: {', '.join(unknown)}")

    timeout = args.get("timeout_seconds")
    try:
        timeout_seconds = float(timeout) if timeout is not None else None
    except (TypeError, ValueError):
        timeout_seconds = None
    if timeout_seconds is None:
        timeout_seconds = WAIT_DEFAULT_TIMEOUT_SECONDS
    timeout_seconds = min(max(timeout_seconds, 1.0), WAIT_MAX_TIMEOUT_SECONDS)

    records, timed_out = await conversation_supervisor.wait(ids, timeout_seconds)
    return json.dumps(
        {
            # Statuses only: reports arrive as <subagent_report> user messages
            # (injected right after this batch), so they are persisted in the
            # trace and rendered as report panels — not buried in this tool
            # result.
            "subagents": [_record_payload(r, include_report=False) for r in records],
            "timed_out": timed_out,
            "note": _REPORTS_AS_MESSAGES_NOTE,
        },
        ensure_ascii=False,
    )


async def _stop(args: dict[str, Any], parent_key: str) -> str:
    subagent_id = args.get("subagent_id")
    if not isinstance(subagent_id, str) or not subagent_id:
        return _error("stop_subagent requires a subagent_id.")
    record = _owned_record(subagent_id, parent_key)
    if record is None:
        return json.dumps({"status": "not_found"}, ensure_ascii=False)
    # The supervisor's stop() is idempotent-void; the outcome vocabulary the
    # model sees (stopped / already_finished / not_found) is the OLD
    # registry's, preserved here because these strings are persisted in parent
    # traces and the skill teaches the model to react to them.
    if record.state.is_terminal:
        return json.dumps({"status": "already_finished"}, ensure_ascii=False)
    await conversation_supervisor.stop(subagent_id)
    return json.dumps({"status": "stopped"}, ensure_ascii=False)


async def handle_session_deleted(conversation_key: str) -> None:
    """Cascade for a deleted chat session (functional spec §5 "deleting a
    session stops its run and cascades to children"; old
    ``SubAgentRegistry.handle_session_deleted``): resolve the deleted key —
    a live session id directly, anything else (any leaf the conversation
    ever had, or the key it was adopted from) through the supervisor's
    whole-chain index. Phase 6: the delete proxy hands us the browser's
    ORIGINAL key (the upstream delete no longer needs a desktop-resolved
    leaf, so none exists to pass). If it names a live conversation, stop its
    children (explicitly — a plain interactive ``stop()`` deliberately does
    NOT cascade since phase 4, but a DELETED parent's children have nothing
    left to consume their reports) and stop the conversation itself — a
    deleted CHILD session stops that child (old behavior), and a deleted
    parent's in-flight run is cancelled."""
    if conversation_supervisor.get(conversation_key) is not None:
        session_id: str | None = conversation_key
    else:
        session_id = conversation_supervisor.session_for_trace(conversation_key)
    if session_id is None:
        return
    await conversation_supervisor.stop_children(session_id)
    record = conversation_supervisor.get(session_id)
    if record is not None and not record.state.is_terminal:
        await conversation_supervisor.stop(session_id)
