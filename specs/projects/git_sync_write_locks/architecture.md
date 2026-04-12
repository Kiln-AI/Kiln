---
status: complete
---

# Architecture: Git Sync Write Locks

## Overview

Two workstreams: (1) add an `atomic_write` context manager to `GitSyncManager`, refactor the middleware to use it, and inject it into runner jobs for SSE endpoints, and (2) add dev-mode dirty state detection in the middleware.

## Component 1: `atomic_write` Context Manager on GitSyncManager

### The Shared Write Pattern

The middleware's write-lock path (middleware.py lines 88-144) implements this sequence:

1. Acquire write lock
2. `ensure_clean()`
3. `ensure_fresh()`
4. Capture `pre_head`
5. Do work
6. If dirty → `commit_and_push(context_string, pre_head)`
7. On error → `rollback(pre_head)`

This same sequence is needed inside runner jobs. Extract it as a method on `GitSyncManager`:

```python
class GitSyncManager:
    @asynccontextmanager
    async def atomic_write(self, context: str):
        """Context manager for atomic file writes with git sync.

        Acquires the write lock, ensures clean+fresh state, yields for the
        caller to perform file writes, then commits and pushes. On error,
        rolls back all writes made within the block.

        Args:
            context: Descriptive string for the commit message
                     (e.g. "POST /api/projects/123/tasks" or "extraction job for doc 456")
        """
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

### Rename `api_path` → `context` in `commit_and_push`

Rename the `api_path` parameter to `context` throughout `commit_and_push` and its callsites. This reflects that the context string is no longer always an API path — it can be a job description, a background task name, etc.

### Generalize commit message format

Update `generate_commit_message` in `commit_message.py`:

```python
# Before:
f"[Kiln] Auto-sync: {files_str}\n\nAPI: {api_path}"

# After:
f"[Kiln] Auto-sync: {files_str}\n\nContext: {context}"
```

Callers pass descriptive strings:
- Middleware: `f"{request.method} {request.url.path}"` (e.g. `"POST /api/projects/123/tasks"`)
- Runner jobs: `f"extraction job for doc {doc.id}"`, `f"eval run for {eval_config.id}"`, etc.
- Integration tests: `"TEST atomic_write"`, `"TEST library_mode"`

### Middleware Refactor

The middleware's write-lock path simplifies to:

```python
# Before: 60 lines of lock/clean/fresh/buffer/commit/rollback
# After:
async with manager.atomic_write(f"{request.method} {request.url.path}"):
    response = await call_next(request)

    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        # SSE safety net (unchanged)
        ...

    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    # Long lock hold warning (unchanged)
    ...

return Response(content=body, ...)
```

The SSE detection, body buffering, and long-lock-hold warning stay in the middleware — they're request-specific concerns. The lock lifecycle moves to `atomic_write`.

Note: the existing error handling in the middleware catches `GitSyncError` and maps to HTTP status codes. This stays in the middleware's `except` block wrapping the `atomic_write` call, since error-to-HTTP mapping is a middleware concern.

## Component 2: Save Context Injection into Runner Jobs

### Pattern: Inject a `save_context` Factory

Each runner accepts an optional callable that returns an async context manager. Wraps the write phase of each job. Default is a no-op (regular library behavior).

**Type (in `libs/core`):**

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable
from typing import AbstractAsyncContextManager

SaveContext = Callable[[], AbstractAsyncContextManager[None]]

@asynccontextmanager
async def default_save_context() -> AsyncIterator[None]:
    yield
```

**Git sync factory (in `app/desktop`):**

```python
def make_git_sync_save_context(manager: GitSyncManager, context: str) -> SaveContext:
    def factory():
        return manager.atomic_write(context=context)
    return factory
```

This is a one-liner — `atomic_write` already does the full lock cycle.

### Runner Changes

Each runner accepts `save_context: SaveContext | None = None` and wraps its write phase:

**ExtractorRunner:**
```python
class ExtractorRunner:
    def __init__(
        self,
        documents: List[Document],
        extractor_configs: List[ExtractorConfig],
        save_context: SaveContext | None = None,
    ):
        self._save_context = save_context or default_save_context
        # ... existing fields ...

    async def run_job(self, job: ExtractorJob) -> bool:
        # Compute phase — no lock, can take minutes
        output = await extractor.extract(...)

        # Write phase — under lock if git sync active, milliseconds
        async with self._save_context():
            extraction = Extraction(parent=job.doc, ...)
            extraction.save_to_file()

        return True
```

**EvalRunner** — same pattern. Compute (run eval/run task), then write phase wrapping `eval_run.save_to_file()`.

**RAG step job functions** (`execute_extractor_job`, `execute_chunker_job`, `execute_embedding_job`) — these are standalone `async def`s. The step runner classes (`RagExtractionStepRunner`, etc.) accept `save_context` in their constructor and pass it via closure/partial to the job functions:

