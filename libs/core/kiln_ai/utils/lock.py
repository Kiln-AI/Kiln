import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, Hashable


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    waiters: int = 0  # tasks waiting to acquire
    holders: int = 0  # 0 or 1 for a mutex


class AsyncLockManager:
    """
    A per-key asyncio lock manager that automatically cleans up locks when they're no longer needed.

    Usage:
        locks = AsyncLockManager()

        async with locks.acquire("user:123"):
            # critical section for "user:123"
            ...

    The manager removes a key when there are no holders and no waiters.
    """

    def __init__(self) -> None:
        # Keep the bookkeeping free of awaits: a cancellation at an await between taking
        # a key's lock and recording the holder would leak the lock.
        self._locks: Dict[Hashable, _Entry] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable, *, timeout: float | None = None):
        """
        Acquire the lock for `key` as an async context manager.

        - `timeout`: optional seconds to wait; raises TimeoutError on expiry.
        """
        entry = self._locks.get(key)
        if entry is None:
            entry = self._locks[key] = _Entry()
        entry.waiters += 1

        try:
            if timeout is None:
                await entry.lock.acquire()
            else:
                await asyncio.wait_for(entry.lock.acquire(), timeout=timeout)
        except BaseException:
            # Timed out or cancelled while waiting: this task never held the lock.
            entry.waiters -= 1
            self._discard_if_idle(key, entry)
            raise

        entry.waiters -= 1
        entry.holders += 1
        try:
            yield  # critical section
        finally:
            entry.lock.release()
            entry.holders -= 1
            self._discard_if_idle(key, entry)

    def _discard_if_idle(self, key: Hashable, entry: _Entry) -> None:
        if entry.waiters == 0 and entry.holders == 0:
            # Double-check we still point to same object (paranoia/race safety).
            if self._locks.get(key) is entry:
                del self._locks[key]

    # Optional: expose a snapshot for metrics/debugging
    async def snapshot(self) -> Dict[Hashable, dict]:
        return {
            k: {"waiters": e.waiters, "holders": e.holders}
            for k, e in self._locks.items()
        }


# callers should use this global instance instead of creating their own
shared_async_lock_manager = AsyncLockManager()
