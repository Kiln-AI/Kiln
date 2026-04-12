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
try:
    async with manager.atomic_write(f"{request.method} {request.url.path}"):
        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            # SSE safety net (unchanged) — returns 500 before atomic_write
            # can commit, so body_iterator is never consumed under lock
            ...

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Long lock hold warning (unchanged)
        ...

    return Response(content=body, ...)
except GitSyncError as e:
    status = ERROR_MAP.get(type(e), 500)
    return JSONResponse({"detail": str(e)}, status_code=status)
```

The SSE detection, body buffering, and long-lock-hold warning stay in the middleware — they're request-specific concerns. The lock lifecycle moves to `atomic_write`.

The `except GitSyncError` block wraps the `atomic_write` call (not inside it), because error-to-HTTP mapping is a middleware concern, not a lock-lifecycle concern. `atomic_write`'s rollback runs on its way out (via `__aexit__`), then the exception propagates to the middleware's `except` for HTTP mapping.

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

**Protocol for type-safe manager references (in `libs/core`):**

`libs/server` cannot import `GitSyncManager` directly (it lives in `app/desktop`). But we still want type-checked calls to `manager.atomic_write(...)` in the `libs/server` helper. Define a structural Protocol in `libs/core`:

```python
from typing import Protocol

class AtomicWriteCapable(Protocol):
    def atomic_write(self, context: str) -> AbstractAsyncContextManager[None]: ...
```

`GitSyncManager` satisfies this protocol structurally (no explicit inheritance needed). `libs/server` imports `AtomicWriteCapable` from `libs/core` and uses it when typing any `manager` reference pulled off `request.state`. A typo like `manager.atomc_write(...)` is then caught by the type checker.

**Git sync factory (in `app/desktop`):**

```python
def make_git_sync_save_context(manager: GitSyncManager, context: str) -> SaveContext:
    def factory():
        return manager.atomic_write(context=context)
    return factory
```

This is a one-liner — `atomic_write` already does the full lock cycle.

### Placement Rule

There is no universal rule for where to wrap with `save_context`. The guiding principle:

- **Wrap a group of writes together** when they must succeed atomically — if one fails, all should roll back (e.g., a parent record + its attachments that only make sense together).
- **Wrap individual writes** when the surrounding job is already designed to tolerate partial success (e.g., a batch job that reports per-item failures and keeps going).

Place the `async with self._save_context():` block **inside** any existing runner try/except. Python's `async with` guarantees `__aexit__` runs before the enclosing `except` clause, so rollback happens even when the runner catches the exception. This means existing runner error-handling (swallow-and-return-False, re-raise, etc.) is preserved untouched — the `save_context` only adds rollback behavior.

### Runner Changes

Each runner accepts `save_context: SaveContext | None = None` and wraps its write phase:

**ExtractorRunner** (`libs/core/.../extractor_runner.py:71-112`) — one `save_to_file()` per job, inside a broad `except Exception` that returns `False`. Wrap just the save call, inside the existing try:

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
        try:
            # Compute phase — no lock, can take minutes
            output = await extractor.extract(...)

            # Write phase — under lock if git sync active
            async with self._save_context():
                extraction = Extraction(parent=job.doc, ...)
                extraction.save_to_file()

            return True
        except Exception as e:
            logger.error(...)
            return False   # rollback already ran via __aexit__
```

**EvalRunner** (`libs/core/.../eval_runner.py:198-277`) — one `save_to_file()` per job, re-raises on error (wrapping retryable errors). Wrap just the save call; rollback runs, then the exception propagates unchanged.

**RAG step job functions** (`execute_extractor_job`, `execute_chunker_job`, `execute_embedding_job` in `libs/core/.../rag_runners.py`) — standalone `async def`s with a single `save_to_file()` each and no try/except. Wrap just the save call; exceptions continue propagating to `GenericErrorCollector` as today.

**General rule for inclusion:** a write needs `save_context` wrapping only if it writes to the filesystem AND that filesystem location is inside the project repo. Vector store writes, remote API calls, external database writes, and writes to temp/cache directories outside the repo are all excluded — `save_context` is strictly about capturing file-level changes into git.

**RagIndexingStepRunner excluded** under this rule — it writes to an external vector store, not a git-tracked file in the project repo. Do not wrap.

