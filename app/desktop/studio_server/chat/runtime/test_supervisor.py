"""ConversationSupervisor unit tests: lifecycle, settle-once (+ the
cancel-before-first-run backstop), caps, report delivery, GC, decisions.

Modeled on auto/test_registry.py + subagents/test_registry.py — the same
lifecycle contracts, now asserted on the one supervisor."""

from __future__ import annotations

import asyncio
import json
from typing import Callable
from unittest.mock import patch

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

from .engine import ConversationEngine
from .models import RunState, SubAgentSeed
from .supervisor import ConversationCapError, ConversationSupervisor

URL = "https://example.test/v1/chat"


def _seed(name: str = "helper") -> SubAgentSeed:
    return SubAgentSeed(
        agent_type="general",
        name=name,
        prompt="Briefing.",
        parent_trace_id="parent-leaf-1",
    )


def _sup(**kwargs) -> ConversationSupervisor:
    return ConversationSupervisor(**kwargs)


@pytest.fixture
def hang_engine():
    """Patch the engine to hang until cancelled — lifecycle tests drive the
    supervisor, not the network loop (same trick as the old registry tests'
    hang_runner)."""

    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with patch.object(ConversationEngine, "run", _hang):
        yield


async def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async def _poll():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)


def _text_run_responses(final_text: str = "final report") -> list[FakeUpstreamResponse]:
    return [FakeUpstreamResponse([text_delta(final_text), trace("tr-1"), finish()])]


async def _collect_stream(sup, session_id: str, settle: float = 0.05) -> list[bytes]:
    received: list[bytes] = []
    sub = sup.subscribe(session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(settle)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await sub.aclose()
    return received


def _state_events(payloads: list[bytes]) -> list[dict]:
    events = []
    for chunk in payloads:
        for line in chunk.decode().split("\n"):
            if line.startswith("data: "):
                body = line[6:].strip()
                if body:
                    event = json.loads(body)
                    if event.get("type") == "conversation-state":
                        events.append(event)
    return events


# ── Lifecycle ─────────────────────────────────────────────────────────────────


async def test_spawn_subagent_runs_to_completed_and_settles():
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        assert record.state == RunState.RUNNING
        await _wait_for(lambda: record.state.is_terminal)

    assert record.state == RunState.COMPLETED
    assert record.final_report == "final report"
    assert record.rounds_used == 1
    # The trace index picked up the child's leaf for the history join.
    assert sup.session_for_trace("tr-1") == record.session_id
    # A late subscriber gets replay + terminal state marker + EOF.
    received = [payload async for payload in sup.subscribe(record.session_id)]
    states = _state_events(received)
    assert states[-1]["state"] == "completed"
    assert states[-1]["kind"] == "subagent"
    assert states[-1]["report_available"] is True


async def test_settle_publishes_state_transitions_to_live_observer():
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses())
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    received: list[bytes] = []
    sub = sup.subscribe(record.session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(0.02)
    with patch.object(httpx, "AsyncClient", return_value=client):
        sup.start_run(
            record.session_id, {"messages": [{"role": "user", "content": "hi"}]}
        )
        await _wait_for(lambda: record.state == RunState.IDLE)
    await asyncio.sleep(0.02)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await sub.aclose()

    states = [e["state"] for e in _state_events(received)]
    # on-subscribe marker (idle) → run started (running) → settled (idle).
    assert states[0] == "idle"
    assert "running" in states
    assert states[-1] == "idle"


async def test_stop_cancels_hung_run_and_synthesizes_stopped_report(hang_engine):
    sup = _sup()
    record = sup.spawn_subagent(
        _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
    )
    await asyncio.sleep(0.02)  # let the run task start hanging
    await sup.stop(record.session_id)
    assert record.state == RunState.STOPPED
    # The settle path synthesized the status-note report (old _settle).
    assert "STOPPED" in (record.final_report or "")
    # Idempotent: a second stop is a no-op.
    await sup.stop(record.session_id)
    assert record.state == RunState.STOPPED


async def test_cancel_before_first_run_backstop_settles(hang_engine):
    # A task cancelled before it ever ran never enters _supervise, so its
    # finally never fires — stop()'s backstop must settle it (the old
    # SubAgentRegistry.stop backstop, generalized).
    sup = _sup()
    record = sup.create_conversation(
        "subagent",
        upstream_url=URL,
        headers={},
        parent_session_id="cv_parent",
        seed=_seed(),
    )
    sup.start_run(record.session_id)
    # NO awaits between start and stop: the created task has not run yet.
    await sup.stop(record.session_id)
    assert record.state == RunState.STOPPED
    assert "STOPPED" in (record.final_report or "")
    # settled fired exactly once — wait() returns immediately.
    records, timed_out = await sup.wait([record.session_id], timeout_seconds=0.05)
    assert timed_out == []
    assert records[0].state == RunState.STOPPED


async def test_wall_clock_timeout_settles_timeout():
    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    sup = _sup()
    with patch.object(ConversationEngine, "run", _hang):
        record = sup.spawn_subagent(
            _seed(),
            parent_session_id="cv_parent",
            upstream_url=URL,
            headers={},
            wall_clock_seconds=0.05,
        )
        await _wait_for(lambda: record.state.is_terminal)
    assert record.state == RunState.TIMEOUT
    assert "TIMED OUT" in (record.final_report or "")


async def test_engine_exception_fails_one_shot_and_idles_auto():
    async def _boom(self, record, policy, io, initial_body=None) -> None:
        raise RuntimeError("kaboom")

    sup = _sup()
    with patch.object(ConversationEngine, "run", _boom):
        child = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: child.state.is_terminal)
        assert child.state == RunState.FAILED
        assert "FAILED" in (child.final_report or "")

        auto = sup.create_conversation("auto", upstream_url=URL, headers={})
        sup.start_run(
            auto.session_id, {"messages": [{"role": "user", "content": "go"}]}
        )
        await _wait_for(lambda: auto.state == RunState.IDLE)
        # The burst failed but the conversation survives with the flag on
        # (old auto exception path).
        assert auto.idle_reason == "error"
        assert auto.auto_flag is True


