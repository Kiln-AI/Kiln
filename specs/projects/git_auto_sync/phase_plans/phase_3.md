---
status: draft
---

# Phase 3: Background Sync and End-to-End

## Overview

This phase adds three features: (1) `BackgroundSync` class with two-phase poll loop (fetch without lock, fast-forward under lock) and idle pause/resume, (2) `ensure_fresh_for_read()` freshness threshold for GET requests in the middleware, and (3) lifecycle management via FastAPI lifespan. It also adds end-to-end integration tests covering the full request lifecycle, concurrent writes, conflict simulation, crash recovery, and background pickup.

## Steps

### 1. Add `ensure_fresh_for_read()` to `GitSyncManager`

New async method on `GitSyncManager`:
- Checks `_last_sync` against `FRESHNESS_THRESHOLD` (15s)
- If stale: attempt fetch + fast-forward (without write lock -- read path)
- If fetch fails (remote unreachable) and stale: raise `RemoteUnreachableError`
- If fresh enough: no-op

```python
async def ensure_fresh_for_read(self) -> None:
    now = time.monotonic()
    if now - self._last_sync < FRESHNESS_THRESHOLD:
        return
    try:
        await self.fetch()
    except RemoteUnreachableError:
        raise
    except Exception as e:
        raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e
    if await self.can_fast_forward():
        async with self.write_lock():
            if await self.can_fast_forward():
                await self.fast_forward()
    self._last_sync = time.monotonic()
```

### 2. Create `app/desktop/git_sync/background_sync.py`

`BackgroundSync` class:
- `__init__(manager, poll_interval=10.0, idle_pause_after=300.0)`
- `notify_request()` -- resets idle timer, wakes paused loop
- `start()` -- creates asyncio task for `_poll_loop`
- `stop()` -- cancels task, awaits completion
- `_poll_loop()` -- while True: sleep poll_interval, check idle, fetch, check for new remote commits, fast-forward under lock if possible

### 3. Update middleware for read freshness

In `GitSyncMiddleware.dispatch()`, replace the Phase 3 comment on the non-mutating path with an actual call to `await manager.ensure_fresh_for_read()`.

### 4. Update registry for background sync tracking

Add `_background_syncs: dict[Path, BackgroundSync]` to `GitSyncRegistry` and clear it in `reset()`.

### 5. Add lifecycle management to `desktop_server.py`

In the `lifespan` context manager:
- On startup: iterate all auto-sync project configs, create managers, start BackgroundSync for each
- On shutdown: stop all BackgroundSync instances, close all managers

### 6. Wire `notify_request()` into middleware

In the middleware dispatch, call `BackgroundSync.notify_request()` for any request that matched a manager (both read and write paths), to keep the idle timer fresh.

## Tests

### `test_background_sync.py`
- test_poll_loop_fetches_and_fast_forwards: remote changes picked up within poll interval
- test_poll_loop_no_new_commits_no_fast_forward: no-op when no new remote commits
- test_idle_pause_and_resume: loop pauses after idle timeout, resumes on notify_request
- test_stop_cancels_task: stop() cleanly shuts down the poll loop
- test_fast_forward_skipped_when_not_ff_able: diverged repos don't fast-forward
- test_fetch_failure_logs_and_retries: network error during fetch logs warning, next cycle retries

### `test_git_sync_manager.py` additions
- test_ensure_fresh_for_read_when_fresh: no-op when within threshold
- test_ensure_fresh_for_read_fetches_when_stale: fetches and fast-forwards when stale
- test_ensure_fresh_for_read_raises_when_unreachable: raises RemoteUnreachableError if stale + offline

### `test_middleware.py` additions
- test_get_request_checks_freshness: GET calls ensure_fresh_for_read
- test_notify_request_called_on_read: middleware calls notify_request for reads
- test_notify_request_called_on_write: middleware calls notify_request for writes

### End-to-end integration tests (`test_end_to_end.py`)
- test_full_write_lifecycle: API POST -> lock -> commit -> push -> verify in remote
- test_concurrent_writes_serialized: two parallel POSTs -> both succeed, serialized
- test_conflict_retry_succeeds: remote diverges between ensure_fresh and push -> retry works
- test_crash_recovery_on_next_write: dirty repo -> next write auto-recovers -> succeeds
- test_background_sync_picks_up_remote_changes: remote changes appear in local within poll cycle
