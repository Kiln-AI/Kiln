"""ByteEventBus unit tests: replay buffer semantics, trace-boundary reset,
on-subscribe marker, terminal end, and observer isolation."""

from __future__ import annotations

import asyncio

import pytest
from app.desktop.studio_server.chat.test_fakes import text_delta, trace

from .bus import BroadcastBus, ByteEventBus, extract_trace_id

MARKER = b'data: {"type": "conversation-state"}\n\n'


async def _collect_replay(bus: ByteEventBus, settle: float = 0.05) -> list[bytes]:
    """Subscribe and collect what arrives eagerly (replay + marker + anything
    already queued), then disconnect."""
    received: list[bytes] = []
    sub = bus.subscribe()

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


class TestExtractTraceId:
    def test_returns_trace_id_for_trace_event(self):
        assert extract_trace_id(trace("tr-9")) == "tr-9"

    def test_none_for_other_events(self):
        assert extract_trace_id(text_delta("hello")) is None

    def test_none_for_non_sse_bytes(self):
        assert extract_trace_id(b"not sse at all") is None

    def test_scans_multi_line_chunks(self):
        chunk = text_delta("a") + trace("tr-multi")
        assert extract_trace_id(chunk) == "tr-multi"


class TestBufferSemantics:
    def test_emit_buffers_until_trace_boundary_then_resets(self):
        bus = ByteEventBus()
        bus.emit(text_delta("partial-1"))
        bus.emit(text_delta("partial-2"))
        assert len(bus.buffer) == 2
        # Snapshot persisted upstream: the trace event forwards, THEN the
        # buffer resets — it always holds exactly "events since the last
        # snapshot".
        bus.emit(trace("tr-9"))
        assert bus.buffer == []
        bus.emit(text_delta("next-turn"))
        assert bus.buffer == [text_delta("next-turn")]

    def test_publish_does_not_buffer(self):
        # Lifecycle markers must not replay stale to later subscribers — the
        # on-subscribe marker callback provides the fresh truth instead.
        bus = ByteEventBus()
        bus.publish(MARKER)
        assert bus.buffer == []


class TestSubscribe:
    async def test_replays_buffer_then_marker_then_live(self):
        markers: list[bytes] = [MARKER]
        bus = ByteEventBus(marker_provider=lambda: markers[0])
        bus.emit(text_delta("buffered"))

        received: list[bytes] = []
        sub = bus.subscribe()

        async def _drain():
            async for payload in sub:
                received.append(payload)

        task = asyncio.create_task(_drain())
        await asyncio.sleep(0.02)
        bus.emit(text_delta("live"))
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await sub.aclose()

        assert received == [text_delta("buffered"), MARKER, text_delta("live")]

    async def test_marker_reflects_state_at_subscribe_time(self):
        # The marker is a callback, not a stored value: it must be computed
        # fresh per subscriber (a stale marker would lie about current state).
        state = {"marker": b"first"}
        bus = ByteEventBus(marker_provider=lambda: state["marker"])
        assert (await _collect_replay(bus))[-1] == b"first"
        state["marker"] = b"second"
        assert (await _collect_replay(bus))[-1] == b"second"

    async def test_none_marker_is_skipped(self):
        bus = ByteEventBus(marker_provider=lambda: None)
        bus.emit(text_delta("only"))
        assert await _collect_replay(bus) == [text_delta("only")]

    async def test_terminal_stream_ends_after_marker(self):
        # A late subscriber to a finished one-shot run gets replay + terminal
        # marker + EOF (never hangs) — old SubAgentEventBus contract.
        bus = ByteEventBus(marker_provider=lambda: MARKER, terminal_check=lambda: True)
        bus.emit(text_delta("tail"))
        received = [payload async for payload in bus.subscribe()]
        assert received == [text_delta("tail"), MARKER]

    async def test_disconnect_only_unsubscribes(self):
        # Observer teardown is side-effect free: other subscribers keep
        # receiving, and emit never fails after a disconnect.
        bus = ByteEventBus()
        sub_a = bus.subscribe()
        received_b: list[bytes] = []
        sub_b = bus.subscribe()

        async def _drain_b():
            async for payload in sub_b:
                received_b.append(payload)

        task_b = asyncio.create_task(_drain_b())
        await asyncio.sleep(0.01)
        # A connects then disconnects mid-run.
        await sub_a.aclose()
        bus.emit(text_delta("after-disconnect"))
        await asyncio.sleep(0.02)
        task_b.cancel()
        try:
            await task_b
        except asyncio.CancelledError:
            pass
        await sub_b.aclose()

        assert received_b == [text_delta("after-disconnect")]

    async def test_events_during_replay_are_not_lost(self):
        # Subscriber registration happens BEFORE the replay is consumed, so an
        # emit that lands mid-replay queues up instead of falling in a gap.
        bus = ByteEventBus()
        bus.emit(text_delta("buffered"))
        sub = bus.subscribe()
        first = await sub.__anext__()  # consume the replayed byte
        bus.emit(text_delta("during"))
        second = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
        await sub.aclose()
        assert first == text_delta("buffered")
        assert second == text_delta("during")

    async def test_close_ends_live_subscriber_stream(self):
        # CR n3: an evicted conversation's bus is closed; a live subscriber
        # must get EOF instead of parking forever on a dead queue.
        bus = ByteEventBus()
        sub = bus.subscribe()
        received: list[bytes] = []

        async def _drain():
            async for payload in sub:
                received.append(payload)

        task = asyncio.create_task(_drain())
        await asyncio.sleep(0.01)
        bus.emit(text_delta("before close"))
        bus.close()
        # The generator ends by itself — no cancellation needed.
        await asyncio.wait_for(task, timeout=1.0)
        assert received == [text_delta("before close")]

    async def test_subscribe_after_close_ends_immediately(self):
        bus = ByteEventBus(marker_provider=lambda: MARKER)
        bus.emit(text_delta("stale"))
        bus.close()
        # No stale replay, no marker — just EOF (the conversation is gone).
        assert [payload async for payload in bus.subscribe()] == []


