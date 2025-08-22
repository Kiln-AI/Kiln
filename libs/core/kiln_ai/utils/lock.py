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
        # Protects the _locks dict and bookkeeping counters.
        self._mu = asyncio.Lock()
        self._locks: Dict[Hashable, _Entry] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable, *, timeout: float | None = None):
        """
        Acquire the lock for `key` as an async context manager.

        - `timeout`: optional seconds to wait; raises TimeoutError on expiry.
        """
        # Phase 1: register as a waiter and get/create the entry (under manager mutex).
        async with self._mu:
            entry = self._locks.get(key)
            if entry is None:
                entry = self._locks[key] = _Entry()
            entry.waiters += 1

        # Phase 2: wait on the per-key lock (outside manager mutex).
        try:
            if timeout is None:
                await entry.lock.acquire()
            else:
                # Manual timeout to keep compatibility across Python versions.
                await asyncio.wait_for(entry.lock.acquire(), timeout=timeout)

            # Phase 3: update counters: became a holder.
            async with self._mu:
                entry.waiters -= 1
                entry.holders += 1

            try:
                yield  # critical section
            finally:
                # Phase 4: release holder and maybe cleanup.
                entry.lock.release()
                async with self._mu:
                    entry.holders -= 1
                    # Remove the entry if fully idle.
                    if entry.waiters == 0 and entry.holders == 0:
                        # Double-check we still point to same object (paranoia/race safety).
                        if self._locks.get(key) is entry:
                            del self._locks[key]

        except asyncio.TimeoutError:
            # Timed out while waiting; undo waiter count and maybe cleanup.
            async with self._mu:
                entry.waiters -= 1
                if entry.waiters == 0 and entry.holders == 0:
                    if self._locks.get(key) is entry:
                        del self._locks[key]
            raise
        except asyncio.CancelledError:
            # Cancelled while waiting; same cleanup as timeout.
            async with self._mu:
                entry.waiters -= 1
                if entry.waiters == 0 and entry.holders == 0:
                    if self._locks.get(key) is entry:
                        del self._locks[key]
            raise

    # Optional: expose a snapshot for metrics/debugging
    async def snapshot(self) -> Dict[Hashable, dict]:
        async with self._mu:
            return {
                k: {"waiters": e.waiters, "holders": e.holders}
                for k, e in self._locks.items()
            }


# callers should use this global instance instead of creating their own
async_lock_manager = AsyncLockManager()
