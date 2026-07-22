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
from .interceptors import DISABLE_AUTO_MODE_STALE_RESULT
from .models import InboundMessage, RunState, SubAgentSeed
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


def _seeded_conversation(
    sup: ConversationSupervisor, leaf: str, kind: str = "interactive"
):
    """A live conversation already holding a persisted leaf — the state
    ``adopt_interactive``/``enable_auto`` used to build from a browser trace
    id. Phase 5 keys the browser surface on session ids, so tests seed the
    record directly (same shape adopt/on_trace produce) instead of going
    through the deleted enable-by-trace path."""
    record = sup.create_conversation(kind, upstream_url=URL, headers={})
    record.current_leaf_trace_id = leaf
    record.seen_trace_ids.append(leaf)
    sup._trace_index[leaf] = record.session_id
    return record


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
        assert sup.send_message(auto.session_id, "try again") is not None
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
    message_id = sup.send_message(record.session_id, "steer this")
    # Phase 4: the accepted message's stable id is returned (own-echo dedupe).
    assert message_id is not None and message_id.startswith("cm_")
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
        assert sup.send_message(record.session_id, "resume please") is not None
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


async def test_conversation_headers_carry_correlation_id():
    sup = _sup()
    record = sup.create_conversation(
        "interactive", upstream_url=URL, headers={"Authorization": "Bearer k"}
    )
    conv = sup._conversations[record.session_id]
    # Every upstream request carries the conversation id so the backend's
    # debug log can be joined with the desktop's per conversation.
    assert conv.headers["X-Kiln-Conversation-Id"] == record.session_id
    assert conv.headers["Authorization"] == "Bearer k"


async def test_send_message_while_idle_delivers_stranded_inbox_first():
    sup = _sup()
    burst = [
        FakeUpstreamResponse([trace("tr-1"), text_delta("resumed"), finish("stop")])
    ]
    client = FakeUpstreamClient(burst)
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    record.current_leaf_trace_id = "tr-0"
    # A message that landed during a NON-natural settle (e.g. a turn that
    # ended in a terminal upstream error): _finish_run deliberately does not
    # restart from it, so it waits in the inbox for the user's next send.
    conv = sup._conversations[record.session_id]
    conv.inbox.append(InboundMessage(content="stranded"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.send_message(record.session_id, "fresh") is not None
        await _wait_for(lambda: record.state == RunState.IDLE)

    # The stranded message rides the fresh turn, in send order, unframed.
    assert client.bodies == [
        {
            "messages": [
                {"role": "user", "content": "stranded"},
                {"role": "user", "content": "fresh"},
            ],
            "trace_id": "tr-0",
        }
    ]
    assert conv.inbox == []


async def test_send_message_unknown_or_terminal_returns_none():
    sup = _sup()
    assert sup.send_message("cv_nope", "x") is None
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: record.state.is_terminal)
    assert sup.send_message(record.session_id, "too late") is None


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


async def test_report_delivered_to_interactive_parent_wakes_idle_parent():
    # Unified-runtime behavior (product decision): an IDLE INTERACTIVE parent
    # is WOKEN by a child's report — the report is injected via the inbox and
    # starts a normal gated turn — instead of the old v1 limitation where an
    # interactive parent's report merely queued and waited for the USER's next
    # message. This is exactly what the auto-parent test above asserts, minus
    # the auto_mode flag on the woken turn's body (the interactive parent runs
    # a gated turn).
    sup = _sup()
    # Response 1: the child's whole run. Response 2: the interactive parent
    # turn the report injection wakes up.
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse([text_delta("child done"), trace("tr-c1"), finish()]),
            FakeUpstreamResponse(
                [text_delta("got it"), trace("tr-p1"), finish("stop")]
            ),
        ]
    )
    parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id=parent.session_id,
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)
        # The injection woke the idle interactive parent into a turn.
        await _wait_for(lambda: len(client.bodies) == 2)
        await _wait_for(lambda: parent.state == RunState.IDLE)

    assert child.report_delivered is True
    # The framed report seeded the parent's turn as an UNFRAMED user message
    # (report frames are excluded from side-note framing), and the woken
    # interactive turn carries NO auto_mode flag (it is gated).
    parent_body = client.bodies[1]
    (msg,) = parent_body["messages"]
    assert msg["role"] == "user"
    assert msg["content"].startswith("<subagent_report")
    assert 'status="completed"' in msg["content"]
    assert f'id="{child.session_id}"' in msg["content"]
    assert "auto_mode" not in parent_body
    # Delivered through the inbox — nothing left queued for drain.
    assert sup.has_pending_reports(parent.session_id) is False


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


async def test_interactive_stop_leaves_children_while_delete_cascades(hang_engine):
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

    # Phase 4: a plain interactive stop() cancels the turn only — the old
    # interactive Stop was a stream abort that never touched running
    # sub-agents (functional spec §2 "interactive: cancel in-flight turn").
    await sup.stop(parent.session_id)
    assert a.state == RunState.RUNNING
    assert b.state == RunState.RUNNING

    # Session DELETION still cascades: orchestration.handle_session_deleted
    # calls stop_children explicitly.
    await sup.stop_children(parent.session_id)
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


async def test_enable_auto_armed_only_flips_idle_record_no_upstream_post():
    # Manual enable with nothing to send upstream: the record is merely ARMED
    # (flag on, IDLE("armed"), NO run task) — the old is_armed_only branch,
    # which existed because an empty upstream POST would be rejected by the
    # backend ("No messages were sent to the server"). Phase 5: keyed by the
    # LIVE conversation's session id (the old enable-by-trace adoption is
    # unreachable — the browser can only name live conversations).
    sup = _sup()
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient([])  # any POST would blow up the fake
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    assert record is seeded
    assert record.kind == "auto"
    assert record.auto_flag is True
    assert record.state == RunState.IDLE
    assert record.idle_reason == "armed"
    assert client.bodies == []
    # The conversation's leaf/index survive the flip (the record IS the
    # conversation), so the sessions-list join sees it at once.
    assert record.current_leaf_trace_id == "t1"
    assert sup.session_for_trace("t1") == record.session_id
    assert sup.auto_record_for_trace("t1") is record


