---
status: complete
---

# Architecture: SSE CancellableStreamingResponse

Small, low-risk architecture. One new module, three call-site swaps, one new test file. No component designs needed.

## Files touched

| Action | File | Purpose |
|---|---|---|
| **new** | `libs/server/kiln_server/cancellable_streaming_response.py` | The subclass. |
| modify | `app/desktop/studio_server/eval_api.py` | Swap `StreamingResponse(...)` for `CancellableStreamingResponse(...)` in `run_eval_runner_with_status`. |
| modify | `libs/server/kiln_server/document_api.py` | Swap in `run_extractor_runner_with_status` and `run_rag_workflow_runner_with_status`. |
| **new** | `libs/server/kiln_server/test_cancellable_streaming_response.py` | Unit tests for the subclass (see functional spec for required cases). |

No new dependencies. `anyio` is already a transitive dep via Starlette.

## Module: `cancellable_streaming_response.py`

**Location:** `libs/server/kiln_server/cancellable_streaming_response.py`

**Reasoning for location:** `libs/server` is the shared FastAPI plumbing layer — both `libs/server/kiln_server/document_api.py` and `app/desktop/studio_server/eval_api.py` import from `libs/server` already. Placing the subclass here avoids any cross-layer import concern and keeps the module dependency-free.

**Contents (reference implementation):**

```python
from functools import partial
from typing import Awaitable, Callable

import anyio
from starlette._utils import collapse_excgroups
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class CancellableStreamingResponse(StreamingResponse):
    """A StreamingResponse that reliably cancels its body iterator on client disconnect.

    Starlette 0.49+ added a `spec_version >= 2.4` fast path in `StreamingResponse.__call__`
    that skips `listen_for_disconnect` and relies on `send()` raising `OSError` on
    disconnect. Under uvicorn, `send()` silently returns on disconnect rather than
    raising, so the fast path never detects disconnect. This subclass restores the
    pre-regression behavior: always run `stream_response` concurrently with
    `listen_for_disconnect` in an anyio task group, so a client disconnect cancels
    the body iterator's `async for` / `try/finally` cleanup promptly.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        with collapse_excgroups():
            async with anyio.create_task_group() as task_group:

                async def wrap(func: Callable[[], Awaitable[None]]) -> None:
                    await func()
                    task_group.cancel_scope.cancel()

                task_group.start_soon(wrap, partial(self.stream_response, send))
                await wrap(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()
```

**Notes on the implementation:**

- The body of `__call__` is **deliberately identical** to the `else` branch of Starlette 0.52.1's `StreamingResponse.__call__` (no `spec_version` check, no `try/except OSError`). Do not reintroduce the spec-version branch under any circumstances — doing so would revert the fix.
- `collapse_excgroups` is a Starlette-internal helper (`starlette._utils.collapse_excgroups`). Importing from a `_`-prefixed module is a small coupling risk if Starlette moves it, but (a) Starlette uses it in several other response classes and removal would be a breaking change, and (b) if the import breaks on a future upgrade, the fix is to either inline the excgroup-collapsing logic or drop it — neither is hard. Acceptable trade-off given the alternative (reimplementing `StreamingResponse.__call__` from scratch) is worse.
- Do not `__init__`-override. The subclass takes the parent's constructor unchanged.
- `self.background` is read after the task group exits, matching parent semantics. Disconnect cancels the streaming, but background tasks still run — that's intentional. If the user wants the background task to not run on disconnect, that's a future change; the parent class also runs background unconditionally in the `else` branch.
- Only override `__call__`. Do not override `listen_for_disconnect` or `stream_response`.

## Call-site changes

### `run_eval_runner_with_status` (eval_api.py)

Currently (eval_api.py around line 126–144):

```python
from fastapi.responses import StreamingResponse

async def run_eval_runner_with_status(eval_runner: EvalRunner) -> StreamingResponse:
    async def event_generator():
        async for progress in eval_runner.run():
            ...
            yield f"data: {json.dumps(data)}\n\n"
        yield "data: complete\n\n"

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )
```

After:

```python
from fastapi.responses import StreamingResponse  # keep for the return type
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse

async def run_eval_runner_with_status(eval_runner: EvalRunner) -> StreamingResponse:
    async def event_generator():
        async for progress in eval_runner.run():
            ...
            yield f"data: {json.dumps(data)}\n\n"
        yield "data: complete\n\n"

    return CancellableStreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
    )
```

The return type stays as `StreamingResponse` (the subclass satisfies it). The import for `StreamingResponse` may still be needed elsewhere in the file — do not remove it reflexively; check for other usages before cleaning up.

### `run_extractor_runner_with_status` (document_api.py)

Same pattern. Add `from kiln_server.cancellable_streaming_response import CancellableStreamingResponse` to the import block (check how the file organizes imports — match the existing style, e.g. if imports are grouped by origin, put it with other `kiln_server.*` imports).

Change:

```python
return StreamingResponse(
    content=event_generator(),
    media_type="text/event-stream",
)
```

to:

```python
return CancellableStreamingResponse(
    content=event_generator(),
    media_type="text/event-stream",
)
```

### `run_rag_workflow_runner_with_status` (document_api.py)

Same pattern. Same file as above — only one import change needed for both helpers in `document_api.py`.