```python
class RagExtractionStepRunner(AbstractRagStepRunner):
    def __init__(self, ..., save_context: SaveContext | None = None):
        self._save_context = save_context or default_save_context

    async def run(self, ...):
        save_ctx = self._save_context
        async def job_fn(job):
            return await execute_extractor_job(job, extractor, save_context=save_ctx)
        runner = AsyncJobRunner(jobs=jobs, run_job_fn=job_fn, ...)
        async for progress in runner.run():
            yield progress
```

The `RagWorkflowRunner` passes `save_context` through to each step runner it creates.

### No AsyncJobRunner Changes

`AsyncJobRunner` is untouched. The lock cycle is invisible to it — happens inside `run_job_fn`.

### Atomic Units

Each job's write phase = one `atomic_write` call = one lock acquisition + file write(s) + one commit + push. A job that writes multiple files (possible in some runners) has all writes in one atomic commit. If an exception occurs mid-write, all files in that block are rolled back.

With concurrent workers (up to 25), the lock serializes writes but compute runs in parallel. Each worker: compute (seconds, no lock) → write (milliseconds, under lock) → next job.

**Performance:** `ensure_clean()` is a no-op when clean. `ensure_fresh()` has a 15-second freshness cache — rapid saves skip the fetch. The main cost is git commit + push per job, which is acceptable given jobs take seconds to minutes each.

## Component 3: SSE Endpoint Wiring

### Decorator Application

All 5 SSE endpoints get `@no_write_lock`:

| Endpoint | File | HTTP |
|----------|------|------|
| `run_extractor_config` | `libs/server/kiln_server/document_api.py` | GET |
| `extract` | `libs/server/kiln_server/document_api.py` | POST |
| `run` (RAG) | `libs/server/kiln_server/document_api.py` | GET |
| `run_comparison` | `app/desktop/studio_server/eval_api.py` | GET |
| `run_calibration` | `app/desktop/studio_server/eval_api.py` | GET |

### Import Boundary

Move `no_write_lock` and `write_lock` decorators from `app/desktop/git_sync/decorators.py` to `libs/server/kiln_server/git_sync_decorators.py`. They're 4 lines each with zero dependencies — just set an attribute on the function. The middleware reads the attribute regardless of where it was set. Update existing imports in middleware and tests.

### Middleware: Attach Manager to `request.state`

In the read path, attach the resolved manager so endpoints can build the save context:

```python
if not needs_lock:
    request.state.git_sync_manager = manager
    # ... existing ensure_fresh_for_read, notify_background_sync ...
```

### Endpoint Changes

Each endpoint reads the manager, builds a save context, passes it to the runner:

```python
@router.get("/.../run_extractor_config")
@no_write_lock
async def run_extractor_config(request: Request, ...):
    manager = getattr(request.state, "git_sync_manager", None)
    save_context = make_git_sync_save_context(manager, request.url.path) if manager else None
    # ... existing setup ...
    runner = ExtractorRunner(documents, extractor_configs, save_context=save_context)
    return run_extractor_runner_with_status(runner)
```

The SSE generator functions are unchanged — they still iterate `runner.run()` and yield SSE events. The lock cycle is invisible to them.

**`make_git_sync_save_context` location:** Lives in `app/desktop/git_sync/` (it imports `GitSyncManager`). The eval endpoints in `app/desktop/studio_server/` can import it directly. The document_api endpoints in `libs/server/` need the save context passed in from the endpoint layer — since these endpoints receive `request.state.git_sync_manager` at runtime, they can build the context there using a helper that doesn't import git sync types (just calls `manager.atomic_write(path)`).

Simpler: put a thin `build_save_context(request)` helper in `libs/server/` that reads from `request.state` and returns a `SaveContext | None`. It calls `manager.atomic_write(path)` on an `Any`-typed manager — no git sync imports needed:

```python
def build_save_context(request: Request) -> SaveContext | None:
    manager = getattr(request.state, "git_sync_manager", None)
    if manager is None:
        return None
    def factory():
        return manager.atomic_write(context=request.url.path)
    return factory
```

## Component 4: Middleware Dev-Mode Dirty Check

### Flow

After a non-locked, non-`@no_write_lock` request completes, check for dirty files in dev mode:

```python
if not needs_lock:
    request.state.git_sync_manager = manager
    is_self_managed = getattr(endpoint, "_git_sync_no_write_lock", False)

    if is_self_managed:
        await manager.ensure_fresh_for_read()
        self._notify_background_sync(manager)
        return await call_next(request)

    # Regular read path
    await manager.ensure_fresh_for_read()
    self._notify_background_sync(manager)
    response = await call_next(request)

    if _is_dev_mode():
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            logger.error(
                "DEV MODE: SSE endpoint missing @no_write_lock: %s %s",
                request.method, request.url.path,
            )
        elif await manager.has_dirty_files():
            dirty = await manager.get_dirty_file_paths()
            logger.error(
                "DEV MODE: Request left repo dirty without write lock!\n"
                "  API: %s %s\n  Dirty files: %s",
                request.method, request.url.path, dirty,
            )
            return Response(
                content=json.dumps({
                    "detail": "Dev mode: this endpoint wrote files without "
                              "holding a write lock. See server logs."
                }),
                status_code=500,
                media_type="application/json",
            )

    return response
```

