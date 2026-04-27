---
status: complete
---

# Phase 2: Save Context Type and Runner Refactoring

## Overview

Introduce a pluggable "save context" factory type that lets callers wrap the write phase of each job in an arbitrary async context manager (no-op by default, `atomic_write` when git sync is active). This keeps `libs/core` runners git-sync-agnostic while letting `libs/server` / `app/desktop` inject the git-sync lock lifecycle around per-job saves.

Concretely:

1. Add a new module `libs/core/kiln_ai/utils/git_sync_protocols.py` exposing:
   - `SaveContext` type alias (zero-arg factory returning an async context manager).
   - `default_save_context` async context manager (no-op) -- callable of `SaveContext` shape.
   - `AtomicWriteCapable` structural Protocol describing any object that exposes `atomic_write(context: str) -> AbstractAsyncContextManager[None]` (satisfied by `GitSyncManager` without explicit inheritance).

2. Refactor `ExtractorRunner` to accept `save_context: SaveContext | None = None`, default to `default_save_context`, and wrap just the `extraction.save_to_file()` call inside the existing `try/except` in `run_job()`. The compute phase (`extractor.extract(...)`) remains outside the lock.

3. Refactor `EvalRunner` the same way: accept `save_context`, wrap just the `eval_run.save_to_file()` call inside the existing `try/except` in `run_job()`. Retryable/non-retryable exceptions continue to propagate.

4. Refactor the three RAG step job functions (`execute_extractor_job`, `execute_chunker_job`, `execute_embedding_job`) to accept `save_context: SaveContext | None = None` and wrap just the `save_to_file()` call. The step runner classes (`RagExtractionStepRunner`, `RagChunkingStepRunner`, `RagEmbeddingStepRunner`) accept `save_context` in their constructors and close over it when building the `run_job_fn` lambda for `AsyncJobRunner`. `RagIndexingStepRunner` is NOT wrapped (it writes to an external vector store, not to git-tracked files).

5. Thread `save_context` through `build_rag_workflow_runner()` in `libs/server/kiln_server/document_api.py` down to the three file-writing step runner constructors. The indexing step runner does not get it.

6. Unit tests for each runner verifying:
   - Deferred save behavior (default context is a no-op; save happens normally).
   - Correct wiring when a custom context is passed (context `__aenter__` / `__aexit__` wrap each save).
   - Rollback-on-error semantics: if the save raises, the context's `__aexit__` sees the exception (so a git-sync implementation can roll back); the surrounding runner error behavior is preserved.

All existing tests continue to pass. No behavior change for callers who don't pass `save_context`.

## Steps

1. **Create `libs/core/kiln_ai/utils/git_sync_protocols.py`:**

   ```python
   from collections.abc import AsyncIterator, Callable
   from contextlib import AbstractAsyncContextManager, asynccontextmanager
   from typing import Protocol

   SaveContext = Callable[[], AbstractAsyncContextManager[None]]

   @asynccontextmanager
   async def default_save_context() -> AsyncIterator[None]:
       yield

   class AtomicWriteCapable(Protocol):
       def atomic_write(self, context: str) -> AbstractAsyncContextManager[None]:
           ...
   ```

2. **Refactor `ExtractorRunner`** (`libs/core/kiln_ai/adapters/extractors/extractor_runner.py`):
   - Add `save_context: SaveContext | None = None` to `__init__`.
   - Store `self._save_context: SaveContext = save_context or default_save_context`.
   - In `run_job`, keep all compute outside the save context; wrap only the `extraction = Extraction(...); extraction.save_to_file()` block:

     ```python
     async with self._save_context():
         extraction = Extraction(...)
         extraction.save_to_file()
     ```

   The outer `try/except Exception` continues to swallow errors and return `False`. The `async with` `__aexit__` runs before the `except`, so rollback happens before the error is swallowed.

3. **Refactor `EvalRunner`** (`libs/core/kiln_ai/adapters/eval/eval_runner.py`):
   - Add `save_context: SaveContext | None = None` to `__init__`.
   - Store `self._save_context`.
   - In `run_job`, wrap only:

     ```python
     async with self._save_context():
         eval_run = EvalRun(...)
         eval_run.save_to_file()
     ```

   Retryable errors continue to raise `RetryableError`; non-retryable errors continue to re-raise. `__aexit__` runs first in both cases.