async def test_engine_timeout_error_on_non_one_shot_idles_with_error():
    # CR M1: on Python ≥ 3.11 asyncio.TimeoutError IS the builtin
    # TimeoutError, which any library inside the engine can raise. On an
    # interactive/auto run (no wall_clock wait_for) it must classify as the
    # generic IDLE("error") — NOT the terminal TIMEOUT, which would brick a
    # kind whose states cycle forever (send_message → False, subscribe →
    # marker + EOF). Old auto's _supervise had no TimeoutError handler, so
    # IDLE("error") is the preserved behavior.
    async def _timeout(self, record, policy, io, initial_body=None) -> None:
        raise asyncio.TimeoutError("socket read timed out")

    sup = _sup()
    with patch.object(ConversationEngine, "run", _timeout):
        auto = sup.create_conversation("auto", upstream_url=URL, headers={})
        sup.start_run(
            auto.session_id, {"messages": [{"role": "user", "content": "go"}]}
        )
        await _wait_for(lambda: auto.state == RunState.IDLE)
    assert auto.state == RunState.IDLE
    assert not auto.state.is_terminal
    assert auto.idle_reason == "error"
    assert auto.auto_flag is True

    # The conversation is NOT bricked: it still accepts messages (queued —
    # this immediately re-arms a burst, so hang the engine for cleanliness).
    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with patch.object(ConversationEngine, "run", _hang):
        assert sup.send_message(auto.session_id, "try again") is True
        await sup.stop(auto.session_id)


async def test_observer_disconnect_does_not_cancel_run(hang_engine):
    sup = _sup()
    record = sup.spawn_subagent(
        _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
    )
    await asyncio.sleep(0.02)
    sub = sup.subscribe(record.session_id)
    await sub.__anext__()  # the on-subscribe state marker
    await sub.aclose()  # client disconnect
    await asyncio.sleep(0.02)
    assert record.state == RunState.RUNNING  # run unaffected
    await sup.stop(record.session_id)


# ── Caps ──────────────────────────────────────────────────────────────────────


async def test_auto_concurrency_cap():
    sup = _sup(auto_max_concurrent=1)
    sup.create_conversation("auto", upstream_url=URL, headers={})
    with pytest.raises(ConversationCapError, match="Too many concurrent auto runs"):
        sup.create_conversation("auto", upstream_url=URL, headers={})
    # Interactive conversations don't count against the auto cap.
    sup.create_conversation("interactive", upstream_url=URL, headers={})


async def test_subagent_global_cap(hang_engine):
    sup = _sup(subagent_max_concurrent=2, subagent_max_per_parent=5)
    sup.spawn_subagent(_seed("a"), parent_session_id="p1", upstream_url=URL, headers={})
    sup.spawn_subagent(_seed("b"), parent_session_id="p2", upstream_url=URL, headers={})
    with pytest.raises(ConversationCapError, match="Too many concurrent sub-agents"):
        sup.spawn_subagent(
            _seed("c"), parent_session_id="p3", upstream_url=URL, headers={}
        )
    for record in sup.list_records():
        await sup.stop(record.session_id)


