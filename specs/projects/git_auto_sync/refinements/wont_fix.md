# Won't Fix

Critique items reviewed and intentionally not addressed, with rationale.

## Crit #2: Parent lock release lets background sync sneak in

**Risk:** Between parent releasing the lock and nested context's first write, background sync could grab the lock and pull/rebase, invalidating the parent's read state.

**Why won't fix:** The freshness threshold already accepts a 5-second staleness window. A few milliseconds of lock-free time between nested contexts is negligible by comparison. If background sync does sneak in and causes a conflict, the push-retry-with-rebase flow handles it — that's the designed safety net.

## Crit #9: check_in_sync=True on reads is overly strict

**Risk:** GET requests block on freshness. Network blip makes the entire app unusable, even for local-only reads.

**Why won't fix:** Accepting an "online only" UX for now. A read is often a preamble to a write — allowing stale reads just lets the user queue up work that will fail on save. Better to surface sync issues immediately. Can loosen later if offline/degraded UX becomes a priority.

## Crit #4: Sync callers can't enter write_context (async-only)

**Risk:** `write_context` is `@asynccontextmanager` — third-party sync-only callers can't use it.

**Why won't fix:** No sync callers exist today. The middleware (async) handles all API paths. The library portion is not general-purpose — document it as async-only. A sync variant can be added later if needed.

## Crit #12: notify_request() may be called from wrong thread

**Risk:** `asyncio.create_task()` inside `notify_request()` requires a running event loop on the current thread.

**Why won't fix:** `notify_request()` is only called from the middleware, which is async and runs on the event loop thread. Single centralized call site — always the right thread. No issue exists.
