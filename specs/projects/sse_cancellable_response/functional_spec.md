---
status: complete
---

# Functional Spec: SSE CancellableStreamingResponse

## Summary

Introduce a `CancellableStreamingResponse` subclass of `starlette.responses.StreamingResponse` that always runs `listen_for_disconnect` concurrently with `stream_response` in an `anyio` task group — restoring Starlette 0.41.2's pre-regression cancellation behavior. Replace `StreamingResponse(...)` with `CancellableStreamingResponse(...)` in three helper functions. Add a test file that exercises the subclass's cancellation contract end-to-end.

Starting point: `main` after commit `63740fa3a` (GitSyncMiddleware ASGI bypass already landed). This branch ships as a separate PR.

## Behavior

### `CancellableStreamingResponse.__call__`

For **every** HTTP scope (no `spec_version` branching):

1. Create an `anyio` task group.
2. Start `self.stream_response(send)` as a task.
3. Run `self.listen_for_disconnect(receive)` inline.
4. Whichever finishes first cancels the other via `task_group.cancel_scope.cancel()`.
5. On `http.disconnect`, `listen_for_disconnect` returns, the cancel scope fires, `stream_response` is cancelled with `CancelledError`, which propagates through the body iterator (the endpoint's `event_generator`), triggering any `finally` / `async with` / `try/finally` cleanup.
6. If `self.background` is set, run it after the task group exits (same as Starlette's existing behavior).
7. Non-HTTP scopes (e.g. `lifespan`, `websocket`) are passed through via `super().__call__(scope, receive, send)` unchanged. In practice a `StreamingResponse` is only invoked for HTTP responses, but keep the safety branch.

The implementation should mirror the `else` branch of Starlette 0.41.2's / 0.52.1's `StreamingResponse.__call__` precisely — including the `collapse_excgroups()` context manager for nicer exception surfacing.

### What is **not** changed

- `listen_for_disconnect`: inherited from the parent class unchanged.
- `stream_response`: inherited unchanged.
- Response headers, status, media type, body iterator semantics: inherited unchanged.
- Constructor signature: inherited unchanged (don't redefine `__init__`).

### Error paths

- If the endpoint's `event_generator` raises an exception mid-stream, `stream_response` surfaces that exception and the task group exits via the exception-group collapse. Same as parent.
- If `listen_for_disconnect`'s `receive()` raises, treat it identically to how the parent's `else` branch does (exception propagates through the task group). No special handling.
- Headers-already-sent is not relevant here — cancellation during mid-body is a no-op for the HTTP response state (uvicorn silently discards).

## Helper call-site changes

Three helper functions currently return `StreamingResponse(...)`. Each becomes `CancellableStreamingResponse(...)` with the same args.

### 1. `run_eval_runner_with_status`

**File:** `app/desktop/studio_server/eval_api.py`
**Current (around line 141):**

```python
return StreamingResponse(
    content=event_generator(),
    media_type="text/event-stream",
)
```

**New:**

```python
return CancellableStreamingResponse(
    content=event_generator(),
    media_type="text/event-stream",
)
```

Also update the `from fastapi.responses import StreamingResponse` import (line ~6) to additionally import `CancellableStreamingResponse` from its new module, or (if the helper no longer uses `StreamingResponse` in its return type) replace the annotation accordingly. **Keep the return type annotation as `StreamingResponse`** — `CancellableStreamingResponse` is a subclass, so it satisfies the annotation, and keeping the parent type keeps the OpenAPI/FastAPI surface identical.

### 2. `run_extractor_runner_with_status`

**File:** `libs/server/kiln_server/document_api.py`
**Current (around line 177):** same pattern as above. Replace with `CancellableStreamingResponse`.

### 3. `run_rag_workflow_runner_with_status`

**File:** `libs/server/kiln_server/document_api.py`
**Current (around line 251):** same pattern as above. Replace with `CancellableStreamingResponse`.

No other SSE helpers need to change. The five endpoints listed in `project_overview.md` all flow through one of these three helpers.

## Prerequisites already satisfied

- All five affected endpoints carry `@no_write_lock` (verified by the `test_streaming_routes_require_no_write_lock` invariant test from commit `63740fa3a`).
- `GitSyncMiddleware.__call__` from commit `63740fa3a` short-circuits `@no_write_lock` endpoints to a pure-ASGI path that passes the real uvicorn `receive`/`send`. This means `listen_for_disconnect` sees genuine `http.disconnect` messages from uvicorn, not a `BaseHTTPMiddleware`-wrapped variant.

## Tests

Add a single new test file: `app/desktop/git_sync/test_cancellable_streaming_response.py` (placed here so it runs in CI with the other git_sync tests; the subclass lives in `libs/server` but sits near the middleware bypass that makes it meaningful).

Alternatively place it at `libs/server/kiln_server/test_cancellable_streaming_response.py` if that fits the project's test-locality convention better. Either location is acceptable — pick the one consistent with how neighboring code is tested.

### Required tests

Each test should use `httpx.AsyncClient` against a minimal FastAPI app or direct ASGI invocation via raw scope/receive/send callables. Avoid uvicorn-in-a-thread setups where possible — the unit of behavior is the subclass's `__call__`, not uvicorn itself.

1. **`test_streams_response_when_no_disconnect`** — happy path. A generator yielding 3 chunks runs to completion; the test collects all body chunks and asserts the full content was sent and the generator's `finally` block ran.

2. **`test_cancels_generator_on_client_disconnect`** — **the core test.** A generator that yields one chunk, then enters an `await asyncio.sleep(30)` inside a `try/finally`. The test simulates `http.disconnect` after receiving the first chunk. Assert:
   - The `finally` block runs within ≈1 second (well under the 30s sleep).
   - No further chunks are emitted after disconnect.
   - `CancelledError` (or no exception — implementation choice, but behavior must be clean) is surfaced in a controlled way, not as an unhandled crash.

3. **`test_background_task_runs_after_completion`** — subclass preserves `background` behavior. Pass a `BackgroundTask` to the response, let the stream complete normally, assert the background task ran.

4. **`test_no_spec_version_branching`** — construct two scopes, one with `asgi.spec_version = "2.3"` and one with `asgi.spec_version = "2.4"`, and verify disconnect cancellation works in both. This locks in the "ignore spec_version" contract so a future refactor can't regress to the parent's branching behavior.

5. **`test_exception_in_generator_propagates`** — a generator that raises `ValueError("boom")` mid-stream. The exception (or its task-group-collapsed equivalent) propagates out of `__call__`. No hang.

### Integration test (optional, nice-to-have)

A sanity-check integration test using the actual `AsyncJobRunner`-style loop (a loop that spawns N `asyncio.create_task` workers and has a `finally` that cancels them): construct `CancellableStreamingResponse` around an `event_generator` that wraps such a runner, simulate disconnect, and assert the worker tasks are cancelled. This is valuable but not blocking — the unit tests above cover the contract.

### Not needed

- Tests that start a real uvicorn on a port — unit-level ASGI invocation is sufficient and more deterministic.
- Tests of the endpoints themselves — they're unchanged behavior-wise, already covered by existing endpoint tests.
- Tests of `GitSyncMiddleware` — already covered by tests from commit `63740fa3a`.

## Manual acceptance

On macOS with `uv run ./checks.sh --agent-mode` clean:

1. Start the desktop dev server (`uv run app/desktop/dev_server.py` or however the project's run script works).
2. In the web UI, kick off an eval `/run_comparison` with at least two run configs and a non-trivial eval that takes >20 seconds.
3. Once logs show `Running eval job for ...` appearing every few seconds, hard-refresh the browser (`Cmd-Shift-R`).
4. **Expected:** log output for `Running eval job for ...` stops within a few seconds of the refresh. No new `EvalRun` rows get created in the project after the refresh.
5. Repeat for an extractor run (`extract_file` or `run_extractor_config` via the UI).
6. Repeat for a RAG index run (`run_rag_config` via the UI).

## Non-functional requirements

- **No performance regression** on the happy path. The task group adds at most one additional `asyncio.Task` per SSE response, which is negligible compared to the per-chunk I/O.
- **No impact on non-SSE endpoints.** The subclass is only used in three helper functions that produce SSE responses.
- **No change to SSE wire protocol.** Clients see the same `data: ...\n\n` events and `data: complete\n\n` terminator.

## Edge cases worth calling out in tests or in code comments

- **Disconnect before first yield.** If the client disconnects before the generator has produced anything, `stream_response` will be cancelled before it has even sent `http.response.start`. Uvicorn handles that gracefully. No special handling needed.
- **Disconnect during `http.response.start`.** Same as above — uvicorn's `send` silently returns.
- **Disconnect during `background`.** Background tasks run after the task group exits; they are not cancelled on disconnect. This matches parent `StreamingResponse` behavior and is intentional — background tasks are for post-response cleanup that should run regardless.
- **Synchronous body iterator.** Starlette handles sync iterators via `iterate_in_threadpool` (parent class). The subclass inherits that. Disconnect cancels the async `stream_response` task; the thread running the sync iterator may finish its current chunk but won't be forced to exit. This is acceptable — our event generators are all async.
- **Multiple `__call__` invocations on the same response instance.** Parent `StreamingResponse` is single-use (body iterator is consumed). The subclass inherits that. Not a new concern.

## Invariants

- `CancellableStreamingResponse` is a strict subclass: any code that type-checks `isinstance(x, StreamingResponse)` continues to work.
- The subclass does **not** override `listen_for_disconnect`, `stream_response`, or any other method. Only `__call__`.
- Subclass does not import from FastAPI — only from `starlette.responses`, `anyio`, and standard library. It must be safe to import from both `libs/server` and `app/desktop`.
