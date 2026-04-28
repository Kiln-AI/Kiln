---
status: complete
---

# SSE CancellableStreamingResponse — Project Overview

## Problem

Hard-refreshing the browser during a long-running SSE job (eval run, extractor, RAG index) does not stop the server-side work. New `EvalRun` rows keep getting created, LLM calls keep firing, and worker pools keep churning until the Python process restarts. The user reproduced this on `/run_comparison`, observing continuous `Running eval job for ...` log output after closing the browser tab.

## Root cause

The real cause is **Starlette version 0.41.2 → 0.52.1** (project commit `5941ae5bf` "update starlette dep", Jan 22 2026, which pinned `starlette>=0.49.1` for a transitive security fix).

- **Starlette 0.41.2** `StreamingResponse.__call__` always ran an `anyio` task group racing `stream_response(send)` against `listen_for_disconnect(receive)`. Whichever finished first cancelled the other via `task_group.cancel_scope.cancel()`. When a client disconnected, `listen_for_disconnect` saw `http.disconnect` on `receive()`, exited, and cancelled the body task. `CancelledError` propagated into the `event_generator` → through `async for progress in runner.run():` → into `AsyncJobRunner.run()`'s `finally` block, which cancels all worker tasks.

- **Starlette 0.49.1+ (including installed 0.52.1)** added a `spec_version` branch. For `scope["asgi"]["spec_version"] >= (2, 4)` it takes a **simple path** with no `listen_for_disconnect`:

  ```python
  async def __call__(self, scope, receive, send):
      spec_version = tuple(...)
      if spec_version >= (2, 4):
          try:
              await self.stream_response(send)
          except OSError:
              raise ClientDisconnect()
      else:
          # task-group + listen_for_disconnect (the working path)
  ```

  Uvicorn advertises `spec_version = "2.4"` (`uvicorn/protocols/http/h11_impl.py:205` and `httptools_impl.py:217`). So the simple path is always taken.

- **The simple path is inert under uvicorn.** Uvicorn's `send()` checks `if self.disconnected: return  # pragma: full coverage` *before* calling `transport.write`. No `OSError` is ever raised from `send()`. And uvicorn's `connection_lost()` does not `.cancel()` the ASGI task. So the `except OSError` branch is effectively dead code and the stream keeps iterating, silently discarding each chunk.

Result: under Starlette 0.49.1+ running on uvicorn, SSE endpoints never detect client disconnect, and any work driven by their generators (eval runners, extractor runners, RAG workflow runners) keeps running to completion.

## Why the prior middleware fix (commit `63740fa3a`) did not solve this

That commit bypassed `BaseHTTPMiddleware` wrapping for `@no_write_lock` endpoints — removing a layer of memory-stream indirection and ensuring the endpoint sees real ASGI `receive`/`send`. This is a prerequisite for any `listen_for_disconnect`-based fix to work cleanly. But it does not restore `listen_for_disconnect` itself, and without that, disconnect is still undetected. The original spec conflated "plumbing cleanup" with "cancellation restore"; they are two distinct fixes.

## Fix approach

Create a `CancellableStreamingResponse` subclass of `starlette.responses.StreamingResponse` whose `__call__` unconditionally uses the old task-group + `listen_for_disconnect` pattern, ignoring `spec_version`. Use this subclass in place of `StreamingResponse` in the three SSE helpers that drive long-running project work.

This restores the Starlette 0.41.2 cancellation semantics for the affected endpoints without monkey-patching Starlette, without downgrading a security-sensitive dep, and without changing endpoint-level code.

## Affected endpoints

Five SSE endpoints share three helper functions that construct `StreamingResponse`:

| Endpoint (method + path)                                                                                          | Helper                                      | Helper file                                          |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------- |
| `GET /api/projects/{p}/tasks/{t}/evals/{e}/eval_config/{c}/run_comparison`                                        | `run_eval_runner_with_status`               | `app/desktop/studio_server/eval_api.py`              |
| `GET /api/projects/{p}/tasks/{t}/evals/{e}/eval_config/{c}/run_config/{r}/run_eval`                               | `run_eval_runner_with_status`               | `app/desktop/studio_server/eval_api.py`              |
| `POST /api/projects/{p}/extractor_configs/{c}/run_extractor_config`                                               | `run_extractor_runner_with_status`          | `libs/server/kiln_server/document_api.py`            |
| `POST /api/projects/{p}/documents/{d}/extract`                                                                    | `run_extractor_runner_with_status`          | `libs/server/kiln_server/document_api.py`            |
| `POST /api/projects/{p}/rag_configs/{r}/run_rag_config`                                                           | `run_rag_workflow_runner_with_status`       | `libs/server/kiln_server/document_api.py`            |

All five endpoints are already decorated with `@no_write_lock` and route through `GitSyncMiddleware.__call__`'s ASGI bypass (landed in commit `63740fa3a`), so the real uvicorn `receive` reaches the endpoint. This fix only needs to change how those helpers construct their response.

## Out of scope

- **Chat SSE endpoints** (`/api/chat`, `/api/chat/execute-tools` in `app/desktop/studio_server/chat/routes.py`) are simple proxies to Kiln Copilot via `ChatStreamSession`. They have different cancellation semantics (the upstream HTTP request is cancelled when the session's generator is closed, which happens naturally when `aclose()` propagates). They are not under `/api/projects/{project_id}/...`, so `GitSyncMiddleware` does not touch them. Applying the subclass there is possible but not part of this project — keeping scope minimal for the release.
- **File-download `StreamingResponse`** (e.g. in `app/desktop/studio_server/finetune_api.py:743`, `libs/server/kiln_server/document_api.py` file responses) is not SSE and does not need cancellation on refresh — normal file-download semantics are fine.
- **Upstream Starlette fix.** The `spec_version` branch appears intentional (a performance optimization for ASGI servers that do raise `OSError` on disconnect). Fixing it upstream or filing an issue is not blocking; our subclass is a local workaround that works under the uvicorn we ship.
- **AsyncJobRunner refactor.** The runner's existing `finally` block at the end of `AsyncJobRunner.run()` already cancels workers correctly when the generator is cancelled via `aclose()`. No changes needed there.

## Goals

- Browser refresh during an SSE job cancels the server-side work within the next `await` point inside the runner loop (sub-second for typical eval/extraction workloads; bounded by the longest in-flight worker call).
- No change to endpoint signatures, client-facing SSE protocol, or error behavior on the happy path.
- Single small test file proving cancellation reaches the runner's `finally`.

## Success criteria

- Manual: with the dev server running, start a `/run_comparison` that spawns multiple workers. Hard-refresh the browser. Log output stops yielding new `Running eval job for ...` within seconds. No new `EvalRun` rows created after the refresh.
- Automated: a pytest integration test that constructs a slow async generator behind `CancellableStreamingResponse`, drives it through the real ASGI stack, sends `http.disconnect` mid-stream, and asserts the generator's `finally` fires before the test ends.
