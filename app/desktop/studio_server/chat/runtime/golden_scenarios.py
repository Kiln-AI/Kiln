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
    SubAgentSeed,
    auto_policy,
    build_auto_seed_body,
    interactive_policy,
    subagent_policy,
)

GOLDEN_DIR = Path(__file__).parent / "golden"

UPSTREAM_URL = "https://example.test/v1/chat"

# A fixed, fully deterministic report frame (real frames carry a random child
# id, which would make fixtures unstable). The frame SHAPE is covered by unit
# tests; these scenarios pin how a drained report rides the continuation.
REPORT_FRAME = (
    '<subagent_report id="sa_fixed" agent_type="general" status="completed" '
    'title="Helper">\nAll done.\n</subagent_report>'
)


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
    reports: list[str] | None = None,
    decisions: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    """Drive the engine over the scripted upstream with a minimal io wiring
    (lists instead of the supervisor), mirroring what the supervisor
    provides: drain-once inbox/report queues and an immediately-deciding
    approval callback."""
    emitted: list[bytes] = []
    inbox_queue = list(inbox or [])
    report_queue = list(reports or [])

    def drain_inbox() -> list[InboundMessage]:
        taken = list(inbox_queue)
        inbox_queue.clear()
        return taken

    def drain_reports() -> list[str]:
        taken = list(report_queue)
        report_queue.clear()
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
        drain_reports=drain_reports,
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


# ── Scenario 3: interactive mid-stream sub-agent report injection ─────────────

_REPORT_INITIAL_BODY = {"messages": [{"role": "user", "content": "check status"}]}


def _report_injection_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                tool_input_available("tc1", "add", {"a": 2, "b": 2}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("noted the report"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_interactive_report_injection() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=interactive_policy(),
        record=ConversationRecord(kind="interactive"),
        client=FakeUpstreamClient(_report_injection_responses()),
        initial_body=dict(_REPORT_INITIAL_BODY),
        reports=[REPORT_FRAME],
    )


# ── Scenario 4: auto seed + tool round + mid-burst side-note injection ────────
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


# ── Scenario 5: stale disable_auto_mode refusal mid-burst (FR1) ──────────────
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


# ── Scenario 6: FR2 spawn-consent accept seed ────────────────────────────────
#
# Accepting a spawn-triggered consent (interactive spawn_subagent with auto
# mode off) rides enable_auto with NO enable tool call id: the gating spawn
# executes first and its {"status": "spawned", ...} result seeds the burst as
# a plain sibling result (models.build_auto_seed_body — the same builder the
# route uses). The fixture pins that seed shape — no enable row, the spawn's
# role:tool result leading the messages, auto_mode riding every continuation —
# plus one normal tool round showing the burst continuing under the auto
# policy. Captured from the engine (the reference implementation).

_SPAWN_ACCEPT_RESULT = json.dumps(
    {"status": "spawned", "subagent_id": "cv_fixed", "name": "helper"},
    ensure_ascii=False,
)
_SPAWN_ACCEPT_SEED_BODY = build_auto_seed_body(
    trace_id="tr-0",
    enable_tool_call_id=None,
    extra_messages=[],
    sibling_results={"tc_spawn": _SPAWN_ACCEPT_RESULT},
)


def _spawn_consent_accept_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                tool_input_available("tc1", "add", {"a": 1, "b": 1}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("child is working"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_auto_spawn_consent_accept_seed() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_spawn_consent_accept_responses()),
        initial_body=dict(_SPAWN_ACCEPT_SEED_BODY),
    )


# ── Scenario 7: sub-agent seed body + steer message ──────────────────────────

_SUBAGENT_SEED = SubAgentSeed(
    agent_type="general",
    name="eval-helper",
    prompt="Briefing: do the thing.",
    parent_trace_id="parent-leaf-1",
)
_STEER_TEXT = "also check model B"


def _subagent_steer_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[text_delta("thought I was done"), trace("tr-1"), finish()]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("real report"), trace("tr-2"), finish()]
        ),
    ]


async def _engine_subagent_seed_and_steer() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=subagent_policy(_SUBAGENT_SEED),
        record=ConversationRecord(
            kind="subagent",
            parent_session_id="cv_parent",
            name=_SUBAGENT_SEED.name,
            agent_type=_SUBAGENT_SEED.agent_type,
        ),
        client=FakeUpstreamClient(_subagent_steer_responses()),
        # None: the engine builds the seed body (agent block + kickoff) from
        # policy.seed — that construction is exactly what this fixture pins.
        initial_body=None,
        inbox=[InboundMessage(content=_STEER_TEXT)],
    )


# ── Scenario 8: a <subagent_report> frame on the auto inbox rides UNWRAPPED ──
#
# Reports reach auto-flag parents through the same inbound channel as user
# asides, but must NOT get the side-note frame: it would misdescribe them to
# the model and break the client's report-panel detection, which keys on the
# persisted message STARTING with the frame.


def _auto_report_inbox_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[text_delta("waiting for helpers"), trace("tr-1"), finish("stop")]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("thanks, wrapping up"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _engine_auto_report_inbox_unwrapped() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_auto_report_inbox_responses()),
        initial_body=dict(_AUTO_SEED_BODY),
        inbox=[InboundMessage(content=REPORT_FRAME)],
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
    GoldenScenario(
        "interactive_report_injection", _engine_interactive_report_injection
    ),
    GoldenScenario("auto_seed_and_tool_round", _engine_auto_seed_and_tool_round),
    GoldenScenario("auto_disable_stale_refusal", _engine_auto_disable_stale_refusal),
    GoldenScenario(
        "auto_spawn_consent_accept_seed", _engine_auto_spawn_consent_accept_seed
    ),
    GoldenScenario("subagent_seed_and_steer", _engine_subagent_seed_and_steer),
    GoldenScenario("auto_report_inbox_unwrapped", _engine_auto_report_inbox_unwrapped),
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
