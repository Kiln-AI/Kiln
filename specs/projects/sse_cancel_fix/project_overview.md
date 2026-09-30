---
status: complete
---

# SSE Cancel Fix — Project Overview

## Problem

Starting an eval, extractor, or RAG job and then hard-refreshing the browser leaves the job running server-side indefinitely. New `EvalRun` rows keep getting created, LLM calls keep firing, and the worker pool keeps churning until the process is restarted. Previously, a browser refresh cancelled the in-flight job; that behavior regressed when `GitSyncMiddleware` landed in Phase 3 of the git-sync work (commit `a46ff424e`, "Phase 3: SSE endpoint wiring").

Affected endpoints (all SSE):

- `GET /api/projects/{p}/tasks/{t}/evals/{e}/eval_config/{c}/run_comparison`
- `GET /api/projects/{p}/tasks/{t}/evals/{e}/eval_config/{c}/run_config/{r}/run_eval` (calibration)
- `run_extractor_config`, `extract_file`, `run_rag_config` in `libs/server/kiln_server/document_api.py`

## Root cause

`GitSyncMiddleware` extends `starlette.middleware.base.BaseHTTPMiddleware`, which wraps every request in its own `anyio` task group and replaces `receive` / `send` with proxies. Two consequences for SSE:

1. Starlette's `StreamingResponse.listen_for_disconnect` never sees the real `http.disconnect` — the middleware's wrapped `receive` consumes it first.
2. Even if the disconnect did propagate, it would cancel the middleware's wrapper task, not the body-stream task, so `CancelledError` never reaches `event_generator`.

With no cancellation reaching `event_generator`, the `async for progress in runner.run():` loop never unwinds, so `AsyncJobRunner.run()`'s `finally:` block (which cancels workers) never fires. Workers keep pulling jobs.

Pre-middleware, the chain that stopped the job was:

1. Browser disconnect → Starlette cancels `stream_response` task.
2. `CancelledError` hits `event_generator` at its `yield`.
3. `async for` unwinds; `runner.run()` is finalized → `aclose()` → `GeneratorExit` inside `AsyncJobRunner.run()`.
4. `AsyncJobRunner.run()`'s `finally:` cancels each worker task. `CancelledError` (a `BaseException`, not caught by the `except Exception` handlers) propagates out and ends the worker.

We want to restore that chain without reintroducing the middleware regression.

## Goals

- **Primary**: browser disconnect cancels the in-flight job within ~1s. Workers stop; no new `EvalRun` / LLM calls are initiated.
- **Preserve**: the write-endpoint commit/push-failure pattern provided by `BaseHTTPMiddleware` — where a commit/push failure after the endpoint returns turns a 200 into an error response. This is important and must not regress.
- **Keep app code stable**: no changes to `AsyncJobRunner`, no changes to the SSE endpoint generators or the `run_*_runner_with_status` helpers. The existing cancellation chain in `AsyncJobRunner.run()`'s `finally:` is correct and should continue to be the only mechanism that stops workers.
- **Catch regressions at dev time**: a test that fails if a new SSE endpoint is added without `@no_write_lock`, or if the middleware ever silently stops bypassing for `@no_write_lock` endpoints.

## Non-goals

- No polling-based disconnect detection (`is_disconnected()` loops).
- No SSE keepalive / heartbeat mechanism.
- No `contextlib.aclosing` wrappers at the endpoint level.
- No changes to `AsyncJobRunner` cancellation semantics.
- No rewrite of `GitSyncMiddleware` as pure ASGI for all request types — only bypass the BaseHTTPMiddleware machinery where it's provably unnecessary.

## Fix shape

**Use `@no_write_lock` as the bypass signal.** `GitSyncMiddleware` becomes:

- If the matched route's endpoint is `@no_write_lock`: pure ASGI pass-through. Resolve the git-sync manager, run `ensure_fresh_for_read()`, attach the manager to `scope["state"]["git_sync_manager"]` (so `build_save_context(request)` still works inside the endpoint), notify the background sync task, then call `await self.app(scope, receive, send)` with the **real** `receive` and `send`. No task group, no receive/send wrapping.
- Otherwise: existing `BaseHTTPMiddleware.dispatch` path, unchanged. Write endpoints still get their response wrapped and commit/push failures still turn 200 into error.

