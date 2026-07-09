"""Golden-protocol scenarios: the behavior contract of the unified runtime.

Each scenario scripts a fake upstream (``chat/auto/test_fakes.py``) and
captures the exact sequence of upstream REQUEST BODIES produced by:

- the OLD loop that owns that behavior today (``ChatStreamSession``,
  ``AutoChatRunner``, or ``SubAgentRunner``), and
- the NEW ``ConversationEngine`` under the equivalent policy.

The captured sequences are pinned as checked-in JSON fixtures under
``golden/`` and compared as parsed JSON (dict equality — key order is
irrelevant on the wire). ``test_golden_protocol.py`` asserts

    old loop == fixture == new engine

While the old loops exist, the first equality keeps the fixtures honest;
once phases 2–4 delete each old loop, its fixture REMAINS the durable
contract the engine (and the supervisor-driven runs built on it) must keep
matching. This is what pins the "persisted traces must be indistinguishable"
requirement (functional spec §3) — the request bodies are exactly what the
backend persists into traces.

Regenerating fixtures (only when a scenario is deliberately changed):

    uv run python -m app.desktop.studio_server.chat.runtime.golden_scenarios

which re-captures from the OLD loops. Once an old loop is deleted, its
scenario's ``run_old`` is deleted too and the fixture becomes append-only
history — regeneration then re-captures from the engine, which by that point
is the reference implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import httpx
from app.desktop.studio_server.chat.auto.test_fakes import (
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
    """Drive the new engine over the scripted upstream with a minimal io
    wiring (lists instead of the supervisor), mirroring what the supervisor
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


async def _old_interactive_tool_round() -> list[dict[str, Any]]:
    from app.desktop.studio_server.chat.stream_session import ChatStreamSession

    client = FakeUpstreamClient(_interactive_tool_round_responses())
    session = ChatStreamSession(
        upstream_url=UPSTREAM_URL,
        headers={},
        initial_body=dict(_INTERACTIVE_INITIAL_BODY),
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        await _consume(session.stream())
    return _bodies(client)


async def _engine_interactive_tool_round() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=interactive_policy(),
        record=ConversationRecord(kind="interactive"),
        client=FakeUpstreamClient(_interactive_tool_round_responses()),
        initial_body=dict(_INTERACTIVE_INITIAL_BODY),
    )


# ── Scenario 2: interactive approval flow ─────────────────────────────────────
#
# Old world: the stream ENDS at tool-calls-pending; the browser POSTs
# /api/chat/execute-tools with the items + decisions, which executes the
# batch and continues on a SECOND ChatStreamSession. New world: the run parks
# on await_decisions and continues in-place. The upstream body sequence must
# be identical across the two shapes.

