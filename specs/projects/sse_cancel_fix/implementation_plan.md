---
status: complete
---

# Implementation Plan: SSE Cancel Fix

Small project, single phase. All changes ship as one PR.

## Phases

- [ ] Phase 1: ASGI bypass for `@no_write_lock` + tests
  - Add `GitSyncMiddleware.__call__` override per `architecture.md`
  - Unit tests: routing matrix, state attachment, error path, unmatched URL, non-HTTP scope
  - Integration test: end-to-end cancellation on `run_comparison` via `httpx` (or `uvicorn` fallback)
  - Invariant test (static): `test_streaming_routes_require_no_write_lock` across full app
  - Invariant test (runtime): `test_dev_mode_logs_missing_no_write_lock_for_sse`
  - Manual acceptance: UI hard-refresh on eval, extractor, and RAG runs
  - Run `uv run ./checks.sh --agent-mode`
