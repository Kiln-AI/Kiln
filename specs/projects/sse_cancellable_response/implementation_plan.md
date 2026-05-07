---
status: complete
---

# Implementation Plan: SSE CancellableStreamingResponse

Small project, single phase. All changes ship as one PR.

## Phases

- [x] Phase 1: CancellableStreamingResponse subclass + 3 call-site swaps + tests
  - Add `libs/server/kiln_server/cancellable_streaming_response.py` per `architecture.md` (body verbatim as shown in the architecture doc).
  - Swap `StreamingResponse(...)` → `CancellableStreamingResponse(...)` in `app/desktop/studio_server/eval_api.py::run_eval_runner_with_status` (around line 141).
  - Swap `StreamingResponse(...)` → `CancellableStreamingResponse(...)` in `libs/server/kiln_server/document_api.py::run_extractor_runner_with_status` (around line 177).
  - Swap `StreamingResponse(...)` → `CancellableStreamingResponse(...)` in `libs/server/kiln_server/document_api.py::run_rag_workflow_runner_with_status` (around line 251).
  - Add `libs/server/kiln_server/test_cancellable_streaming_response.py` with the required tests per `functional_spec.md`:
    - `test_streams_response_when_no_disconnect`
    - `test_cancels_generator_on_client_disconnect` (core test)
    - `test_background_task_runs_after_completion`
    - `test_no_spec_version_branching`
    - `test_exception_in_generator_propagates`
  - Do NOT modify `AsyncJobRunner`, `event_generator` functions, `GitSyncMiddleware`, or any endpoint handler.
  - Keep return type annotations as `StreamingResponse` on the helpers (the subclass satisfies the annotation).
  - Manual acceptance (bosses-only, not CI): hard-refresh during `/run_comparison`, `extract_file`, and `run_rag_config` SSE jobs and confirm the server stops work within seconds.
  - Run `uv run ./checks.sh --agent-mode`.

## Out of this plan

- Chat SSE endpoints (`/api/chat`, `/api/chat/execute-tools`). Different architecture, separate future project.
- Any changes to runners, middleware, or endpoint handlers.
- Upstream Starlette fix.
