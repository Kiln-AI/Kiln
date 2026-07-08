from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from .models import SubAgentRecord, SubAgentSeed
from .registry import SubAgentCapError, subagent_registry

logger = logging.getLogger(__name__)

SPAWN_SUBAGENT_TOOL_NAME = "spawn_subagent"
GET_SUBAGENT_STATUS_TOOL_NAME = "get_subagent_status"
WAIT_FOR_SUBAGENTS_TOOL_NAME = "wait_for_subagents"
STOP_SUBAGENT_TOOL_NAME = "stop_subagent"

# Names must match the backend's client-visible tool schemas
# (kiln_server tools/subagent_tools.py). These are dispatched by
# ``execute_tool_batch`` to ``execute_orchestration_tool`` instead of the
# kiln_ai tool registry — they need parent identity + registry access that
# ``tool.run(**args)`` can't carry.
ORCHESTRATION_TOOL_NAMES: frozenset[str] = frozenset(
    [
        SPAWN_SUBAGENT_TOOL_NAME,
        GET_SUBAGENT_STATUS_TOOL_NAME,
        WAIT_FOR_SUBAGENTS_TOOL_NAME,
        STOP_SUBAGENT_TOOL_NAME,
    ]
)

# Matches the backend tool schema; the desktop clamp is authoritative (the
# interactive POST /api/chat stream has no keepalive, so waits stay bounded).
WAIT_DEFAULT_TIMEOUT_SECONDS = 120.0
WAIT_MAX_TIMEOUT_SECONDS = 300.0


@dataclass
class OrchestrationContext:
    """Identity of the conversation a batch of tool calls belongs to.

    Exactly one of the parent handles is set: ``parent_auto_run_id`` for calls
    executed by the auto runner, ``parent_trace_id`` for the interactive stream
    (updated per round as the leaf rotates). ``depth`` > 0 marks a sub-agent's
    own loop, whose orchestration calls are rejected before dispatch.
    """

    parent_trace_id: str | None = None
    parent_auto_run_id: str | None = None
    depth: int = 0

    def parent_key(self) -> str | None:
        if self.parent_auto_run_id is not None:
            key = subagent_registry.parent_key_for_auto_run(self.parent_auto_run_id)
            # Alias the conversation's leaf to the auto key so trace-id lookups
            # (UI children list, next-turn report injection) resolve; the
            # runners chain later leaf rotations via note_parent_trace.
            if self.parent_trace_id is not None:
                subagent_registry.register_parent_alias(self.parent_trace_id, key)
            return key
        if self.parent_trace_id is not None:
            return subagent_registry.parent_key_for_trace(self.parent_trace_id)
        return None


def _error(message: str) -> str:
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def is_spawn_consented(ctx: OrchestrationContext) -> bool:
    """Whether this conversation already granted spawn consent (used to
    downgrade spawn_subagent's requires_approval after the first approval).
    Auto-run parents are implicitly consented — the auto-mode consent dialog
    covers autonomous work, and the runner auto-approves everything anyway."""
    if ctx.parent_auto_run_id is not None:
        return True
    key = ctx.parent_key()
    return key is not None and subagent_registry.is_consented(key)


def _record_payload(record: SubAgentRecord, include_report: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subagent_id": record.subagent_id,
        "name": record.name,
        "agent_type": record.agent_type,
        "state": record.status.value,
        "rounds": record.rounds_used,
    }
    if record.current_trace_id is not None:
        payload["session_id"] = record.current_trace_id
    if include_report and record.status.is_terminal and record.final_report:
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
            return await _spawn(args, ctx, parent_key)
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


async def _spawn(
    args: dict[str, Any], ctx: OrchestrationContext, parent_key: str
) -> str:
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

    # Reaching execution means the spawn was approved (or previously consented);
    # remember it so later spawns in this conversation skip the approval gate.
    subagent_registry.mark_consented(parent_key)

    # Lazy import: routes imports stream_session which lazily imports this
    # module; by execution time routes is fully loaded.
    from app.desktop.studio_server.chat.routes import (
        _build_upstream_headers,
        _upstream_chat_url,
    )
    from app.desktop.studio_server.utils.copilot_utils import get_copilot_api_key

    seed = SubAgentSeed(
        agent_type=agent_type,
        name=name.strip()[:80],
        prompt=prompt,
        parent_key=parent_key,
        parent_trace_id=ctx.parent_trace_id,
    )
    try:
        record = subagent_registry.spawn(
            seed,
            upstream_url=_upstream_chat_url(),
            headers=_build_upstream_headers(get_copilot_api_key()),
            orchestration_tool_names=ORCHESTRATION_TOOL_NAMES,
        )
    except SubAgentCapError as e:
        return _error(str(e))
    return json.dumps(
        {"status": "spawned", "subagent_id": record.subagent_id, "name": record.name},
        ensure_ascii=False,
    )


def _owned_record(subagent_id: str, parent_key: str) -> SubAgentRecord | None:
    """A record visible to this parent — cross-conversation ids are unknown."""
    run = subagent_registry.get(subagent_id)
    if run is None or run.record.parent_key != parent_key:
        return None
    return run.record


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

    records = subagent_registry.list_for_parent(parent_key)
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

    records, timed_out = await subagent_registry.wait(ids, timeout_seconds)
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
    if _owned_record(subagent_id, parent_key) is None:
        return json.dumps({"status": "not_found"}, ensure_ascii=False)
    outcome = await subagent_registry.stop(subagent_id)
    return json.dumps({"status": outcome}, ensure_ascii=False)
