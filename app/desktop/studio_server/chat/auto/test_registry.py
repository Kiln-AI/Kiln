"""AutoChatRegistry + AutoChatRun.emit / AutoChatEventBus unit tests."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest

from . import registry as registry_mod
from .events import KeepalivePing, iter_with_keepalive
from .models import AutoChatSeed, AutoRunRecord, AutoRunStatus, InboundMessage
from .registry import AutoChatConcurrencyError, AutoChatRegistry, AutoChatRun
from .test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    finish_tool_calls,
    text_delta,
    tool_input_available,
    trace,
)

URL = "https://example.test/v1/chat"


def _seed(trace_id: str = "tr-0") -> AutoChatSeed:
    return AutoChatSeed(trace_id=trace_id, enable_tool_call_id="enable-1")


async def _wait_terminal(reg: AutoChatRegistry, run_id: str, timeout: float = 2.0):
    async def _poll():
        while True:
            run = reg.get(run_id)
            if run is None or run.record.status.is_terminal:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)


async def _wait_settled(reg: AutoChatRegistry, run_id: str, timeout: float = 2.0):
    """Wait until a burst settles — the run leaves RUNNING (→ IDLE or off)."""

    async def _poll():
        while True:
            run = reg.get(run_id)
            if run is None or run.record.status != AutoRunStatus.RUNNING:
                return
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout)


# Back-compat alias: most legacy tests wait for the burst to settle, which under
# Revision R1 is IDLE (flag on) rather than a terminal status.
_wait_idle = _wait_settled


class _GatedClient:
    """Fake client whose single round blocks until `release` is set, then emits a
    text turn and finishes. Lets a test observe a run while it is still RUNNING."""

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release
        self.bodies = []

    def stream(self, method, url, *, content, headers):
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
        yield text_delta("done")
        yield finish("stop")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_cap_enforced():
    reg = AutoChatRegistry(max_concurrent=2)
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec_a = reg.start(_seed("a"), reason=None, upstream_url=URL, headers={})
        rec_b = reg.start(_seed("b"), reason=None, upstream_url=URL, headers={})
        # Both slots taken → a third start is rejected (no queueing).
        with pytest.raises(AutoChatConcurrencyError):
            reg.start(_seed("c"), reason=None, upstream_url=URL, headers={})
        assert len(reg.list_active()) == 2
        # Revision R1: settling to IDLE keeps the conversation flag on, so the
        # slots stay taken — the cap counts flag-on (RUNNING or IDLE) runs.
        release.set()
        await _wait_settled(reg, rec_a.run_id)
        await _wait_settled(reg, rec_b.run_id)
        with pytest.raises(AutoChatConcurrencyError):
            reg.start(_seed("c"), reason=None, upstream_url=URL, headers={})
        # Explicitly stopping one frees its slot; a new start then succeeds.
        await reg.stop(rec_a.run_id)
        rec_c = reg.start(_seed("c"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec_c.run_id)


@pytest.mark.asyncio
async def test_on_trace_updates_index_and_record():
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason="why", upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)

    run = reg.get(rec.run_id)
    assert run is not None
    assert run.record.reason == "why"
    assert "tr-0" in run.record.seen_trace_ids
    assert "tr-1" in run.record.seen_trace_ids
    assert run.record.current_trace_id == "tr-1"
    # Index keeps both ids; the run is now IDLE (flag on), so run_id_for_trace
    # still resolves both leaves to the live run.
    assert reg._trace_index["tr-1"] == rec.run_id
    assert reg.run_id_for_trace("tr-1") == rec.run_id


@pytest.mark.asyncio
async def test_resolve_trace_stale_in_chain_returns_run_and_current_leaf():
    """A hard-refresh tab holds the STALE seed leaf (tr-0); the run advanced to
    tr-1 while it was gone. resolve_trace matches via the whole-chain index and
    returns the run id + the run's CURRENT leaf so the client can catch up."""
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)

    # Stale leaf (tr-0) still resolves to the active run, current leaf is tr-1,
    # and the run's status is surfaced (settled → IDLE).
    assert reg.resolve_trace("tr-0") == (rec.run_id, "tr-1", AutoRunStatus.IDLE)
    # Current leaf resolves too.
    assert reg.resolve_trace("tr-1") == (rec.run_id, "tr-1", AutoRunStatus.IDLE)