async def test_subagent_per_parent_cap_frees_on_terminal(hang_engine):
    sup = _sup(subagent_max_concurrent=10, subagent_max_per_parent=1)
    first = sup.spawn_subagent(
        _seed("a"), parent_session_id="p1", upstream_url=URL, headers={}
    )
    with pytest.raises(ConversationCapError, match="running sub-agents"):
        sup.spawn_subagent(
            _seed("b"), parent_session_id="p1", upstream_url=URL, headers={}
        )
    # A different parent is unaffected.
    other = sup.spawn_subagent(
        _seed("c"), parent_session_id="p2", upstream_url=URL, headers={}
    )
    # A terminal child frees its parent's slot.
    await sup.stop(first.session_id)
    sup.spawn_subagent(_seed("d"), parent_session_id="p1", upstream_url=URL, headers={})
    for record in sup.list_records():
        await sup.stop(record.session_id)
    assert other.state == RunState.STOPPED


# ── Messages ──────────────────────────────────────────────────────────────────


async def test_send_message_while_running_enqueues_and_echoes(hang_engine):
    sup = _sup()
    record = sup.spawn_subagent(
        _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
    )
    await asyncio.sleep(0.02)
    assert sup.send_message(record.session_id, "steer this") is True
    conv = sup._conversations[record.session_id]
    assert [m.content for m in conv.inbox] == ["steer this"]
    # Echoed onto the bus + replay buffer at enqueue time (echo-once).
    buffered = b"".join(conv.bus.buffer).decode()
    assert "steer this" in buffered
    assert '"type": "user-message"' in buffered
    await sup.stop(record.session_id)


async def test_send_message_while_idle_starts_turn_with_preserved_body_shape():
    sup = _sup()
    burst = [
        FakeUpstreamResponse([trace("tr-1"), text_delta("resumed"), finish("stop")])
    ]
    client = FakeUpstreamClient(burst)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    # Simulate a conversation that already has a leaf (idle between bursts).
    record.current_leaf_trace_id = "tr-0"
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.send_message(record.session_id, "resume please") is True
        assert record.state == RunState.RUNNING
        await _wait_for(lambda: record.state == RunState.IDLE)

    # Body shape preserved from the old idle re-arm: current leaf + unframed
    # message + auto_mode riding because the flag is on.
    assert client.bodies == [
        {
            "messages": [{"role": "user", "content": "resume please"}],
            "trace_id": "tr-0",
            "auto_mode": True,
        }
    ]


async def test_send_message_unknown_or_terminal_returns_false():
    sup = _sup()
    assert sup.send_message("cv_nope", "x") is False
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: record.state.is_terminal)
    assert sup.send_message(record.session_id, "too late") is False


# ── Approvals (decide) ────────────────────────────────────────────────────────


async def test_decide_flow_with_conflict_and_not_found():
    sup = _sup()
    responses = [
        FakeUpstreamResponse(
            [
                tool_input_available(
                    "tc1", "add", {"a": 1, "b": 2}, {"requires_approval": True}
                ),
                trace("tr-1"),
                finish_tool_calls(),
            ]
        ),
        FakeUpstreamResponse([text_delta("sum is 3"), trace("tr-2"), finish("stop")]),
    ]
    client = FakeUpstreamClient(responses)
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sid = record.session_id
    assert sup.decide(sid, "ab_whatever", {"tc1": True}) == "not_found"

    with patch.object(httpx, "AsyncClient", return_value=client):
        sup.start_run(sid, {"messages": [{"role": "user", "content": "add"}]})
        await _wait_for(lambda: sup.pending_approval(sid) is not None)
        assert record.state == RunState.AWAITING_APPROVAL
        batch = sup.pending_approval(sid)
        assert batch is not None
        assert sup.decide(sid, "ab_wrong", {"tc1": True}) == "not_found"
        assert sup.decide(sid, batch.batch_id, {"tc1": True}) == "ok"
        # Second decision set loses (two-tabs contract → route maps to 409).
        assert sup.decide(sid, batch.batch_id, {"tc1": False}) == "conflict"
        await _wait_for(lambda: record.state == RunState.IDLE)

    # The approved tool executed and the run continued to completion.
    assert len(client.bodies) == 2
    assert record.state == RunState.IDLE


async def test_pending_batch_cleared_when_run_settles(hang_engine):
    # A parked batch can't outlive its run: stopping the conversation clears
    # it (recovery in phase 4 rebuilds from the trace tail instead).
    sup = _sup()
    record = sup.spawn_subagent(
        _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
    )
    conv = sup._conversations[record.session_id]
    conv.pending_batch = object()  # type: ignore[assignment]
    await sup.stop(record.session_id)
    assert conv.pending_batch is None


# ── Report delivery ───────────────────────────────────────────────────────────


