"""execute_orchestration_tool dispatch tests against the unified runtime.

Port of the old ``chat/subagents/test_orchestration.py`` (deleted in phase 2)
plus the registry-level behaviors that moved here with the executor (the
delete cascade). The assertions are unchanged where the old suite had them —
they are the behavior contract of functional spec §3 "Sub-agents".

Phase 4: EVERY parent is a supervisor record, so the ctx carries only
``{parent_session_id, depth}`` — the ``ParentConversationIndex`` alias chain,
its consent set (``is_spawn_consented``), and the trace-keyed report drain
(``pending_reports_for_trace``) died with the old interactive loop. Consent
lives on ``ConversationRecord.spawn_consent_granted`` (engine-written, tested
in runtime/test_engine.py) and report drains are session-keyed
(supervisor.drain_reports, exercised end-to-end in runtime/test_supervisor.py's
idle-start drain test)."""

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
    execute_orchestration_tool,
)
from app.desktop.studio_server.chat.runtime.engine import ConversationEngine
from app.desktop.studio_server.chat.runtime.models import RunState
from app.desktop.studio_server.chat.runtime.supervisor import ConversationSupervisor


@pytest.fixture
def supervisor():
    """A fresh supervisor patched in as the module singleton, with a hanging
    engine (no network). Patched via the module OBJECT (not a string path) so
    it hits the same module instance these imports resolved to — the exact
    pattern the old registry-patching fixture used."""
    fresh = ConversationSupervisor(
        subagent_max_concurrent=10, subagent_max_per_parent=3
    )

    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with (
        patch.object(orchestration_module, "conversation_supervisor", fresh),
        patch.object(ConversationEngine, "run", _hang),
        patch(
            "app.desktop.studio_server.utils.copilot_utils.get_copilot_api_key",
            return_value="key",
        ),
    ):
        yield fresh


def _parent_ctx(
    supervisor: ConversationSupervisor,
    kind: str = "interactive",
    leaf: str | None = "leaf-1",
) -> OrchestrationContext:
    """A real supervisor-resident parent + its ctx (phase 4: parent identity
    is always a session id; there is no trace-keyed parent anymore)."""
    record = supervisor.create_conversation(
        kind, upstream_url="https://example.test", headers={}
    )
    if leaf is not None:
        record.current_leaf_trace_id = leaf
        record.seen_trace_ids.append(leaf)
        supervisor._trace_index[leaf] = record.session_id
    return OrchestrationContext(parent_session_id=record.session_id)


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
    ctx = _parent_ctx(supervisor)
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    assert spawned["status"] == "spawned"
    sid = spawned["subagent_id"]
    # The child handle IS its conversation session id in the unified world.
    assert sid.startswith("cv_")
    assert supervisor.get(sid) is not None

    status = await _call("get_subagent_status", {}, ctx)
    assert [s["subagent_id"] for s in status["subagents"]] == [sid]
    assert status["subagents"][0]["state"] == "running"


async def test_spawn_seed_lineage_reads_parent_records_leaf(supervisor):
    # Phase 4: the agent block's parent_trace_id (durable backend lineage)
    # comes from the parent RECORD's current leaf — the single source the
    # engine's on_trace keeps fresh (the old per-round ctx refresh is gone).
    ctx = _parent_ctx(supervisor, leaf="leaf-current")
    with patch.object(
        supervisor, "spawn_subagent", wraps=supervisor.spawn_subagent
    ) as spawn_spy:
        spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    assert spawned["status"] == "spawned"
    seed = spawn_spy.call_args.args[0]
    assert seed.parent_trace_id == "leaf-current"
    await supervisor.stop(spawned["subagent_id"])


async def test_spawn_validates_args(supervisor):
    result = await _call(
        "spawn_subagent", _spawn_args(prompt="  "), _parent_ctx(supervisor)
    )
    assert result["status"] == "error"


async def test_spawn_cap_surfaces_as_tool_error(supervisor):
    ctx = _parent_ctx(supervisor)
    for i in range(3):
        await _call("spawn_subagent", _spawn_args(name=f"h{i}"), ctx)
    result = await _call("spawn_subagent", _spawn_args(name="h3"), ctx)
    # Caps are TOOL-RESULT errors, never HTTP (the model must be able to
    # react) — message text preserved from the old registry.
    assert result["status"] == "error"
    assert "running sub-agents" in result["message"]


async def test_ownership_scoping(supervisor):
    ctx_a = _parent_ctx(supervisor, leaf="leaf-a")
    ctx_b = _parent_ctx(supervisor, leaf="leaf-b")
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
    ctx = _parent_ctx(supervisor)
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
    ctx = _parent_ctx(supervisor)
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


