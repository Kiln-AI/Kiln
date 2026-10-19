---
status: complete
---

# Functional Spec: SSE Cancel Fix

## Summary

`GitSyncMiddleware` gains a pure-ASGI bypass for `@no_write_lock` endpoints. This restores client-disconnect cancellation for all SSE endpoints without touching endpoint code, helpers, or `AsyncJobRunner`. Two automatic dev-time guards protect the invariant ("SSE endpoints must be `@no_write_lock`") so the regression cannot silently return.

Starting point: `main` branch. Five existing SSE endpoints are already `@no_write_lock`, so the fix is middleware-only plus tests.

## Middleware behavior

### Routing matrix

For every HTTP request reaching `GitSyncMiddleware`:

| Condition                                                                 | Path taken                              |
| ------------------------------------------------------------------------- | --------------------------------------- |
| URL does not match `/api/projects/{id}/...`                               | existing `_unmatched_dispatch` (unchanged) |
| URL matches, no git-sync manager for project                              | existing pass-through (unchanged)       |
| URL matches, endpoint has `_git_sync_no_write_lock = True`                | **new**: pure-ASGI bypass (see below)   |
| URL matches, mutating method or `@write_lock`                             | existing write-lock path (unchanged)    |
| URL matches, read path without `@no_write_lock`                           | existing read path + dev-mode dirty check (unchanged) |

Everything except the third row is unchanged from `main`.

### Pure-ASGI bypass (new)

Implemented as an override of `BaseHTTPMiddleware.__call__(self, scope, receive, send)`. When the matched endpoint carries `_git_sync_no_write_lock`:

1. Resolve the manager using the existing `_get_manager_for_request` (or equivalent, given the middleware sees `scope` rather than `Request`).
2. If no manager, call `self.app(scope, receive, send)` and return. Matches the existing "no manager" passthrough.
3. Otherwise: `await manager.ensure_fresh_for_read()`.
   - On `GitSyncError`: build a `Response(status, {"detail": ...})` using the existing `_map_error`, await it against the real `(scope, receive, send)`, and return. Matches the existing error path's JSON shape.
4. Call `self._notify_background_sync(manager)`.
5. Attach manager to `scope["state"]["git_sync_manager"]` (creating the `state` dict if absent) so `build_save_context(request)` inside the endpoint keeps working.
6. `await self.app(scope, receive, send)` with the **real** `receive` and `send` — no task-group wrapping, no proxy receive, no buffered response.

All other ASGI scope types (`"lifespan"`, `"websocket"`) fall through to `super().__call__` unchanged.

### Fallthrough for everything else

If the endpoint is not `@no_write_lock`, `__call__` delegates to `super().__call__(scope, receive, send)`, which runs the existing `dispatch` unchanged. Write endpoints keep their commit/push-failure-to-error behavior.

### Endpoint resolution at ASGI layer

