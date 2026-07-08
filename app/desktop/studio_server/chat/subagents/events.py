from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator

# Reuse the jobs keepalive helper verbatim, exactly as the auto stream does.
from app.desktop.studio_server.jobs.events import (
    KEEPALIVE_PING,
    KeepalivePing,
    iter_with_keepalive,
)

if TYPE_CHECKING:
    from .registry import SubAgentRun

__all__ = [
    "SubAgentEventBus",
    "SubAgentStatusBus",
    "KEEPALIVE_PING",
    "KeepalivePing",
    "iter_with_keepalive",
]


class _ByteSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()


class SubAgentEventBus:
    """Per-run async pub/sub of raw chat SSE bytes (mirrors ``AutoChatEventBus``).

    On subscribe it replays the current-turn buffer (every byte since the last
    persisted ``kiln_chat_trace`` snapshot) for gapless re-attach, then emits the
    run's current status marker so an attaching observer immediately reflects
    running-vs-terminal, then goes live. A subscriber joining a terminal run gets
    the terminal marker and the stream ends.
    """

    def __init__(self, run: "SubAgentRun") -> None:
        self._run = run
        self._subscribers: set[_ByteSubscriber] = set()

    def publish(self, payload: bytes) -> None:
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(payload)

    async def subscribe(self) -> AsyncGenerator[bytes, None]:
        subscriber = _ByteSubscriber()
        self._subscribers.add(subscriber)
        try:
            for payload in list(self._run.buffer):
                yield payload
            yield self._run.status_marker_bytes()
            if self._run.record.status.is_terminal:
                return
            while True:
                yield await subscriber.queue.get()
        finally:
            self._subscribers.discard(subscriber)


class SubAgentStatusBus:
    """Registry-level firehose of ``kiln-subagent-status`` events.

    One subscription per UI client (the sub-agent store), filtered client-side
    by parent. Exists so an interactive, idle parent still learns that a child
    finished — there is no parent stream to ride in that case.
    """

    def __init__(self) -> None:
        self._subscribers: set[_ByteSubscriber] = set()

    def publish(self, payload: bytes) -> None:
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(payload)

    async def subscribe(self) -> AsyncGenerator[bytes, None]:
        subscriber = _ByteSubscriber()
        self._subscribers.add(subscriber)
        try:
            while True:
                yield await subscriber.queue.get()
        finally:
            self._subscribers.discard(subscriber)
