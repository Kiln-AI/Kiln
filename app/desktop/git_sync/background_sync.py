import asyncio
import logging
import time
from contextlib import suppress

from app.desktop.git_sync.git_sync_manager import GitSyncManager

logger = logging.getLogger(__name__)


class BackgroundSync:
    """Polls remote for changes. Two-phase: fetch without lock,
    fast-forward under lock.

    Pauses automatically when idle (no API requests) to avoid
    running indefinitely in the background.
    """

    def __init__(
        self,
        manager: GitSyncManager,
        poll_interval: float = 10.0,
        idle_pause_after: float = 300.0,
    ):
        self._manager = manager
        self._poll_interval = poll_interval
        self._idle_pause_after = idle_pause_after
        self._task: asyncio.Task[None] | None = None
        self._last_request_time: float = 0.0
        self._wake_event: asyncio.Event = asyncio.Event()

    def notify_request(self) -> None:
        """Called by middleware on each request. Resets idle timer, wakes paused loop."""
        self._last_request_time = time.monotonic()
        self._wake_event.set()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._last_request_time = time.monotonic()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)

            idle_time = time.monotonic() - self._last_request_time
            if idle_time > self._idle_pause_after:
                logger.info(
                    "Background sync pausing -- no requests for %.0fs", idle_time
                )
                self._wake_event.clear()
                # Re-check after clear: notify_request() sets _last_request_time
                # before set(), so this catches requests arriving during the race window.
                if time.monotonic() - self._last_request_time > self._idle_pause_after:
                    await self._wake_event.wait()
                continue

            try:
                await self._manager.fetch()

                if not await self._manager.has_new_remote_commits():
                    continue

                async with self._manager.write_lock():
                    if await self._manager.can_fast_forward():
                        await self._manager.fast_forward()

            except Exception:
                logger.warning("Background sync failed, will retry", exc_info=True)
