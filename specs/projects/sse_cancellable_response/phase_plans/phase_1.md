---
status: complete
---

# Phase 1: CancellableStreamingResponse subclass + 3 call-site swaps + tests

## Overview

Add a `CancellableStreamingResponse` subclass of `starlette.responses.StreamingResponse` that unconditionally runs `listen_for_disconnect` concurrently with `stream_response` in an anyio task group, restoring Starlette 0.41.2's cancellation behavior. Swap it into the three SSE helper functions. Add unit tests exercising the cancellation contract.

## Steps

1. Create `libs/server/kiln_server/cancellable_streaming_response.py` with the `CancellableStreamingResponse` class. Override only `__call__`, using the anyio task group pattern from the architecture doc. No `__init__` override.

2. In `app/desktop/studio_server/eval_api.py`:
   - Add `from kiln_server.cancellable_streaming_response import CancellableStreamingResponse`
   - Change `return StreamingResponse(...)` to `return CancellableStreamingResponse(...)` in `run_eval_runner_with_status` (line 141)
   - Keep return type annotation as `StreamingResponse`

3. In `libs/server/kiln_server/document_api.py`:
   - Add `from kiln_server.cancellable_streaming_response import CancellableStreamingResponse`
   - Change `return StreamingResponse(...)` to `return CancellableStreamingResponse(...)` in `run_extractor_runner_with_status` (line 177)
   - Change `return StreamingResponse(...)` to `return CancellableStreamingResponse(...)` in `run_rag_workflow_runner_with_status` (line 251)
   - Keep return type annotations as `StreamingResponse`

4. Create `libs/server/kiln_server/test_cancellable_streaming_response.py` with the five required tests using direct ASGI invocation (raw scope/receive/send callables).

## Tests

- `test_streams_response_when_no_disconnect`: Happy path. Generator yields 3 chunks, all received, generator's finally block runs.
- `test_cancels_generator_on_client_disconnect`: Core test. Generator yields one chunk then sleeps 30s. Disconnect after first chunk. Assert finally runs within ~1s, no second chunk sent.
- `test_background_task_runs_after_completion`: Pass a BackgroundTask, stream completes normally, assert background task ran.
- `test_no_spec_version_branching`: Disconnect cancellation works with both spec_version 2.3 and 2.4 scopes.
- `test_exception_in_generator_propagates`: Generator raises ValueError mid-stream. Exception propagates out of __call__. No hang.