async def test_report_delivered_to_auto_parent_via_inbox_wakes_idle_parent():
    sup = _sup()
    # Response 1: the child's whole run. Response 2: the parent burst that the
    # report injection wakes up.
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse([text_delta("child done"), trace("tr-c1"), finish()]),
            FakeUpstreamResponse(
                [text_delta("thanks"), trace("tr-p1"), finish("stop")]
            ),
        ]
    )
    parent = sup.create_conversation("auto", upstream_url=URL, headers={})
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)
        # The injection woke the idle auto parent into a burst.
        await _wait_for(lambda: len(client.bodies) == 2)
        await _wait_for(lambda: parent.state == RunState.IDLE)

    assert child.report_delivered is True
    # The framed report seeded the parent's burst (unframed idle re-arm body).
    parent_body = client.bodies[1]
    (msg,) = parent_body["messages"]
    assert msg["role"] == "user"
    assert msg["content"].startswith("<subagent_report")
    assert "child done" in msg["content"]
    assert f'id="{child.session_id}"' in msg["content"]
    # Nothing queued for drain — inbox was the one channel.
    assert sup.has_pending_reports(parent.session_id) is False


async def test_report_queued_for_interactive_parent_and_drained_once():
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses("child done"))
    parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)

    # Queued (interactive parents drain at their next continuation), not
    # delivered through the inbox.
    assert sup.has_pending_reports(parent.session_id) is True
    assert child.report_delivered is False
    reports = sup.drain_reports(parent.session_id)
    assert len(reports) == 1
    assert 'status="completed"' in reports[0]
    assert child.report_delivered is True
    # Drained exactly once.
    assert sup.drain_reports(parent.session_id) == []


