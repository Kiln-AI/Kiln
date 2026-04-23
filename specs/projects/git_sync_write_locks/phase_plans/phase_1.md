---
status: complete
---

# Phase 1: `atomic_write` context manager and middleware refactor

## Overview

Establish the foundation for the rest of the project by:

1. Adding an `atomic_write` async context manager to `GitSyncManager` that encapsulates the full write lock cycle (acquire lock -> ensure clean -> ensure fresh -> capture head -> yield -> commit-and-push / rollback on error).
2. Generalizing the "commit context" naming -- renaming the `api_path` parameter on `commit_and_push` / `_create_commit` / `generate_commit_message` to `context`, and switching the commit message format from `API: {...}` to `Context: {...}` so callers other than the middleware (runner jobs, background tasks) can supply meaningful strings.
3. Refactoring the middleware write path to delegate its lock lifecycle to `atomic_write`, keeping only the middleware-specific concerns (SSE safety net, body buffering, long-lock warning, HTTP error mapping).
4. Adding `atomic_write` as a third parametrization of the `write_ctx` integration-test fixture so all existing black-box scenarios automatically run against the new context manager.

All existing tests must continue to pass. The external behavior (HTTP mapping, SSE safety net, crash recovery, commit message structure) is unchanged.

## Steps

1. **Rename `api_path` -> `context` in `commit_message.py`**
   - Update `generate_commit_message(file_count: int, context: str) -> str`.
   - Change the trailing `f"\n\nAPI: {api_path}"` to `f"\n\nContext: {context}"`.
   - Update the three tests in `test_commit_message.py` to pass `context=` and assert `"Context: ..."` instead of `"API: ..."`. Keep the tests otherwise identical.

2. **Rename `api_path` -> `context` in `GitSyncManager`**
   - `commit_and_push(self, context: str, pre_request_head: str)` (replacing `api_path`).
   - `_create_commit(self, context: str)` (replacing `api_path`).
   - Update `test_git_sync_manager.py` callsites (`api_path="..."` -> `context="..."`) in three tests.

3. **Add `atomic_write` to `GitSyncManager`**
   - New method, under `write_lock`, at class level (declared above `ensure_clean` or just below `write_lock` for readability):

     ```python
     @asynccontextmanager
     async def atomic_write(self, context: str):
         async with self.write_lock():
             await self.ensure_clean()
             await self.ensure_fresh()
             pre_head = await self.get_head()
             try:
                 yield
                 if await self.has_dirty_files():
                     await self.commit_and_push(
                         context=context,
                         pre_request_head=pre_head,
                     )
             except Exception:
                 await self.rollback(pre_head)
                 raise
     ```

   - Rely on the existing `asynccontextmanager` import.

4. **Refactor middleware write path to use `atomic_write`**
   - Keep everything up to `if not needs_lock:` unchanged.
   - Replace the body of the write-locked path (lines 84-156) with a structure that:
     - Calls `self._notify_background_sync(manager)` and starts `lock_start = time.monotonic()` outside the try (unchanged ordering).
     - Uses `async with manager.atomic_write(f"{request.method} {request.url.path}"):` to wrap the inner work.
     - Inside the `atomic_write` block: `response = await call_next(request)`, SSE detection (return-500-and-let-atomic_write-rollback via `raise`), body buffering into `body`, long-lock-hold warning after body read (still inside the block so it covers the real hold duration).
     - After the `atomic_write` block returns cleanly, return `Response(content=body, ...)` as today.
     - Wrap the whole `atomic_write` call in `except GitSyncError as e:` to map the error to an HTTP response using `_map_error`. Non-`GitSyncError` exceptions propagate (same as today); `atomic_write` will have already rolled back.
   - For the SSE safety net specifically: inside the `atomic_write` block, if the response is `text/event-stream`, log the error and raise `StreamingUnderWriteLockError` (new local exception or just raise a plain `RuntimeError` wrapped in a helper so it triggers rollback). To keep a clean boundary, define a small private sentinel exception `_StreamingUnderWriteLock(Exception)` at module scope, raise it inside the block, and catch it just outside to return the existing 500 JSON response. This preserves today's behavior: return 500 JSON, rollback dirty changes, do NOT commit.
   - Net result: the lock acquisition, `ensure_clean`, `ensure_fresh`, `pre_request_head` capture, dirty check, commit-and-push, and rollback all move into `atomic_write`. The middleware retains HTTP concerns only.