_APPROVAL_INITIAL_BODY = {"messages": [{"role": "user", "content": "please add"}]}
_APPROVAL_DECISIONS = {"tc1": True}


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
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("Sum is 3"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _old_interactive_approval_flow() -> list[dict[str, Any]]:
    from app.desktop.studio_server.chat.stream_session import (
        ChatStreamSession,
        ToolCallInfo,
        execute_tool_batch,
    )

    # ONE fake client shared by both requests so the captured body sequence
    # spans the whole flow (the fixture is the flow's protocol, not one HTTP
    # request's).
    client = FakeUpstreamClient(_approval_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        session = ChatStreamSession(
            upstream_url=UPSTREAM_URL,
            headers={},
            initial_body=dict(_APPROVAL_INITIAL_BODY),
        )
        emitted = await _consume(session.stream())
        # The stream ended at tool-calls-pending. Recover the pending items
        # exactly as the browser would (the event payload).
        pending = None
        for chunk in emitted:
            for line in chunk.decode().split("\n"):
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if payload.get("type") == "tool-calls-pending":
                        pending = payload
        assert pending is not None, "old flow did not surface a pending batch"
        # Mirror routes.post_execute_tools: execute with the POSTed decisions,
        # then continue from the trace with only role:tool messages.
        tool_calls = [ToolCallInfo.model_validate(item) for item in pending["items"]]
        tool_results = await execute_tool_batch(tool_calls, dict(_APPROVAL_DECISIONS))
        continuation_body: dict[str, Any] = {
            "trace_id": "tr-1",
            "messages": [
                {"role": "tool", "tool_call_id": tc_id, "content": output}
                for tc_id, output in tool_results.items()
            ],
        }
        continuation = ChatStreamSession(
            upstream_url=UPSTREAM_URL,
            headers={},
            initial_body=continuation_body,
        )
        await _consume(continuation.stream())
    return _bodies(client)


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


async def _old_interactive_report_injection() -> list[dict[str, Any]]:
    from app.desktop.studio_server.chat import orchestration
    from app.desktop.studio_server.chat.stream_session import ChatStreamSession

    client = FakeUpstreamClient(_report_injection_responses())
    session = ChatStreamSession(
        upstream_url=UPSTREAM_URL,
        headers={},
        initial_body=dict(_REPORT_INITIAL_BODY),
    )
    # Drain-once semantics, like the real supervisor queue. Patching the drain
    # (rather than staging real supervisor state) keeps the fixture free of
    # random session ids; the queue mechanics have their own unit tests — this
    # scenario pins how a drained report rides the continuation body. (Phase 2
    # moved the drain from the deleted sub-agent registry to
    # chat/orchestration.pending_reports_for_trace; the old interactive loop
    # calls it as a module attribute precisely so this patch lands.)
    queue = [REPORT_FRAME]

    def fake_pending_reports_for_trace(trace_id: str) -> list[str]:
        taken = list(queue)
        queue.clear()
        return taken

    with (
        patch.object(httpx, "AsyncClient", return_value=client),
        patch.object(
            orchestration,
            "pending_reports_for_trace",
            side_effect=fake_pending_reports_for_trace,
        ),
    ):
        await _consume(session.stream())
    return _bodies(client)


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
# hand-built on the engine side: constructing it is the enable endpoint's job
# (ported in phase 3). The equality assertion against the old runner's
# _build_seed_body output is exactly what keeps the hand-built shape honest.

_AUTO_SEED_BODY = {
    "trace_id": "tr-0",
    "messages": [
        {
            "role": "tool",
            "tool_call_id": "enable-1",
            "content": json.dumps({"status": "enabled"}, ensure_ascii=False),
        }
    ],
    "auto_mode": True,
}
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


def _old_auto_runner(client: FakeUpstreamClient, inbound_texts: list[str]):
    """An AutoChatRunner wired like AutoChatRun wires it (drain-once queue),
    without the registry (matching auto/test_runner.py's harness)."""
    from app.desktop.studio_server.chat.auto.models import (
        AutoChatSeed,
        InboundMessage as OldInboundMessage,
    )
    from app.desktop.studio_server.chat.auto.runner import AutoChatRunner

    queue = [OldInboundMessage(content=t) for t in inbound_texts]

    def drain_inbound():
        taken = list(queue)
        queue.clear()
        return taken

    return AutoChatRunner(
        run_id="ar_golden",
        seed=AutoChatSeed(trace_id="tr-0", enable_tool_call_id="enable-1"),
        upstream_url=UPSTREAM_URL,
        headers={},
        emit=lambda payload: None,
        drain_inbound=drain_inbound,
    )


async def _old_auto_seed_and_tool_round() -> list[dict[str, Any]]:
    client = FakeUpstreamClient(_auto_tool_round_responses())
    runner = _old_auto_runner(client, [_SIDE_NOTE_TEXT])
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()
    return _bodies(client)


async def _engine_auto_seed_and_tool_round() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_auto_tool_round_responses()),
        initial_body=dict(_AUTO_SEED_BODY),
        inbox=[InboundMessage(content=_SIDE_NOTE_TEXT)],
    )


# ── Scenario 5: auto disable_auto_mode resolve (terminal continuation) ───────