4. **Refactor RAG step job functions** (`libs/core/kiln_ai/adapters/rag/rag_runners.py`):
   - `execute_extractor_job(job, extractor, save_context=None)`: compute `output`, build `extraction`, then `async with (save_context or default_save_context)(): extraction.save_to_file()`.
   - `execute_chunker_job(job, chunker, save_context=None)`: same pattern around `chunked_document.save_to_file()`.
   - `execute_embedding_job(job, embedding_adapter, save_context=None)`: same pattern around `chunk_embeddings.save_to_file()`. The early `return True` for the empty-chunks case remains outside the context.

5. **Refactor RAG step runner classes** (`libs/core/kiln_ai/adapters/rag/rag_runners.py`):
   - `RagExtractionStepRunner.__init__` takes `save_context: SaveContext | None = None`; stores `self._save_context = save_context or default_save_context`.
   - In `RagExtractionStepRunner.run`, capture `save_ctx = self._save_context` and build the `run_job_fn` lambda as `lambda job: execute_extractor_job(job, extractor, save_context=save_ctx)`.
   - Same for `RagChunkingStepRunner` and `RagEmbeddingStepRunner`.
   - `RagIndexingStepRunner` unchanged.

6. **Thread `save_context` through `build_rag_workflow_runner`** (`libs/server/kiln_server/document_api.py`):
   - Add `save_context: SaveContext | None = None` parameter.
   - Pass it to `RagExtractionStepRunner`, `RagChunkingStepRunner`, `RagEmbeddingStepRunner`. Do NOT pass to `RagIndexingStepRunner`.
   - No callsite changes required (callers omit the kwarg; phase 3 will wire it from the endpoint).

7. **Add unit tests** (see Tests section below).

## Tests

### `test_git_sync_protocols.py` (new, in `libs/core/kiln_ai/utils/`)

- `test_default_save_context_is_no_op`: enter and exit; no side effect; runs cleanly.
- `test_default_save_context_propagates_exceptions`: raising inside `async with default_save_context():` still raises.
- `test_atomic_write_capable_structural`: a minimal duck-typed class with an `atomic_write` method satisfies `AtomicWriteCapable` (runtime smoke test; the real type-check is static).

### `test_extractor_runner.py` additions

- `test_run_job_default_save_context_saves_extraction`: with no `save_context` passed, `run_job` saves the extraction as before. (Existing behavior regression guard.)
- `test_run_job_custom_save_context_wraps_save`: pass a recording context manager that tracks enter/exit + whether the file exists at enter-time and at exit-time; assert enter happened before save and exit happened after save completed.
- `test_run_job_save_context_sees_save_exception`: pass a recording context manager; patch `Extraction.save_to_file` to raise; assert the context's `__aexit__` was called with the exception info, and `run_job` returns `False` (existing swallow behavior preserved).

### `test_eval_runner.py` additions

- `test_run_job_default_save_context_saves_eval_run`: default path saves the eval run normally.
- `test_run_job_custom_save_context_wraps_save`: passes a recording context manager; asserts enter before save, exit after save.
- `test_run_job_save_context_sees_save_exception`: save raises; context's `__aexit__` sees the exception; the exception propagates (non-retryable); existing re-raise behavior preserved.

### `test_rag_runners.py` additions

- `test_execute_extractor_job_default_save_context`: calls the function with no `save_context`; verifies extraction is saved.
- `test_execute_extractor_job_custom_save_context`: recording context wraps save.
- `test_execute_extractor_job_save_context_sees_exception`: save raises; context sees exception; function propagates.
- Same three tests for `execute_chunker_job` and `execute_embedding_job`.
- `test_rag_extraction_step_runner_passes_save_context`: construct with a recording save context; run one job; assert the context was entered for the save.
- Same wiring test for `RagChunkingStepRunner` and `RagEmbeddingStepRunner`.

### `document_api` tests

- `test_build_rag_workflow_runner_threads_save_context`: call `build_rag_workflow_runner` with a custom `save_context`; assert that `RagExtractionStepRunner`, `RagChunkingStepRunner`, and `RagEmbeddingStepRunner` received it (by checking `_save_context` attribute) and `RagIndexingStepRunner` did not (it has no such attribute).
