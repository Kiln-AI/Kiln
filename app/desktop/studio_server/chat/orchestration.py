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
  approval downgrade);
- depth ≥ 1 calls are rejected before dispatch (sub-agents cannot manage
  sub-agents).

PHASE-2 BRIDGE STATE (deleted as parents migrate onto the supervisor):
interactive and auto parents still run on the OLD loops, so a parent has no
supervisor record/session id yet. The old ``parent_key`` model therefore
survives here — ``ParentConversationIndex`` keeps the trace→key alias chain
and the spawn-consent set the old registry kept — and children store the
parent_key string AS their ``parent_session_id``. Removal map:

- phase 3 (auto port): the ``auto:*`` branch of the legacy report deliverer
  dies; auto parents become supervisor records and reports route internally.
- phase 4 (interactive port): ``ParentConversationIndex`` dies entirely —
  parent identity becomes the parent conversation's real session id (no alias
  chaining needed; stable by construction) and consent moves to
  ``ConversationRecord.spawn_consent_granted`` (already written by the
  engine's spawn bookkeeping).
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

# Matches the backend tool schema; the desktop clamp is authoritative (the
# interactive POST /api/chat stream has no keepalive, so waits stay bounded).
WAIT_DEFAULT_TIMEOUT_SECONDS = 120.0
WAIT_MAX_TIMEOUT_SECONDS = 300.0


class ParentConversationIndex:
    """PHASE-2-ONLY identity bridge for parents still on the OLD loops.

    Verbatim port of the parent-key half of the old ``SubAgentRegistry``:

    - ``_alias`` maps ANY leaf trace id an old-world parent has ever had to
      its stable parent key (``trace:<first-leaf>`` for interactive parents,
      ``auto:<run_id>`` for auto parents). Interactive parents rotate their
      leaf every turn; ``note_parent_trace`` chains new leaves to the same key
      so consent memory / pending reports / the children listing survive
      across turns.
    - ``_consented`` is the spawn-consent memory keyed by parent key (an
      old-world parent has no ``ConversationRecord`` to carry
      ``spawn_consent_granted``).

    Both die in phase 4 when interactive parents get supervisor records:
    session ids are stable, so no alias chain is needed, and consent lives on
    the record.
    """

    def __init__(self) -> None:
        self._alias: dict[str, str] = {}
        self._consented: set[str] = set()

    # -- parent keys ----------------------------------------------------------

    def parent_key_for_auto_run(self, run_id: str) -> str:
        return f"auto:{run_id}"

    def parent_key_for_trace(self, trace_id: str) -> str:
        """Resolve (or mint) the stable parent key for an interactive parent's
        leaf trace id, registering the alias."""
        key = self._alias.get(trace_id)
        if key is None:
            key = f"trace:{trace_id}"
            self._alias[trace_id] = key
        return key

    def alias_for_trace(self, trace_id: str) -> str | None:
        """Peek the alias WITHOUT minting one — for read paths (children
        listing, report drains, delete cascades) where an unknown trace simply
        means "no children/reports", never a new identity."""
        return self._alias.get(trace_id)

    def register_parent_alias(self, trace_id: str, parent_key: str) -> None:
        """Map a parent conversation's leaf trace id to its stable key.

        Needed for auto-run parents: their children are keyed
        ``auto:<run_id>``, but UI lookups (children list, next-turn report
        injection) arrive by leaf trace id — without the alias those lookups
        resolve to nothing."""
        self._alias[trace_id] = parent_key

    def note_parent_trace(self, old_leaf: str | None, new_leaf: str | None) -> None:
        """Chain an interactive parent's rotating leaf ids to its stable key."""
        if not old_leaf or not new_leaf or old_leaf == new_leaf:
            return
        key = self._alias.get(old_leaf)
        if key is not None:
            self._alias[new_leaf] = key

    # -- consent ----------------------------------------------------------------

    def mark_consented(self, parent_key: str) -> None:
        self._consented.add(parent_key)

    def is_consented(self, parent_key: str) -> bool:
        return parent_key in self._consented


# Module singleton, patched by tests exactly like the old subagent_registry.
parent_index = ParentConversationIndex()


@dataclass
class OrchestrationContext:
    """Identity of the conversation a batch of tool calls belongs to.

    Exactly one of the parent handles is set: ``parent_auto_run_id`` for calls
    executed by the auto runner, ``parent_trace_id`` for the interactive stream
    (updated per round as the leaf rotates). ``depth`` > 0 marks a sub-agent's
    own loop, whose orchestration calls are rejected before dispatch.

    (Unchanged from the old module; phase 4 shrinks this to
    ``{parent_session_id, depth}`` once parents have real session ids.)
    """

    parent_trace_id: str | None = None
    parent_auto_run_id: str | None = None
    depth: int = 0

    def parent_key(self) -> str | None:
        if self.parent_auto_run_id is not None:
            key = parent_index.parent_key_for_auto_run(self.parent_auto_run_id)
            # Alias the conversation's leaf to the auto key so trace-id lookups
            # (UI children list, next-turn report injection) resolve; the
            # runners chain later leaf rotations via note_parent_trace.
            if self.parent_trace_id is not None:
                parent_index.register_parent_alias(self.parent_trace_id, key)
            return key
        if self.parent_trace_id is not None:
            return parent_index.parent_key_for_trace(self.parent_trace_id)
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
    return key is not None and parent_index.is_consented(key)


def _record_payload(record: ConversationRecord, include_report: bool) -> dict[str, Any]:
    """The model-visible view of one child. Field names and semantics are the
    OLD wire shape, preserved verbatim (they are persisted into parent traces
    via tool results): ``subagent_id`` is the child handle used for
    wait/stop — now the child's session id — and ``session_id`` is the
    child's current UPSTREAM leaf trace id (what the backend's session
    endpoints understand today; renamed only when the backend adopts session
    ids in phase 6)."""
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
    # (Marked BEFORE the cap check, like the old executor: the user consented
    # to spawning even if this particular spawn bounces off a cap.)
    parent_index.mark_consented(parent_key)

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
        parent_trace_id=ctx.parent_trace_id,
    )
    try:
        record = conversation_supervisor.spawn_subagent(
            seed,
            # Phase-2 bridge: the parent_key string doubles as the child's
            # parent_session_id until parents have real session ids (see the
            # module docstring). Everything downstream (children index,
            # report queue, cascades) just matches this string.
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
    The kind guard is defense in depth: the supervisor will also hold
    interactive/auto records in later phases, and those must never be
    addressable as sub-agents."""
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


# ── Report drains + cascades for OLD-loop parents (the callers that used to
#    hit the sub-agent registry directly: stream_session's mid-stream drain,
#    routes' next-turn injection + delete cascade). ───────────────────────────


def pending_reports_for_trace(trace_id: str) -> list[str]:
    """Drain (and mark delivered) the framed reports awaiting delivery to the
    interactive parent whose (possibly rotated) leaf trace id this is.

    Old ``SubAgentRegistry.pending_reports_for_trace``: peek the alias chain —
    an unknown trace means "no reports", never a new identity — then drain the
    supervisor queue for that parent exactly once."""
    key = parent_index.alias_for_trace(trace_id)
    if key is None:
        return []
    return conversation_supervisor.drain_reports(key)


async def handle_session_deleted(trace_id: str) -> None:
    """Cascade for a deleted chat session (old
    ``SubAgentRegistry.handle_session_deleted``): if it was a sub-agent
    parent, stop its children and drop their pending reports; if the id
    belongs to a child's own session, stop that child."""
    parent_key = parent_index.alias_for_trace(trace_id)
    if parent_key is not None:
        await conversation_supervisor.stop_children(parent_key)
    session_id = conversation_supervisor.session_for_trace(trace_id)
    if session_id is not None:
        record = conversation_supervisor.get(session_id)
        if (
            record is not None
            and record.kind == "subagent"
            and not record.state.is_terminal
        ):
            await conversation_supervisor.stop(session_id)


def deliver_report_to_legacy_parent(parent_session_id: str, framed_report: str) -> bool:
    """PHASE-2-ONLY report bridge (see the module docstring; wired into
    ``conversation_supervisor.legacy_report_deliverer`` below, deleted in
    phase 3 when auto parents live on the supervisor).

    Preserves the old auto-parent completion injection: a child of an
    ``auto:*`` parent pushes its framed report into the OLD auto registry's
    inbox immediately (waking an IDLE parent into a fresh burst). Returns
    False for interactive (``trace:*``) parents and for a stopped/GC'd auto
    parent — the supervisor then queues the report for the interactive-parent
    drains, the old fallback verbatim."""
    if not parent_session_id.startswith("auto:"):
        return False
    run_id = parent_session_id.removeprefix("auto:")
    # Lazy import: the auto package is old-world; keep it out of this module's
    # import graph so nothing new grows a hard dependency on it (it is deleted
    # in phase 3).
    from app.desktop.studio_server.chat.auto.models import InboundMessage
    from app.desktop.studio_server.chat.auto.registry import auto_chat_registry

    return auto_chat_registry.send_message(
        run_id, InboundMessage(content=framed_report)
    )


# Wire the bridge at import time. Any path that creates a child imports this
# module first (spawns dispatch through execute_orchestration_tool), so the
# hook is always in place before a child can settle.
conversation_supervisor.legacy_report_deliverer = deliver_report_to_legacy_parent
