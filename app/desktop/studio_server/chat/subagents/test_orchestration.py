"""execute_orchestration_tool dispatch tests (against a patched registry)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from . import orchestration as orchestration_module
from .models import SubAgentSeed, SubAgentStatus
from .orchestration import (
    ORCHESTRATION_TOOL_NAMES,
    OrchestrationContext,
    execute_orchestration_tool,
    is_spawn_consented,
)
from .registry import SubAgentRegistry
from .runner import SubAgentRunner


@pytest.fixture
def registry():
    """A fresh registry patched in as the module singleton, with hanging
    runners (no network). Patched via the module OBJECT (not a string path) so
    it hits the same module instance these relative imports resolved to."""
    fresh = SubAgentRegistry(max_concurrent=10, max_per_parent=3)

    async def _hang(self) -> None:
        await asyncio.Event().wait()

    with (
        patch.object(orchestration_module, "subagent_registry", fresh),
        patch.object(SubAgentRunner, "run", _hang),
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


async def test_depth_guard_rejects(registry):
    result = await _call(
        "spawn_subagent", _spawn_args(), OrchestrationContext(depth=1)
    )
    assert result["status"] == "error"
    assert "cannot spawn" in result["message"]


async def test_no_context_rejects(registry):
    result = await _call("spawn_subagent", _spawn_args(), OrchestrationContext())
    assert result["status"] == "error"


async def test_spawn_and_status_roundtrip(registry):
    ctx = _ctx()
    spawned = await _call("spawn_subagent", _spawn_args(), ctx)
    assert spawned["status"] == "spawned"
    sid = spawned["subagent_id"]

    status = await _call("get_subagent_status", {}, ctx)
    assert [s["subagent_id"] for s in status["subagents"]] == [sid]
    assert status["subagents"][0]["state"] == "running"

    # Spawn marks consent for later downgrade.
    assert is_spawn_consented(ctx) is True


async def test_spawn_validates_args(registry):
    result = await _call("spawn_subagent", _spawn_args(prompt="  "), _ctx())
    assert result["status"] == "error"


async def test_spawn_cap_surfaces_as_tool_error(registry):
    ctx = _ctx()
    for i in range(3):
        await _call("spawn_subagent", _spawn_args(name=f"h{i}"), ctx)
    result = await _call("spawn_subagent", _spawn_args(name="h3"), ctx)
    assert result["status"] == "error"
    assert "running sub-agents" in result["message"]


async def test_ownership_scoping(registry):
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


async def test_wait_returns_reports_and_timeouts(registry):
    ctx = _ctx()
    a = (await _call("spawn_subagent", _spawn_args(name="a"), ctx))["subagent_id"]
    b = (await _call("spawn_subagent", _spawn_args(name="b"), ctx))["subagent_id"]
    await registry.stop(a)

    result = await _call(
        "wait_for_subagents",
        {"subagent_ids": [a, b], "timeout_seconds": 0.05},
        ctx,
    )
    by_id = {s["subagent_id"]: s for s in result["subagents"]}
    assert by_id[a]["state"] == "stopped"
    assert "report" in by_id[a]
    assert result["timed_out"] == [b]

    unknown = await _call(
        "wait_for_subagents", {"subagent_ids": ["sa_nope"]}, ctx
    )
    assert unknown["status"] == "error"


async def test_stop_tool(registry):
    ctx = _ctx()
    sid = (await _call("spawn_subagent", _spawn_args(), ctx))["subagent_id"]
    assert (await _call("stop_subagent", {"subagent_id": sid}, ctx))[
        "status"
    ] == "stopped"
    assert registry.get(sid).record.status == SubAgentStatus.STOPPED
    assert (await _call("stop_subagent", {"subagent_id": sid}, ctx))[
        "status"
    ] == "already_finished"


async def test_auto_parent_is_implicitly_consented(registry):
    ctx = OrchestrationContext(parent_auto_run_id="ar_1")
    assert is_spawn_consented(ctx) is True


def test_tool_name_set_matches_backend_contract():
    assert ORCHESTRATION_TOOL_NAMES == {
        "spawn_subagent",
        "get_subagent_status",
        "wait_for_subagents",
        "stop_subagent",
    }
