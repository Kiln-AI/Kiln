"""The ONE per-conversation byte event bus + current-turn replay buffer.

Generalizes (and will replace) the two near-identical copies that exist
today — ``chat/auto/events.py``'s ``AutoChatEventBus`` and
``chat/subagents/events.py``'s ``SubAgentEventBus`` — plus the buffer-owning
``emit()`` methods on ``AutoChatRun`` / ``SubAgentRun``. Both old copies are
deleted as phases 2–3 port their kinds.

Contract (identical to both old buses):

- ``emit(payload)`` appends to the current-turn buffer and publishes to every
  live subscriber. When the payload carries a ``kiln_chat_trace`` event a
  snapshot was just persisted upstream, so the in-progress turn ends: the
  event is forwarded/buffered FIRST, then the buffer resets — the buffer thus
  always holds exactly "events since the last persisted snapshot", which is
  what makes re-attach gapless (replay + hydrate-from-snapshot covers the
  whole transcript with no seam).
- ``publish(payload)`` publishes WITHOUT buffering. Used for lifecycle
  markers (``conversation-state``): they describe the moment they fire, so
  replaying a stale one to a later subscriber would lie about the current
  state — the on-subscribe marker callback provides the fresh truth instead.
- ``subscribe()`` yields the buffer replay, then a fresh on-subscribe marker
  from the supervisor-supplied callback (so an attaching observer immediately
  reflects running-vs-idle-vs-terminal instead of looking done until the next
  event lands — the old auto "Phase 9" state-marker fix and the sub-agent
  status marker, unified), then goes live. If the terminal callback reports
  the conversation can never produce another event, the stream ends after the
  marker (a late subscriber to a finished sub-agent gets exactly the terminal
  status and EOF — same as ``SubAgentEventBus``).
- Disconnecting a subscriber only unsubscribes; it never touches the
  conversation's supervising task (observer teardown is always side-effect
  free — the core "disconnect never affects the run" invariant).

Keepalive is NOT this bus's job: SSE routes wrap ``subscribe()`` with the
shared ``jobs/events.iter_with_keepalive`` helper exactly as the old routes
do (its feeder-task design is what makes a quiet-window timeout safe).
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Callable

from app.desktop.studio_server.chat.constants import KILN_SSE_CHAT_TRACE


def extract_trace_id(payload: bytes) -> str | None:
    """Return the trace id if ``payload`` carries a kiln_chat_trace SSE event.

    Canonical copy of ``chat/auto/registry.py``'s ``_extract_trace_id`` (that
    module is deleted in phase 3; the sub-agent registry already imports this
    logic from there today).

    Each forwarded chunk is newline-joined SSE lines; scan the ``data:`` lines
    for the trace event so the buffer reset lands exactly when a snapshot was
    persisted upstream.

    This is a deliberate second, narrow SSE parse (the full pipeline parse
    lives in ``EventParser``) — ``emit()`` runs on every forwarded chunk and
    only needs the trace boundary, not full event semantics. A cheap substring
    guard skips the JSON parse entirely for the overwhelming majority of
    chunks that can't carry the event, keeping the dual-parse cost negligible.
    """
    if KILN_SSE_CHAT_TRACE.encode() not in payload:
        return None
    for line in payload.split(b"\n"):
        if not line.startswith(b"data: "):
            continue
        body = line[6:].strip()
        if not body or body == b"[DONE]":
            continue
        try:
            event = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict) and event.get("type") == KILN_SSE_CHAT_TRACE:
            tid = event.get("trace_id")
            if isinstance(tid, str) and tid:
                return tid
    return None


class _CloseSentinel:
    """Pushed onto every subscriber's queue by ``close()`` to end its stream
    promptly, distinct from real event bytes. Same pattern as
    ``jobs/events.py``'s ``JobEventBus.shutdown``."""


_CLOSE = _CloseSentinel()


class _ByteSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes | _CloseSentinel] = asyncio.Queue()


# Callback returning the fresh on-subscribe marker bytes for an attaching
# observer (typically one conversation-state event), or None for none. A
# callback — not a stored value — because the marker must reflect the state
# at SUBSCRIBE time, not at bus construction time.
MarkerProvider = Callable[[], bytes | None]
# Callback reporting whether the conversation can ever produce another event.
# True ⇒ the stream ends right after the on-subscribe marker.
TerminalCheck = Callable[[], bool]