@pytest.mark.asyncio
async def test_resolve_trace_unknown_returns_none():
    reg = AutoChatRegistry()
    assert reg.resolve_trace("never-seen") is None


@pytest.mark.asyncio
async def test_resolve_trace_none_when_flag_off():
    """Once auto mode is off for the conversation the trace no longer resolves to
    an active run (resync should fall back to the normal restored state)."""
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        # While the burst is in-flight resolve reports RUNNING (the gated client
        # blocks the round open) so a resyncing client shows the thinking state.
        assert reg.resolve_trace("tr-0") == (rec.run_id, "tr-0", AutoRunStatus.RUNNING)
        release.set()
        await _wait_settled(reg, rec.run_id)
        await reg.stop(rec.run_id)

    assert reg.resolve_trace("tr-0") is None


@pytest.mark.asyncio
async def test_is_active_for_trace_true_while_running_and_idle_false_when_off():
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        # Active while running.
        active, rid = reg.is_active_for_trace("tr-0")
        assert active and rid == rec.run_id
        release.set()
        await _wait_settled(reg, rec.run_id)

        # Revision R1: still active while IDLE (flag on) — the green dot persists.
        run = reg.get(rec.run_id)
        assert run is not None and run.record.status == AutoRunStatus.IDLE
        active, rid = reg.is_active_for_trace("tr-0")
        assert active and rid == rec.run_id
        assert len(reg.list_active()) == 1

        # Explicit stop clears the flag → no longer active.
        await reg.stop(rec.run_id)

    active, rid = reg.is_active_for_trace("tr-0")
    assert active is False and rid is None
    assert reg.list_active() == []


@pytest.mark.asyncio
async def test_stop_is_hard_cancel_ends_immediately():
    # Hard stop: Stop cancels the in-flight burst immediately rather than waiting
    # for the round to finish. The run goes terminal (USER_STOPPED) and publishes
    # auto-mode-off(user_stopped) without the gated round ever being released, and
    # never surfaces tool-calls-pending for approval.
    reg = AutoChatRegistry()
    release = asyncio.Event()  # the round blocks here until cancelled
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None
        sub = run.bus.subscribe()
        received: list[bytes] = []

        async def _drain():
            async for b in sub:
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.05)  # let the run start + buffer replay
        # Stop while the round is still blocked open. The burst is cancelled
        # mid-round and goes terminal immediately — the gate is never released.
        await reg.stop(rec.run_id)
        await _wait_terminal(reg, rec.run_id)
        await asyncio.sleep(0.02)
        drain_task.cancel()
        release.set()  # cleanup: unblock the gated client

    assert run.record.status == AutoRunStatus.USER_STOPPED
    decoded = b"".join(received).decode()
    assert '"type": "auto-mode-off"' in decoded
    assert '"reason": "user_stopped"' in decoded
    assert '"type": "tool-calls-pending"' not in decoded


@pytest.mark.asyncio
async def test_client_disconnect_does_not_cancel_run():
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None

        # A subscriber connects then disconnects mid-run.
        sub = run.bus.subscribe()
        await sub.__anext__()  # pull at least one buffered byte
        await sub.aclose()  # client disconnect
        assert run.record.status == AutoRunStatus.RUNNING

        # The run keeps advancing despite the dropped subscriber.
        release.set()
        await _wait_idle(reg, rec.run_id)

    assert run.record.status == AutoRunStatus.IDLE


async def _subscribe_replay(run, *, settle: float = 0.05) -> str:
    """Subscribe to a run's bus and collect the on-subscribe replay (buffer +
    current-state marker) as a decoded string, then disconnect. Reads until the
    subscriber's queue is momentarily empty (the replay is yielded eagerly before
    the live ``await queue.get()``)."""
    sub = run.bus.subscribe()
    received: list[bytes] = []

    async def _drain():
        async for b in sub:
            received.append(b)

    task = asyncio.create_task(_drain())
    await asyncio.sleep(settle)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await sub.aclose()
    return b"".join(received).decode()


