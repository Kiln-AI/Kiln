"""ConversationSupervisor unit tests: lifecycle, settle-once (+ the
cancel-before-first-run backstop), the auto cap, auto enable/disable/stop,
approvals and recovery, eviction."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import httpx
import pytest

from app.desktop.studio_server.chat.debug_log import ENV_VAR as DEBUG_LOG_ENV_VAR
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
from .models import InboundMessage, RunState
from .supervisor import ConversationCapError, ConversationSupervisor

URL = "https://example.test/v1/chat"


def _sup(**kwargs) -> ConversationSupervisor:
    return ConversationSupervisor(**kwargs)


@pytest.fixture
def hang_engine():
    """Patch the engine to hang until cancelled — lifecycle tests drive the
    supervisor, not the network loop."""

    async def _hang(self, record, policy, io, initial_body=None) -> None:
        await asyncio.Event().wait()

    with patch.object(ConversationEngine, "run", _hang):
        yield


async def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async def _poll():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)


def _text_run_responses(final_text: str = "done") -> list[FakeUpstreamResponse]:
    return [FakeUpstreamResponse([text_delta(final_text), trace("tr-1"), finish()])]


def _seeded_conversation(
    sup: ConversationSupervisor, leaf: str, kind: str = "interactive"
):
    """A live conversation already holding a persisted leaf (same shape
    adopt/on_trace produce)."""
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


async def test_stop_cancels_hung_interactive_turn(hang_engine):
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)  # let the run task start hanging
    assert record.state == RunState.RUNNING
    await sup.stop(record.session_id)
    assert record.state == RunState.IDLE
    assert sup._conversations[record.session_id].task is None
    # Idempotent: a second stop is a no-op.
    await sup.stop(record.session_id)
    assert record.state == RunState.IDLE


async def test_cancel_before_first_run_backstop_settles(hang_engine):
    # A task cancelled before it ever ran never enters _supervise, so its
    # finally never fires — stop()'s backstop must settle it.
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    # NO awaits between start and stop: the created task has not run yet.
    await sup.stop(record.session_id)
    conv = sup._conversations[record.session_id]
    assert record.state == RunState.IDLE
    assert conv.task is None
    assert conv.run_finished is True


async def test_engine_exception_idles_auto_with_flag_on():
    async def _boom(self, record, policy, io, initial_body=None) -> None:
        raise RuntimeError("kaboom")

    sup = _sup()
    with patch.object(ConversationEngine, "run", _boom):
        auto = sup.create_conversation("auto", upstream_url=URL, headers={})
        sup.start_run(
            auto.session_id, {"messages": [{"role": "user", "content": "go"}]}
        )
        await _wait_for(lambda: auto.state == RunState.IDLE)
        # The burst failed but the conversation survives with the flag on.
        assert auto.idle_reason == "error"
        assert auto.auto_flag is True


async def test_engine_timeout_error_idles_with_error():
    # On Python ≥ 3.11 asyncio.TimeoutError IS the builtin TimeoutError,
    # which any library inside the engine can raise. It classifies as the
    # generic IDLE("error"), like any other engine exception.
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
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
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


# ── Messages ──────────────────────────────────────────────────────────────────


async def test_send_message_while_running_enqueues_and_echoes(hang_engine):
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)
    message_id = sup.send_message(record.session_id, "also this")
    # The accepted message's stable id is returned (own-echo dedupe).
    assert message_id is not None and message_id.startswith("cm_")
    conv = sup._conversations[record.session_id]
    assert [m.content for m in conv.inbox] == ["also this"]
    # Echoed onto the bus + replay buffer at enqueue time (echo-once).
    buffered = b"".join(conv.bus.buffer).decode()
    assert "also this" in buffered
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

    # Idle re-arm body shape: current leaf + unframed message + auto_mode
    # riding because the flag is on.
    assert client.bodies == [
        {
            "messages": [{"role": "user", "content": "resume please"}],
            "trace_id": "tr-0",
            "auto_mode": True,
        }
    ]


async def test_upstream_requests_carry_conversation_id_header():
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses())
    record = sup.create_conversation(
        "interactive", upstream_url=URL, headers={"Authorization": "Bearer k"}
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        assert sup.send_message(record.session_id, "hello") is not None
        await _wait_for(lambda: record.state == RunState.IDLE)

    assert client.headers == [
        {"Authorization": "Bearer k", "X-Kiln-Conversation-Id": record.session_id}
    ]


async def test_debug_log_records_run_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_file = tmp_path / "chat_debug.jsonl"
    monkeypatch.setenv(DEBUG_LOG_ENV_VAR, str(log_file))
    sup = _sup()
    client = FakeUpstreamClient(_text_run_responses())
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    with patch.object(httpx, "AsyncClient", return_value=client):
        message_id = sup.send_message(record.session_id, "hello")
        await _wait_for(lambda: record.state == RunState.IDLE)

    events = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert [e["event"] for e in events] == [
        "message_starts_idle_turn",
        "run_started",
        "engine_run_started",
        "upstream_round_started",
        "run_settled",
    ]
    assert all(e["conversation_id"] == record.session_id for e in events)
    assert events[0]["message_id"] == message_id
    assert events[-1]["state"] == "idle"
    assert events[-1]["idle_reason"] == "asked_user"
    assert "hello" not in log_file.read_text()


async def test_send_message_while_running_logs_enqueue(
    hang_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    log_file = tmp_path / "chat_debug.jsonl"
    monkeypatch.setenv(DEBUG_LOG_ENV_VAR, str(log_file))
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    message_id = sup.send_message(record.session_id, "queued")

    events = [json.loads(line) for line in log_file.read_text().splitlines()]
    (enqueued,) = [e for e in events if e["event"] == "message_enqueued"]
    assert enqueued["conversation_id"] == record.session_id
    assert enqueued["message_id"] == message_id
    assert enqueued["state"] == "running"
    assert enqueued["inbox_len"] == 1
    await sup.stop(record.session_id)


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


async def test_send_message_unknown_returns_none():
    sup = _sup()
    assert sup.send_message("cv_nope", "x") is None


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
    # it (recovery rebuilds from the trace tail instead).
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    conv = sup._conversations[record.session_id]
    conv.pending_batch = object()  # type: ignore[assignment]
    await sup.stop(record.session_id)
    assert conv.pending_batch is None


# ── Auto stop semantics ───────────────────────────────────────────────────────


async def test_stop_idle_auto_clears_flag_and_publishes_off_state():
    sup = _sup()
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
    sup = _sup()
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)
    assert record.state == RunState.RUNNING
    await sup.stop(record.session_id)
    # Hard cancel mid-burst: flag off, reason preserved (the pre-marked
    # reason must survive the CancelledError handler).
    assert record.state == RunState.IDLE
    assert record.auto_flag is False
    assert record.idle_reason == "user_stopped"


# ── Auto enable ───────────────────────────────────────────────────────────────


async def test_enable_auto_armed_only_flips_idle_record_no_upstream_post():
    # Manual enable with nothing to send upstream: the record is merely ARMED
    # (flag on, IDLE("armed"), NO run task), because an empty upstream POST
    # would be rejected by the backend ("No messages were sent to the
    # server").
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


async def test_enable_auto_unknown_session_id_is_rejected():
    # An unknown sid means the record (and any consent context) died with a
    # restart — 404 at the route, never a silently forked parallel record.
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


async def test_enable_auto_consent_accept_starts_burst_with_seed_body():
    # Consent accept: the enable_auto_mode call resolves as enabled in the
    # seed body and the burst starts immediately (body shape pinned
    # end-to-end by the auto_seed_and_tool_round golden fixture).
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
    # The continuation targets the RECORD's own leaf (the engine's on_trace
    # keeps it fresh).
    assert seed_body["trace_id"] == "t1"
    assert seed_body["auto_mode"] is True
    assert seed_body["messages"][0]["tool_call_id"] == "tc_enable"
    assert json.loads(seed_body["messages"][0]["content"]) == {"status": "enabled"}
    # Burst settled → idle, flag stays on (RUNNING/IDLE vocabulary).
    assert record.auto_flag is True
    assert record.idle_reason == "asked_user"


async def test_enable_auto_busy_accept_raises_before_executing(hang_engine):
    # A consent accept racing an in-flight run must 409 (RuntimeError) with
    # NO side effects — the busy guard sits before the flag flip and before
    # execute_tool_batch, so no pending call executes behind the 409 and the
    # interactive record is left untouched: not flipped to auto with no
    # seeded burst (the racing run started under the interactive policy, so
    # _finish_run would never swap it back) and holding no auto-cap slot.
    from unittest.mock import AsyncMock

    from app.desktop.studio_server.chat.stream_session import ToolCallInfo

    from . import supervisor as supervisor_module

    sup = _sup(auto_max_concurrent=1)
    seeded = _seeded_conversation(sup, "t1")
    sup.start_run(seeded.session_id, {"messages": [{"role": "user", "content": "x"}]})

    execute_mock = AsyncMock(return_value={"tc_add": "2"})
    with patch.object(supervisor_module, "execute_tool_batch", execute_mock):
        with pytest.raises(RuntimeError, match="already has a run in flight"):
            await sup.enable_auto(
                session_id=seeded.session_id,
                enable_tool_call_id="tc_enable",
                pending_tool_calls=[
                    ToolCallInfo(
                        toolCallId="tc_add",
                        toolName="add",
                        input={"a": 1, "b": 1},
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
    # Enable on a brand-new conversation — no session_id, the first user
    # message rides extra_messages; the backend mints the first trace, which
    # then indexes the conversation.
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
    # — the policy flips on the SAME run; no second record per conversation).
    sup = _sup()
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


# ── Auto disable ──────────────────────────────────────────────────────────────


async def test_disable_auto_cancels_running_burst(hang_engine):
    sup = _sup()
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    await asyncio.sleep(0.02)
    assert record.state == RunState.RUNNING

    assert await sup.disable_auto(record.session_id) is True
    # Pre-marked reason survives the cancel: the flag cleared with
    # user_disabled, NOT user_stopped.
    assert record.auto_flag is False
    assert record.idle_reason == "user_disabled"
    assert record.state == RunState.IDLE
    # Off semantics: the record swapped back to its interactive life (kind +
    # policy) and joins the idle-interactive pool.
    assert record.kind == "interactive"
    assert sup._conversations[record.session_id].policy.approvals == "gated"


async def test_disable_auto_idle_branch_publishes_off_and_swaps_interactive():
    sup = _sup()
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
    # The published off event has the auto shape (kind=auto, flag off,
    # reason) — the interactive swap happens after the publish.
    assert states[-1]["auto_flag"] is False
    assert states[-1]["idle_reason"] == "user_disabled"
    assert states[-1]["kind"] == "auto"
    # An off-auto conversation IS an idle interactive conversation (policy +
    # kind swapped on the SAME record).
    assert record.kind == "interactive"
    assert sup._conversations[record.session_id].policy.approvals == "gated"
    # Idempotent re-disable; unknown ids report False (route maps semantics).
    assert await sup.disable_auto(record.session_id) is True
    assert await sup.disable_auto("cv_missing") is False


async def test_set_auto_flag_outcomes():
    sup = _sup(auto_max_concurrent=1)
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    assert await sup.set_auto_flag("cv_missing", True) == "not_found"
    # enabled=false → disable semantics + the interactive swap.
    assert await sup.set_auto_flag(record.session_id, False) == "ok"
    assert record.auto_flag is False and record.idle_reason == "user_disabled"
    assert record.kind == "interactive"
    # enabled=true on the (now interactive) record → the flip: policy + kind
    # swap to auto, ARMED shape, cap re-checked (the only slot is free again).
    assert await sup.set_auto_flag(record.session_id, True) == "ok"
    assert record.auto_flag is True and record.idle_reason == "armed"
    assert record.kind == "auto"
    assert sup._conversations[record.session_id].policy.approvals == "auto"


# ── Trace-index join (sessions-list only) ─────────────────────────────────────


async def test_auto_record_for_trace_matches_stale_leaf_and_filters():
    # The whole-chain lookup powering routes.py's sessions-list auto join
    # (the upstream sessions LIST is leaf-keyed).
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


# ── Eviction ──────────────────────────────────────────────────────────────────


async def test_off_auto_record_survives_as_idle_interactive():
    # Stopping an auto conversation swaps it back to an idle INTERACTIVE
    # record (LRU-bounded), so the conversation can simply continue
    # interactively.
    sup = _sup()
    record = sup.create_conversation("auto", upstream_url=URL, headers={})
    await sup.stop(record.session_id)  # flag off → interactive swap
    await asyncio.sleep(0.05)
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
    # LRU eviction can hit a record with a live subscriber; the evicted
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
    emits a text turn and finishes — lets a test hold a run RUNNING."""

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
    # Stopping an auto conversation swaps it back to the INTERACTIVE policy,
    # so the next send starts a normal gated turn — never an auto-approving
    # burst without an active consent (a structural safety property).
    from .models import auto_policy

    sup = _sup()
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