The step runner classes (`RagExtractionStepRunner`, `RagChunkingStepRunner`, `RagEmbeddingStepRunner`) accept `save_context` in their constructor and pass it via closure/partial to the job functions:

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

### Threading `save_context` Through RAG Construction

`RagWorkflowRunner` does NOT construct its step runners — it receives them pre-built via `RagWorkflowRunnerConfiguration`. Construction happens in `build_rag_workflow_runner()` at `libs/server/kiln_server/document_api.py:807`, which instantiates each step runner and packages them into the config.

The injection point is therefore `build_rag_workflow_runner()`, not `RagWorkflowRunner`:

```python
async def build_rag_workflow_runner(
    project, rag_config_id, save_context: SaveContext | None = None,
):
    # ... existing setup ...
    step_runners = [
        RagExtractionStepRunner(..., save_context=save_context),
        RagChunkingStepRunner(..., save_context=save_context),
        RagEmbeddingStepRunner(..., save_context=save_context),
        RagIndexingStepRunner(...),  # no save_context — writes to vector store
    ]
    # ... pack into RagWorkflowRunnerConfiguration, construct RagWorkflowRunner ...
```

`RagWorkflowRunner` itself requires no changes. The endpoint passes `save_context` (built via `build_save_context(request)`) into `build_rag_workflow_runner()`.

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

### Endpoint Signature: `Request` Parameter Required

None of the 5 SSE endpoints currently accept `request: Request` in their signature:

- `run_extractor_config` — `document_api.py:1380`
- `extract_file` — `document_api.py:1725`
- `run_rag_config` (the `run` endpoint) — `document_api.py:2360`
- `run_eval_config_eval` / `run_comparison` — `eval_api.py:769`
- `run_calibration` — `eval_api.py:873`

Each needs `request: Request` added so it can read `request.state.git_sync_manager`. FastAPI auto-injects the `Request` object — no callers need to change. This is a required mechanical change to all 5 endpoint signatures.

### Endpoint Changes

Each endpoint reads the manager, builds a save context, passes it to the runner:

```python
@router.get("/.../run_extractor_config")
@no_write_lock
async def run_extractor_config(request: Request, ...):
    save_context = build_save_context(request)
    # ... existing setup ...
    runner = ExtractorRunner(documents, extractor_configs, save_context=save_context)
    return run_extractor_runner_with_status(runner)
```

The SSE generator functions (`run_extractor_runner_with_status`, `run_rag_workflow_runner_with_status`) are unchanged — they still iterate `runner.run()` and yield SSE events. The lock cycle is invisible to them.

**`build_save_context` helper** lives in `libs/server/` and returns a `SaveContext | None` using the `AtomicWriteCapable` Protocol for type safety:

```python
from kiln_ai.git_sync_protocols import AtomicWriteCapable  # from libs/core

def build_save_context(request: Request) -> SaveContext | None:
    manager: AtomicWriteCapable | None = getattr(
        request.state, "git_sync_manager", None
    )
    if manager is None:
        return None
    def factory():
        return manager.atomic_write(context=request.url.path)
    return factory
```

No git sync imports from `app/desktop` are needed. The Protocol lives in `libs/core`, which both `libs/server` and `app/desktop` can import.

### Error Mapping for Self-Managed Endpoints

By moving lock management from the middleware into the endpoints, `GitSyncError` subclasses raised inside the endpoint no longer hit the middleware's `ERROR_MAP`. This is intentional — the SSE runner loop already catches per-item exceptions and surfaces them as per-item error events in the SSE stream, which is more informative than a single top-level 503. For example, "6 of 50 documents failed to extract because of git push rejection" is more actionable than a blanket 503 for the whole request.

A bare `GitSyncError` raised outside any per-item try (e.g., from the initial `ensure_clean()` on the first job) will still bubble up as a generic 500 from FastAPI. This is acceptable — per-item errors are the common case, and first-job-setup failures are rare and loud.

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
        pre_head = get_head_sync(self.repo_path)
        try:
            async with self.manager.atomic_write("TEST atomic_write"):
                write_fn(self.repo_path)

            post_head = get_head_sync(self.repo_path)
            committed = post_head != pre_head
            pushed = committed and remote_has_commit(self.remote_path, post_head)
            return WriteResult(committed=committed, pushed=pushed)
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