@pytest.mark.asyncio
async def test_subscribe_emits_working_state_marker_for_running_mid_think():
    """Phase 9: a RUNNING burst momentarily between events (the trace boundary
    cleared the buffer, the model is thinking server-side) must still tell a
    re-attaching observer it is WORKING — otherwise the transcript looks done
    until the next event lands."""
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None
        # Let the round open (trace("tr-1") clears the buffer) and block before
        # the next event: RUNNING with an empty current-turn buffer.
        await asyncio.sleep(0.05)
        assert run.record.status == AutoRunStatus.RUNNING
        assert run.buffer == []

        replay = await _subscribe_replay(run)
        # The on-subscribe state marker reports working so the client shows the
        # thinking indicator immediately, with no preceding event.
        assert '"type": "auto-mode-state"' in replay
        assert '"working": true' in replay
        assert '"flag_on": true' in replay

        release.set()
        await _wait_settled(reg, rec.run_id)


@pytest.mark.asyncio
async def test_subscribe_emits_idle_marker_for_idle_run():
    """Phase 9: an IDLE run (flag on, burst settled) tells a re-attaching observer
    it is idle/armed (working off → "· waiting for you")."""
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)
        run = reg.get(rec.run_id)
        assert run is not None
        assert run.record.status == AutoRunStatus.IDLE

        replay = await _subscribe_replay(run)
        # Idle marker conveys working-off; no working state marker (which would
        # double-fire confusingly).
        assert '"type": "auto-mode-idle"' in replay
        assert '"type": "auto-mode-state"' not in replay


@pytest.mark.asyncio
async def test_subscribe_emits_idle_marker_for_armed_run():
    """Phase 9: a manually-armed run (created IDLE, never ran a burst) is idle —
    the re-attaching observer sees the idle marker (waiting for you)."""
    reg = AutoChatRegistry()
    client = FakeUpstreamClient([])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(
            AutoChatSeed(trace_id="tr-0"), reason=None, upstream_url=URL, headers={}
        )
        await asyncio.sleep(0.02)
        run = reg.get(rec.run_id)
        assert run is not None
        assert run.record.status == AutoRunStatus.IDLE

        replay = await _subscribe_replay(run)
        # The armed run's buffered on→idle markers replay, conveying flag-on/idle.
        assert '"type": "auto-mode-idle"' in replay
        assert '"reason": "armed"' in replay
        assert '"type": "auto-mode-state"' not in replay


@pytest.mark.asyncio
async def test_terminal_ttl_gc_evicts_only_off_runs(monkeypatch):
    monkeypatch.setattr(registry_mod, "TERMINAL_TTL_SECONDS", 0.05)
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)
        # Revision R1: an IDLE run (flag on) is NOT GC'd — it persists.
        await asyncio.sleep(0.15)
        assert reg.get(rec.run_id) is not None
        assert reg._trace_index["tr-1"] == rec.run_id

        # Explicitly stopping it (flag off) schedules terminal GC.
        await reg.stop(rec.run_id)
        await asyncio.sleep(0.15)  # let GC fire

    assert reg.get(rec.run_id) is None
    assert "tr-0" not in reg._trace_index
    assert "tr-1" not in reg._trace_index


# ── Revision R1: send_message / disable ───────────────────────────────────────


@pytest.mark.asyncio
async def test_send_message_while_running_enqueues():
    reg = AutoChatRegistry()
    release = asyncio.Event()  # keep the burst RUNNING
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None
        await asyncio.sleep(0.02)
        assert run.record.status == AutoRunStatus.RUNNING

        accepted = reg.send_message(rec.run_id, InboundMessage(content="inject me"))
        assert accepted is True
        # Queued for drain at the next round boundary; no new burst started.
        assert [m.content for m in run.inbound] == ["inject me"]
        # Echoed onto the bus/buffer for observers.
        assert b"inject me" in b"".join(run.buffer)

        # Graceful stop: release the round so the burst winds down cleanly.
        await reg.stop(rec.run_id)
        release.set()
        await _wait_terminal(reg, rec.run_id)


@pytest.mark.asyncio
async def test_send_message_echo_carries_message_id():
    # The echoed user-message event carries the injected message's stable id so a
    # re-attaching client can dedupe a replayed echo against a message it shows.
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None
        await asyncio.sleep(0.02)

        msg = InboundMessage(content="inject me")
        assert msg.id.startswith("am_")
        assert reg.send_message(rec.run_id, msg) is True

        echo = next(
            e
            for e in (
                json.loads(line[6:].strip())
                for chunk in run.buffer
                for line in chunk.decode().split("\n")
                if line.startswith("data: ") and line[6:].strip()
            )
            if isinstance(e, dict) and e.get("type") == "user-message"
        )
        assert echo["content"] == "inject me"
        assert echo["id"] == msg.id

        await reg.stop(rec.run_id)
        release.set()
        await _wait_terminal(reg, rec.run_id)