Rationale: `BaseHTTPMiddleware` earns its complexity specifically for write endpoints that need post-response commit/push-failure handling. `@no_write_lock` is, by definition, the set that doesn't need this. Every SSE endpoint in Kiln is already `@no_write_lock`, and this invariant holds naturally — once you opt out of writes, you can't generate a commit/push failure to handle.

With the bypass in place, the real `receive` reaches `StreamingResponse.listen_for_disconnect`, which cancels the body task, and the existing `AsyncJobRunner.run()` `finally:` handles worker cleanup exactly as it did pre-middleware.

## Dev-time invariant checks

Enforce the design invariant ("every SSE endpoint must be `@no_write_lock`") with two automatic mechanisms. Both — no prerequisite flags, no per-endpoint opt-in.

### 1. Static: annotation-based test

Iterate `app.routes` at test time; for each route whose endpoint's return type (via `typing.get_type_hints`) is `StreamingResponse` (including subclasses and union members), assert the endpoint is `@no_write_lock`. Failure message names the route path and states the fix ("Add `@no_write_lock` so `GitSyncMiddleware` takes the ASGI bypass; otherwise client disconnects won't cancel the stream.").

Catches: any endpoint with a correct return-type annotation. The Kiln SSE helpers already annotate this way (`run_eval_runner_with_status(...) -> StreamingResponse`), so most coverage is free.

Does not catch: endpoints with missing or weakened return annotations (`-> Response`, `-> Any`, none). The runtime check below handles those.

### 2. Runtime: dev-mode dispatch-path sniff

`app/desktop/git_sync/middleware.py` already has this check at `_dev_mode_dirty_check` (lines 259-266 on the current branch): when the non-bypass `dispatch` path returns and the response's `content-type` is `text/event-stream`, log `"DEV MODE: SSE endpoint missing @no_write_lock: <method> <path>"`. A correctly-tagged SSE endpoint takes the ASGI bypass and never reaches `dispatch`, so any streaming response seen here is, by construction, a bug.

Preserve this check in the new middleware shape. Verify it still fires after the refactor (covered by a new test that hits a deliberately-untagged streaming endpoint and asserts the log).

Pattern to follow (already used in the file):

```python
if _is_dev_mode():
    logger.error("DEV MODE: SSE endpoint missing @no_write_lock: %s %s", ...)
```

Scope: dev mode only (`KILN_DEV_MODE=true`, set in `app/desktop/dev_server.py`). Matches the existing dev-mode dirty-check pattern; no impact on production behavior.

Catches: any untagged streaming endpoint that gets exercised even once during development or in test runs that enable dev mode. Since all existing SSE endpoints are well-tested, coverage is effectively automatic.

### No prerequisite

Dropping the earlier proposal to add `response_class=StreamingResponse` to each SSE route decorator. It required devs to remember the same thing as `@no_write_lock`, so it bought no additional enforcement. Return-type annotations (test 1) plus the runtime sniff (test 2) give full coverage without an opt-in step.

## Acceptance tests

- **Manual**: start an eval run, hard-refresh the browser. Within ~1s, server logs show workers cancelled and no further `EvalRun` rows are created. Repeat for extractor and RAG SSE endpoints.
- **Automated**: integration test that issues an SSE request to a `@no_write_lock` endpoint backed by a mock `AsyncJobRunner`, closes the client, and asserts the runner's `finally:` ran (e.g. via an observer recording worker cancellation).
- **Automated (regression guard)**: the two invariant tests above.

## Scope boundaries

- In scope: `app/desktop/git_sync/middleware.py` (ASGI bypass for `@no_write_lock` endpoints; preserve existing dev-mode SSE-content-type check), the annotation-based invariant test, a test that verifies the dev-mode SSE log still fires for untagged streaming endpoints, the integration test for cancellation.
- Out of scope: `libs/server/kiln_server/sse.py` (should not be created), `contextlib.aclosing` wrappers at endpoint level, `response_class=StreamingResponse` changes to route decorators, any changes to `AsyncJobRunner`, the SSE helpers' internal shape, or the SSE endpoint generators.

## Starting point

This project is specified against `main`, not against the existing `scosman/sse_middleware` branch. The existing branch (which adds `stream_with_heartbeat`, `contextlib.aclosing` wrappers, and polling) is being abandoned in favor of this simpler, smaller-surface-area fix. No revert needed — a fresh branch from `main` will be used.