class TestBroadcastBusSnapshot:
    """The registry firehose's subscribe(snapshot=...) must register the
    subscriber BEFORE building the snapshot, so a conversation-state published
    while the snapshot is being built (a sub-agent spawned at that instant) is
    delivered rather than dropped — the missed-running-child bug."""

    async def test_event_published_during_snapshot_is_delivered(self):
        # THE gap test: the snapshot builder publishes an event as a side
        # effect (modelling a spawn that races snapshot construction — i.e. a
        # conversation created after list_records() would have been read but
        # before the live drain). Because the subscriber is already registered
        # when the builder runs, that event must reach us.
        bus = BroadcastBus()
        live = b"data: live-during-snapshot\n\n"
        snap = b"data: snap-a\n\n"

        def _snapshot():
            bus.publish(live)  # racing publish; subscriber already registered
            return [snap]

        gen = bus.subscribe(snapshot=_snapshot)
        got = [await asyncio.wait_for(gen.__anext__(), timeout=1.0)]
        # The event published DURING snapshot construction is drained right
        # after the snapshot rather than lost.
        got.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        await gen.aclose()
        assert got == [snap, live]

    async def test_redundant_backlog_duplicate_is_deduped(self):
        # A byte-identical re-publish of a state already in the snapshot (same
        # session + state) is dropped: nothing new for the idempotent client.
        bus = BroadcastBus()
        snap = b"data: snap-a\n\n"
        follow = b"data: live-b\n\n"

        def _snapshot():
            bus.publish(snap)  # redundant duplicate of the snapshot payload
            return [snap]

        gen = bus.subscribe(snapshot=_snapshot)
        got = [await asyncio.wait_for(gen.__anext__(), timeout=1.0)]
        # The duplicate was dropped; a later genuinely-new event still flows.
        bus.publish(follow)
        got.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        await gen.aclose()
        assert got == [snap, follow]

    async def test_transition_after_snapshot_is_never_suppressed(self):
        # Dedup must NOT hide a real transition — even one that flaps back to a
        # snapshot state. Backlog: a differing event (turns dedup off), then a
        # payload equal to the snapshot; both must be delivered.
        bus = BroadcastBus()
        running = b"data: X-running\n\n"
        idle = b"data: X-idle\n\n"

        def _snapshot():
            bus.publish(idle)  # a real change (X went idle) — must pass
            bus.publish(running)  # flap back to the snapshot state — must pass
            return [running]

        gen = bus.subscribe(snapshot=_snapshot)
        got = [await asyncio.wait_for(gen.__anext__(), timeout=1.0)]  # snapshot
        got.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        got.append(await asyncio.wait_for(gen.__anext__(), timeout=1.0))
        await gen.aclose()
        assert got == [running, idle, running]

    async def test_bare_subscribe_still_works(self):
        # Backward compatibility: subscribe() with no snapshot is the plain
        # fan-out other callers (the test drain in test_supervisor) still use.
        bus = BroadcastBus()
        gen = bus.subscribe()
        first = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.01)
        bus.publish(b"data: only\n\n")
        assert await asyncio.wait_for(first, timeout=1.0) == b"data: only\n\n"
        await gen.aclose()


@pytest.mark.asyncio
async def test_keepalive_helper_composes_with_subscribe():
    # SSE routes wrap subscribe() with the shared jobs keepalive helper; a
    # quiet window must yield pings WITHOUT tearing down the subscription
    # (the feeder-task property the helper exists for).
    from app.desktop.studio_server.jobs.events import (
        KeepalivePing,
        iter_with_keepalive,
    )

    bus = ByteEventBus()
    it = iter_with_keepalive(bus.subscribe(), timeout_seconds=0.02)
    saw_ping = False
    async for item in it:
        if isinstance(item, KeepalivePing):
            saw_ping = True
            # Prove the subscription survived the quiet window: a live emit
            # still arrives after the ping.
            bus.emit(text_delta("post-ping"))
            continue
        assert item == text_delta("post-ping")
        break
    await it.aclose()
    assert saw_ping