@pytest.mark.asyncio
async def test_send_message_while_idle_starts_new_burst():
    reg = AutoChatRegistry()
    # First burst settles IDLE; second burst (from /message) runs to settle too.
    burst1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    burst2 = [trace("tr-2"), text_delta("resumed"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=burst1), FakeUpstreamResponse(chunks=burst2)]
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)
        run = reg.get(rec.run_id)
        assert run is not None and run.record.status == AutoRunStatus.IDLE

        accepted = reg.send_message(
            rec.run_id, InboundMessage(content="resume please", trace_id="tr-1")
        )
        assert accepted is True
        # A fresh burst is running.
        assert run.record.status == AutoRunStatus.RUNNING
        await _wait_settled(reg, rec.run_id)

    # The second burst was seeded with the queued user message.
    second_body = client.bodies[1]
    assert second_body["messages"] == [{"role": "user", "content": "resume please"}]


@pytest.mark.asyncio
async def test_idle_resume_carries_conversation_id_from_run_state():
    # Regression: an idle→running resume rebuilds a fresh AutoChatSeed. The
    # conversation_id must be recovered from run state (the client does not
    # re-send it on /message), otherwise the resumed burst runs with
    # conversation_id=None — silently disabling the budget gate and spend
    # tracking for exactly the "budget exhausted → extend → continue" flow.
    conversation_id = "1f2e3d4c-5b6a-4789-8abc-def012345678"
    reg = AutoChatRegistry()
    burst1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    burst2 = [trace("tr-2"), text_delta("resumed"), finish("stop")]
    client = FakeUpstreamClient(
        [FakeUpstreamResponse(chunks=burst1), FakeUpstreamResponse(chunks=burst2)]
    )
    seed = AutoChatSeed(
        trace_id="tr-0",
        enable_tool_call_id="enable-1",
        conversation_id=conversation_id,
    )
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(seed, reason=None, upstream_url=URL, headers={})
        # The run persists the identity so it survives seed reconstruction.
        run = reg.get(rec.run_id)
        assert run is not None
        assert run.record.conversation_id == conversation_id

        await _wait_settled(reg, rec.run_id)
        assert run.record.status == AutoRunStatus.IDLE

        # Resume via /message WITHOUT re-supplying conversation_id.
        accepted = reg.send_message(
            rec.run_id, InboundMessage(content="resume please", trace_id="tr-1")
        )
        assert accepted is True
        await _wait_settled(reg, rec.run_id)

    # The resumed burst's upstream continuation carries the conversation_id,
    # so the backend keeps persisting it and the gate/credit stay active.
    second_body = client.bodies[1]
    assert second_body["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_send_message_unknown_or_off_returns_false():
    reg = AutoChatRegistry()
    assert reg.send_message("ar_nope", InboundMessage(content="x")) is False


@pytest.mark.asyncio
async def test_manual_enable_arms_without_empty_upstream_turn():
    # Manual enable (functional spec §4.1(2)): a seed with no enable_tool_call_id,
    # no pending tool calls, and no extra messages only ARMS the conversation. The
    # registry must NOT start a burst (an empty upstream POST errors at the
    # backend) — the run is created IDLE (flag on, indicator shown) with no task.
    reg = AutoChatRegistry()
    client = FakeUpstreamClient([])  # any upstream POST would raise (no responses)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(
            AutoChatSeed(trace_id="tr-0"),
            reason=None,
            upstream_url=URL,
            headers={},
        )
        await asyncio.sleep(0.02)
        run = reg.get(rec.run_id)
        assert run is not None
        # Armed: IDLE, flag on, no supervising task, NO upstream POST.
        assert run.record.status == AutoRunStatus.IDLE
        assert run.record.status.flag_on is True
        assert rec.run_id not in reg._tasks
        assert client.bodies == []
        # The on→idle markers are buffered so a connecting observer lands on
        # flag-on/idle (waiting for you).
        buffered = b"".join(run.buffer).decode()
        assert '"type": "auto-mode-on"' in buffered
        assert '"type": "auto-mode-idle"' in buffered
        assert '"reason": "armed"' in buffered

        # The FIRST /message starts the burst (IDLE → RUNNING), now WITH content.
        burst = [trace("tr-1"), text_delta("on it"), finish("stop")]
        client._responses.append(FakeUpstreamResponse(chunks=burst))
        accepted = reg.send_message(
            rec.run_id, InboundMessage(content="please start", trace_id="tr-0")
        )
        assert accepted is True
        assert run.record.status == AutoRunStatus.RUNNING
        await _wait_settled(reg, rec.run_id)

    # The first (and only) upstream body carried the user message — never empty.
    assert len(client.bodies) == 1
    assert client.bodies[0]["messages"] == [{"role": "user", "content": "please start"}]


