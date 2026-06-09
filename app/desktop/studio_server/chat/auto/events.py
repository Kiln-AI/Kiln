from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator

# Reuse the jobs keepalive helper verbatim — same feeder-task fix (a quiet-window
# timeout must never cancel/tear down the underlying subscription).
from app.desktop.studio_server.jobs.events import (
    KEEPALIVE_PING,
    KeepalivePing,
    iter_with_keepalive,
)

from .models import AutoRunStatus

if TYPE_CHECKING:
    from .registry import AutoChatRun

__all__ = [
    "AutoChatEventBus",
    "KEEPALIVE_PING",
    "KeepalivePing",
    "iter_with_keepalive",
]


class _ByteSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()


class AutoChatEventBus:
    """Per-run async pub/sub of raw chat SSE bytes.

    Mirrors ``jobs/events.py``'s ``JobEventBus`` (an ``asyncio.Queue`` per
    subscriber) with one difference required for gapless re-attach: on subscribe
    it first **replays the current-turn buffer** (every byte since the last
    persisted ``kiln_chat_trace`` snapshot), then goes live. A subscriber that
    joins after the run is already terminal gets the terminal ``auto-mode-off``
    marker immediately and the stream ends.

    The buffer itself (and its reset on ``kiln_chat_trace``) is owned by the
    run's ``emit`` (see ``AutoChatRun``), not the bus — the bus only reads it.
    Disconnecting a subscriber only unsubscribes; it never touches the run's
    supervising task.
    """

    def __init__(self, run: "AutoChatRun") -> None:
        self._run = run
        self._subscribers: set[_ByteSubscriber] = set()

    def publish(self, payload: bytes) -> None:
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(payload)

    async def subscribe(self) -> AsyncGenerator[bytes, None]:
        subscriber = _ByteSubscriber()
        self._subscribers.add(subscriber)
        try:
            # Replay the in-progress turn (everything since the last snapshot).
            for payload in list(self._run.buffer):
                yield payload
            status = self._run.record.status
            # Already off (explicit disable/stop) → emit the terminal marker and
            # stop. (A live run will publish its own auto-mode-off via the queue.)
            if status.is_terminal:
                yield self._run.terminal_off_bytes()
                return
            # Idle between bursts: the flag is still on. Emit the idle marker so a
            # re-attaching observer renders the persistent indicator (working
            # off → "· waiting for you"), then stay subscribed for the next burst
            # (started via /message).
            if status == AutoRunStatus.IDLE:
                yield self._run.idle_marker_bytes()
            # RUNNING: a burst is actively working. The replayed buffer may be
            # empty (the model is thinking server-side between events, just after
            # a snapshot cleared the buffer), so without this an attaching client
            # would look idle/done until the next event lands. Emit a current-
            # liveness snapshot (Phase 9) so the client shows the thinking
            # indicator immediately on attach. (Re-emitting working state is
            # idempotent if the buffer already carried auto-mode-on.)
            elif status == AutoRunStatus.RUNNING:
                yield self._run.state_marker_bytes()
            while True:
                yield await subscriber.queue.get()
        finally:
            self._subscribers.discard(subscriber)