## Cancellation propagation chain

Once the subclass is in place, the full cancellation chain for `/run_comparison` is:

1. User refreshes browser → browser closes TCP connection.
2. Uvicorn's `connection_lost()` sets `cycle.disconnected = True` and signals `message_event`.
3. The `listen_for_disconnect` task calls `await receive()`, which unblocks and returns `{"type": "http.disconnect"}`.
4. `listen_for_disconnect` exits; its `wrap()` helper calls `task_group.cancel_scope.cancel()`.
5. The task group cancels the `stream_response` task → `CancelledError` raised inside `stream_response`'s `async for chunk in self.body_iterator:` loop.
6. `CancelledError` propagates into `event_generator`'s `async for progress in eval_runner.run():`.
7. Python's generator-cleanup machinery calls `.aclose()` on `eval_runner.run()` (an async generator), throwing `GeneratorExit` into it.
8. `AsyncJobRunner.run()`'s existing `finally` block cancels all worker tasks and awaits `asyncio.gather(*workers)`.
9. Workers unwind their `await` chains (LLM API calls, etc.) and the finally block exits.

This chain is restored entirely by the subclass — no changes to `AsyncJobRunner`, `event_generator`, or endpoint handlers are required.

## Test module: `test_cancellable_streaming_response.py`

**Location:** `libs/server/kiln_server/test_cancellable_streaming_response.py` (next to the module under test).

**Style:** pytest with `pytest-asyncio`. Use direct ASGI invocation (call `response(scope, receive, send)` with callables) rather than spinning up `httpx.AsyncClient` against a FastAPI app — it's simpler and more deterministic for cancellation tests.

**Pattern for the core cancellation test:**

```python
import asyncio
import pytest
from starlette.types import Message
from kiln_server.cancellable_streaming_response import CancellableStreamingResponse


@pytest.mark.asyncio
async def test_cancels_generator_on_client_disconnect():
    finally_ran = asyncio.Event()

    async def slow_generator():
        try:
            yield b"data: chunk1\n\n"
            await asyncio.sleep(30)  # would never complete naturally
            yield b"data: chunk2\n\n"
        finally:
            finally_ran.set()

    response = CancellableStreamingResponse(
        content=slow_generator(),
        media_type="text/event-stream",
    )

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET",
        "path": "/",
        "headers": [],
    }

    sent: list[Message] = []
    send_done = asyncio.Event()

    async def send(message: Message) -> None:
        sent.append(message)
        # After the first body chunk, trigger a disconnect.
        if message["type"] == "http.response.body" and message.get("body"):
            send_done.set()

    disconnect_event = asyncio.Event()

    async def receive() -> Message:
        # Wait for the first chunk to be sent, then return http.disconnect.
        await send_done.wait()
        # Small yield so stream_response has scheduler time to continue into sleep.
        await asyncio.sleep(0.05)
        disconnect_event.set()
        return {"type": "http.disconnect"}

    async with asyncio.timeout(5):  # hard cap; cancellation should be sub-second
        await response(scope, receive, send)

    assert finally_ran.is_set(), "generator's finally did not run on disconnect"
    # First chunk arrived; second did not.
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    assert any(b.get("body") == b"data: chunk1\n\n" for b in bodies)
    assert not any(b.get("body") == b"data: chunk2\n\n" for b in bodies)
```

The other tests (`test_streams_response_when_no_disconnect`, `test_background_task_runs_after_completion`, `test_no_spec_version_branching`, `test_exception_in_generator_propagates`) follow the same ASGI-invocation pattern — see `functional_spec.md` for required behaviors.

**Important in tests:**

- Use `asyncio.timeout(5)` or similar to prevent hangs from turning into CI timeouts.
- Do not use `TestClient` / `httpx.AsyncClient` — they abstract away the `receive`/`send` callables that we need to control to simulate disconnect.
- The `spec_version = "2.4"` scope value is critical: it proves the subclass is *not* taking the parent's fast path (which would fail these tests).

## Rollback plan

If the subclass causes an unexpected regression (e.g. `collapse_excgroups` import breaks on a Starlette upgrade, or some SSE endpoint has a body iterator that misbehaves under the task-group pattern):

1. Revert the three call-site swaps — restore `StreamingResponse(...)`. Endpoints go back to "no cancellation but streaming works."
2. Leave the `CancellableStreamingResponse` module in place for a follow-up investigation.

Rollback is a four-line git diff. Risk is low.

## What this architecture deliberately does NOT do

- **Does not modify** `AsyncJobRunner.run()`, `event_generator` functions, or any endpoint handler. The runner's cleanup is already correct; what was missing was a mechanism to *trigger* it.
- **Does not** apply to chat SSE endpoints (`/api/chat`, `/api/chat/execute-tools`). Those have their own cancellation semantics via `ChatStreamSession`. Left for a future project if needed.
- **Does not** try to fix the Starlette simple path upstream. Monkey-patching `starlette.responses.StreamingResponse` at import time was considered and rejected — it's global mutation, it affects third-party code we don't own, and it's harder to reason about than a local subclass.
- **Does not** change `GitSyncMiddleware` or any middleware. The bypass from commit `63740fa3a` is the necessary plumbing; this project builds on top of it.