async def test_start_run_rejects_double_start(hang_engine):
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "go"}]})
    with pytest.raises(RuntimeError, match="already has a run in flight"):
        sup.start_run(
            record.session_id, {"messages": [{"role": "user", "content": "go"}]}
        )
    await sup.stop(record.session_id)


# ── Interactive create/adopt + approval recovery ─────────────────────────────


async def test_adopt_interactive_creates_and_is_idempotent():
    sup = _sup()
    with patch.object(
        ConversationSupervisor, "_fetch_persisted_trace", return_value=None
    ):
        record = await sup.adopt_interactive("leaf-1", upstream_url=URL, headers={})
        assert record.kind == "interactive"
        assert record.state == RunState.IDLE
        # The adopted key is stored as the RESUME key, not a leaf — the
        # backend resolves it on the first session_id continuation.
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


def _tail_trace_with_pending_calls() -> list[dict]:
    """A persisted trace tail: last assistant turn carries four tool calls —
    one answered, two signals (skipped: a pending enable and a stale
    disable), one genuinely unanswered."""
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
    # A key-adopted record has no leaf, so the batch's trace-only
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
    # approval batch.
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
    # The upstream snapshot response carries session_meta.root_id at
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
    # with decisions, continue from the batch's trace-only base (the same
    # continuation body POST /api/chat/execute-tools produced).
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

    # Trace-only base → role:tool rows (keyed by session_id for a
    # key-adopted record — the builder treats a session_id base as
    # trace-only, so the wire stays results-only). The signal siblings are
    # answered right alongside the executed call so the persisted trace has
    # no dangling tool call: the enable as declined, the stale disable with
    # the FR1 refusal.
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
    # The consent decline: the pending gating call resolves as declined +
    # denied siblings via an interactive turn.
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
    # The key-adopted record's continuation identity is its resume key
    # (session_id); a record with a live leaf would ride trace_id here.
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


async def test_decline_auto_refuses_busy(hang_engine):
    sup = _sup()
    record = sup.create_conversation("interactive", upstream_url=URL, headers={})
    sup.start_run(record.session_id, {"messages": [{"role": "user", "content": "x"}]})
    assert (
        sup.decline_auto(record.session_id, gating_tool_call_id="tc", siblings=[])
        == "busy"
    )
    await sup.stop(record.session_id)


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
    # The seed continued from the adopted conversation's key (a key-adopted
    # record has no leaf until its first persist, so the seed rides
    # session_id and the backend resolves the current leaf).
    assert client.bodies[0]["session_id"] == "leaf-1"
    assert "trace_id" not in client.bodies[0]
    assert client.bodies[0]["auto_mode"] is True


# ── Inbox-drain-on-settle (server-side stranding race) ─────────────────────────


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
