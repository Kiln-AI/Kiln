---
status: complete
---

# Implementation Plan: Git Sync Write Locks

## Phases

- [ ] Phase 1: `atomic_write` context manager and middleware refactor
  - Add `atomic_write` to `GitSyncManager`
  - Rename `api_path` → `context` in `commit_and_push` and `generate_commit_message`
  - Refactor middleware to use `atomic_write`
  - Add `atomic_write` parametrization to integration tests
  - All existing tests must continue to pass

- [ ] Phase 2: Save context type and runner refactoring
  - Add `SaveContext` type and `default_save_context` to `libs/core`
  - Refactor `ExtractorRunner` to accept `save_context` and separate compute from write in `run_job()`
  - Refactor `EvalRunner` the same way
  - Refactor RAG step runners (`execute_extractor_job`, `execute_chunker_job`, `execute_embedding_job`) and wire `save_context` through `RagWorkflowRunner` → step runners
  - Unit tests for each runner verifying deferred save behavior

- [ ] Phase 3: SSE endpoint wiring
  - Move decorators to `libs/server/kiln_server/git_sync_decorators.py`, update imports
  - Attach manager to `request.state` in middleware read path
  - Add `build_save_context` helper in `libs/server`
  - Apply `@no_write_lock` and wire `save_context` to all 5 SSE endpoints
  - Add `KILN_DEV_MODE` env var to `dev_server.py`

- [ ] Phase 4: Dev-mode dirty state detection
  - Add `get_dirty_file_paths()` to `GitSyncManager`
  - Add `_is_dev_mode()` helper and post-request dirty check in middleware read path
  - Unit tests for dirty check (dev on/off, SSE detection, `@no_write_lock` skip, clean repo)