def _auto_disable_responses() -> list[FakeUpstreamResponse]:
    return [
        FakeUpstreamResponse(
            chunks=[
                text_delta("turning off auto mode"),
                tool_input_available("tc_disable", "disable_auto_mode", {}),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse(
            chunks=[text_delta("okay, auto mode off"), trace("tr-2"), finish("stop")]
        ),
    ]


async def _old_auto_disable_resolve() -> list[dict[str, Any]]:
    client = FakeUpstreamClient(_auto_disable_responses())
    runner = _old_auto_runner(client, [])
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()
    return _bodies(client)


async def _engine_auto_disable_resolve() -> list[dict[str, Any]]:
    return await _run_engine(
        policy=auto_policy(),
        record=ConversationRecord(kind="auto", auto_flag=True),
        client=FakeUpstreamClient(_auto_disable_responses()),
        initial_body=dict(_AUTO_SEED_BODY),
    )


# ── Scenario 6: sub-agent seed body + steer message ──────────────────────────

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


# NOTE (phase 2): the OLD side of this scenario is gone — SubAgentRunner was
# deleted when sub-agents moved onto the unified runtime. Its checked-in
# fixture (captured from the old runner while it existed) REMAINS the durable
# protocol contract: test_engine_matches_fixture still asserts the engine's
# byte-equivalence against it, exactly as the fixture-lifecycle plan in the
# module docstring prescribes. run_old=None makes test_old_loop_matches_fixture
# skip for this scenario.


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


# ── Scenario 7: a <subagent_report> frame on the auto inbox rides UNWRAPPED ──
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


async def _old_auto_report_inbox_unwrapped() -> list[dict[str, Any]]:
    client = FakeUpstreamClient(_auto_report_inbox_responses())
    runner = _old_auto_runner(client, [REPORT_FRAME])
    with patch.object(httpx, "AsyncClient", return_value=client):
        await runner.run()
    return _bodies(client)


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
    # Captures the upstream request bodies from the OLD loop. Deleted along
    # with its loop in phases 2–4 (None once the loop is gone — the sub-agent
    # loop went in phase 2); the JSON fixture then remains the contract.
    run_old: Callable[[], Awaitable[list[dict[str, Any]]]] | None
    # Captures the same from the new ConversationEngine.
    run_engine: Callable[[], Awaitable[list[dict[str, Any]]]]


SCENARIOS: tuple[GoldenScenario, ...] = (
    GoldenScenario(
        "interactive_tool_round",
        _old_interactive_tool_round,
        _engine_interactive_tool_round,
    ),
    GoldenScenario(
        "interactive_approval_flow",
        _old_interactive_approval_flow,
        _engine_interactive_approval_flow,
    ),
    GoldenScenario(
        "interactive_report_injection",
        _old_interactive_report_injection,
        _engine_interactive_report_injection,
    ),
    GoldenScenario(
        "auto_seed_and_tool_round",
        _old_auto_seed_and_tool_round,
        _engine_auto_seed_and_tool_round,
    ),
    GoldenScenario(
        "auto_disable_resolve",
        _old_auto_disable_resolve,
        _engine_auto_disable_resolve,
    ),
    GoldenScenario(
        "subagent_seed_and_steer",
        None,  # SubAgentRunner deleted in phase 2; the fixture is the contract.
        _engine_subagent_seed_and_steer,
    ),
    GoldenScenario(
        "auto_report_inbox_unwrapped",
        _old_auto_report_inbox_unwrapped,
        _engine_auto_report_inbox_unwrapped,
    ),
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
        # While an old loop exists it is the reference; once deleted the
        # engine IS the reference implementation (module docstring), so
        # deliberate scenario changes re-capture from it.
        capture = scenario.run_old or scenario.run_engine
        bodies = await capture()
        _write_fixture(scenario.name, bodies)
        print(f"wrote {fixture_path(scenario.name)} ({len(bodies)} bodies)")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_regenerate_all())
