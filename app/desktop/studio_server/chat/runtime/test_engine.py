"""ConversationEngine unit tests against the shared fake upstream.

Modeled on ``auto/test_runner.py`` + ``subagents/test_runner.py`` — the same
scripted rounds, asserted per policy kind, so the behavior contracts of the
three old loops are all exercised on the ONE engine. Upstream body sequences
are additionally pinned by test_golden_protocol.py; these tests cover the
lifecycle outcomes, emitted event streams, and the paths the golden scenarios
don't script (denials, stops, errors, budgets)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.desktop.studio_server.chat.test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)
from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
from app.desktop.studio_server.chat.stream_session import MAX_CHAT_RETRIES

from .engine import ConversationEngine, EngineIO
from .interceptors import (
    AUTO_MODE_NOOP_RESULT,
    DEPTH_LIMIT_RESULT,
    DISABLE_AUTO_MODE_STALE_RESULT,
)
from .models import (
    INTERACTIVE_MAX_ROUNDS_MESSAGE,
    SUBAGENT_MAX_ROUNDS_MESSAGE,
    ConversationRecord,
    InboundMessage,
    PendingApprovalBatch,
    RunState,
    SubAgentSeed,
    auto_policy,
    interactive_policy,
    subagent_policy,
)

URL = "https://example.test/v1/chat"
APPROVAL_META = {"requires_approval": True}
SERVER_META = {"executor": "server"}


@dataclass
class Harness:
    """Everything a test needs to drive one engine run and inspect it."""

    engine: ConversationEngine
    record: ConversationRecord
    io: EngineIO
    emitted: list[bytes]
    traces: list[str]
    inbox: list[InboundMessage]
    reports: list[str]
    parked_batches: list[PendingApprovalBatch] = field(default_factory=list)
    parked_states: list[RunState] = field(default_factory=list)


def _harness(
    *,
    kind: str = "interactive",
    inbox: list[str] | None = None,
    reports: list[str] | None = None,
    decisions: dict[str, bool] | None = None,
    stop_requested: bool = False,
    record: ConversationRecord | None = None,
) -> Harness:
    emitted: list[bytes] = []
    traces: list[str] = []
    inbox_queue = [InboundMessage(content=t) for t in (inbox or [])]
    report_queue = list(reports or [])
    rec = record or ConversationRecord(
        kind=kind,
        auto_flag=(kind == "auto"),  # type: ignore[arg-type]
    )
    h = Harness(
        engine=ConversationEngine(URL, {}),
        record=rec,
        io=None,  # type: ignore[arg-type]
        emitted=emitted,
        traces=traces,
        inbox=inbox_queue,
        reports=report_queue,
    )

    async def on_trace(tid: str) -> None:
        traces.append(tid)

    def drain_inbox() -> list[InboundMessage]:
        taken = list(h.inbox)
        h.inbox.clear()
        return taken

    def drain_reports() -> list[str]:
        taken = list(h.reports)
        h.reports.clear()
        return taken

    async def await_decisions(batch: PendingApprovalBatch) -> dict[str, bool]:
        h.parked_batches.append(batch)
        # Capture the state the engine parked in (AWAITING_APPROVAL) so tests
        # can assert the park actually happened as a state transition.
        h.parked_states.append(h.record.state)
        assert decisions is not None, "test parked without providing decisions"
        return dict(decisions)

    h.io = EngineIO(
        emit=emitted.append,
        on_trace=on_trace,
        drain_inbox=drain_inbox,
        drain_reports=drain_reports,
        await_decisions=await_decisions,
        stop_requested=lambda: stop_requested,
    )
    return h


def _events(emitted: list[bytes]) -> list[dict]:
    events: list[dict] = []
    for chunk in emitted:
        for line in chunk.decode().split("\n"):
            if line.startswith("data: "):
                payload = line[6:].strip()
                if payload and payload != "[DONE]":
                    events.append(json.loads(payload))
    return events


def _outputs(emitted: list[bytes]) -> dict[str, str]:
    return {
        e["toolCallId"]: e["output"]
        for e in _events(emitted)
        if e.get("type") == "tool-output-available"
    }


def _decoded(emitted: list[bytes]) -> str:
    return b"".join(emitted).decode()


async def _run(
    h: Harness, client: FakeUpstreamClient, policy, initial_body: dict | None
) -> None:
    with patch.object(httpx, "AsyncClient", return_value=client):
        await h.engine.run(h.record, policy, h.io, initial_body)


_USER_TURN = {"messages": [{"role": "user", "content": "go"}]}
_AUTO_SEED = {
    "trace_id": "tr-0",
    "messages": [{"role": "tool", "tool_call_id": "enable-1", "content": "{}"}],
    "auto_mode": True,
}
_CHILD_SEED = SubAgentSeed(agent_type="general", name="helper", prompt="Do the thing.")


# ── Natural ends per policy ───────────────────────────────────────────────────


async def test_interactive_text_only_turn_settles_idle():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("tr-1"), finish("stop")])]
    )
    h = _harness()
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    assert h.record.state == RunState.IDLE
    assert h.record.idle_reason == "asked_user"
    assert h.record.current_leaf_trace_id == "tr-1"
    assert h.record.seen_trace_ids == ["tr-1"]
    assert h.traces == ["tr-1"]
    # Phase 5: a FRESH record's first persisted snapshot is the session's
    # durable root (the backend stamps session_meta.root_id = snapshot_id on
    # the first persist — stream_orchestration.save_chat_snapshot), so the
    # engine records it for the browser's restart-recovery key.
    assert h.record.root_id == "tr-1"
    assert "hi" in _decoded(h.emitted)


async def test_root_and_leaf_stamped_before_the_trace_byte_is_emitted():
    # Phase-5 CR LOW 3: the browser's one-shot "learn the root id" item GET is
    # triggered BY the kiln_chat_trace byte itself, so the record must already
    # carry root_id/current_leaf when that byte reaches any observer — the
    # engine stamps them pre-emit (the parser sets round_state.trace_id before
    # the payload is yielded), not only at the round boundary.
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("tr-1"), finish("stop")])]
    )
    h = _harness()
    stamped_at_emit: list[tuple[str | None, str | None]] = []
    plain_emit = h.io.emit

    def emit(payload: bytes) -> None:
        if b"kiln_chat_trace" in payload:
            stamped_at_emit.append((h.record.root_id, h.record.current_leaf_trace_id))
        plain_emit(payload)

    h.io.emit = emit
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    assert stamped_at_emit == [("tr-1", "tr-1")]


async def test_adopted_record_never_stamps_root_from_a_trace():
    # A record adopted mid-conversation (history open) joined the chain at an
    # arbitrary leaf — its seen_trace_ids are seeded at adopt, so the engine
    # must NOT claim a later leaf as the root (only the conversation's FIRST
    # persist is the root; adoption learns the true root from the key
    # resolution or the rehydration fetch instead).
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("tr-9"), finish("stop")])]
    )
    record = ConversationRecord(
        kind="interactive",
        current_leaf_trace_id="tr-8",
        seen_trace_ids=["tr-8"],
    )
    h = _harness(record=record)
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    assert h.record.current_leaf_trace_id == "tr-9"
    assert h.record.root_id is None


async def test_session_id_resume_body_switches_to_trace_id_after_first_trace():
    # Phase 6: a resume-by-key first POST carries session_id (the backend
    # resolves the current leaf). Once the round persists a trace, the
    # continuation rebuild must DROP session_id and continue by trace_id —
    # the backend 400s the two keys together, so leaving it riding would
    # break every multi-round resumed turn.
    round1 = [
        text_delta("adding"),
        tool_input_available("tc1", "add", {"a": 2, "b": 3}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("sum is 5"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    record = ConversationRecord(
        kind="interactive",
        resume_session_key="1111111119_root",
        seen_trace_ids=["1111111119_root"],
    )
    h = _harness(record=record, decisions={"tc1": True})
    body = {
        "session_id": "1111111119_root",
        "messages": [{"role": "user", "content": "go"}],
    }
    await _run(h, client, interactive_policy(), body)
    first, second = client.bodies
    assert first["session_id"] == "1111111119_root"
    assert second["trace_id"] == "tr-1"
    assert "session_id" not in second
    # An adopted record never claims a continuation leaf as its durable root
    # (the seeded seen_trace_ids chain is the mid-conversation marker).
    assert h.record.root_id is None
    assert h.record.current_leaf_trace_id == "tr-2"


async def test_auto_text_only_round_settles_idle_flag_on():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("done?"), trace("tr-1"), finish("stop")])]
    )
    h = _harness(kind="auto")
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.record.state == RunState.IDLE
    assert h.record.idle_reason == "asked_user"
    # The flag survives a settled burst (old Revision R1 semantics).
    assert h.record.auto_flag is True


async def test_one_shot_text_turn_completes_with_report():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("final report"), trace("tr-1"), finish()])]
    )
    h = _harness(
        kind="subagent",
        record=ConversationRecord(kind="subagent", name="helper", agent_type="general"),
    )
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    assert h.record.state == RunState.COMPLETED
    assert h.record.final_report == "final report"
    assert h.record.rounds_used == 1
    # The kickoff echo is the FIRST event on the stream, with a stable id so a
    # re-attaching client can dedupe it.
    first = _events(h.emitted)[0]
    assert first["type"] == "user-message"
    assert first["id"] == f"kickoff-{h.record.session_id}"
    assert "helper" in first["content"]
    assert "Do the thing." in first["content"]


async def test_server_tool_only_round_settles_done():
    # A finish=tool-calls round with only server-executed tools has nothing to
    # execute locally: empty exec framing, then the run settles (old
    # interactive/auto empty-results path).
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [
                    tool_input_available("s1", "server_tool", {}, SERVER_META),
                    trace("tr-1"),
                    finish_tool_calls(),
                ]
            )
        ]
    )
    h = _harness(kind="auto")
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.record.state == RunState.IDLE
    assert h.record.idle_reason == "done"
    decoded = _decoded(h.emitted)
    assert '"tool_count": 0' in decoded
    assert '"type": "tool-calls-pending"' not in decoded


# ── Approval gate (gated policy) ─────────────────────────────────────────────


async def test_gated_parks_then_decisions_resume_run():
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 2}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("sum is 3"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(decisions={"tc1": True})
    await _run(h, client, interactive_policy(), dict(_USER_TURN))

    # It parked: the pending SSE fired, the batch carried the wire-shape item,
    # and the state during the park was AWAITING_APPROVAL.
    assert h.parked_states == [RunState.AWAITING_APPROVAL]
    (batch,) = h.parked_batches
    assert batch.batch_id.startswith("ab_")
    assert batch.items == [
        {
            "toolCallId": "tc1",
            "toolName": "add",
            "input": {"a": 1, "b": 2},
            "requiresApproval": True,
        }
    ]
    pending = [e for e in _events(h.emitted) if e["type"] == "tool-calls-pending"]
    assert len(pending) == 1
    # Approved → executed → continuation ran → settled idle.
    assert _outputs(h.emitted)["tc1"] == "3"
    assert len(client.bodies) == 2
    assert h.record.state == RunState.IDLE


async def test_gated_denied_tool_resolves_denied_output():
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 2}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("ok, skipping"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(decisions={"tc1": False})
    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        await _run(h, client, interactive_policy(), dict(_USER_TURN))
    # Denied → never executed; the DENIED result is fed back on the
    # continuation so the trace has no dangling call (approval UX contract).
    execute_tool_mock.assert_not_called()
    assert _outputs(h.emitted)["tc1"] == DENIED_TOOL_OUTPUT
    tool_msgs = [m for m in client.bodies[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs == [
        {"role": "tool", "tool_call_id": "tc1", "content": DENIED_TOOL_OUTPUT}
    ]


async def test_auto_policy_never_parks_on_approval_metadata():
    # The same approval-flagged tool runs unattended under the auto policy —
    # no pending event, no park (old AutoChatRunner auto-approve).
    round1 = [
        tool_input_available("tc1", "multiply", {"a": 6, "b": 7}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("42"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(kind="auto")
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.parked_batches == []
    assert '"type": "tool-calls-pending"' not in _decoded(h.emitted)
    assert _outputs(h.emitted)["tc1"] == "42"


async def test_auto_enable_noop_rides_continuation_with_old_framing_counts():
    # CR m1: a redundant enable_auto_mode during an auto burst is a plain
    # resolve — never executed, resolved as "already enabled", fed back on the
    # continuation, and the exec framing counts match the old runner exactly
    # (start = the round's client batch size incl. the intercepted call,
    # end = number of results).
    from .interceptors import ENABLE_AUTO_MODE_RESULT

    round1 = [
        text_delta("enabling and computing"),
        tool_input_available("tc_enable", "enable_auto_mode", {}),
        tool_input_available("tc_add", "add", {"a": 2, "b": 3}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("carrying on"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )

    async def _fake_execute_tool(name: str, args: dict) -> str:
        return str(args["a"] + args["b"])

    h = _harness(kind="auto")
    # Mocked (as AsyncMock — execute_tool is async) so the test can PROVE the
    # intercepted call never reached tool execution, while the sibling still
    # produces a real-looking result for the count/continuation assertions.
    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool",
        side_effect=_fake_execute_tool,
    ) as execute_tool_mock:
        await _run(h, client, auto_policy(), dict(_AUTO_SEED))

    # The burst continued (not disabled, not errored) and settled idle.
    assert h.record.state == RunState.IDLE
    # enable_auto_mode was never executed as a tool ("Unknown tool name"
    # would have been the old failure mode); only the sibling ran.
    executed_names = [call.args[0] for call in execute_tool_mock.call_args_list]
    assert executed_names == ["add"]
    # Both calls resolved on the stream: the sibling's real result and the
    # intercepted no-op.
    outputs = _outputs(h.emitted)
    assert outputs["tc_add"] == "5"
    assert outputs["tc_enable"] == ENABLE_AUTO_MODE_RESULT
    # Old exec-framing counts: start counts the whole client batch (2, the
    # intercepted call included), end counts the results (2).
    events = _events(h.emitted)
    start = next(e for e in events if e["type"] == "kiln-tool-execution-start")
    end = next(e for e in events if e["type"] == "kiln-tool-execution-end")
    assert start["tool_count"] == 2
    assert end["tool_count"] == 2
    # The continuation answers BOTH tool_call_ids (clean trace, no dangling
    # call), the intercepted one with ENABLE_AUTO_MODE_RESULT.
    tool_msgs = {
        m["tool_call_id"]: m["content"]
        for m in client.bodies[1]["messages"]
        if m.get("role") == "tool"
    }
    assert tool_msgs == {"tc_add": "5", "tc_enable": ENABLE_AUTO_MODE_RESULT}


_SPAWN_INPUT = {"agent_type": "general", "name": "helper", "prompt": "Dig in."}


async def test_interactive_spawn_without_auto_emits_consent_and_ends_turn():
    # FR2: an interactive spawn_subagent with auto mode off never executes
    # and never parks — the turn ends on the spawn-triggered auto-mode
    # consent control event; accept/decline resolves out-of-band.
    round1 = [
        text_delta("spawning a helper"),
        tool_input_available("tc_spawn", "spawn_subagent", dict(_SPAWN_INPUT)),
        tool_input_available("tc_sib", "add", {"a": 1, "b": 2}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness()
    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        await _run(h, client, interactive_policy(), dict(_USER_TURN))
    execute_tool_mock.assert_not_called()
    consent = [
        e for e in _events(h.emitted) if e["type"] == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["trigger"] == "spawn_subagent"
    assert consent[0]["gating_tool_call_id"] == "tc_spawn"
    assert consent[0]["spawn"] == _SPAWN_INPUT
    assert [s["toolCallId"] for s in consent[0]["sibling_tool_calls"]] == ["tc_sib"]
    # No park, no execution, no continuation — resolution is out-of-band.
    assert h.parked_batches == []
    assert '"type": "tool-calls-pending"' not in _decoded(h.emitted)
    assert len(client.bodies) == 1
    assert h.record.state == RunState.IDLE


async def test_interactive_spawn_with_auto_flag_on_proceeds():
    # FR2: a set flag IS the consent (armed record / racing user enable) —
    # the spawn passes the gate and reaches execution. The harness wires no
    # orchestration ctx, so it resolves to the structured "unavailable"
    # error, which is enough to prove it went to execution rather than the
    # consent flow.
    round1 = [
        tool_input_available("tc_spawn", "spawn_subagent", dict(_SPAWN_INPUT)),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("ok"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    record = ConversationRecord(kind="interactive", auto_flag=True)
    h = _harness(record=record)
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    assert '"type": "auto-mode-consent-required"' not in _decoded(h.emitted)
    assert "unavailable" in _outputs(h.emitted)["tc_spawn"]
    assert len(client.bodies) == 2


async def test_enable_consent_outranks_spawn_gate_in_combined_batch():
    # Chain priority: enable+spawn in one round surfaces the ENABLE consent
    # (the spawn rides as a sibling, resolved by the same accept/decline).
    round1 = [
        tool_input_available("tc_enable", "enable_auto_mode", {"reason": "big"}),
        tool_input_available("tc_spawn", "spawn_subagent", dict(_SPAWN_INPUT)),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness()
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    consent = [
        e for e in _events(h.emitted) if e["type"] == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["trigger"] == "enable_auto_mode"
    assert consent[0]["gating_tool_call_id"] == "tc_enable"
    assert [s["toolCallId"] for s in consent[0]["sibling_tool_calls"]] == ["tc_spawn"]
    assert len(client.bodies) == 1
    assert h.record.state == RunState.IDLE


# ── Interceptions ─────────────────────────────────────────────────────────────


async def test_enable_auto_mode_interactive_emits_consent_and_ends_turn():
    round1 = [
        text_delta("want auto mode"),
        tool_input_available("tc_enable", "enable_auto_mode", {"reason": "big task"}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness()
    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        await _run(h, client, interactive_policy(), dict(_USER_TURN))
    # Never executed as a tool; the turn ended on the consent control event.
    execute_tool_mock.assert_not_called()
    consent = [
        e for e in _events(h.emitted) if e["type"] == "auto-mode-consent-required"
    ]
    assert len(consent) == 1
    assert consent[0]["enable_tool_call_id"] == "tc_enable"
    assert consent[0]["reason"] == "big task"
    assert len(client.bodies) == 1  # no continuation — resolution is out-of-band
    assert h.record.state == RunState.IDLE


async def test_stale_disable_mid_auto_burst_refuses_and_continues():
    # FR1: the model has no auto-mode off-switch. A stale disable_auto_mode
    # call mid-burst resolves as the refusal — no flag clear, no terminal
    # round — and the burst CONTINUES through a normal continuation.
    round1 = [
        text_delta("turning off"),
        tool_input_available("tc_disable", "disable_auto_mode", {}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("understood, continuing"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(kind="auto")
    with patch(
        "app.desktop.studio_server.chat.stream_session.execute_tool"
    ) as execute_tool_mock:
        await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    execute_tool_mock.assert_not_called()
    # The flag survives; the burst ran the continuation round and settled
    # idle with the NORMAL text-turn reason, not the old "user_disabled".
    assert h.record.auto_flag is True
    assert h.record.idle_reason == "asked_user"
    assert h.record.state == RunState.IDLE
    assert _outputs(h.emitted)["tc_disable"] == DISABLE_AUTO_MODE_STALE_RESULT
    # The refusal rode the continuation (no dangling tool call upstream).
    tool_rows = {
        m["tool_call_id"]: m["content"]
        for m in client.bodies[1]["messages"]
        if m.get("role") == "tool"
    }
    assert tool_rows == {"tc_disable": DISABLE_AUTO_MODE_STALE_RESULT}
    assert len(client.bodies) == 2
    assert h.record.current_leaf_trace_id == "tr-2"
    assert h.traces == ["tr-1", "tr-2"]


async def test_stale_disable_interactive_refuses_and_sibling_parks_normally():
    # FR1: the stale refusal is a PLAIN resolve, not a round takeover — an
    # approval-requiring sibling in the same batch goes through the normal
    # approval park instead of the old immediate-resolve denial.
    round1 = [
        tool_input_available("tc_disable", "disable_auto_mode", {}),
        tool_input_available("tc_sib", "add", {"a": 1, "b": 2}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("continuing"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(decisions={"tc_sib": True})
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    # The sibling parked for a normal decision and executed on approval.
    assert len(h.parked_batches) == 1
    outputs = _outputs(h.emitted)
    assert outputs["tc_disable"] == DISABLE_AUTO_MODE_STALE_RESULT
    assert outputs["tc_sib"] == "3"
    assert len(client.bodies) == 2
    assert h.record.state == RunState.IDLE


async def test_stale_disable_never_clears_a_set_flag():
    # An interactive record whose flag is on (a mid-flip race) keeps it on
    # through a stale disable call — the whole clear_auto_flag/cascade
    # mechanism is gone; only user-initiated paths clear the flag.
    round1 = [
        tool_input_available("tc_disable", "disable_auto_mode", {}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("ok"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    record = ConversationRecord(kind="interactive", auto_flag=True)
    h = _harness(record=record)
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    assert record.auto_flag is True
    assert h.record.state == RunState.IDLE


async def test_child_intercepts_orchestration_and_auto_signals():
    round1 = [
        tool_input_available("tc_spawn", "spawn_subagent", {}),
        tool_input_available("tc_auto", "enable_auto_mode", {}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("report"), trace("tr-2"), finish()]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(kind="subagent")
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    # Both intercepted results ride the continuation so every tool_call_id is
    # answered (clean trace).
    tool_msgs = {
        m["tool_call_id"]: m["content"]
        for m in client.bodies[1]["messages"]
        if m.get("role") == "tool"
    }
    assert tool_msgs["tc_spawn"] == DEPTH_LIMIT_RESULT
    assert tool_msgs["tc_auto"] == AUTO_MODE_NOOP_RESULT
    assert h.record.state == RunState.COMPLETED


# ── Graceful stop ─────────────────────────────────────────────────────────────


async def test_auto_graceful_stop_surfaces_pending_and_clears_flag():
    round1 = [
        text_delta("on it"),
        tool_input_available("tc1", "add", {"a": 1, "b": 2}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness(kind="auto", stop_requested=True)
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    decoded = _decoded(h.emitted)
    # The round finished streaming (no cut-off), the tool calls surfaced for
    # normal approval instead of executing, and no continuation was sent.
    assert "on it" in decoded
    assert '"type": "tool-calls-pending"' in decoded
    assert '"type": "kiln-tool-execution-start"' not in decoded
    assert len(client.bodies) == 1
    assert h.record.state == RunState.IDLE
    assert h.record.auto_flag is False
    assert h.record.idle_reason == "user_stopped"


async def test_one_shot_stop_at_tool_boundary_does_not_surface_pending():
    # Sub-agents just end on stop — their calls die with them (the policy's
    # graceful_stop_surfaces_pending is False).
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 2}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness(kind="subagent", stop_requested=True)
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    assert h.record.state == RunState.STOPPED
    decoded = _decoded(h.emitted)
    assert '"type": "tool-calls-pending"' not in decoded
    # Old SubAgentRunner stops AFTER executing + building the continuation
    # (the results are conceptually fed back; no new round starts).
    assert len(client.bodies) == 1


async def test_graceful_stop_on_plain_text_drops_queued_inbox():
    # A stop never starts a new round: queued messages are dropped, not
    # continued with (old auto stop-on-plain-text).
    round1 = [text_delta("summary."), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness(kind="auto", inbox=["keep going"], stop_requested=True)
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.record.state == RunState.IDLE
    assert h.record.auto_flag is False
    assert len(client.bodies) == 1


# ── Drains ────────────────────────────────────────────────────────────────────


async def test_drain_before_idle_continues_with_queued_message():
    round1 = [text_delta("anything else?"), trace("tr-1"), finish("stop")]
    round2 = [text_delta("done now"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(kind="auto", inbox=["keep going"])
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    # It did NOT settle after round 1 — the queued message became a fresh
    # (side-note framed) turn.
    assert len(client.bodies) == 2
    (msg,) = client.bodies[1]["messages"]
    assert msg["role"] == "user"
    assert "keep going" in msg["content"]
    assert "<system-reminder>" in msg["content"]
    # The engine does NOT echo drained messages (the supervisor echoes at
    # enqueue — echo-once).
    assert '"type": "user-message"' not in _decoded(h.emitted)


async def test_interactive_drain_rides_unframed():
    # The interactive policy has no framing: a queued message continues the
    # turn as plain user input (phase-4 send-while-running behavior).
    round1 = [text_delta("thinking"), trace("tr-1"), finish("stop")]
    round2 = [text_delta("answered"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(inbox=["one more thing"])
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    (msg,) = client.bodies[1]["messages"]
    assert msg == {"role": "user", "content": "one more thing"}


def test_frame_inbox_message_matrix():
    # Direct pin of the per-policy framing rules (ported with the old
    # runners' framing helpers when chat/subagents/ was deleted in phase 2):
    # - side_note (auto): framed, EXCEPT <subagent_report> frames — the frame
    #   IS the message, and wrapping it would break the client's report-panel
    #   detection (old auto _side_note_message).
    # - steer (sub-agent): framed unconditionally — children never receive
    #   report frames, so the old _steer_message had no skip; preserved as-is.
    # - none (interactive): raw.
    from .engine import SIDE_NOTE_REMINDER, STEER_REMINDER, _frame_inbox_message

    report = '<subagent_report id="x" agent_type="g" status="completed" title="t">\nhi\n</subagent_report>'
    aside = InboundMessage(content="also do X")
    report_msg = InboundMessage(content=report)

    auto = auto_policy()
    assert _frame_inbox_message(aside, auto)["content"] == (
        f"{SIDE_NOTE_REMINDER}\n\nalso do X"
    )
    assert _frame_inbox_message(report_msg, auto)["content"] == report

    child = subagent_policy(_CHILD_SEED)
    assert _frame_inbox_message(aside, child)["content"] == (
        f"{STEER_REMINDER}\n\nalso do X"
    )
    assert _frame_inbox_message(report_msg, child)["content"] == (
        f"{STEER_REMINDER}\n\n{report}"
    )

    assert _frame_inbox_message(aside, interactive_policy()) == {
        "role": "user",
        "content": "also do X",
    }


async def test_steer_message_drained_before_finish_continues_run():
    # Port of the old subagents/test_runner.py drain-before-finish contract: a
    # steer sent the instant the child would COMPLETE must not be dropped —
    # the run continues with the framed steer as a fresh turn and the LATER
    # text becomes the report.
    inbound = ["also check model B"]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [text_delta("thought I was done"), trace("tr-1"), finish()]
            ),
            FakeUpstreamResponse([text_delta("real report"), trace("tr-2"), finish()]),
        ]
    )
    h = _harness(kind="subagent", inbox=inbound)
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    steer_body = client.bodies[1]
    contents = [m.get("content", "") for m in steer_body["messages"]]
    assert any("also check model B" in c for c in contents)
    assert any("system-reminder" in c for c in contents)
    assert h.record.state == RunState.COMPLETED
    assert h.record.final_report == "real report"


async def test_report_drain_appends_and_echoes():
    report = '<subagent_report id="x" agent_type="g" status="completed" title="t">\nhi\n</subagent_report>'
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 1}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("noted"), trace("tr-2"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(reports=[report])
    await _run(h, client, interactive_policy(), dict(_USER_TURN))
    # Report rides the continuation AND is echoed to observers (id-less echo,
    # like the old interactive report injection).
    user_msgs = [m for m in client.bodies[1]["messages"] if m.get("role") == "user"]
    assert user_msgs == [{"role": "user", "content": report}]
    echoes = [e for e in _events(h.emitted) if e.get("type") == "user-message"]
    assert echoes == [{"type": "user-message", "content": report}]


# ── Errors and budgets ────────────────────────────────────────────────────────


async def test_upstream_400_settles_error_idle_for_auto():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(status_code=400, body=b'{"message": "boom"}')]
    )
    h = _harness(kind="auto")
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.record.state == RunState.IDLE
    assert h.record.idle_reason == "error"
    assert h.record.auto_flag is True  # flag survives a burst error
    assert "boom" in _decoded(h.emitted)
    assert len(client.bodies) == 1  # 4xx is non-retryable


async def test_upstream_400_fails_one_shot():
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(status_code=400, body=b'{"message": "bad"}')]
    )
    h = _harness(kind="subagent")
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    assert h.record.state == RunState.FAILED


async def test_retryable_error_recovers_and_retry_event_carries_session_id():
    round_ok = [text_delta("done"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(status_code=503, body=b'{"message": "busy"}'),
            FakeUpstreamResponse(round_ok),
        ]
    )
    h = _harness(kind="auto")
    with patch(
        "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
        new=AsyncMock(),
    ):
        await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    retries = [e for e in _events(h.emitted) if e["type"] == "kiln-chat-retry"]
    assert [e["attempt"] for e in retries] == [1]
    assert all(e["max_attempts"] == MAX_CHAT_RETRIES for e in retries)
    # Unattended streams carry the run handle on retry events (now the
    # session id); the transient error is never surfaced.
    assert retries[0]["run_id"] == h.record.session_id
    assert "busy" not in _decoded(h.emitted)
    assert h.record.state == RunState.IDLE


async def test_interactive_retry_event_omits_run_id():
    # Preserved protocol detail: the old interactive stream's retry events had
    # no run_id field.
    round_ok = [text_delta("hi"), trace("tr-1"), finish("stop")]
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(status_code=503, body=b'{"message": "busy"}'),
            FakeUpstreamResponse(round_ok),
        ]
    )
    h = _harness()
    with patch(
        "app.desktop.studio_server.chat.stream_session.asyncio.sleep",
        new=AsyncMock(),
    ):
        await _run(h, client, interactive_policy(), dict(_USER_TURN))
    retries = [e for e in _events(h.emitted) if e["type"] == "kiln-chat-retry"]
    assert len(retries) == 1
    assert "run_id" not in retries[0]


async def test_max_rounds_auto_settles_idle_with_reason():
    from app.desktop.studio_server.chat.constants import MAX_TOOL_ROUNDS

    def looping(i: int) -> FakeUpstreamResponse:
        return FakeUpstreamResponse(
            [
                tool_input_available(f"tc{i}", "add", {"a": 1, "b": 1}),
                trace(f"tr-{i}"),
                finish_tool_calls(),
            ]
        )

    client = FakeUpstreamClient([looping(i) for i in range(MAX_TOOL_ROUNDS)])
    h = _harness(kind="auto")
    await _run(h, client, auto_policy(), dict(_AUTO_SEED))
    assert h.record.state == RunState.IDLE
    assert h.record.idle_reason == "max_rounds"
    assert h.record.auto_flag is True
    assert INTERACTIVE_MAX_ROUNDS_MESSAGE in _decoded(h.emitted)


async def test_max_rounds_one_shot_times_out_with_subagent_message():
    def looping(i: int) -> FakeUpstreamResponse:
        return FakeUpstreamResponse(
            [
                tool_input_available(f"tc{i}", "add", {"a": 1, "b": 1}),
                trace(f"tr-{i}"),
                finish_tool_calls(),
            ]
        )

    client = FakeUpstreamClient([looping(i) for i in range(2)])
    h = _harness(kind="subagent")
    await _run(h, client, subagent_policy(_CHILD_SEED, max_rounds=2), None)
    assert h.record.state == RunState.TIMEOUT
    assert h.record.rounds_used == 2
    assert SUBAGENT_MAX_ROUNDS_MESSAGE in _decoded(h.emitted)


async def test_agent_block_dropped_after_first_trace():
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 1}),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    round2 = [text_delta("report"), trace("tr-2"), finish()]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(round1), FakeUpstreamResponse(round2)]
    )
    h = _harness(kind="subagent")
    await _run(h, client, subagent_policy(_CHILD_SEED), None)
    assert "agent" in client.bodies[0]
    continuation = client.bodies[1]
    # First-POST-only: the backend 400s agent + trace_id together.
    assert "agent" not in continuation
    assert continuation["trace_id"] == "tr-1"
    assert continuation["auto_mode"] is True


async def test_engine_requires_seed_or_body():
    h = _harness()
    with pytest.raises(ValueError, match="initial_body or a policy seed"):
        await h.engine.run(h.record, interactive_policy(), h.io, None)


async def test_gated_policy_requires_await_decisions():
    round1 = [
        tool_input_available("tc1", "add", {"a": 1, "b": 2}, APPROVAL_META),
        trace("tr-1"),
        finish_tool_calls(),
    ]
    client = FakeUpstreamClient([FakeUpstreamResponse(round1)])
    h = _harness()
    h.io.await_decisions = None
    with patch.object(httpx, "AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="await_decisions"):
            await h.engine.run(h.record, interactive_policy(), h.io, dict(_USER_TURN))


# ── Phase 4: resume runs (runless-batch recovery) ─────────────────────────────


def _staged_batch(trace_id: str = "tr-1") -> PendingApprovalBatch:
    """A batch in the shape rehydration builds (or a live park stores): the
    trace-only continuation base + the round's client events."""
    from kiln_ai.adapters.model_adapters.stream_events import (
        ToolInputAvailableEvent,
    )

    from app.desktop.studio_server.chat.stream_session import (
        _pending_item_from_event,
    )

    events = [
        ToolInputAvailableEvent(
            toolCallId="tc_ok",
            toolName="add",
            input={"a": 2, "b": 3},
            kiln_metadata=APPROVAL_META,
        ),
        ToolInputAvailableEvent(
            toolCallId="tc_no",
            toolName="add",
            input={"a": 9, "b": 9},
            kiln_metadata=APPROVAL_META,
        ),
    ]
    return PendingApprovalBatch(
        items=[_pending_item_from_event(e) for e in events],
        body={"trace_id": trace_id, "messages": []},
        assistant_text="",
        tool_input_events=events,
    )