### Dev-Mode Detection

Add a new `KILN_DEV_MODE` env var set in `dev_server.py` (alongside the existing `DEBUG_EVENT_LOOP`). This is a dedicated flag for dev-mode safety nets, separate from the asyncio debug flag:

```python
# dev_server.py
os.environ["KILN_DEV_MODE"] = "true"
```

```python
# middleware.py
def _is_dev_mode() -> bool:
    return os.environ.get("KILN_DEV_MODE", "false") == "true"
```

### New Method: `get_dirty_file_paths()`

Add to `GitSyncManager`. Wraps the existing `repo.status()` call used by `has_dirty_files()` but returns the list of file paths instead of a boolean.

## Component 5: Integration Test Parametrization

### Existing Infrastructure

The integration tests use a `write_ctx` fixture parametrized over two modes (`conftest.py:451`):

```python
@pytest.fixture(params=["library", "api"])
def write_ctx(request, git_repos):
```

- **`library`** — `LibraryWriteContext`: calls `write_lock()`, `ensure_clean()`, `ensure_fresh()`, `commit_and_push()` directly (the manual lock cycle)
- **`api`** — `APIWriteContext`: sends HTTP requests through `TestClient` with `GitSyncMiddleware` (the middleware lock cycle)

Both implement the `WriteContext` protocol: `do_write(write_fn)` and `do_read()`. Tests use `write_ctx` and are agnostic to which mode runs. This is black-box coverage — the same scenarios verify both code paths.

### Adding `atomic_write` as a Third Mode

Add an `AtomicWriteContext` class that uses `manager.atomic_write()`:

```python
class AtomicWriteContext:
    def __init__(self, manager: GitSyncManager, repo_path: Path, remote_path: Path):
        self.manager = manager
        self.repo_path = repo_path
        self.remote_path = remote_path

    async def do_write(
        self,
        write_fn: Callable[[Path], object],
        expect_error: bool = False,
    ) -> WriteResult:
        try:
            async with self.manager.atomic_write("TEST atomic_write"):
                write_fn(self.repo_path)

            post_head = get_head_sync(self.repo_path)
            pushed = remote_has_commit(self.remote_path, post_head)
            return WriteResult(
                committed=await self.manager.has_dirty_files() is False
                    and pushed,  # simplified — check head moved
                committed=True,
                pushed=pushed,
            )
        except Exception as e:
            if expect_error:
                return WriteResult(committed=False, pushed=False, error=str(e))
            raise

    async def do_read(self) -> ReadResult:
        return ReadResult(body={"status": "ok"})
```

Update the fixture parametrization:

```python
@pytest.fixture(params=["library", "api", "atomic_write"])
def write_ctx(request, git_repos):
    local_path, remote_path = git_repos
    config = auto_config(str(local_path))

    if request.param == "library":
        # ... existing ...
    elif request.param == "atomic_write":
        mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
        ctx = AtomicWriteContext(mgr, local_path, remote_path)
        with mock_git_sync_config(config):
            yield ctx
        mgr._git_executor.shutdown(wait=False)
    else:
        # ... existing api ...
```

**No other test changes.** All existing `write_ctx` tests (happy path, rollback, conflicts, crash recovery, file operations, network failures) automatically run against `atomic_write` via the new parametrization. This validates that `atomic_write` behaves identically to the manual lock cycle and the middleware path.

### What This Validates

The `LibraryWriteContext` is essentially the inline expansion of what `atomic_write` does. Running the same black-box tests against both proves that `atomic_write` correctly encapsulates the lock cycle — if any test passes for `library` but fails for `atomic_write`, the extraction has a bug.

## Component 6: New Unit Tests

**`atomic_write` on GitSyncManager:**
- Clean write → files committed and pushed
- Exception mid-write → all files rolled back
- No dirty files after yield → no commit attempted
- Context string appears in commit message

**Middleware refactor:**
- Existing middleware tests continue to pass (behavior unchanged, just using `atomic_write` internally)
- New: dev-mode dirty check tests (dirty + dev → 500, dirty + non-dev → pass, SSE without decorator → logged, `@no_write_lock` → skip check, clean → pass)

**`save_context` injection:**
- Runner with `save_context=None` → files saved directly (existing behavior)
- Runner with git sync save context → `atomic_write` called per job
- Multiple saves in one job → one atomic commit
- Exception during write phase → rollback, other jobs unaffected

**`get_dirty_file_paths()`:**
- Returns correct paths for modified/added/deleted files
- Returns empty list for clean repo