@pytest.mark.asyncio
async def test_no_trace_seed_starts_running_and_indexes_on_first_trace():
    # Revision R2: enabling on a brand-new conversation. The seed carries the
    # first user message and NO trace_id, so the run starts RUNNING (not the
    # armed-only IDLE case) and POSTs the message (never empty). The backend
    # mints the first trace, which _on_trace records in the index.
    reg = AutoChatRegistry()
    burst = [trace("tr-new-1"), text_delta("on it"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=burst)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(
            AutoChatSeed(
                trace_id=None,
                extra_messages=[{"role": "user", "content": "first message"}],
            ),
            reason=None,
            upstream_url=URL,
            headers={},
        )
        # Created RUNNING (real content to run), no trace index entry yet, and a
        # supervising task is spawned.
        assert rec.status == AutoRunStatus.RUNNING
        assert rec.current_trace_id is None
        assert rec.run_id in reg._tasks
        assert reg._trace_index == {}
        await _wait_settled(reg, rec.run_id)
        run = reg.get(rec.run_id)
        assert run is not None
        # First trace minted by the backend now indexes the run.
        assert run.record.current_trace_id == "tr-new-1"
        assert reg._trace_index["tr-new-1"] == rec.run_id
        assert reg.run_id_for_trace("tr-new-1") == rec.run_id

    # The opening POST carried the first user message with NO trace_id — never
    # empty (no "No messages were sent" backend error).
    assert len(client.bodies) == 1
    assert "trace_id" not in client.bodies[0]
    assert client.bodies[0]["messages"] == [
        {"role": "user", "content": "first message"}
    ]


@pytest.mark.asyncio
async def test_disable_for_trace_clears_idle_flag_and_publishes_off():
    # The interactive disable path: the conversation has settled IDLE and the
    # model called disable_auto_mode. disable_for_trace clears the flag
    # (USER_DISABLED) and publishes auto-mode-off(user_disabled).
    reg = AutoChatRegistry()
    burst1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=burst1)])
    received: list[bytes] = []
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_settled(reg, rec.run_id)
        run = reg.get(rec.run_id)
        assert run is not None and run.record.status == AutoRunStatus.IDLE

        async def _drain():
            async for b in run.bus.subscribe():
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.02)

        # tr-1 was indexed via on_trace during the first burst.
        assert await reg.disable_for_trace("tr-1") is True
        await asyncio.sleep(0.02)
        drain_task.cancel()

    assert run.record.status == AutoRunStatus.USER_DISABLED
    decoded = b"".join(received).decode()
    assert '"reason": "user_disabled"' in decoded


@pytest.mark.asyncio
async def test_disable_for_trace_unknown_returns_false():
    reg = AutoChatRegistry()
    assert await reg.disable_for_trace("tr-nope") is False


