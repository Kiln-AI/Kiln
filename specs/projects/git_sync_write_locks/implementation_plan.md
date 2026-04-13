---
status: complete
---

# Implementation Plan: Git Sync Write Locks

## Phases

- [x] Phase 1: `atomic_write` context manager and middleware refactor
  - Add `atomic_write` to `GitSyncManager`
  - Rename `api_path` → `context` in `commit_and_push` and `generate_commit_message`
  - Refactor middleware to use `atomic_write`
  - Add `atomic_write` parametrization to integration tests
  - All existing tests must continue to pass

- [x] Phase 2: Save context type and runner refactoring
  - Add `SaveContext` type, `default_save_context`, and `AtomicWriteCapable` Protocol to `libs/core`
  - Refactor `ExtractorRunner` to accept `save_context` and wrap `save_to_file()` inside the existing try/except in `run_job()`
  - Refactor `EvalRunner` the same way
  - Refactor RAG step job functions (`execute_extractor_job`, `execute_chunker_job`, `execute_embedding_job`) to wrap `save_to_file()` — exclude `RagIndexingStepRunner` (vector store)
  - Thread `save_context` through `build_rag_workflow_runner()` in `libs/server` to the three file-writing step runner constructors
  - Unit tests for each runner verifying deferred save behavior and rollback on error

- [x] Phase 3: SSE endpoint wiring
  - Move decorators to `libs/server/kiln_server/git_sync_decorators.py`, update imports
  - Attach manager to `request.state` in middleware read path
  - Add `build_save_context` helper in `libs/server` (typed via `AtomicWriteCapable`)
  - Add `request: Request` parameter to all 5 SSE endpoint signatures
  - Apply `@no_write_lock` and wire `save_context` to all 5 SSE endpoints
  - Add `KILN_DEV_MODE` env var to `dev_server.py`

- [ ] Phase 4: Dev-mode dirty state detection
  - Add `get_dirty_file_paths()` to `GitSyncManager`
  - Add `_is_dev_mode()` helper and post-request dirty check in middleware read path
  - Unit tests for dirty check (dev on/off, SSE detection, `@no_write_lock` skip, clean repo)