class BroadcastBus:
    """Registry-level fan-out of raw SSE bytes — no buffering, no replay, no
    marker.

    Generalizes the old ``SubAgentStatusBus`` (``chat/subagents/events.py``,
    deleted in phase 2): one subscription per UI client (the conversation
    store's firehose), filtered client-side. It exists so an interactive, idle
    parent still learns that a child finished — there is no parent stream to
    ride in that case. Deliberately NOT a ``ByteEventBus``: lifecycle events
    describe the moment they fire, so replaying stale ones would lie about
    current state — the firehose route prepends a fresh snapshot instead.
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
                item = await subscriber.queue.get()
                if isinstance(item, _CloseSentinel):
                    return
                yield item
        finally:
            self._subscribers.discard(subscriber)


class ByteEventBus:
    """Per-conversation async pub/sub of raw chat SSE bytes with a
    current-turn replay buffer (see module docstring for the full contract).

    The bus knows nothing about records or policies: the supervisor injects
    the marker/terminal callbacks so this stays the one reusable copy for
    every conversation kind.
    """

    def __init__(
        self,
        *,
        marker_provider: MarkerProvider | None = None,
        terminal_check: TerminalCheck | None = None,
    ) -> None:
        self._marker_provider = marker_provider
        self._terminal_check = terminal_check
        # Everything emitted since the last persisted kiln_chat_trace
        # snapshot — the gapless re-attach replay window.
        self.buffer: list[bytes] = []
        self._subscribers: set[_ByteSubscriber] = set()
        self._closed = False

    def close(self) -> None:
        """End every open subscription and reject new ones.

        Called when the conversation is evicted from the supervisor: without
        it a live observer of an evicted record would park forever on a dead
        bus nothing can ever emit to again (CR n3 — the interactive LRU
        eviction in particular can hit records with open subscribers). Ending
        the stream lets the SSE route close, and the client re-opens the
        conversation from history, which recreates the record (architecture
        §5 restart-recovery contract). Pure observer teardown — never touches
        any run task.
        """
        self._closed = True
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(_CLOSE)

    def emit(self, payload: bytes) -> None:
        """Buffer + publish; reset the buffer at each persisted snapshot.

        Order matters: the trace event itself is buffered/published BEFORE the
        reset so a subscriber that replayed the pre-snapshot turn still sees
        the boundary event (clients key hydration on it), and the buffer never
        contains bytes from two different turns.
        """
        self.buffer.append(payload)
        self.publish(payload)
        if extract_trace_id(payload) is not None:
            self.buffer.clear()

    def publish(self, payload: bytes) -> None:
        """Deliver to live subscribers WITHOUT buffering (lifecycle markers
        must not replay stale — see module docstring)."""
        for subscriber in self._subscribers:
            subscriber.queue.put_nowait(payload)

    async def subscribe(self) -> AsyncGenerator[bytes, None]:
        # A closed bus belongs to an evicted conversation: end immediately
        # rather than replaying stale buffer bytes nothing will ever follow.
        if self._closed:
            return
        subscriber = _ByteSubscriber()
        # Register BEFORE replaying so events emitted while the replay is
        # being consumed queue up rather than falling in a gap (same ordering
        # both old buses used).
        self._subscribers.add(subscriber)
        try:
            # Replay the in-progress turn (everything since the last snapshot).
            # list() snapshots the buffer so a concurrent emit can't mutate it
            # mid-iteration (the emit still reaches us via the queue).
            for payload in list(self.buffer):
                yield payload
            # Fresh liveness marker so the attaching observer immediately
            # reflects the CURRENT state — the replayed buffer may be empty
            # (model thinking server-side right after a snapshot cleared it)
            # and would otherwise look idle/done until the next event lands.
            if self._marker_provider is not None:
                marker = self._marker_provider()
                if marker is not None:
                    yield marker
            # A terminal conversation (one-shot run finished) can never emit
            # again: end the stream so a late subscriber gets marker + EOF
            # instead of hanging forever.
            if self._terminal_check is not None and self._terminal_check():
                return
            while True:
                item = await subscriber.queue.get()
                if isinstance(item, _CloseSentinel):
                    return
                yield item
        finally:
            # Pure observer teardown: never touches the conversation's task.
            self._subscribers.discard(subscriber)