class _GatedToolClient:
    """Fake client driving two rounds: round 1 is a (server-resolved) tool call
    whose first chunk blocks until ``release`` is set — letting a test inject a
    message into the ACTIVE burst before the round boundary drain — then round 2
    is a plain text turn that settles the burst."""

    def __init__(self, release: asyncio.Event) -> None:
        self._release = release
        self.bodies: list = []
        self._round = 0

    def stream(self, method, url, *, content, headers):
        self.bodies.append(json.loads(content.decode()))
        self._round += 1
        if self._round == 1:
            return _GatedToolResponse(self._release)
        return _GatedToolResponse(None, text=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _GatedToolResponse:
    def __init__(self, release: asyncio.Event | None, text: bool = False) -> None:
        self.status_code = 200
        self._release = release
        self._text = text

    async def aread(self):
        return b""

    async def aiter_bytes(self):
        if self._text:
            yield trace("tr-2")
            yield text_delta("done")
            yield finish("stop")
            return
        # Round 1: a tool call. Block before the round completes so a test can
        # inject a message into the still-RUNNING burst.
        if self._release is not None:
            await self._release.wait()
        yield tool_input_available("tc1", "add", {"a": 1, "b": 1})
        yield trace("tr-1")
        yield finish_tool_calls()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_inject_during_active_burst_echoes_message_exactly_once():
    # CR Moderate 1: the COMBINED registry+runner path. A message injected into an
    # active (RUNNING) burst is echoed by the registry on enqueue; the runner must
    # NOT echo it again at drain time. Assert the user-message echo appears exactly
    # once across the whole stream.
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedToolClient(release)
    received: list[bytes] = []
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None

        async def _drain():
            async for b in run.bus.subscribe():
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.02)
        assert run.record.status == AutoRunStatus.RUNNING

        # Inject while the burst is RUNNING (round 1 is gated). The runner drains
        # this at the round boundary and appends it to the continuation.
        accepted = reg.send_message(rec.run_id, InboundMessage(content="inject me"))
        assert accepted is True

        release.set()  # let round 1 complete → tool runs → drain → round 2
        await _wait_settled(reg, rec.run_id)
        await asyncio.sleep(0.02)
        drain_task.cancel()

    # The message was appended to the round-2 continuation (drained by the runner),
    # framed as a side note so the model answers inline and keeps working.
    second_body = client.bodies[1]
    user_messages = [m for m in second_body["messages"] if m.get("role") == "user"]
    assert len(user_messages) == 1
    assert "inject me" in user_messages[0]["content"]
    assert "<system-reminder>" in user_messages[0]["content"]

    # The user-message echo appears EXACTLY ONCE across the whole observer stream
    # (registry echoes on enqueue; the runner must not re-echo on drain).
    user_message_events = [
        e
        for e in (
            json.loads(line[6:].strip())
            for chunk in received
            for line in chunk.decode().split("\n")
            if line.startswith("data: ") and line[6:].strip()
        )
        if isinstance(e, dict)
        and e.get("type") == "user-message"
        and e.get("content") == "inject me"
    ]
    assert len(user_message_events) == 1


@pytest.mark.asyncio
async def test_disable_while_burst_running_ends_off_not_idle():
    # CR Moderate 2: disable() while a burst is RUNNING must cancel it and leave
    # the run OFF (USER_DISABLED) — _supervise must NOT re-settle it to IDLE (which
    # would re-enable the flag and republish the idle marker).
    reg = AutoChatRegistry()
    release = asyncio.Event()  # never set → the burst stays RUNNING
    client = _GatedClient(release)
    received: list[bytes] = []
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None

        async def _drain():
            async for b in run.bus.subscribe():
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.05)  # let the burst start (tr-0 indexed at start())
        assert run.record.status == AutoRunStatus.RUNNING

        # Disable mid-burst (the interactive disable_auto_mode path). tr-0 is
        # indexed at start(); the gated round never completes so tr-1 isn't.
        assert await reg.disable_for_trace("tr-0") is True
        await asyncio.sleep(0.05)
        drain_task.cancel()

    # Ended OFF (user_disabled), NOT re-enabled to IDLE.
    assert run.record.status == AutoRunStatus.USER_DISABLED
    assert run.record.status.is_terminal is True
    assert run.record.status.flag_on is False
    assert reg.is_active_for_trace("tr-0") == (False, None)

    decoded = b"".join(received).decode()
    assert '"type": "auto-mode-off"' in decoded
    assert '"reason": "user_disabled"' in decoded
    # The idle marker must NOT have been republished (would re-enable the flag).
    assert '"type": "auto-mode-idle"' not in decoded