def test_tool_name_set_matches_backend_contract():
    assert ORCHESTRATION_TOOL_NAMES == {
        "spawn_subagent",
        "get_subagent_status",
        "wait_for_subagents",
        "stop_subagent",
    }


async def test_children_keyed_by_parent_session_id(supervisor):
    # Children are keyed by the parent's SESSION id — stable across leaf
    # rotations, so no alias chaining exists anywhere anymore (the
    # trace:<leaf> keys died with ParentConversationIndex in phase 4).
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    ctx = OrchestrationContext(parent_session_id=parent.session_id)
    assert ctx.parent_key() == parent.session_id
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    sid = spawned["subagent_id"]

    assert [r.session_id for r in supervisor.children_of(parent.session_id)] == [sid]
    await supervisor.stop(sid)


# ── Behaviors that moved here from the old registry (report routing, delete
#    cascade). ──────────────────────────────────────────────────────────────


async def test_interactive_parent_report_queued_and_drained_once(supervisor):
    ctx = _parent_ctx(supervisor)
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    await supervisor.stop(sid)

    # Queued for the parent's next-turn / mid-stream drain — session-keyed
    # since phase 4 (the trace-keyed pending_reports_for_trace died with the
    # old loop; the engine drains via io.drain_reports and the idle-start
    # send drains via supervisor.send_message).
    assert supervisor.has_pending_reports(ctx.parent_key())
    reports = supervisor.drain_reports(ctx.parent_key())
    assert len(reports) == 1
    assert f'id="{sid}"' in reports[0]
    assert 'status="stopped"' in reports[0]
    # Drained exactly once.
    assert supervisor.drain_reports(ctx.parent_key()) == []


async def test_auto_parent_report_injected_natively_via_supervisor_inbox(supervisor):
    # A child of an AUTO parent delivers its framed report straight through
    # the supervisor's inbox routing. The injection wakes the idle parent
    # into a burst (engine hangs here; the state transition is the
    # observable).
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


async def test_in_burst_disable_reports_queue_for_the_swapped_parent(supervisor):
    # An auto burst spawns a child → the model calls disable_auto_mode
    # IN-BURST (resolve_terminal: flag off + user_disabled, deliberately NO
    # child cascade — the old _supervise never cascaded on the tool path) →
    # the child settles AFTER the flag cleared → its report queues under the
    # parent's SESSION id, where the conversation's next interactive turn
    # (supervisor.send_message idle-start drain) picks it up.
    parent = supervisor.create_conversation(
        "auto", upstream_url="https://example.test", headers={}
    )
    ctx = OrchestrationContext(parent_session_id=parent.session_id)
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    # In-burst disable: the engine clears the flag and ends the burst; the
    # child survives and keeps running.
    parent.auto_flag = False
    parent.idle_reason = "user_disabled"

    await supervisor.stop(sid)  # the surviving child settles
    # Queued (the off parent can't take inbox messages), not lost — the
    # session-keyed queue survives the policy swap because the record and
    # its session id are the SAME object across the flip.
    assert supervisor.has_pending_reports(parent.session_id)
    reports = supervisor.drain_reports(parent.session_id)
    assert len(reports) == 1
    assert f'id="{sid}"' in reports[0]
    assert supervisor.get(sid).report_delivered is True


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
    ctx = _parent_ctx(supervisor, leaf="leaf-1")
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    # Deleting the parent session stops its children (and drops reports) —
    # resolved through the supervisor's whole-chain trace index. The explicit
    # stop_children matters since phase 4: a plain interactive stop() no
    # longer cascades, but a DELETED parent's children have nothing left to
    # consume their reports.
    await orchestration_module.handle_session_deleted("leaf-1")
    assert supervisor.get(sid).state == RunState.STOPPED
    assert not supervisor.has_pending_reports(ctx.parent_key())
    parent_record = supervisor.get(ctx.parent_key())
    assert parent_record is not None and parent_record.state == RunState.IDLE

    # Deleting a child's own session stops that child. Simulate the child's
    # session trace becoming known via the supervisor's trace index.
    ctx2 = _parent_ctx(supervisor, leaf="leaf-2")
    sid2 = (await _call("spawn_subagent", _spawn_args(name="h2"), ctx2))["subagent_id"]
    supervisor._trace_index["child-leaf"] = sid2
    await orchestration_module.handle_session_deleted("child-leaf")
    assert supervisor.get(sid2).state == RunState.STOPPED

    # An unknown trace is a no-op.
    await orchestration_module.handle_session_deleted("never-seen")
