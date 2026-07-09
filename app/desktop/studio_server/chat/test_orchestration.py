"""execute_orchestration_tool dispatch tests against the unified runtime.

Port of the old ``chat/subagents/test_orchestration.py`` (deleted in phase 2)
plus the registry-level behaviors that moved here with the executor
(report drains, delete cascade, the legacy auto-parent report bridge). The
assertions are unchanged where the old suite had them — they are the
behavior contract of functional spec §3 "Sub-agents"."""

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


async def test_auto_parent_is_implicitly_consented(supervisor):
    ctx = OrchestrationContext(parent_auto_run_id="ar_1")
    assert is_spawn_consented(ctx) is True


def test_tool_name_set_matches_backend_contract():
    assert ORCHESTRATION_TOOL_NAMES == {
        "spawn_subagent",
        "get_subagent_status",
        "wait_for_subagents",
        "stop_subagent",
    }


async def test_auto_parent_children_resolvable_by_trace(supervisor):
    # Children of an AUTO parent are keyed auto:<run_id>; spawning must alias
    # the conversation's leaf trace id to that key so UI lookups by trace id
    # (children list, report injection) resolve.
    ctx = OrchestrationContext(parent_auto_run_id="ar_9", parent_trace_id="leaf-1")
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    sid = spawned["subagent_id"]

    index = orchestration_module.parent_index
    key = index.alias_for_trace("leaf-1")
    assert key == "auto:ar_9"
    assert [r.session_id for r in supervisor.children_of(key)] == [sid]
    # Later leaf rotations chain to the same key (what the auto runner does).
    index.note_parent_trace("leaf-1", "leaf-2")
    assert index.alias_for_trace("leaf-2") == key
    await supervisor.stop(sid)


# ── Behaviors that moved here from the old registry (report drains, delete
#    cascade, the legacy auto-parent bridge). ─────────────────────────────────


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


async def test_auto_parent_report_injected_via_legacy_bridge(supervisor):
    # PHASE-2 bridge (dies in phase 3): a child of an auto:* parent pushes its
    # framed report into the OLD auto registry's inbox on settle — the exact
    # old SubAgentRegistry._deliver_report behavior.
    supervisor.legacy_report_deliverer = (
        orchestration_module.deliver_report_to_legacy_parent
    )
    ctx = OrchestrationContext(parent_auto_run_id="ar_123")
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]

    with patch(
        "app.desktop.studio_server.chat.auto.registry.auto_chat_registry.send_message",
        return_value=True,
    ) as mock_send:
        await supervisor.stop(sid)

    mock_send.assert_called_once()
    run_id, message = mock_send.call_args.args
    assert run_id == "ar_123"
    assert f'id="{sid}"' in message.content
    assert supervisor.get(sid).report_delivered is True


async def test_auto_parent_gone_falls_back_to_queue(supervisor):
    supervisor.legacy_report_deliverer = (
        orchestration_module.deliver_report_to_legacy_parent
    )
    ctx = OrchestrationContext(parent_auto_run_id="ar_gone")
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    with patch(
        "app.desktop.studio_server.chat.auto.registry.auto_chat_registry.send_message",
        return_value=False,
    ):
        await supervisor.stop(sid)
    # Queued for a resumed interactive turn on the same trace (old fallback).
    assert supervisor.has_pending_reports("auto:ar_gone")
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
