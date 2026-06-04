"""AutoChatRegistry + AutoChatRun.emit / AutoChatEventBus unit tests."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest

from . import registry as registry_mod
from .events import KeepalivePing, iter_with_keepalive
from .models import AutoChatSeed, AutoRunRecord, AutoRunStatus
from .registry import AutoChatConcurrencyError, AutoChatRegistry, AutoChatRun
from .test_fakes import (
    FakeUpstreamClient,
    FakeUpstreamResponse,
    finish,
    text_delta,
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
        # Let the two runs finish, freeing slots; a new start now succeeds.
        release.set()
        await _wait_terminal(reg, rec_a.run_id)
        await _wait_terminal(reg, rec_b.run_id)
        rec_c = reg.start(_seed("c"), reason=None, upstream_url=URL, headers={})
        await _wait_terminal(reg, rec_c.run_id)


@pytest.mark.asyncio
async def test_on_trace_updates_index_and_record():
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason="why", upstream_url=URL, headers={})
        await _wait_terminal(reg, rec.run_id)

    run = reg.get(rec.run_id)
    assert run is not None
    assert run.record.reason == "why"
    assert "tr-0" in run.record.seen_trace_ids
    assert "tr-1" in run.record.seen_trace_ids
    assert run.record.current_trace_id == "tr-1"
    # Index keeps both ids → the run (terminal now, so run_id_for_trace is None
    # but the raw index still maps until GC).
    assert reg._trace_index["tr-1"] == rec.run_id


@pytest.mark.asyncio
async def test_is_active_for_trace_true_while_running_false_when_terminal():
    reg = AutoChatRegistry()
    release = asyncio.Event()
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        # Active while running.
        active, rid = reg.is_active_for_trace("tr-0")
        assert active and rid == rec.run_id
        release.set()
        await _wait_terminal(reg, rec.run_id)

    active, rid = reg.is_active_for_trace("tr-0")
    assert active is False and rid is None
    assert reg.list_active() == []


@pytest.mark.asyncio
async def test_stop_cancels_to_user_stopped_and_publishes_off():
    reg = AutoChatRegistry()
    release = asyncio.Event()  # never set → run hangs until stopped
    client = _GatedClient(release)
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        run = reg.get(rec.run_id)
        assert run is not None
        # Subscribe so we can confirm auto-mode-off(user_stopped) is published.
        sub = run.bus.subscribe()
        received: list[bytes] = []

        async def _drain():
            async for b in sub:
                received.append(b)

        drain_task = asyncio.create_task(_drain())
        await asyncio.sleep(0.05)  # let the run start + buffer replay
        await reg.stop(rec.run_id)
        await asyncio.sleep(0.05)
        drain_task.cancel()

    assert run.record.status == AutoRunStatus.USER_STOPPED
    decoded = b"".join(received).decode()
    assert '"type": "auto-mode-off"' in decoded
    assert '"reason": "user_stopped"' in decoded


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

        # The run keeps advancing to terminal despite the dropped subscriber.
        release.set()
        await _wait_terminal(reg, rec.run_id)

    assert run.record.status == AutoRunStatus.DONE


@pytest.mark.asyncio
async def test_terminal_ttl_gc_evicts_run_and_index(monkeypatch):
    monkeypatch.setattr(registry_mod, "TERMINAL_TTL_SECONDS", 0.05)
    reg = AutoChatRegistry()
    round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
    client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
    with patch.object(httpx, "AsyncClient", return_value=client):
        rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
        await _wait_terminal(reg, rec.run_id)
        await asyncio.sleep(0.15)  # let GC fire

    assert reg.get(rec.run_id) is None
    assert "tr-0" not in reg._trace_index
    assert "tr-1" not in reg._trace_index


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
            await _wait_terminal(reg, rec.run_id)
            await asyncio.sleep(0.02)
            drain_task.cancel()

        decoded = b"".join(received).decode()
        assert "done" in decoded  # live text delivered after subscribe
        # Ended on a plain-text turn → asked_user; auto-mode-off delivered live.
        assert '"reason": "asked_user"' in decoded

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
    async def test_terminal_run_yields_off_immediately(self):
        reg = AutoChatRegistry()
        round1 = [trace("tr-1"), text_delta("hi"), finish("stop")]
        client = FakeUpstreamClient([FakeUpstreamResponse(chunks=round1)])
        with patch.object(httpx, "AsyncClient", return_value=client):
            rec = reg.start(_seed("tr-0"), reason=None, upstream_url=URL, headers={})
            await _wait_terminal(reg, rec.run_id)
            run = reg.get(rec.run_id)
            assert run is not None
            received = [b async for b in run.bus.subscribe()]

        # A late subscriber to a terminal run gets exactly the off marker.
        decoded = b"".join(received).decode()
        assert '"type": "auto-mode-off"' in decoded

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
            await _wait_terminal(reg, rec.run_id)

        assert saw_ping
