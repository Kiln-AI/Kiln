"""Golden-protocol scenarios: the behavior contract of the unified runtime.

Each scenario scripts a fake upstream (``chat/test_fakes.py``) and captures
the exact sequence of upstream REQUEST BODIES produced by the
``ConversationEngine`` under each policy. The captured sequences are pinned
as checked-in JSON fixtures under ``golden/`` and compared as parsed JSON
(dict equality — key order is irrelevant on the wire).
``test_golden_protocol.py`` asserts ``fixture == engine``.

The interactive fixtures were captured from the request-scoped interactive
loop (``ChatStreamSession`` behind ``POST /api/chat`` +
``POST /api/chat/execute-tools``) that this runtime replaces, so they pin
that the engine's request bodies — exactly what the backend persists into
traces — are unchanged (functional spec §3). The auto-mode fixtures were
captured from the engine, the reference implementation.

Regenerating fixtures (only when a scenario is deliberately changed):

    uv run python -m app.desktop.studio_server.chat.runtime.golden_scenarios
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import httpx

from app.desktop.studio_server.chat.test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)

from .engine import ConversationEngine, EngineIO
from .models import (
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    auto_policy,
    build_auto_seed_body,
    interactive_policy,
)

GOLDEN_DIR = Path(__file__).parent / "golden"

UPSTREAM_URL = "https://example.test/v1/chat"


# ── Capture helpers ───────────────────────────────────────────────────────────


def _bodies(client: FakeUpstreamClient) -> list[dict[str, Any]]:
    """The captured upstream request bodies (already JSON-parsed by the fake)."""
    return list(client.bodies)


async def _consume(stream) -> list[bytes]:
    return [chunk async for chunk in stream]


async def _run_engine(
    *,
    policy,
    record: ConversationRecord,
    client: FakeUpstreamClient,
    initial_body: dict[str, Any] | None,
    inbox: list[InboundMessage] | None = None,
    decisions: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    """Drive the engine over the scripted upstream with a minimal io wiring
    (lists instead of the supervisor), mirroring what the supervisor
    provides: a drain-once inbox and an immediately-deciding approval
    callback."""
    emitted: list[bytes] = []
    inbox_queue = list(inbox or [])

    def drain_inbox() -> list[InboundMessage]:
        taken = list(inbox_queue)
        inbox_queue.clear()
        return taken

    async def await_decisions(batch: PendingApprovalBatch) -> dict[str, bool]:
        # Golden scenarios decide instantly; the parked-task mechanics are
        # covered by the engine/supervisor unit tests.
        assert decisions is not None, "scenario parked but provided no decisions"
        return decisions

    async def on_trace(tid: str) -> None:  # index bookkeeping is supervisor's
        pass

    io = EngineIO(
        emit=emitted.append,
        on_trace=on_trace,
        drain_inbox=drain_inbox,
        await_decisions=await_decisions,
    )
    engine = ConversationEngine(UPSTREAM_URL, {})
    with patch.object(httpx, "AsyncClient", return_value=client):
        await engine.run(record, policy, io, initial_body)
    return _bodies(client)


# ── Scenario 1: interactive tool round + continuation ────────────────────────

_INTERACTIVE_INITIAL_BODY = {"messages": [{"role": "user", "content": "add 10 and 5"}]}


def _interactive_tool_round_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                text_delta("computing"),
                tool_input_available("tc1", "add", {"a": 10, "b": 5}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("Result is 15"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_interactive_tool_round() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=interactive_policy(),
        record=ConversationRecord(kind="interactive"),
        client=FakeUpstreamClient(_interactive_tool_round_responses()),
        initial_body=dict(_INTERACTIVE_INITIAL_BODY),
    )


# ── Scenario 2: interactive approval flow ─────────────────────────────────────
#
# The request-scoped loop ENDED the stream at tool-calls-pending and the
# browser POSTed /api/chat/execute-tools to continue on a second stream. The
# runtime parks the run on await_decisions and continues in-place. The
# upstream body sequence is identical across the two shapes.

_APPROVAL_INITIAL_BODY = {"messages": [{"role": "user", "content": "please add"}]}
# Mixed decision set: one approved, one DENIED — the denial continuation
# (DENIED_TOOL_OUTPUT riding a role:tool row) is part of the persisted-trace
# protocol and is pinned here at the fixture level, not just in unit tests.
_APPROVAL_DECISIONS = {"tc1": True, "tc2": False}


def _approval_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                text_delta("need approval"),
                tool_input_available(
                    "tc1",
                    "add",
                    {"a": 1, "b": 2},
                    kiln_metadata={
                        "requires_approval": True,
                        "permission": "math",
                        "approval_description": "Add numbers",
                    },
                ),
                tool_input_available(
                    "tc2",
                    "multiply",
                    {"a": 3, "b": 4},
                    kiln_metadata={
                        "requires_approval": True,
                        "permission": "math",
                        "approval_description": "Multiply numbers",
                    },
                ),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("Sum is 3"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_interactive_approval_flow() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=interactive_policy(),
        record=ConversationRecord(kind="interactive"),
        client=FakeUpstreamClient(_approval_responses()),
        initial_body=dict(_APPROVAL_INITIAL_BODY),
        decisions=dict(_APPROVAL_DECISIONS),
    )


# ── Scenario 3: auto seed + tool round + mid-burst side-note injection ────────
#
# The auto seed body (enable_auto_mode resolution + the auto_mode flag) is
# built by the builder the enable flow uses in production
# (models.build_auto_seed_body ← supervisor.enable_auto), so the checked-in
# fixture keeps the builder's shape honest.

_AUTO_SEED_BODY = build_auto_seed_body(
    trace_id="tr-0",
    enable_tool_call_id="enable-1",
    extra_messages=[],
    sibling_results={},
)
_SIDE_NOTE_TEXT = "also do X"


def _auto_tool_round_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                tool_input_available("tc1", "add", {"a": 1, "b": 1}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(chunks=[text_delta("ok"), trace("tr-2"), finish("stop")]),
    ]


async def _engine_auto_seed_and_tool_round() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_auto_tool_round_responses()),
        initial_body=dict(_AUTO_SEED_BODY),
        inbox=[InboundMessage(content=_SIDE_NOTE_TEXT)],
    )


# ── Scenario 4: stale disable_auto_mode refusal mid-burst (FR1) ──────────────
#
# Auto mode turns off only by user action: a disable_auto_mode call is
# refused without side effects — the refusal rides the continuation next to
# the executed sibling's result and the burst CONTINUES.


def _auto_disable_stale_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                text_delta("turning off auto mode"),
                tool_input_available("tc_disable", "disable_auto_mode", {}),
                tool_input_available("tc_add", "add", {"a": 1, "b": 1}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("understood, continuing"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_auto_disable_stale_refusal() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_auto_disable_stale_responses()),
        initial_body=dict(_AUTO_SEED_BODY),
    )


# ── Scenario table ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldenScenario:
    name: str
    # Captures the upstream request bodies from the ConversationEngine.
    run_engine: Callable[[], Awaitable[list[dict[str, Any]]]]


SCENARIOS: tuple[GoldenScenario, ...] = (
    GoldenScenario("interactive_tool_round", _engine_interactive_tool_round),
    GoldenScenario("interactive_approval_flow", _engine_interactive_approval_flow),
    GoldenScenario("auto_seed_and_tool_round", _engine_auto_seed_and_tool_round),
    GoldenScenario("auto_disable_stale_refusal", _engine_auto_disable_stale_refusal),
)


def fixture_path(name: str) -> Path:
    return GOLDEN_DIR / f"{name}.json"


def load_fixture(name: str) -> list[dict[str, Any]]:
    with fixture_path(name).open() as f:
        data = json.load(f)
    return data["bodies"]


def _write_fixture(name: str, bodies: list[dict[str, Any]]) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    with fixture_path(name).open("w") as f:
        json.dump({"scenario": name, "bodies": bodies}, f, indent=2, ensure_ascii=False)
        f.write("\n")


async def _regenerate_all() -> None:
    for scenario in SCENARIOS:
        bodies = await scenario.run_engine()
        _write_fixture(scenario.name, bodies)
        sys.stdout.write(
            f"wrote {fixture_path(scenario.name)} ({len(bodies)} bodies)\n"
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(_regenerate_all())