async def test_enable_auto_unknown_or_subagent_session_id_is_rejected():
    # Phase 5: the browser names conversations by session id, so an unknown
    # sid means the record (and any consent context) died with a restart —
    # 404 at the route, never a silently forked parallel record. Sub-agent
    # records can't enable auto mode (mirrors set_auto_flag's "invalid").
    sup = _sup()
    with pytest.raises(KeyError, match="cv_missing"):
        await sup.enable_auto(
            session_id="cv_missing",
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    child = sup.create_conversation(
        "subagent",
        upstream_url=URL,
        headers={},
        parent_session_id="cv_parent",
        seed=_seed(),
    )
    with pytest.raises(ValueError, match="cannot enable auto mode"):
        await sup.enable_auto(
            session_id=child.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )


async def test_enable_auto_consent_accept_starts_burst_with_seed_body():
    # Consent accept: the enable_auto_mode call resolves as enabled in the
    # seed body and the burst starts immediately (old enable flow; body shape
    # pinned end-to-end by the auto_seed_and_tool_round golden fixture).
    sup = _sup()
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient(_text_run_responses("on it"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    seed_body = client.bodies[0]
    # Phase 5: the continuation targets the RECORD's own leaf (the browser's
    # copy of the same id is gone; the engine's on_trace keeps this fresh).
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}
    # Burst settled → idle, flag stays on (RUNNING/IDLE vocabulary).
    assert record.auto_flag is True
    assert record.idle_reason == "asked_user"


async def test_enable_auto_accepts_spawn_consent_pending_executes_spawn():
    # FR2 spawn-consent accept: enable_auto with NO enable id and the gating
    # spawn riding pending_tool_calls flips the policy AND executes the spawn
    # with the conversation's own orchestration ctx; the spawn's result seeds
    # the burst as a role:tool row (no enable row — the flag flip is the
    # consent). The batch executor is patched so the test pins the call shape
    # without spinning a real child run.
    from unittest.mock import AsyncMock

    # Relative, matching this test module's own imports — the absolute
    # spelling resolves a DIFFERENT module instance under pytest (see the
    # import note in chat/test_orchestration.py) and the patch would miss.
    from . import supervisor as supervisor_module

    spawn_result = json.dumps(
        {"status": "spawned", "subagent_id": "cv_child", "name": "helper"},
        ensure_ascii=False,
    )
    sup = _sup()
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient(_text_run_responses("child is working"))
    from app.desktop.studio_server.chat.stream_session import ToolCallInfo

    execute_mock = AsyncMock(return_value={"tc_spawn": spawn_result})
    with (
        patch.object(supervisor_module, "execute_tool_batch", execute_mock),
        patch.object(httpx, "AsyncClient", return_value=client),
    ):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[
                ToolCallInfo(
                    toolCallId="tc_spawn",
                    toolName="spawn_subagent",
                    input={"agent_type": "general", "name": "helper", "prompt": "p"},
                    requiresApproval=False,
                )
            ],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    # The policy flipped on the SAME record (accept == enable).
    assert record is seeded
    assert record.kind == "auto" and record.auto_flag is True
    assert sup._conversations[record.session_id].policy.approvals == "auto"
    # The spawn executed through the conversation's orchestration ctx (spawn
    # lineage/ownership identical to an in-burst spawn), auto-approved.
    execute_mock.assert_awaited_once()
    (calls, decisions), kwargs = execute_mock.call_args
    assert [(tc.tool_call_id, tc.tool_name, tc.requires_approval) for tc in calls] == [
        ("tc_spawn", "spawn_subagent", False)
    ]
    assert decisions == {}
    ctx = kwargs["orchestration_ctx"]
    assert ctx is sup._conversations[record.session_id].orchestration_ctx
    assert ctx.parent_key() == record.session_id
    # The seed body: NO enable row, the spawn's result as the only role:tool
    # message, continuing from the record's own leaf under auto_mode.
    seed_body = client.bodies[0]
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"] == [
        {"role": "tool", "tool_call_id": "tc_spawn", "content": spawn_result}
    ]


async def test_enable_auto_busy_accept_raises_before_spawning(hang_engine):
    # A spawn-consent accept racing an in-flight run must 409 (RuntimeError)
    # with NO side effects — the busy guard sits before the flag flip and
    # before execute_tool_batch, so no orphan child is left running behind
    # the 409 (start_run's own check would fire only after the spawn) and
    # the interactive record is left untouched: not flipped to auto with no
    # seeded burst (the racing run started under the interactive policy, so
    # _finish_run would never swap it back) and holding no auto-cap slot.
    from unittest.mock import AsyncMock

    from . import supervisor as supervisor_module
    from app.desktop.studio_server.chat.stream_session import ToolCallInfo

    sup = _sup(auto_max_concurrent=1)
    seeded = _seeded_conversation(sup, "t1")
    sup.start_run(seeded.session_id, {"messages": [{"role": "user", "content": "x"}]})

    execute_mock = AsyncMock(return_value={"tc_spawn": "{}"})
    with patch.object(supervisor_module, "execute_tool_batch", execute_mock):
        with pytest.raises(RuntimeError, match="already has a run in flight"):
            await sup.enable_auto(
                session_id=seeded.session_id,
                enable_tool_call_id=None,
                pending_tool_calls=[
                    ToolCallInfo(
                        toolCallId="tc_spawn",
                        toolName="spawn_subagent",
                        input={"agent_type": "general", "name": "h", "prompt": "p"},
                        requiresApproval=False,
                    )
                ],
                extra_messages=[],
                upstream_url=URL,
                headers={},
            )
    execute_mock.assert_not_awaited()
    assert seeded.kind == "interactive"
    assert seeded.auto_flag is False
    assert sup._conversations[seeded.session_id].policy.approvals == "gated"
    # The only auto slot is still free (the cap counts flag-on records).
    sup._check_auto_cap()
    await sup.stop(seeded.session_id)


async def test_enable_auto_armed_only_during_running_burst_flips_flag(hang_engine):
    # An armed-only enable (no seed to run) while a burst is RUNNING stays
    # legal — the busy guard applies only to seed-carrying enables. The flag
    # and policy flip on the live record; the idle/armed stamp is skipped (the
    # run is not idle) and the in-flight task is untouched.
    sup = _sup()
    seeded = _seeded_conversation(sup, "t1")
    sup.start_run(seeded.session_id, {"messages": [{"role": "user", "content": "x"}]})
    task = sup._conversations[seeded.session_id].task
    assert task is not None and not task.done()

    record = await sup.enable_auto(
        session_id=seeded.session_id,
        enable_tool_call_id=None,
        pending_tool_calls=[],
        extra_messages=[],
        upstream_url=URL,
        headers={},
    )
    assert record is seeded
    assert record.kind == "auto"
    assert record.auto_flag is True
    assert sup._conversations[record.session_id].policy.approvals == "auto"
    assert record.state == RunState.RUNNING
    assert record.idle_reason != "armed"
    assert sup._conversations[record.session_id].task is task
    await sup.stop(record.session_id)


async def test_enable_auto_no_session_r2_seed_carries_first_message():
    # Revision R2: enable on a brand-new conversation — no session_id, the
    # first user message rides extra_messages; the backend mints the first
    # trace, which then indexes the conversation.
    sup = _sup()
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("on it"), trace("t-new-1"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=None,
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
    # A fresh conversation's first persisted snapshot IS its durable root
    # (the backend stamps session_meta.root_id = snapshot_id on the first
    # persist) — the engine records it for the browser's recovery key.
    assert record.root_id == "t-new-1"


async def test_enable_auto_flips_existing_record_instead_of_duplicating():
    # Re-enable after a stop: the SAME record flips back on (architecture §2
    # — the policy flips on the SAME run; the old registry minted a fresh run
    # here, stranding two entries per conversation).
    sup = _sup(terminal_ttl_seconds=60.0)
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await sup.stop(record.session_id)
        assert record.auto_flag is False
        again = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
    assert again.session_id == record.session_id
    assert record.auto_flag is True
    assert record.idle_reason == "armed"
    # The flip cancelled any pending GC on the record.
    assert record.session_id not in sup._gc_tasks


async def test_enable_auto_cap_counts_flag_on_conversations():
    sup = _sup(auto_max_concurrent=1)
    seeded_one = _seeded_conversation(sup, "t1")
    seeded_two = _seeded_conversation(sup, "t2")
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        first = await sup.enable_auto(
            session_id=seeded_one.session_id,
            enable_tool_call_id=None,
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        with pytest.raises(ConversationCapError, match="concurrent auto runs"):
            await sup.enable_auto(
                session_id=seeded_two.session_id,
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
            session_id=seeded_two.session_id,
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
    # Phase 4 off semantics: no TTL GC — the record swapped back to its
    # interactive life (kind + policy) and joins the idle-interactive pool.
    assert record.session_id not in sup._gc_tasks
    assert record.kind == "interactive"
    assert sup._conversations[record.session_id].policy.approvals == "gated"


async def test_disable_auto_idle_branch_publishes_off_and_swaps_interactive():
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
    # The published off event keeps the phase-3 shape (kind=auto, flag off,
    # reason) — the interactive swap happens after the publish.
    assert states[-1]["auto_flag"] is False
    assert states[-1]["idle_reason"] == "user_disabled"
    assert states[-1]["kind"] == "auto"
    # Phase 4: no TTL GC — an off-auto conversation IS an idle interactive
    # conversation (policy + kind swapped on the SAME record).
    assert record.session_id not in sup._gc_tasks
    assert record.kind == "interactive"
    assert sup._conversations[record.session_id].policy.approvals == "gated"
    # Idempotent re-disable; unknown ids report False (route maps semantics).
    assert await sup.disable_auto(record.session_id) is True
    assert await sup.disable_auto("cv_missing") is False


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
    # Sub-agent records are never user-flippable; interactive and auto
    # records both are (phase 4 — the true policy flip on the SAME record).
    assert await sup.set_auto_flag(child.session_id, True) == "invalid"
    # enabled=false → today's disable semantics + the interactive swap.
    assert await sup.set_auto_flag(record.session_id, False) == "ok"
    assert record.auto_flag is False and record.idle_reason == "user_disabled"
    assert record.kind == "interactive"
    # enabled=true on the (now interactive) record → the flip: policy + kind
    # swap to auto, ARMED shape, cap re-checked (the only slot is free again).
    assert await sup.set_auto_flag(record.session_id, True) == "ok"
    assert record.auto_flag is True and record.idle_reason == "armed"
    assert record.kind == "auto"
    assert sup._conversations[record.session_id].policy.approvals == "auto"


# ── Trace-index join (INTERNAL since phase 5 — sessions-list only) ────────────


async def test_auto_record_for_trace_matches_stale_leaf_and_filters():
    # The whole-chain lookup powering routes.py's sessions-list auto join.
    # Its browser-facing sibling (resolve_auto_for_trace behind
    # GET /api/conversations/resolve) died in phase 5 — the browser keys
    # conversations on session ids and never resyncs by trace — but the join
    # still resolves upstream leaf-keyed rows (the sessions LIST stays
    # leaf-keyed even after phase 6's session-id continuation).
    sup = _sup(terminal_ttl_seconds=60.0)
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("t2"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    # The stale seed leaf t1 resolves via the whole-chain index even though
    # the record's current leaf advanced to t2.
    assert record.current_leaf_trace_id == "t2"
    assert sup.auto_record_for_trace("t1") is record
    assert sup.auto_record_for_trace("t2") is record
    assert sup.auto_record_for_trace("never-seen") is None
    # Flag-off records stop resolving (green dot gone once stopped).
    await sup.stop(record.session_id)
    assert sup.auto_record_for_trace("t1") is None


# ── Orchestration identity threading ──────────────────────────────────────────


async def test_auto_conversation_gets_orchestration_ctx_with_fresh_leaf():
    # Parent kinds carry a real OrchestrationContext (their session id as the
    # stable parent identity — no alias chaining). The spawn lineage leaf is
    # no longer a ctx copy (phase 4 shrank the ctx to {parent_session_id,
    # depth}): the spawn executor reads record.current_leaf_trace_id, which
    # the engine advances per round — assert the record carries the fresh
    # leaf a spawn would forward as the agent block's parent_trace_id.
    sup = _sup()
    seeded = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("hi"), trace("t2"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        record = await sup.enable_auto(
            session_id=seeded.session_id,
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
    assert ctx.parent_key() == record.session_id
    # The spawn-lineage leaf lives on the record (single source of truth).
    assert record.current_leaf_trace_id == "t2"  # advanced with the burst
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
    # A report stays UNDELIVERED (and pins the child record) only when it
    # can't be delivered — a live parent now WAKES on the report via the inbox
    # (see test_report_delivered_to_interactive_parent_wakes_idle_parent). The
    # realistic undelivered case is a GONE parent (evicted / never registered):
    # _deliver_report finds no parent record and queues the report, which pins
    # the child past the terminal TTL until the report TTL lapses.
    sup = _sup(terminal_ttl_seconds=0.05, undelivered_report_ttl_seconds=0.3)
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(),
            parent_session_id="cv_gone_parent",  # not a live supervisor record
            upstream_url=URL,
            headers={},
        )
        await _wait_for(lambda: child.state.is_terminal)
        assert sup.has_pending_reports("cv_gone_parent")  # queued, undelivered
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


async def test_off_auto_record_survives_as_idle_interactive():
    # Phase 4 replaced the OFF-auto TTL GC: stopping an auto conversation
    # swaps it back to an idle INTERACTIVE record (LRU-bounded), so the
    # conversation can simply continue interactively.
    sup = _sup(terminal_ttl_seconds=0.05)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    await sup.stop(record.session_id)  # flag off → interactive swap
    assert record.session_id not in sup._gc_tasks
    await asyncio.sleep(0.15)
    assert sup.get(record.session_id) is record
    assert record.kind == "interactive"
    assert record.auto_flag is False


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


async def test_send_to_off_auto_record_runs_interactive_then_reenables():
    # Phase 4 lifted the phase-3 flag-off refusal BY CONSTRUCTION: stopping
    # an auto conversation swaps it back to the INTERACTIVE policy, so the
    # next send starts a normal gated turn — never an auto-approving burst
    # without an active consent (the old safety property, now structural).
    from .models import auto_policy

    sup = _sup(terminal_ttl_seconds=0.2)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    record.current_leaf_trace_id = "tr-0"
    await sup.stop(record.session_id)  # flag off → interactive swap
    assert record.auto_flag is False
    assert record.kind == "interactive"

    # The refusal survives only for the narrow window where a record still
    # carries the AUTO policy with the flag off (disable pre-marks the flag
    # before the settle swaps the policy).
    conv = sup._conversations[record.session_id]
    conv.policy = auto_policy()
    assert sup.send_message(record.session_id, "mid-window") is None
    sup._swap_to_interactive(conv)

    # An interactive send now runs a plain gated turn — no auto_mode riding,
    # continuing from the conversation's leaf.
    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("sure"), trace("tr-1"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.send_message(record.session_id, "hello again") is not None
        await _wait_for(lambda: record.state == RunState.IDLE)
    assert client.bodies[0]["trace_id"] == "tr-0"
    assert "auto_mode" not in client.bodies[0]

    # Flip back on (the true policy flip): ARMED shape, slot re-taken; the
    # next send starts a burst WITH auto_mode riding from the fresh leaf —
    # the idle re-arm body shape.
    assert await sup.set_auto_flag(record.session_id, True) == "ok"
    assert record.auto_flag is True and record.kind == "auto"
    assert record.idle_reason == "armed"

    release = asyncio.Event()
    gated = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=gated):
        assert sup.send_message(record.session_id, "go autonomous") is not None
        assert record.state == RunState.RUNNING
        release.set()
        await _wait_for(lambda: record.state == RunState.IDLE)
    assert gated.bodies[0]["auto_mode"] is True
    assert gated.bodies[0]["trace_id"] == "tr-1"


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


# ── Phase 4: interactive create/adopt + approval recovery ─────────────────────


async def test_adopt_interactive_creates_and_is_idempotent():
    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
        assert record.kind == "interactive"
        assert record.state == RunState.IDLE
        # Phase 6: the adopted key is stored as the RESUME key, not a leaf —
        # the desktop no longer resolves keys to leaves (the backend does,
        # on the first session_id continuation).
        assert record.current_leaf_trace_id is None
        assert record.resume_session_key == "leaf-1"
        # …and NEVER stamped into root_id (a legacy-leaf key there would hand
        # the browser a recovery key that goes stale on the next persist).
        assert record.root_id is None
        assert sup.session_for_trace("leaf-1") == record.session_id

        # Idempotent: the same key (or ANY leaf the conversation ever had)
        # returns the SAME record instead of minting a duplicate.
        again = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
        assert again is record

        # A key resolving to a live AUTO record adopts THAT record — one
        # record per conversation is the whole point of the flip model.
        auto = _seeded_conversation(sup, "t-auto", kind="auto")
        adopted = await sup.adopt_interactive("t-auto", upstream_url=URL, headers={})
        assert adopted is auto

        # No key at all (brand-new conversation): a fresh empty record.
        fresh = await sup.adopt_interactive(None, upstream_url=URL, headers={})
        assert fresh.kind == "interactive"
        assert fresh.current_leaf_trace_id is None
        assert fresh.resume_session_key is None


async def test_adopt_interactive_does_not_steal_terminal_records_index_entry():
    # Re-opening a FINISHED sub-agent's session from history continues its
    # TRACE on a fresh interactive record, but the terminal child's index
    # entry survives so the sessions-list "finished" chip keeps resolving.
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses())
    with patch.object(httpx, "AsyncClient", return_value=client):
        child = sup.spawn_subagent(
            _seed(), parent_session_id="cv_parent", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: child.state.is_terminal)
    assert sup.session_for_trace("tr-1") == child.session_id

    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        adopted = await sup.adopt_interactive("tr-1", upstream_url=URL, headers={})
    assert adopted.session_id != child.session_id
    assert adopted.kind == "interactive"
    # The fresh record resumes the child's TRACE by key (phase 6): the leaf
    # arrives with its first persist, the key seeds the resume continuation.
    assert adopted.resume_session_key == "tr-1"
    # The child still owns the leaf in the index.
    assert sup.session_for_trace("tr-1") == child.session_id


def _tail_trace_with_pending_calls() -> list[dict]:
    """A persisted trace tail: last assistant turn carries four tool calls —
    one answered, two signals (skipped: a pending enable and a stale
    pre-upgrade disable), one genuinely unanswered."""
    return [
        {"role": "user", "content": "please add"},
        {
            "role": "assistant",
            "content": "on it",
            "tool_calls": [
                {
                    "id": "tc_done",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 1, "b": 1}'},
                },
                {
                    "id": "tc_enable",
                    "type": "function",
                    "function": {"name": "enable_auto_mode", "arguments": "{}"},
                },
                {
                    "id": "tc_disable",
                    "type": "function",
                    "function": {"name": "disable_auto_mode", "arguments": "{}"},
                },
                {
                    "id": "tc_open",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "tc_done", "content": "2"},
    ]


async def test_rehydrate_pending_approvals_from_trace_tail():
    # Functional spec §5 / architecture §2: after a desktop restart the parked
    # batch is reconstructible from the persisted trace tail — unanswered
    # calls only, signal tools skipped, every rebuilt call conservatively
    # gated (stream metadata is not persisted).
    sup = _sup()
    with patch.object(
        ConversationSupervisor,
        "_fetch_persisted_trace",
        return_value=_tail_trace_with_pending_calls(),
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})

    assert record.state == RunState.AWAITING_APPROVAL
    batch = sup.pending_approval(record.session_id)
    assert batch is not None
    assert [item["toolCallId"] for item in batch.items] == ["tc_open"]
    assert batch.items[0]["requiresApproval"] is True
    # Phase 6: a key-adopted record has no leaf, so the batch's trace-only
    # base rides the resume key — the backend resolves the current leaf
    # (whose tail is exactly what the batch was rebuilt from).
    assert batch.body == {"session_id": "leaf-1", "messages": []}
    assert batch.assistant_text == "on it"
    # The unanswered SIGNAL siblings never enter the items (nothing to
    # approve) but ride the batch pre-resolved so the resume continuation
    # answers them (no dangling tool call upstream): the enable as declined
    # (its consent dialog died with the restart), the stale disable with the
    # FR1 refusal — never as if the disable succeeded.
    assert json.loads(batch.preresolved_results["tc_enable"]) == {"status": "declined"}
    assert batch.preresolved_results["tc_disable"] == DISABLE_AUTO_MODE_STALE_RESULT
    assert {e.toolCallId for e in batch.tool_input_events} == {
        "tc_open",
        "tc_enable",
        "tc_disable",
    }
    # The pending event was re-emitted onto the bus BUFFER so observers
    # (attaching or live) re-surface the approval box.
    conv = sup._conversations[record.session_id]
    buffered = b"".join(conv.bus.buffer).decode()
    assert '"type": "tool-calls-pending"' in buffered
    assert "tc_open" in buffered

    # Rehydration is idempotent while the batch is undecided.
    again = await sup.rehydrate_pending_approvals(record.session_id)
    assert again is batch


async def test_rehydrate_skips_answered_and_signal_only_tails():
    sup = _sup()
    answered_tail = [
        {
            "role": "assistant",
            "content": "done",
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {"name": "add", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "tc1", "content": "ok"},
    ]
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=answered_tail
    ):
        record = await sup.adopt_interactive("leaf-a", upstream_url=URL, headers={})
    assert record.state == RunState.IDLE
    assert sup.pending_approval(record.session_id) is None

    # An unanswered enable_auto_mode alone is a lost consent dialog, not an
    # approval batch (the old world lost it across restarts too).
    signal_tail = [
        {
            "role": "assistant",
            "content": "want auto?",
            "tool_calls": [
                {
                    "id": "tc_e",
                    "type": "function",
                    "function": {"name": "enable_auto_mode", "arguments": "{}"},
                }
            ],
        },
    ]
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=signal_tail
    ):
        record2 = await sup.adopt_interactive("leaf-b", upstream_url=URL, headers={})
    assert record2.state == RunState.IDLE
    assert sup.pending_approval(record2.session_id) is None


def _spawn_tail(*, with_client_call: bool = False) -> list[dict]:
    """A persisted tail whose pending call is a gating spawn_subagent (FR2
    consent control event ended the turn without answering it), optionally
    with a real client call riding the same round."""
    tool_calls = [
        {
            "id": "tc_spawn",
            "type": "function",
            "function": {
                "name": "spawn_subagent",
                "arguments": '{"agent_type": "general", "name": "helper", "prompt": "go"}',
            },
        },
    ]
    if with_client_call:
        tool_calls.append(
            {
                "id": "tc_open",
                "type": "function",
                "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'},
            }
        )
    return [
        {"role": "user", "content": "spawn a helper"},
        {"role": "assistant", "content": "spawning", "tool_calls": tool_calls},
    ]


async def test_rehydrate_flag_off_spawn_only_tail_is_not_an_approval_batch():
    # FR2: a rehydrated gating spawn must NEVER come back as a plain
    # approvable call while the flag is off — approving it would execute a
    # real spawn without auto mode (and resurrect the spawn-as-approval
    # surface FR3 deletes). A spawn-only tail is a lost consent dialog,
    # exactly like a lost enable_auto_mode consent.
    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=_spawn_tail()
    ):
        record = await sup.adopt_interactive("leaf-s", upstream_url=URL, headers={})
    assert record.state == RunState.IDLE
    assert sup.pending_approval(record.session_id) is None


async def test_rehydrate_flag_off_spawn_next_to_client_call_is_preresolved_declined():
    # A gating spawn riding next to a real client call: the client call
    # rehydrates as the batch, the spawn rides pre-resolved as declined (the
    # lost-consent decline shape) and never enters the approvable items.
    sup = _sup()
    with patch.object(
        ConversationSupervisor,
        "_fetch_persisted_trace",
        return_value=_spawn_tail(with_client_call=True),
    ):
        record = await sup.adopt_interactive("leaf-sc", upstream_url=URL, headers={})
    assert record.state == RunState.AWAITING_APPROVAL
    batch = sup.pending_approval(record.session_id)
    assert batch is not None
    assert [item["toolCallId"] for item in batch.items] == ["tc_open"]
    assert json.loads(batch.preresolved_results["tc_spawn"]) == {"status": "declined"}
    # The spawn still rides tool_input_events so its declined resolution
    # lands on the resume continuation (no dangling tool call upstream).
    assert {e.toolCallId for e in batch.tool_input_events} == {"tc_open", "tc_spawn"}


async def test_rehydrate_flag_on_spawn_stays_approvable():
    # With the flag ON the flag IS the consent (same rule as the live
    # interceptor chain): the spawn rehydrates as a normal — conservatively
    # gated — approvable call.
    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        record = await sup.adopt_interactive("leaf-on", upstream_url=URL, headers={})
    record.auto_flag = True
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=_spawn_tail()
    ):
        batch = await sup.rehydrate_pending_approvals(record.session_id)
    assert batch is not None
    assert [item["toolCallId"] for item in batch.items] == ["tc_spawn"]
    assert batch.items[0]["requiresApproval"] is True
    assert batch.preresolved_results == {}
    assert record.state == RunState.AWAITING_APPROVAL


class _FakeSnapshotClient:
    """httpx.AsyncClient stand-in for the rehydration snapshot GET."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.urls: list[str] = []

    async def get(self, url: str, headers: dict | None = None) -> httpx.Response:
        self.urls.append(url)
        return httpx.Response(200, json=self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def test_rehydrate_fetch_backfills_root_id():
    # Phase 5: the upstream snapshot response carries session_meta.root_id at
    # the top level; a record adopted from a bare legacy leaf learns its
    # durable handle opportunistically from the rehydration fetch (the
    # browser then persists it as the restart-recovery key).
    sup = _sup()
    payload = {
        "id": "leaf-1",
        "root_id": "root-1",
        "task_run": {"trace": _tail_trace_with_pending_calls()},
    }
    with patch.object(httpx, "AsyncClient", return_value=_FakeSnapshotClient(payload)):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
    assert record.root_id == "root-1"
    # The tail rehydration itself still worked off the same fetch.
    assert record.state == RunState.AWAITING_APPROVAL


async def test_decide_runless_batch_starts_resume_run():
    # Deciding a rehydrated (runless) batch starts the RESUME RUN: execute
    # with decisions, continue from the batch's trace-only base — the exact
    # continuation body the old POST /api/chat/execute-tools produced.
    sup = _sup()
    with patch.object(
        ConversationSupervisor,
        "_fetch_persisted_trace",
        return_value=_tail_trace_with_pending_calls(),
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
    batch = sup.pending_approval(record.session_id)
    assert batch is not None

    client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("sum is 5"), trace("tr-2"), finish("stop")])]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.decide(record.session_id, batch.batch_id, {"tc_open": True}) == "ok"
        assert record.state == RunState.RUNNING
        # A racing second decide still conflicts while the resume run lives.
        assert (
            sup.decide(record.session_id, batch.batch_id, {"tc_open": False})
            == "conflict"
        )
        await _wait_for(lambda: record.state == RunState.IDLE)

    # Old execute-tools continuation shape: trace-only base → role:tool rows
    # (phase 6: keyed by session_id for a key-adopted record — the builder
    # treats a session_id base as trace-only, so the wire stays results-only).
    # The signal siblings are answered right alongside the executed call so
    # the persisted trace has no dangling tool call (LOW-2 recovery
    # contract): the enable as declined, the stale disable with the FR1
    # refusal.
    (body,) = client.bodies
    assert body["session_id"] == "leaf-1"
    assert "trace_id" not in body
    rows = {m["tool_call_id"]: m for m in body["messages"]}
    assert all(m["role"] == "tool" for m in body["messages"])
    assert rows["tc_open"]["content"] == "5"
    assert json.loads(rows["tc_enable"]["content"]) == {"status": "declined"}
    assert rows["tc_disable"]["content"] == DISABLE_AUTO_MODE_STALE_RESULT
    assert record.current_leaf_trace_id == "tr-2"


async def test_decline_auto_starts_interactive_declined_continuation():
    # The folded-in decline (old POST /api/chat/auto/decline): the pending
    # gating call resolves as declined + denied siblings via an interactive
    # turn whose seed body is byte-identical to the old endpoint's. The
    # gating id is trigger-agnostic (FR2): an enable_auto_mode call and a
    # consent-gated spawn_subagent decline through the exact same shape.
    from app.desktop.studio_server.chat.stream_session import ToolCallInfo

    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [text_delta("ok, staying manual"), trace("tr-2"), finish("stop")]
            )
        ]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        outcome = sup.decline_auto(
            record.session_id,
            gating_tool_call_id="tc_enable",
            siblings=[
                ToolCallInfo(
                    toolCallId="tc_sib",
                    toolName="add",
                    input={},
                    requiresApproval=False,
                )
            ],
        )
        assert outcome == "ok"
        await _wait_for(lambda: record.state == RunState.IDLE)

    (body,) = client.bodies
    # Phase 6: the key-adopted record's continuation identity is its resume
    # key (session_id); a record with a live leaf would ride trace_id here.
    assert body["session_id"] == "leaf-1"
    assert body["messages"][0] == {
        "role": "tool",
        "tool_call_id": "tc_enable",
        "content": '{"status": "declined"}',
    }
    from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT

    assert body["messages"][1] == {
        "role": "tool",
        "tool_call_id": "tc_sib",
        "content": DENIED_TOOL_OUTPUT,
    }
    # Declining never flips anything on.
    assert record.auto_flag is False and record.kind == "interactive"
    assert sup.decline_auto("cv_missing", gating_tool_call_id="x", siblings=[]) == (
        "not_found"
    )


async def test_decline_auto_spawn_gating_resolves_spawn_declined():
    # FR2 decline: the gating SPAWN call resolves {"status": "declined"} —
    # exactly the spawn tool's documented decline shape — and a sibling
    # spawn is denied with the standard denied shape (behaviorally
    # equivalent to the model); auto mode stays off.
    from app.desktop.studio_server.chat.constants import DENIED_TOOL_OUTPUT
    from app.desktop.studio_server.chat.stream_session import ToolCallInfo

    sup = _sup()
    record = _seeded_conversation(sup, "t1")
    client = FakeUpstreamClient(
        [
            FakeUpstreamResponse(
                [text_delta("continuing without helpers"), trace("t2"), finish("stop")]
            )
        ]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        outcome = sup.decline_auto(
            record.session_id,
            gating_tool_call_id="tc_spawn",
            siblings=[
                ToolCallInfo(
                    toolCallId="tc_spawn2",
                    toolName="spawn_subagent",
                    input={"agent_type": "general", "name": "n2", "prompt": "p"},
                    requiresApproval=True,
                )
            ],
        )
        assert outcome == "ok"
        await _wait_for(lambda: record.state == RunState.IDLE)

    (body,) = client.bodies
    assert body["trace_id"] == "t1"
    assert body["messages"] == [
        {
            "role": "tool",
            "tool_call_id": "tc_spawn",
            "content": '{"status": "declined"}',
        },
        {
            "role": "tool",
            "tool_call_id": "tc_spawn2",
            "content": DENIED_TOOL_OUTPUT,
        },
    ]
    assert record.auto_flag is False and record.kind == "interactive"


async def test_decline_auto_refuses_busy_and_subagent(hang_engine):
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "x"}]})
    assert (
        sup.decline_auto(record.session_id, gating_tool_call_id="tc", siblings=[])
        == "busy"
    )
    await sup.stop(record.session_id)
    child = sup.spawn_subagent(
        _seed(), parent_session_id=record.session_id, upstream_url=URL, headers={}
    )
    assert (
        sup.decline_auto(child.session_id, gating_tool_call_id="tc", siblings=[])
        == "invalid"
    )
    await sup.stop(child.session_id)


async def test_enable_auto_flips_interactive_record_policy_and_kind():
    # The true "same run, new policy" flip (architecture §2): consent accept
    # on an interactive conversation flips ITS record instead of minting a
    # parallel auto record.
    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
    client = FakeUpstreamClient(_text_run_responses("working"))
    with patch.object(httpx, "AsyncClient", return_value=client):
        flipped = await sup.enable_auto(
            session_id=record.session_id,
            enable_tool_call_id="tc_enable",
            pending_tool_calls=[],
            extra_messages=[],
            upstream_url=URL,
            headers={},
        )
        assert flipped is record  # SAME record, not a duplicate
        assert record.kind == "auto"
        assert record.auto_flag is True
        assert sup._conversations[record.session_id].policy.approvals == "auto"
        await _wait_for(lambda: record.state == RunState.IDLE)
    # The seed continued from the adopted conversation's key (phase 6: a
    # key-adopted record has no leaf until its first persist, so the seed
    # rides session_id and the backend resolves the current leaf).
    assert client.bodies[0]["session_id"] == "leaf-1"
    assert "trace_id" not in client.bodies[0]
    assert client.bodies[0]["auto_mode"] is True


async def test_message_idle_start_drains_queued_reports_into_seed():
    # send_message's idle-start still drains any QUEUED reports into the fresh
    # turn's seed (old routes.post_chat next-turn injection). A LIVE parent now
    # WAKES on report delivery instead (see
    # test_report_delivered_to_interactive_parent_wakes_idle_parent), so this
    # exercises the FALLBACK: a report that could NOT be delivered when the
    # child settled (parent off-auto / gone) queued under the parent's session
    # id, and drains when the conversation next runs an interactive turn (the
    # in-burst-disable → swap-to-interactive flow leaves exactly this state).
    sup = _sup()
    parent = sup.create_conversation("interactive", upstream_url=URL, headers={})
    # A terminal child whose report is queued (the state the off-auto / gone-
    # parent fallback leaves behind); re-home the queue entry onto the live
    # interactive parent, as the off-auto→swap flow would.
    child_client = FakeUpstreamClient(_text_run_responses("child done"))
    with patch.object(httpx, "AsyncClient", return_value=child_client):
        child = sup.spawn_subagent(
            _seed(), parent_session_id="cv_offauto_holder", upstream_url=URL, headers={}
        )
        await _wait_for(lambda: child.state.is_terminal)
    assert sup.has_pending_reports("cv_offauto_holder")
    sup._pending_reports.pop("cv_offauto_holder")
    child.report_delivered = False
    sup._pending_reports[parent.session_id] = [child.session_id]
    assert sup.has_pending_reports(parent.session_id)

    turn_client = FakeUpstreamClient(
        [FakeUpstreamResponse([text_delta("noted"), trace("tr-p"), finish("stop")])]
    )
    received: list[bytes] = []
    sub = sup.subscribe(parent.session_id)

    async def _drain():
        async for payload in sub:
            received.append(payload)

    drain_task = asyncio.create_task(_drain())
    await asyncio.sleep(0.02)
    with patch.object(httpx, "AsyncClient", return_value=turn_client):
        assert sup.send_message(parent.session_id, "how did it go?") is not None
        await _wait_for(lambda: parent.state == RunState.IDLE)
    await asyncio.sleep(0.02)
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass
    await sub.aclose()

    (body,) = turn_client.bodies
    assert body["messages"][0] == {"role": "user", "content": "how did it go?"}
    assert body["messages"][1]["role"] == "user"
    assert body["messages"][1]["content"].startswith("<subagent_report")
    assert child.report_delivered is True
    # Echoed (user message at enqueue + report at drain) so the live
    # transcript shows both immediately.
    streamed = b"".join(received).decode()
    assert "how did it go?" in streamed
    assert "subagent_report" in streamed


async def test_interactive_lru_spares_pending_reports_and_live_children(hang_engine):
    # Phase-4 pinning re-homed to the LRU filter (OFF-auto records live in
    # this pool now): records holding undelivered child reports — or live
    # children — must not be evicted, however stale.
    sup = _sup(max_idle_interactive_records=1)
    pinned = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup._pending_reports[pinned.session_id] = ["cv_child_x"]
    with_child = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.spawn_subagent(
        _seed(), parent_session_id=with_child.session_id, upstream_url=URL, headers={}
    )
    # Overflow the pool: only the plain idle record is evictable.
    plain = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup._touch(sup._conversations[plain.session_id])
    newest = sup.create_conversation("interactive", upstream_url=URL, headers={})
    assert sup.get(pinned.session_id) is not None
    assert sup.get(with_child.session_id) is not None
    assert sup.get(newest.session_id) is not None
    assert sup.get(plain.session_id) is None
    for record in sup.children_of(with_child.session_id):
        await sup.stop(record.session_id)


# ── BUG 1: inbox-drain-on-settle (server-side stranding race) ──────────────────


async def test_finish_run_restarts_stranded_inbox_message():
    # The drain-settle race: a send_message POST lands in the window between
    # the engine's LAST drain_inbox() (empty → the engine settles) and the
    # state flipping to IDLE. The message is appended to the inbox with the
    # state still RUNNING, the engine settles, and WITHOUT the fix nothing
    # consumes it — the browser rendered its echo ("looks sent") but no turn
    # ever answers it. The fix restarts a fresh turn from the stranded inbox.
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    record.current_leaf_trace_id = "tr-0"
    sid = record.session_id

    first_running = asyncio.Event()
    release_first = asyncio.Event()
    restart_bodies: list[dict] = []

    async def _run(self, record, policy, io, initial_body=None):
        if not first_running.is_set():
            # FIRST turn: pause so the test can POST a message while RUNNING…
            first_running.set()
            await release_first.wait()
            # …then settle idle WITHOUT draining it (its send landed after the
            # engine's last drain — the stranding window).
            record.state = RunState.IDLE
            record.idle_reason = "done"
            return
        # SECOND turn = the settle-triggered restart. Capture its seed body.
        restart_bodies.append(initial_body)
        record.state = RunState.IDLE
        record.idle_reason = "done"

    with patch.object(ConversationEngine, "run", _run):
        sup.start_run(sid, {"messages": [{"role": "user", "content": "go"}]})
        await first_running.wait()
        # A user message POSTs while the turn is RUNNING: appended to the inbox
        # and echoed onto the bus (echo-once — send_message echoes at enqueue).
        assert sup.send_message(sid, "did it work?") is not None
        conv = sup._conversations[sid]
        assert [m.content for m in conv.inbox] == ["did it work?"]
        release_first.set()
        await _wait_for(lambda: len(restart_bodies) == 1)

    # The stranded message rode a fresh turn (no stranding) with the EXACT
    # idle re-arm shape: unframed message + current leaf, no auto_mode (the
    # record is interactive) — indistinguishable from a live send_message
    # idle-start.
    assert restart_bodies[0] == {
        "messages": [{"role": "user", "content": "did it work?"}],
        "trace_id": "tr-0",
    }
    # The restart drained the inbox — nothing left stranded.
    assert conv.inbox == []
    assert record.state == RunState.IDLE
    # Echo-once: the message was echoed exactly once (at send_message enqueue),
    # NOT re-echoed by the restart.
    buffered = b"".join(conv.bus.buffer).decode()
    assert buffered.count("did it work?") == 1


async def test_stop_does_not_restart_stranded_inbox(hang_engine):
    # The inbox-drain-on-settle restart is scoped to a NATURAL settle: an
    # explicit stop must NOT resurrect a run. stop() awaits the cancelled task
    # (whose _finish_run runs with restart_stranded_inbox=False) then calls
    # _finish_run AGAIN as a backstop, relying on run-once — a restart on the
    # cancel path would double-settle. (The client-side flush owns re-sending a
    # stopped conversation's queue.)
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    record.current_leaf_trace_id = "tr-0"
    sid = record.session_id
    sup.start_run(sid, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)
    conv = sup._conversations[sid]
    # A message queues into the inbox while the turn is RUNNING.
    assert sup.send_message(sid, "queued") is not None
    assert [m.content for m in conv.inbox] == ["queued"]

    await sup.stop(sid)

    # Idle after the stop, and the stranded message was NOT auto-restarted:
    # conv.task stays None (no new turn) and the inbox is untouched.
    assert record.state == RunState.IDLE
    assert conv.task is None
    assert [m.content for m in conv.inbox] == ["queued"]