async def test_resume_batch_executes_decisions_and_continues():
    # The recovery entry (architecture §2 / functional spec §5): a decided
    # RUNLESS batch resumes by executing with the decisions and continuing
    # from the batch's stored round context. Denied → DENIED_TOOL_OUTPUT,
    # exactly like the parked path; the continuation body is the old
    # POST /api/chat/execute-tools shape (trace-only base → role:tool rows).
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("resumed"), trace("tr-2"), finish("stop")])]
    )
    h = _harness()
    batch = _staged_batch()
    batch.decisions = {"tc_ok": True, "tc_no": False}
    batch.decided.set()
    with patch.object(httpx, "AsyncClient", return_value=client):
        await h.engine.run(
            h.record, interactive_policy(), h.io, None, resume_batch=batch
        )

    outputs = _outputs(h.emitted)
    assert outputs["tc_ok"] == "5"
    assert outputs["tc_no"] == DENIED_TOOL_OUTPUT
    # Exec framing brackets the batch (start = batch size, end = results).
    types = [e["type"] for e in _events(h.emitted)]
    assert types[0] == "kiln-tool-execution-start"
    assert "kiln-tool-execution-end" in types
    # Continuation: trace-only base → role:tool rows only (the persisted
    # trace is indistinguishable from the old execute-tools flow).
    (body,) = client.bodies
    assert body["trace_id"] == "tr-1"
    assert [m["role"] for m in body["messages"]] == ["tool", "tool"]
    assert {m["tool_call_id"] for m in body["messages"]} == {"tc_ok", "tc_no"}
    # The loop then ran the continuation round to a natural idle end.
    assert h.record.state == RunState.IDLE
    assert h.record.current_leaf_trace_id == "tr-2"