Routing happens on a `Request`-less ASGI scope, so the existing `_resolve_endpoint(request)` helper is reused by constructing a minimal `Request(scope=scope)` (Starlette's `Request` accepts a scope-only constructor for routing purposes). Alternative if that proves awkward: factor `_resolve_endpoint` to take a scope directly. Implementation detail; either is acceptable.

## Cancellation chain (post-fix)

Restores the pre-middleware chain. No new code in the chain — all downstream code already behaves correctly.

1. Browser hard-refresh → TCP close.
2. uvicorn emits `{"type": "http.disconnect"}` on the **real** `receive` channel.
3. `StreamingResponse.__call__` — reached directly, not via the middleware's wrapped send — has its `listen_for_disconnect` coroutine running against the real `receive`. It sees the disconnect and returns.
4. Starlette's task group exits; the body task (`stream_response`) is cancelled.
5. `CancelledError` raised inside `event_generator` at its `yield`.
6. `async for progress in runner.run():` unwinds. The temporary generator reference is dropped; Python's async-gen finalizer calls `aclose()`.
7. `aclose()` raises `GeneratorExit` inside `AsyncJobRunner.run()`.
8. Existing `finally:` block at `libs/core/kiln_ai/utils/async_job_runner.py:127` runs: `for w in workers: w.cancel()`.
9. Each worker's current `await run_job_fn(job)` raises `CancelledError`. Since `CancelledError` inherits from `BaseException`, the `except RetryableError` / `except Exception` handlers do not catch it. Workers unwind.
10. `await asyncio.gather(*workers)` resolves. `AsyncJobRunner.run()` exits.

Worst-case latency between TCP close and workers having `cancel()` called is whatever Starlette's disconnect detection adds — no polling window introduced by this fix.

## Dev-time invariant

### Invariant

Every FastAPI route whose endpoint returns `StreamingResponse` must be decorated `@no_write_lock`.

Rationale: a streaming endpoint without `@no_write_lock` falls through to the normal dispatch path, which wraps the body iterator in the middleware's buffering / task group and breaks client-disconnect cancellation.

### Check 1 — static annotation test

New test in `app/desktop/git_sync/test_middleware.py` (or a new `test_sse_invariants.py` if clearer):

```python
def test_streaming_routes_require_no_write_lock():
    app = build_test_app()   # full FastAPI app as wired for the desktop server
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _return_type_is_streaming(route.endpoint):
            continue
        assert getattr(route.endpoint, "_git_sync_no_write_lock", False), (
            f"{route.path} returns StreamingResponse but is missing "
            f"@no_write_lock. Without it, GitSyncMiddleware will buffer "
            f"the stream and client disconnects will not cancel in-flight "
            f"workers. Add @no_write_lock to the route handler."
        )
```

`_return_type_is_streaming` uses `typing.get_type_hints(fn).get("return")` and recognises:
- `StreamingResponse` and subclasses
- `Optional[StreamingResponse]` / `StreamingResponse | None`
- Union/UnionType members that include `StreamingResponse`

Missing or non-type annotations (`None`, `Any`) are ignored — those endpoints fall to check 2.

### Check 2 — dev-mode runtime sniff (preserve existing)

Already implemented on `main` at `app/desktop/git_sync/middleware.py` in `_dev_mode_dirty_check`:

```python
if "text/event-stream" in content_type:
    logger.error("DEV MODE: SSE endpoint missing @no_write_lock: %s %s", ...)
```

After the refactor: a correctly-tagged SSE endpoint takes the ASGI bypass and never reaches `_dev_mode_dirty_check`. A mis-tagged one falls through to dispatch, produces a `StreamingResponse`, and triggers the log. No change to this method's body is required.

New test `test_dev_mode_logs_missing_no_write_lock_for_sse`:
- Enable `KILN_DEV_MODE=true`.
- Register an untagged streaming endpoint on a test app.
- Issue a request.
- Assert the expected `logger.error` fires with the endpoint path.

### Production mode behavior

In production, check 2 is silent (dev-mode gate). Only check 1 runs in normal test runs. No production-facing log or assertion is added, so a missing tag has no user-visible effect beyond the bug we're fixing — which is the same as today.

## Tests

### Unit: middleware routing

In `app/desktop/git_sync/test_middleware.py`, add:

- `test_no_write_lock_takes_asgi_bypass`: constructs an ASGI scope for a `@no_write_lock` route, spies on `BaseHTTPMiddleware.dispatch`, asserts `dispatch` is not called and `self.app` is called with the original `receive` and `send`.
- `test_write_endpoint_uses_dispatch`: POST to a mutating endpoint; asserts `dispatch` is called (sanity — write path unchanged).
- `test_no_write_lock_attaches_manager_to_state`: after bypass, `scope["state"]["git_sync_manager"]` is the resolved manager.
- `test_no_write_lock_ensure_fresh_error_returns_json`: inject `GitSyncError` into `ensure_fresh_for_read`; assert the response is the same JSON-error shape as today's dispatch path.
- `test_no_write_lock_no_manager_passes_through`: when `_get_manager_for_request` returns `None`, `self.app` is called immediately.
- `test_unmatched_url_unchanged`: URLs not matching the project pattern take the existing `_unmatched_dispatch`.

### Integration: cancellation

In `app/desktop/studio_server/test_eval_api.py` (or nearby), add one end-to-end test:

- Build a FastAPI app with `GitSyncMiddleware` applied.
- Replace the eval runner factory with one that yields a fake `AsyncJobRunner` whose workers record their cancellation state (an observer capturing `asyncio.CancelledError` on workers, or a sentinel set in the runner's `finally:`).
- Use `httpx.AsyncClient` + `stream()` to open the SSE endpoint.
- Read one chunk to confirm streaming started, then close the client.
- Await a short bounded window (e.g. 1s) and assert workers were cancelled and the runner's `finally:` ran.

Cover one endpoint (e.g. `run_comparison`) — the middleware behavior is shared across all five, so one integration test is sufficient.

### Invariant tests

Already detailed under "Dev-time invariant" above.

## Error handling

No new error classes. All existing error paths preserved:

- `GitSyncError` on `ensure_fresh_for_read` in bypass path → existing JSON response.
- `_StreamingUnderWriteLock` sentinel in dispatch path → unchanged.
- `GitSyncError` during write → unchanged.

## Non-functional

### Performance

Bypass path is strictly lighter than dispatch: no task group, no body buffering, no header copying. One additional synchronous routing match at ASGI layer, replacing the match that dispatch does anyway.

### Compatibility

No public API change. No change to endpoint signatures, helper signatures, or `AsyncJobRunner`. No new dependency. No config flag.

### Security

No auth-path changes. `ensure_fresh_for_read` still runs before every matched read, matching today.

## Out of scope

- Polling-based disconnect detection (no `is_disconnected()` loops).
- SSE keepalive/heartbeat frames.
- `contextlib.aclosing` wrappers at the endpoint level.
- New `libs/server/kiln_server/sse.py` helper.
- `response_class=StreamingResponse` additions to route decorators.
- Changes to `AsyncJobRunner`, the `run_*_runner_with_status` helpers, or the SSE endpoint `event_generator` functions.
- Rewriting `GitSyncMiddleware` as pure-ASGI for non-bypass paths.
- Tests for cancellation behavior under non-standard transports (WebSocket, HTTP/2 push) — neither used by Kiln SSE endpoints.

## Acceptance

Manual:
- Start an eval run via the UI. Hard-refresh the browser. Server logs show `AsyncJobRunner.run()`'s `finally:` cleanup within ~1s. No new `EvalRun` rows are created afterwards.
- Repeat for extractor and RAG SSE endpoints (at least one each).

Automated:
- All existing tests pass.
- New middleware unit tests (above) pass.
- New integration cancellation test passes.
- Invariant test 1 passes on the untouched endpoint set.
- Dev-mode log test (invariant test 2) passes.
- `uv run ./checks.sh --agent-mode` green.