async def test_report_queues_when_auto_parent_flag_off_before_child_settles():
    # The old auto-parent-gone fallback, native since phase 3 (the phase-2
    # legacy_report_deliverer bridge died with chat/auto/): a child whose auto
    # parent was stopped/disabled before the report landed queues it, so a
    # resumed interactive turn on the same conversation can still pick it up.
    sup = _sup(terminal_ttl_seconds=60.0)
    parent = sup.create_conversation("auto", upstream_url=URL, headers={})
    client = FakeUpstreamClient(_text_run_responses("child done"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        # Flag flips off while the child is still running — the parent can no
        # longer take inbox messages (send_message refuses flag-off auto), but
        # stop() on the child (not the parent) must not run: let it finish.
        parent.auto_flag = False
        await _wait_for(lambda: child.state.is_terminal)

    assert child.report_delivered is False
    assert sup.has_pending_reports(parent.session_id) is True
    # The old-loop drain path can still consume it.
    reports = sup.drain_reports(parent.session_id)
    assert len(reports) == 1 and reports[0].startswith("<subagent_report")


async def test_state_publishes_mirror_to_status_bus():
    # Every conversation-state publish must reach the registry firehose too
    # (the UI's children store may have no per-run stream open) — the old
    # SubAgentRegistry._publish_status dual-publish contract.
    sup = _sup()
    received: list[bytes] = []

    async def _drain():
        async for payload in sup.status_bus.subscribe():
            received.append(payload)

    drain_task = asyncio.create_task(_drain())
    await asyncio.sleep(0)  # let the subscription register
    client = FakeUpstreamClient(_text_run_responses("done"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id="trace:leaf-1",
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)
        await _wait_for(lambda: len(received) >= 2)
    drain_task.cancel()

    events = _state_events(received)
    assert [e["state"] for e in events] == ["running", "completed"]
    assert all(e["session_id"] == child.session_id for e in events)


async def test_stop_parent_cascades_to_children_and_drops_reports(hang_engine):
    sup = _sup()
    parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    a = sup.spawn_subagent(
        _seed("a"), parent_session_id=parent.session_id, upstream_url=URL, headers={}
    )
    b = sup.spawn_subagent(
        _seed("b"), parent_session_id=parent.session_id, upstream_url=URL, headers={}
    )
    other_parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    c = sup.spawn_subagent(
        _seed("c"),
        parent_session_id=other_parent.session_id,
        upstream_url=URL,
        headers={},
    )
    await asyncio.sleep(0.02)
    assert [r.session_id for r in sup.children_of(parent.session_id)] == [
        a.session_id,
        b.session_id,
    ]

    await sup.stop(parent.session_id)
    assert a.state == RunState.STOPPED
    assert b.state == RunState.STOPPED
    assert c.state == RunState.RUNNING  # other parent's child unaffected
    # STOPPED children would have queued their (failure-note) reports for the
    # interactive parent — the cascade drops them (nothing left to consume).
    assert sup.has_pending_reports(parent.session_id) is False
    await sup.stop(c.session_id)


async def test_wait_returns_on_terminal_and_timeout(hang_engine):
    sup = _sup()
    done = sup.spawn_subagent(
        _seed("fast"), parent_session_id="p1", upstream_url=URL, headers={}
    )
    slow = sup.spawn_subagent(
        _seed("slow"), parent_session_id="p2", upstream_url=URL, headers={}
    )
    await sup.stop(done.session_id)

    records, timed_out = await sup.wait(
        [done.session_id, slow.session_id, "cv_unknown"], timeout_seconds=0.05
    )
    assert {r.session_id for r in records} == {done.session_id, slow.session_id}
    assert timed_out == [slow.session_id]
    # Wait never consumes reports — delivery stays on the injection channel.
    assert done.report_delivered is False
    await sup.stop(slow.session_id)


# ── Auto stop semantics ───────────────────────────────────────────────────────


async def test_stop_idle_auto_clears_flag_and_publishes_off_state():
    sup = _sup(terminal_ttl_seconds=60.0)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    received: list[bytes] = []
    sub = sup.subscribe(record.session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(0.02)
    await sup.stop(record.session_id)
    await asyncio.sleep(0.02)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await sub.aclose()

    assert record.auto_flag is False
    assert record.idle_reason == "user_stopped"
    assert record.state == RunState.IDLE
    states = _state_events(received)
    # The live observer saw the flag clear with the preserved off-reason.
    assert states[-1]["auto_flag"] is False
    assert states[-1]["idle_reason"] == "user_stopped"


async def test_stop_running_auto_burst_preserves_stop_reason(hang_engine):
    sup = _sup(terminal_ttl_seconds=60.0)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)
    assert record.state == RunState.RUNNING
    await sup.stop(record.session_id)
    # Hard cancel mid-burst: flag off, reason preserved (old CR Moderate 2 —
    # the pre-marked reason must survive the CancelledError handler).
    assert record.state == RunState.IDLE
    assert record.auto_flag is False
    assert record.idle_reason == "user_stopped"


# ── Auto enable (old POST /api/chat/auto/enable → AutoChatRegistry.start) ─────


async def test_enable_auto_armed_only_creates_idle_record_no_upstream_post():
    # Manual enable with nothing to send upstream: the record is merely ARMED
    # (flag on, IDLE("armed"), NO run task) — the old is_armed_only branch,
    # which existed because an empty upstream POST would be rejected by the
    # backend ("No messages were sent to the server").
    sup = _sup()
    client = FakeUpstreamClient([])  # any POST would blow up the fake
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    assert record.kind == "auto"
    assert record.auto_flag is True
    assert record.state == RunState.IDLE
    assert record.idle_reason == "armed"
    assert client.bodies == []
    # The seed trace was adopted: leaf + chain + index (old AutoRunRecord
    # seeding), so the sessions-list join and resync see the record at once.
    assert record.current_leaf_trace_id == "t1"
    assert sup.session_for_trace("t1") == record.session_id
    assert sup.auto_record_for_trace("t1") is record


async def test_enable_auto_consent_accept_starts_burst_with_seed_body():
    # Consent accept: the enable_auto_mode call resolves as enabled in the
    # seed body and the burst starts immediately (old enable flow; body shape
    # pinned end-to-end by the auto_seed_and_tool_round golden fixture).
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses("on it"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    seed_body = client.bodies[0]
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}
    # Burst settled → idle, flag stays on (RUNNING/IDLE vocabulary).
    assert record.auto_flag is True
    assert record.idle_reason == "asked_user"


async def test_enable_auto_no_trace_r2_seed_carries_first_message():
    # Revision R2: enable on a brand-new conversation — no trace_id, the
    # first user message rides extra_messages; the backend mints the first
    # trace, which then indexes the conversation.
    sup = _sup()
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("on it"), trace("t-new-1"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id=None,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[{"role": "user", "content": "first message"}],
            upstream_url=URL,
            headers={},
        )
        assert record.state == RunState.RUNNING
        await _wait_for(lambda: record.state == RunState.IDLE)

    seed_body = client.bodies[0]
    assert "trace_id" not in seed_body
    assert seed_body["messages"] == [{"role": "user", "content": "first message"}]
    assert record.current_leaf_trace_id == "t-new-1"
    assert sup.session_for_trace("t-new-1") == record.session_id


async def test_enable_auto_flips_existing_record_instead_of_duplicating():
    # Re-enable before the OFF record's TTL evicts it: the SAME record flips
    # back on (architecture §2 — the policy flips on the SAME run; the old
    # registry minted a fresh run here, stranding two entries per trace).
    sup = _sup(terminal_ttl_seconds=60.0)
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await sup.stop(record.session_id)
        assert record.auto_flag is False
        again = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    assert again.session_id == record.session_id
    assert record.auto_flag is True
    assert record.idle_reason == "armed"
    # The flip cancelled the OFF record's pending GC.
    assert record.session_id not in sup._gc_tasks


async def test_enable_auto_cap_counts_flag_on_conversations():
    sup = _sup(auto_max_concurrent=1)
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        first = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        with pytest.raises(ConversationCapError, match="concurrent auto runs"):
            await sup.enable_auto(
                trace_id="t2",
                enable_tool_call_id=None,
                pending_tool_calls=[],
                extra_messages=[],
                upstream_url=URL,
                headers={},
            )
        # Stopping the first frees its slot (flag-off records don't count) —
        # including for a FLIP of a lingering off record.
        await sup.stop(first.session_id)
        second = await sup.enable_auto(
            trace_id="t2",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    assert second.auto_flag is True


# ── Auto disable (old AutoChatRegistry.disable / disable_for_trace) ───────────


async def test_disable_auto_cancels_running_burst_and_cascades(hang_engine):
    sup = _sup(terminal_ttl_seconds=60.0)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    child = sup.spawn_subagent(
        _seed(), parent_session_id=record.session_id, upstream_url=URL, headers={}
    )
    await asyncio.sleep(0.02)
    assert record.state == RunState.RUNNING

    assert await sup.disable_auto(record.session_id) is True
    # Pre-marked reason survives the cancel (old CR Moderate 2): the flag
    # cleared with user_disabled, NOT user_stopped.
    assert record.auto_flag is False
    assert record.idle_reason == "user_disabled"
    assert record.state == RunState.IDLE
    # The disable cascade stopped the conversation's children (old
    # disable → _stop_subagent_children).
    assert child.state == RunState.STOPPED
    # Off semantics: the record is TTL-GC-scheduled.
    assert record.session_id in sup._gc_tasks


async def test_disable_auto_idle_branch_publishes_off_and_gcs():
    sup = _sup(terminal_ttl_seconds=60.0)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    received: list[bytes] = []
    sub = sup.subscribe(record.session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(0.02)
    assert await sup.disable_auto(record.session_id) is True
    await asyncio.sleep(0.02)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await sub.aclose()

    assert record.auto_flag is False
    assert record.idle_reason == "user_disabled"
    states = _state_events(received)
    assert states[-1]["auto_flag"] is False
    assert states[-1]["idle_reason"] == "user_disabled"
    assert record.session_id in sup._gc_tasks
    # Idempotent re-disable; unknown ids report False (route maps semantics).
    assert await sup.disable_auto(record.session_id) is True
    assert await sup.disable_auto("cv_missing") is False


async def test_disable_auto_for_trace_resolves_chain_and_guards_kind(hang_engine):
    # The interactive-loop disable interception entry point (the phase-1
    # TODO(phase-3) cascade): stale leaves resolve through the whole-chain
    # index; sub-agent leaves — also indexed here, unlike the old auto-only
    # index — must never be disabled by it.
    sup = _sup(terminal_ttl_seconds=60.0)
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    child = sup.spawn_subagent(
        _seed(), parent_session_id="trace:leaf-x", upstream_url=URL, headers={}
    )
    sup._trace_index["child-leaf"] = child.session_id

    assert await sup.disable_auto_for_trace("child-leaf") is False
    assert child.state == RunState.RUNNING
    assert await sup.disable_auto_for_trace("never-seen") is False
    assert await sup.disable_auto_for_trace("t1") is True
    assert record.auto_flag is False
    assert record.idle_reason == "user_disabled"
    await sup.stop(child.session_id)


async def test_set_auto_flag_outcomes():
    sup = _sup(terminal_ttl_seconds=60.0, auto_max_concurrent=1)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    child = sup.create_conversation(
        "subagent",
        upstream_url=URL,
        headers={},
        parent_session_id=record.session_id,
        seed=_seed(),
    )
    assert await sup.set_auto_flag("cv_missing", True) == "not_found"
    # Phase 3: only auto records are flippable (interactive conversations
    # aren't supervisor records yet; sub-agents never are).
    assert await sup.set_auto_flag(child.session_id, True) == "invalid"
    # enabled=false → today's disable semantics.
    assert await sup.set_auto_flag(record.session_id, False) == "ok"
    assert record.auto_flag is False and record.idle_reason == "user_disabled"
    # enabled=true → re-arm (cap re-checked; the only slot is free again).
    assert await sup.set_auto_flag(record.session_id, True) == "ok"
    assert record.auto_flag is True and record.idle_reason == "armed"


# ── Resync resolve (old GET /api/chat/auto/resolve) ───────────────────────────


async def test_resolve_auto_for_trace_matches_stale_leaf_and_filters():
    sup = _sup(terminal_ttl_seconds=60.0)
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("t2"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    # The stale seed leaf t1 resolves via the whole-chain index; the record's
    # CURRENT leaf (t2) is what the resyncing client hydrates from.
    resolved = sup.resolve_auto_for_trace("t1")
    assert resolved is record
    assert record.current_leaf_trace_id == "t2"
    assert sup.resolve_auto_for_trace("t2") is record
    assert sup.resolve_auto_for_trace("never-seen") is None
    # Flag-off records stop resolving (green dot/resync gone once stopped).
    await sup.stop(record.session_id)
    assert sup.resolve_auto_for_trace("t1") is None


# ── Orchestration identity threading ──────────────────────────────────────────


async def test_auto_conversation_gets_orchestration_ctx_with_fresh_leaf():
    # Parent kinds carry a real OrchestrationContext (their session id as the
    # stable parent identity — no auto:<run_id> alias chaining) whose
    # parent_trace_id is kept fresh by on_trace (spawn lineage: the agent
    # block's parent_trace_id, resolved by the backend into durable lineage).
    sup = _sup()
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("t2"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            trace_id="t1",
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        conv = sup._conversations[record.session_id]
        await _wait_for(lambda: record.state == RunState.IDLE)

    ctx = conv.orchestration_ctx
    assert ctx is not None
    assert ctx.parent_session_id == record.session_id
    assert ctx.parent_trace_id == "t2"  # advanced with the burst's trace
    assert ctx.parent_key() == record.session_id
    # Children never get a ctx (depth guard + execute_tool_batch backstop).
    child = sup.create_conversation(
        "subagent",
        upstream_url=URL,
        headers={},
        parent_session_id=record.session_id,
        seed=_seed(),
    )
    assert sup._orchestration_ctx(sup._conversations[child.session_id]) is None


# ── GC ────────────────────────────────────────────────────────────────────────


async def test_terminal_ttl_evicts_delivered_child():
    sup = _sup(terminal_ttl_seconds=0.05, undelivered_report_ttl_seconds=0.05)
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: child.state.is_terminal)
        # Mark delivered so the pin doesn't apply.
        sup._mark_report_delivered(sup._conversations[child.session_id])
        await asyncio.sleep(0.15)
    assert sup.get(child.session_id) is None
    assert sup.session_for_trace("tr-1") is None  # index cleaned


async def test_undelivered_report_pins_record_past_terminal_ttl():
    sup = _sup(terminal_ttl_seconds=0.05, undelivered_report_ttl_seconds=0.3)
    client = FakeUpstreamClient(_text_run_responses())
    parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)
        # Past the terminal TTL the undelivered report still pins the record…
        await asyncio.sleep(0.15)
        assert sup.get(child.session_id) is not None
        # …until the report TTL finally lapses.
        await asyncio.sleep(0.3)
    assert sup.get(child.session_id) is None


async def test_queued_reports_pin_off_auto_parent_past_terminal_ttl():
    # The GC side of the in-burst-disable flow: the OFF-auto parent record
    # holds BOTH the report queue and the trace-index entries the resumed
    # interactive turn resolves through — evicting it at the plain terminal
    # TTL would strand the report. Queued undelivered reports therefore pin
    # the parent to the undelivered-report TTL, exactly like the child's own
    # pin (old world: the auto alias map outlived the run's eviction and the
    # child pin bounded drainability at the same TTL).
    sup = _sup(terminal_ttl_seconds=0.05, undelivered_report_ttl_seconds=0.4)
    parent = sup.create_conversation("auto", upstream_url=URL, headers={})
    parent.current_leaf_trace_id = "t-p"
    parent.seen_trace_ids.append("t-p")
    sup._trace_index["t-p"] = parent.session_id

    client = FakeUpstreamClient(_text_run_responses("child done"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        # In-burst disable: flag clears; the child survives (no cascade).
        parent.auto_flag = False
        parent.idle_reason = "user_disabled"
        await _wait_for(lambda: child.state.is_terminal)
        assert sup.has_pending_reports(parent.session_id)
        # The flag-off settle branch schedules the parent's GC after a real
        # burst; the flag was flipped without one here, so schedule directly.
        sup._schedule_gc(parent.session_id)

        # Past the terminal TTL the queued report pins the parent record —
        # the trace index still resolves, so a resumed interactive turn can
        # still drain the report.
        await asyncio.sleep(0.15)
        assert sup.get(parent.session_id) is not None
        assert sup.session_for_trace("t-p") == parent.session_id
        reports = sup.drain_reports(parent.session_id)
        assert len(reports) == 1 and reports[0].startswith("<subagent_report")
        # The pin is bounded: the record still evicts once the report TTL
        # lapses (the pin decision was taken at the terminal-TTL check).
        await asyncio.sleep(0.4)
    assert sup.get(parent.session_id) is None


async def test_off_auto_record_gcs_after_ttl():
    sup = _sup(terminal_ttl_seconds=0.05)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    await sup.stop(record.session_id)  # flag off, schedules GC
    await asyncio.sleep(0.15)
    assert sup.get(record.session_id) is None


async def test_idle_interactive_records_evict_lru_beyond_cap():
    sup = _sup(max_idle_interactive_records=2)
    first = sup.create_conversation("interactive", upstream_url=URL, headers={})
    second = sup.create_conversation("interactive", upstream_url=URL, headers={})
    # Make the LRU order deterministic.
    sup._touch(sup._conversations[second.session_id])
    third = sup.create_conversation("interactive", upstream_url=URL, headers={})
    # The oldest idle record was evicted to keep the pool at the cap.
    assert sup.get(first.session_id) is None
    assert sup.get(second.session_id) is not None
    assert sup.get(third.session_id) is not None


async def test_eviction_ends_live_observer_stream():
    # CR n3: LRU eviction can hit a record with a live subscriber; the evicted
    # conversation's bus is closed so the observer gets EOF (and the client
    # can re-open from history) instead of parking forever on a dead bus.
    sup = _sup(max_idle_interactive_records=1)
    first = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sub = sup.subscribe(first.session_id)
    received: list[bytes] = []

    async def _drain():
        async for payload in sub:
            received.append(payload)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(0.02)
    # A second create overflows the cap and LRU-evicts `first` mid-observe.
    sup.create_conversation("interactive", upstream_url=URL, headers={})
    assert sup.get(first.session_id) is None
    # The observer's generator ended by itself — no cancellation needed.
    await asyncio.wait_for(task, timeout=1.0)
    # It received the on-subscribe marker before the eviction closed the bus.
    assert _state_events(received)[0]["state"] == "idle"


class _GatedClient:
    """Fake client whose single round blocks until `release` is set, then
    emits a text turn and finishes — lets a test hold a run RUNNING (same
    trick as auto/test_registry.py's _GatedClient)."""

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release
        self.bodies: list[dict] = []

    def stream(self, method, url, *, content, headers):
        self.bodies.append(json.loads(content.decode()))
        return _GatedResponse(self._release)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _GatedResponse:
    def __init__(self, release: asyncio.Event) -> None:
        self.status_code = 200
        self._release = release

    async def aread(self):
        return b""

    async def aiter_bytes(self):
        yield trace("tr-1")
        await self._release.wait()
        yield text_delta("back")
        yield finish("stop")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def test_send_to_off_auto_record_is_refused_until_reenabled():
    # Phase 3: a flag-off auto record REFUSES messages — the old registry's
    # "not found or no longer active" 404 (AutoChatRegistry.send_message
    # required flag_on), and a safety property: a run started here would
    # execute under the AUTO policy (auto-approving every tool) without an
    # active consent. Re-enabling via set_auto_flag cancels the pending GC
    # and re-arms; the next send then starts a burst WITH auto_mode riding.
    # TODO(phase-4): an off-auto record becomes an idle INTERACTIVE
    # conversation (policy swap) and the refusal is lifted.
    sup = _sup(terminal_ttl_seconds=0.2)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    record.current_leaf_trace_id = "tr-0"
    await sup.stop(record.session_id)  # flag off, schedules the off-auto GC
    assert record.auto_flag is False
    assert sup.send_message(record.session_id, "hello again") is False

    # Flip back on: GC cancelled, ARMED shape, slot re-taken.
    assert await sup.set_auto_flag(record.session_id, True) == "ok"
    assert record.auto_flag is True
    assert record.idle_reason == "armed"

    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.send_message(record.session_id, "hello again") is True
        assert record.state == RunState.RUNNING
        # Ride out the ORIGINAL TTL while the burst runs: had the re-enable
        # not cancelled the GC, the record would be evicted mid-run.
        await asyncio.sleep(0.3)
        assert sup.get(record.session_id) is not None
        release.set()
        await _wait_for(lambda: record.state == RunState.IDLE)

    # auto_mode rides the re-armed burst (the flag is on again), continuing
    # from the conversation's leaf — the idle re-arm body shape.
    assert client.bodies[0]["auto_mode"] is True
    assert client.bodies[0]["trace_id"] == "tr-0"


# ── Records / policy wiring sanity ───────────────────────────────────────────


async def test_create_conversation_validates_subagent_args():
    sup = _sup()
    with pytest.raises(ValueError, match="require a seed"):
        sup.create_conversation(
            "subagent", upstream_url=URL, headers={}, parent_session_id="p"
        )
    with pytest.raises(ValueError, match="parent_session_id"):
        sup.create_conversation("subagent", upstream_url=URL, headers={}, seed=_seed())


async def test_start_run_rejects_double_start(hang_engine):
    sup = _sup()
    record = sup.spawn_subagent(
        _seed(), parent_session_id="p", upstream_url=URL, headers={}
    )
    with pytest.raises(RuntimeError, match="already has a run in flight"):
        sup.start_run(record.session_id)
    await sup.stop(record.session_id)
    with pytest.raises(RuntimeError, match="already ended"):
        sup.start_run(record.session_id)