class TestBusAndBuffer:
    @pytest.mark.asyncio
    async def test_subscribe_replays_current_turn_then_live(self):
        reg = AutoChatRegistry()
        release = asyncio.Event()
        client = _GatedClient(release)
        with patch.object(httpx, "AsyncClient", return_value=client):
            rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
            run = reg.get(rec.run_id)
            assert run is not None
            await asyncio.sleep(0.05)  # let auto-mode-on + trace land

            # Buffer was reset after the kiln_chat_trace event, so a late
            # subscriber replays only post-snapshot bytes (currently empty),
            # then receives the live text once released.
            sub = run.bus.subscribe()
            received: list[bytes] = []

            async def _drain():
                async for b in sub:
                    received.append(b)

            drain_task = asyncio.create_task(_drain())
            await asyncio.sleep(0.02)
            release.set()
            await _wait_settled(reg, rec.run_id)
            await asyncio.sleep(0.02)
            drain_task.cancel()

        decoded = b"".join(received).decode()
        assert "done" in decoded  # live text delivered after subscribe
        # Revision R1: ended on a plain-text turn → IDLE; auto-mode-idle(asked_user)
        # is delivered live (NOT auto-mode-off — the flag stays on).
        assert '"type": "auto-mode-idle"' in decoded
        assert '"reason": "asked_user"' in decoded
        assert '"type": "auto-mode-off"' not in decoded

    @pytest.mark.asyncio
    async def test_buffer_resets_on_kiln_chat_trace(self):
        # Construct AutoChatRun directly so emit/buffer mechanics are tested in
        # isolation — no registry.start(), hence no supervising task racing the
        # run to a terminal status in the background.
        record = AutoRunRecord(
            run_id="run-test",
            status=AutoRunStatus.RUNNING,
            current_trace_id="tr-0",
            seen_trace_ids=["tr-0"],
        )
        run = AutoChatRun(
            record=record,
            seed=_seed("tr-0"),
            upstream_url=URL,
            headers={},
            on_trace=None,
        )

        # Drive emit directly to exercise the buffer reset deterministically.
        run.emit(text_delta("partial-1"))
        run.emit(text_delta("partial-2"))
        assert len(run.buffer) == 2
        run.emit(trace("tr-9"))  # snapshot boundary → buffer cleared after
        assert run.buffer == []
        run.emit(text_delta("next-turn"))
        assert run.buffer == [text_delta("next-turn")]

    @pytest.mark.asyncio
    async def test_off_run_yields_off_marker_immediately(self):
        # A run whose flag was explicitly cleared (stopped) is terminal — a late
        # subscriber gets exactly the off marker and the stream ends. Graceful
        # stop: request stop, then let the in-flight round finish so the burst
        # winds down to USER_STOPPED before the late subscribe.
        reg = AutoChatRegistry()
        release = asyncio.Event()
        client = _GatedClient(release)
        with patch.object(httpx, "AsyncClient", return_value=client):
            rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
            await asyncio.sleep(0.02)
            await reg.stop(rec.run_id)
            release.set()
            await _wait_terminal(reg, rec.run_id)
            run = reg.get(rec.run_id)
            assert run is not None
            received = [b async for b in run.bus.subscribe()]

        decoded = b"".join(received).decode()
        assert '"type": "auto-mode-off"' in decoded

    @pytest.mark.asyncio
    async def test_idle_run_yields_idle_marker_on_subscribe(self):
        # Revision R1: a settled IDLE run (flag on) is not terminal — a late
        # subscriber gets the idle marker then stays subscribed for the next
        # burst. Collect only the replay + marker, then cancel.
        reg = AutoChatRegistry()
        round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
        client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
        received: list[bytes] = []
        with patch.object(httpx, "AsyncClient", return_value=client):
            rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
            await _wait_settled(reg, rec.run_id)
            run = reg.get(rec.run_id)
            assert run is not None and run.record.status == AutoRunStatus.IDLE

            async def _drain():
                async for b in run.bus.subscribe():
                    received.append(b)

            drain_task = asyncio.create_task(_drain())
            await asyncio.sleep(0.02)
            drain_task.cancel()

        decoded = b"".join(received).decode()
        assert '"type": "auto-mode-idle"' in decoded
        assert '"type": "auto-mode-off"' not in decoded

    @pytest.mark.asyncio
    async def test_keepalive_injects_pings(self):
        reg = AutoChatRegistry()
        release = asyncio.Event()
        client = _GatedClient(release)
        with patch.object(httpx, "AsyncClient", return_value=client):
            rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
            run = reg.get(rec.run_id)
            assert run is not None
            await asyncio.sleep(0.02)

            saw_ping = False
            it = iter_with_keepalive(run.bus.subscribe(), timeout_seconds=0.02)
            async for item in it:
                if isinstance(item, KeepalivePing):
                    saw_ping = True
                    break
            await it.aclose()
            release.set()
            await _wait_settled(reg, rec.run_id)

        assert saw_ping
