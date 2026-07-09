"""execute_orchestration_tool dispatch tests against the unified runtime.

Port of the old ``chat/subagents/test_orchestration.py`` (deleted in phase 2)
plus the registry-level behaviors that moved here with the executor (report
drains, delete cascade). The assertions are unchanged where the old suite had
them — they are the behavior contract of functional spec §3 "Sub-agents".
Phase 3: auto parents are supervisor records, so their ctx carries a real
``parent_session_id`` (the ``auto:<run_id>`` keys, alias registration, and
the legacy report bridge are gone)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

# Absolute imports throughout: chat/orchestration.py imports the runtime by
# its absolute path, and mixing relative test imports would resolve DIFFERENT
# module instances under pytest — a fresh supervisor would then raise a
# ConversationCapError class the executor's except clause doesn't match.
from app.desktop.studio_server.chat import orchestration as orchestration_module
from app.desktop.studio_server.chat.orchestration import (
    ORCHESTRATION_TOOL_NAMES,
    OrchestrationContext,
    ParentConversationIndex,
    execute_orchestration_tool,
    is_spawn_consented,
)
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine
from app.desktop.studio_server.chat.runtime.models import RunState
from app.desktop.studio_server.chat.runtime.supervisor import ConversationSupervisor


@pytest.fixture
def supervisor():
    """A fresh supervisor + parent index patched in as the module singletons,
    with a hanging engine (no network). Patched via the module OBJECT (not a
    string path) so it hits the same module instance these relative imports
    resolved to — the exact pattern the old registry-patching fixture used."""
    fresh = ConversationSupervisor(
        subagent_max_concurrent=10, subagent_max_per_parent=3
    )
    fresh_index = ParentConversationIndex()

    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with (
        patch.object(orchestration_module, "conversation_supervisor", fresh),
        patch.object(orchestration_module, "parent_index", fresh_index),
        patch.object(ConversationEngine, "run", _hang),
        patch(
            "app.desktop.studio_server.utils.copilot_utils.get_copilot_api_key",
            return_value="key",
        ),
    ):
        yield fresh


def _ctx(trace: str = "leaf-1") -> OrchestrationContext:
    return OrchestrationContext(parent_trace_id=trace)


def _spawn_args(**overrides):
    return {
        "agent_type": "general",
        "name": "helper",
        "prompt": "Briefing.",
        **overrides,
    }


async def _call(name: str, args: dict, ctx: OrchestrationContext) -> dict:
    return json.loads(await execute_orchestration_tool(name, args, ctx))


async def test_depth_guard_rejects(supervisor):
    result = await _call("spawn_subagent", _spawn_args(), OrchestrationContext(depth=1))
    assert result["status"] == "error"
    assert "cannot spawn" in result["message"]


async def test_no_context_rejects(supervisor):
    result = await _call("spawn_subagent", _spawn_args(), OrchestrationContext())
    assert result["status"] == "error"


async def test_spawn_and_status_roundtrip(supervisor):
    ctx = _ctx()
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    assert spawned["status"] == "spawned"
    sid = spawned["subagent_id"]
    # The child handle IS its conversation session id in the unified world.
    assert sid.startswith("cv_")
    assert supervisor.get(sid) is not None

    status = await _call("get_subagent_status", {}, ctx)
    assert [s["subagent_id"] for s in status["subagents"]] == [sid]
    assert status["subagents"][0]["state"] == "running"

    # Spawn marks consent for later downgrade.
    assert is_spawn_consented(ctx) is True


async def test_spawn_validates_args(supervisor):
    result = await _call("spawn_subagent", _spawn_args(prompt="  "), _ctx())
    assert result["status"] == "error"


async def test_spawn_cap_surfaces_as_tool_error(supervisor):
    ctx = _ctx()
    for i in range(3):
        await _call("spawn_subagent", _spawn_args(name=f"h{i}"), ctx)
    result = await _call("spawn_subagent", _spawn_args(name="h3"), ctx)
    # Caps are TOOL-RESULT errors, never HTTP (the model must be able to
    # react) — message text preserved from the old registry.
    assert result["status"] == "error"
    assert "running sub-agents" in result["message"]


async def test_ownership_scoping(supervisor):
    ctx_a = _ctx("leaf-a")
    ctx_b = _ctx("leaf-b")
    spawned = await _call("spawn_subagent", _spawn_args(), ctx_a)
    sid = spawned["subagent_id"]

    # Another conversation can't see or stop it.
    status = await _call("get_subagent_status", {"subagent_id": sid}, ctx_b)
    assert status["status"] == "error"
    stop = await _call("stop_subagent", {"subagent_id": sid}, ctx_b)
    assert stop["status"] == "not_found"
    listed = await _call("get_subagent_status", {}, ctx_b)
    assert listed["subagents"] == []


async def test_wait_returns_statuses_and_timeouts(supervisor):
    ctx = _ctx()
    a = (await _call("spawn_subagent", _spawn_args(name="a"), ctx))["subagent_id"]
    b = (await _call("spawn_subagent", _spawn_args(name="b"), ctx))["subagent_id"]
    await supervisor.stop(a)

    result = await _call(
        "wait_for_subagents",
        {"subagent_ids": [a, b], "timeout_seconds": 0.05},
        ctx,
    )
    by_id = {s["subagent_id"]: s for s in result["subagents"]}
    assert by_id[a]["state"] == "stopped"
    # Statuses only — reports flow through the injection channel so they are
    # persisted in the parent trace and rendered as report panels.
    assert "report" not in by_id[a]
    assert "note" in result
    assert result["timed_out"] == [b]
    # The terminal child's report stays queued for injection.
    assert supervisor.has_pending_reports(ctx.parent_key())

    unknown = await _call("wait_for_subagents", {"subagent_ids": ["cv_nope"]}, ctx)
    assert unknown["status"] == "error"


async def test_stop_tool(supervisor):
    ctx = _ctx()
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    assert (await _call("stop_subagent", {"subagent_id": sid}, ctx))[
        "status"
    ] == "stopped"
    assert supervisor.get(sid).state == RunState.STOPPED
    # The old outcome vocabulary survives the supervisor's idempotent-void
    # stop(): the executor classifies terminal records itself.
    assert (await _call("stop_subagent", {"subagent_id": sid}, ctx))[
        "status"
    ] == "already_finished"


async def test_supervisor_parent_is_implicitly_consented(supervisor):
    # Phase 3: every supervisor-resident parent is an AUTO conversation, whose
    # consent dialog covers autonomous work (the old "auto-run parents are
    # implicitly consented" rule, keyed by session id now).
    ctx = OrchestrationContext(parent_session_id="cv_parent1")
    assert is_spawn_consented(ctx) is True


def test_tool_name_set_matches_backend_contract():
    assert ORCHESTRATION_TOOL_NAMES == {
        "spawn_subagent",
        "get_subagent_status",
        "wait_for_subagents",
        "stop_subagent",
    }


async def test_supervisor_parent_children_keyed_by_session_id(supervisor):
    # Children of a supervisor-resident (auto) parent are keyed by the
    # parent's SESSION id — stable across leaf rotations, so no alias
    # chaining exists for them anymore (the old auto:<run_id> key +
    # register_parent_alias plumbing died with chat/auto/). The trace id
    # still rides the ctx purely as backend spawn lineage.
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    ctx = OrchestrationContext(
        parent_session_id=parent.session_id, parent_trace_id="leaf-1"
    )
    assert ctx.parent_key() == parent.session_id
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    sid = spawned["subagent_id"]

    assert [r.session_id for r in supervisor.children_of(parent.session_id)] == [sid]
    # No alias was minted for the leaf — session ids need none.
    assert orchestration_module.parent_index.alias_for_trace("leaf-1") is None
    # Consent stayed off the parent index too (it lives on the record /
    # implicit-auto rule, not in the phase-4-doomed index).
    assert not orchestration_module.parent_index.is_consented(parent.session_id)
    await supervisor.stop(sid)


# ── Behaviors that moved here from the old registry (report drains, delete
#    cascade). ──────────────────────────────────────────────────────────────


async def test_interactive_parent_report_queued_and_drained_once(supervisor):
    ctx = _ctx("leaf-1")
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    await supervisor.stop(sid)

    # The parent's leaf rotates; the alias chain keeps the key reachable.
    orchestration_module.parent_index.note_parent_trace("leaf-1", "leaf-2")
    reports = orchestration_module.pending_reports_for_trace("leaf-2")
    assert len(reports) == 1
    assert f'id="{sid}"' in reports[0]
    assert 'status="stopped"' in reports[0]
    # Drained exactly once; an unknown trace never mints an identity.
    assert orchestration_module.pending_reports_for_trace("leaf-2") == []
    assert orchestration_module.pending_reports_for_trace("never-seen") == []
    assert orchestration_module.parent_index.alias_for_trace("never-seen") is None


async def test_auto_parent_report_injected_natively_via_supervisor_inbox(supervisor):
    # Phase 3: a child of a supervisor-resident AUTO parent delivers its
    # framed report straight through the supervisor's inbox routing — the
    # phase-2 legacy_report_deliverer bridge (which pushed into the OLD auto
    # registry) is gone. The injection wakes the idle parent into a burst
    # (engine hangs here; the state transition is the observable).
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    ctx = OrchestrationContext(parent_session_id=parent.session_id)
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    await supervisor.stop(sid)

    assert supervisor.get(sid).report_delivered is True
    # Inbox was the one channel — nothing queued for the drain path.
    assert not supervisor.has_pending_reports(parent.session_id)
    # The idle auto parent woke into a burst seeded with the report.
    assert parent.state == RunState.RUNNING
    await supervisor.stop(parent.session_id)


async def test_in_burst_disable_reports_drain_on_next_interactive_turn(supervisor):
    # MODERATE regression guard (full flow): an auto burst spawns a child →
    # the model calls disable_auto_mode IN-BURST (the engine's
    # resolve_terminal outcome: flag off + user_disabled, deliberately NO
    # child cascade — the old _supervise never cascaded on the tool path) →
    # the child settles AFTER the flag cleared → its report queues under the
    # auto parent's SESSION id → the user continues on the OLD interactive
    # loop, whose injection drains (routes.py next-turn, stream_session
    # mid-stream) only hold the conversation's TRACE id — the supervisor
    # trace-index fallback in pending_reports_for_trace must resolve it, or
    # the report is stranded.
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    # Adopt the conversation's leaf exactly like enable_auto does.
    parent.current_leaf_trace_id = "leaf-auto-1"
    parent.seen_trace_ids.append("leaf-auto-1")
    supervisor._trace_index["leaf-auto-1"] = parent.session_id

    ctx = OrchestrationContext(
        parent_session_id=parent.session_id, parent_trace_id="leaf-auto-1"
    )
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    # In-burst disable: the engine clears the flag and ends the burst; the
    # child survives and keeps running.
    parent.auto_flag = False
    parent.idle_reason = "user_disabled"

    await supervisor.stop(sid)  # the surviving child settles
    # Queued (the off parent can't take inbox messages), not lost.
    assert supervisor.has_pending_reports(parent.session_id)

    # The resumed interactive turn drains by trace id.
    reports = orchestration_module.pending_reports_for_trace("leaf-auto-1")
    assert len(reports) == 1
    assert f'id="{sid}"' in reports[0]
    assert supervisor.get(sid).report_delivered is True
    # Drained exactly once; a child's own leaf never drains a queue (the
    # fallback's kind guard).
    assert orchestration_module.pending_reports_for_trace("leaf-auto-1") == []
    supervisor._trace_index["child-leaf"] = sid
    assert orchestration_module.pending_reports_for_trace("child-leaf") == []


async def test_auto_parent_flag_off_falls_back_to_queue(supervisor):
    # Old auto-parent-gone fallback, session-id keyed: a parent whose flag
    # already cleared can't take inbox messages, so the report queues for a
    # resumed interactive turn on the same conversation.
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    ctx = OrchestrationContext(parent_session_id=parent.session_id)
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    parent.auto_flag = False  # stopped/disabled before the child settled
    await supervisor.stop(sid)
    assert supervisor.has_pending_reports(parent.session_id)
    assert supervisor.get(sid).report_delivered is False


async def test_handle_session_deleted_stops_parent_children_and_child(supervisor):
    ctx = _ctx("leaf-1")
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    # Deleting the parent session stops its children (and drops reports).
    await orchestration_module.handle_session_deleted("leaf-1")
    assert supervisor.get(sid).state == RunState.STOPPED
    assert not supervisor.has_pending_reports(ctx.parent_key())

    # Deleting a child's own session stops that child. Simulate the child's
    # session trace becoming known via the supervisor's trace index.
    ctx2 = _ctx("leaf-2")
    sid2 = (await _call("spawn_subagent", _spawn_args(name="h2"), ctx2))["subagent_id"]
    supervisor._trace_index["child-leaf"] = sid2
    await orchestration_module.handle_session_deleted("child-leaf")
    assert supervisor.get(sid2).state == RunState.STOPPED


async def test_consent_memory_survives_leaf_rotation(supervisor):
    index = orchestration_module.parent_index
    key = index.parent_key_for_trace("leaf-1")
    index.mark_consented(key)
    index.note_parent_trace("leaf-1", "leaf-2")
    assert index.parent_key_for_trace("leaf-2") == key
    assert is_spawn_consented(_ctx("leaf-2")) is True
