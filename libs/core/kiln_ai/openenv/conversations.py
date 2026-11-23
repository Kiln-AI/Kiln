"""OpenEnv sessions held open between the turns of multi-turn conversations.

A conversation that uses an environment keeps one session for all its turns. Between
turns the session is held here, keyed by the id of the conversation's latest turn, so
only that turn can be continued. A session closes when it has been idle too long, when
its latest turn is deleted, or when the session manager shuts down.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from kiln_ai.run_context import EpisodeContext

logger = logging.getLogger(__name__)

IDLE_SECONDS = 30 * 60
"""How long a conversation's session stays open without a turn."""

REAP_INTERVAL_SECONDS = 60.0

MAX_END_REASONS = 1000
"""How many ended conversations' reasons are kept, oldest dropped first."""


@dataclass
class HeldSession:
    context: EpisodeContext
    loop: asyncio.AbstractEventLoop
    """The event loop the session's socket was opened on, the only one that can use it."""
    turn_run_ids: set[str] = field(default_factory=set)
    """Every turn of the conversation, so a fork from an earlier one can be told apart
    from a conversation whose session is gone."""
    last_used: float = 0.0


class ConversationSessions:
    """The sessions held between turns. Entries change only in synchronous methods, so
    two requests on one event loop can't interleave inside a change; a session is
    released after its entry is removed."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        idle_seconds: float = IDLE_SECONDS,
        reap_interval_seconds: float = REAP_INTERVAL_SECONDS,
    ) -> None:
        self._clock = clock
        self._idle_seconds = idle_seconds
        self._reap_interval_seconds = reap_interval_seconds
        self._held: dict[str, HeldSession] = {}
        self._end_reasons: dict[str, str] = {}
        self._reaper: asyncio.Task[None] | None = None

    def take(self, parent_run_id: str) -> HeldSession | None:
        """Remove and return the session held under the conversation's latest turn, so
        two sends continuing the same turn can't share it. A session opened on another
        event loop (a library caller using one `asyncio.run` per turn) can't be used
        here, so it is forgotten and None is returned."""
        if self.peek(parent_run_id) is None:
            return None
        return self._held.pop(parent_run_id)

    def peek(self, run_id: str) -> HeldSession | None:
        """The session held under this turn, left in place. A session opened on another
        event loop is forgotten, as in `take`."""
        held = self._held.get(run_id)
        if held is None or held.loop is asyncio.get_running_loop():
            return held
        del self._held[run_id]
        manager = held.context.session_manager
        if held.loop.is_running():
            # Another thread's loop: its socket can only be closed there.
            asyncio.run_coroutine_threadsafe(
                manager.release(held.context.episode), held.loop
            )
        else:
            # The loop that opened it is gone. Once the manager drops its reference,
            # the socket is closed when it's garbage-collected, and the environment
            # frees the slot.
            manager.forget(held.context.episode)
        logger.warning(
            "OpenEnv server %s session %s was opened on another event loop; ending it",
            held.context.openenv_server.id,
            held.context.episode.episode_id,
        )
        return None

    def put(self, latest_run_id: str, held: HeldSession) -> None:
        """Hold the session under the conversation's latest turn. Must be called on the
        event loop that will release it."""
        held.turn_run_ids.add(latest_run_id)
        held.last_used = self._clock()
        self._held[latest_run_id] = held
        self._ensure_reaper()

    def record_end(self, latest_run_id: str, reason: str) -> None:
        """Remember why the conversation whose latest turn is `latest_run_id` lost its
        session. `reason` follows "ended", e.g. "after 30 minutes without a message".
        Kept in memory only, so a restart forgets it."""
        self._end_reasons.pop(latest_run_id, None)
        self._end_reasons[latest_run_id] = reason
        if len(self._end_reasons) > MAX_END_REASONS:
            del self._end_reasons[next(iter(self._end_reasons))]

    def end_reason(self, latest_run_id: str) -> str | None:
        """Why the conversation's session ended, when this process ended it."""
        return self._end_reasons.get(latest_run_id)

    def holds_turn(self, run_id: str) -> bool:
        """True when a held conversation includes this turn."""
        return any(run_id in held.turn_run_ids for held in self._held.values())

    async def release_runs(self, run_ids: Iterable[str]) -> None:
        """Close the sessions held under any of these turns."""
        await self._release(
            [self._held.pop(i) for i in set(run_ids) if i in self._held]
        )

    async def reap(self) -> None:
        """Close the sessions idle for longer than the idle limit."""
        now = self._clock()
        idle = [
            run_id
            for run_id, held in self._held.items()
            if now - held.last_used > self._idle_seconds
        ]
        minutes = round(self._idle_seconds / 60)
        for run_id in idle:
            self.record_end(run_id, f"after {minutes} minutes without a message")
        await self._release([self._held.pop(run_id) for run_id in idle])

    async def close_all(self) -> None:
        """Stop the reaper and close every held session."""
        reaper, self._reaper = self._reaper, None
        if reaper is not None and not reaper.done():
            reaper.cancel()
        held = list(self._held.values())
        self._held.clear()
        await self._release(held)

    def _ensure_reaper(self) -> None:
        loop = asyncio.get_running_loop()
        reaper = self._reaper
        if reaper is not None and not reaper.done() and reaper.get_loop() is loop:
            return
        self._reaper = loop.create_task(self._reap_until_empty())

    async def _reap_until_empty(self) -> None:
        while self._held:
            await asyncio.sleep(self._reap_interval_seconds)
            try:
                await self.reap()
            except Exception:
                logger.exception("Couldn't close idle OpenEnv conversation sessions")
        if self._reaper is asyncio.current_task():
            self._reaper = None

    async def _release(self, held: list[HeldSession]) -> None:
        results = await asyncio.gather(
            *(h.context.session_manager.release(h.context.episode) for h in held),
            return_exceptions=True,
        )
        for h, result in zip(held, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Couldn't close OpenEnv server %s session %s: %s",
                    h.context.openenv_server.id,
                    h.context.episode.episode_id,
                    result,
                )