5. **Update `write_ctx` fixture to add an `atomic_write` parametrization**
   - In `app/desktop/git_sync/integration_tests/conftest.py`:
     - Add an `AtomicWriteContext` class implementing the `WriteContext` protocol. It holds a `GitSyncManager` and calls `async with self.manager.atomic_write("TEST atomic_write"):` inside `do_write`, captures pre/post head for `committed`/`pushed` just like `LibraryWriteContext`, maps `Exception` to `WriteResult(error=...)` when `expect_error=True`.
     - Change `LibraryWriteContext.do_write` call to use `context="TEST library_mode"` (rename from `api_path=`). Also update the `APIWriteContext` commit-message assertion test (`test_api_commit_message_contains_path` in `test_happy_path.py`) -- it asserts `"POST" in head_commit.message` which still holds because the middleware still passes `"{method} {path}"`, so no test change needed there.
     - Change `write_ctx` fixture params to `["library", "api", "atomic_write"]` and add the third branch that constructs an `AtomicWriteContext`.
   - Update `test_no_write_lock_batch.py` to pass `context=api_path` (rename callsite) in its `commit_and_push` call.

6. **Sanity-check SSE middleware path**
   - After refactor, verify that the existing SSE tests (in `test_decorators.py`, and/or any other middleware tests hitting the streaming response path) still return a 500 JSON payload with the same `detail`. If the sentinel-exception approach isn't clean enough, alternative: have the SSE branch call `await manager.rollback(pre_head_captured_separately)` directly and return early -- but this re-leaks the lock lifecycle back into the middleware. Prefer the sentinel approach to keep lock lifecycle inside `atomic_write`.

## Tests

- `test_commit_message.py`: three existing tests updated to use `context=` parameter name and assert `Context: ...` substring in the message. (Renames only -- behavior unchanged.)

- `test_git_sync_manager.py`: three existing `commit_and_push` tests updated to pass `context=` instead of `api_path=`. No new behavioral assertions in these tests.

- **New: `test_atomic_write_success`** (in `test_git_sync_manager.py`) -- writes a file inside `async with manager.atomic_write("test ctx"):`, asserts post-yield repo is clean, a new commit exists on local and remote, and `"Context: test ctx"` appears in the HEAD commit message.

- **New: `test_atomic_write_rolls_back_on_exception`** -- writes a file then raises inside the block; asserts repo is back to `pre_head`, no new commit on remote, no dirty files.

- **New: `test_atomic_write_no_op`** -- enters the block but writes nothing; asserts no commit is made and HEAD is unchanged.

- **New: `test_atomic_write_context_in_commit_message`** -- writes a file with a specific context string; asserts the HEAD commit body contains `Context: {that string}`.

- **Integration tests**: by adding the `atomic_write` parametrization, every existing test in `test_happy_path.py`, `test_rollback.py`, `test_conflicts.py`, `test_crash_recovery.py`, `test_file_operations.py`, `test_network_failure.py`, and `test_freshness.py` that uses `write_ctx` automatically gains a third parametrization run. They must all pass. Some tests that only use `api_ctx` or `library_ctx` directly need no change. Scenario 1's `test_api_commit_message_contains_path` uses `api_ctx` only -- no new parametrization needed there, and its assertions (`"1 file"`, `"POST"`, `"test_write"`) still hold because the middleware still forms the string as `"{method} {path}"`.

- Existing middleware tests (in `test_middleware.py` and integration middleware/routing tests) must continue to pass -- behavior is unchanged externally.
