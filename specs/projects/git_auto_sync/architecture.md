---
status: draft
---

# Architecture: Git Auto Sync

## Overview

Git Auto Sync adds transparent git-based synchronization to Kiln projects. The system works at the HTTP middleware level — no changes to `libs/core/` or `KilnBaseModel`. File I/O happens exactly as it does today; the git sync system observes and commits changes after the fact via `git status`.

The architecture has four major components:
1. **FastAPI Middleware** — Acquires write lock for mutating requests, commits/pushes on exit
2. **GitSyncManager** — Core sync engine (locking, pygit2, commit/push/rollback)
3. **Background Sync** — Async poller keeping repos fresh
4. **Manager Registry** — Singleton management of per-repo managers

## Component Breakdown

### 1. FastAPI Middleware (`app/desktop/`)

Uses Starlette's `BaseHTTPMiddleware` to buffer the response body before committing. This allows commit/push failures to return error responses instead of silently failing after a 200 has been sent.

**Fallback:** If integration testing reveals issues with `BaseHTTPMiddleware` (contextvar propagation, Starlette version compatibility), a raw ASGI middleware is the documented fallback. An early integration test is a blocking gate before other git sync work proceeds.

```python
# app/desktop/git_sync/middleware.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class GitSyncMiddleware(BaseHTTPMiddleware):
    """Wraps mutating requests with write lock + git commit/push.

    For non-mutating requests and non-auto-sync routes,
    passes through without buffering (preserves streaming responses).
    """

    async def dispatch(self, request: Request, call_next):
        manager = self._get_manager_for_request(request)

        if manager is None:
            # No auto-sync for this route — pass through
            return await call_next(request)

        endpoint = request.scope.get("endpoint")
        needs_lock = (
            request.method in MUTATING_METHODS
            or getattr(endpoint, "_git_sync_write_lock", False)
        ) and not getattr(endpoint, "_git_sync_no_write_lock", False)

        if not needs_lock:
            # GET/HEAD — pass through, no locking or buffering
            # Check freshness threshold for reads
            await manager.ensure_fresh_for_read()
            # Dev-mode: check for dirty state before/after (safety net)
            if settings.dev_mode:
                await self._check_dirty_state(manager, request, "before")
            response = await call_next(request)
            if settings.dev_mode:
                await self._check_dirty_state(manager, request, "after")
            return response

        # Mutating request — acquire lock, commit on exit
        lock_start = time.monotonic()
        async with manager.write_lock():
            # Recovery: ensure clean state
            await manager.ensure_clean()

            # Ensure fresh: pull/rebase
            await manager.ensure_fresh()

            # Capture pre-request HEAD for rollback
            pre_request_head = await manager.get_head()

            try:
                response = await call_next(request)

                # Buffer full body — route handler has completed
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Dev-mode: warn on long lock hold
                if settings.dev_mode:
                    held = time.monotonic() - lock_start
                    if held > 5.0:
                        logger.warning(
                            "Write lock held %.1fs for %s %s — "
                            "consider @no_write_lock",
                            held, request.method, request.url.path,
                        )

                # Detect streaming responses — refuse to buffer
                if hasattr(response, "media_type") and response.media_type == "text/event-stream":
                    logger.error(
                        "Streaming response under write lock for %s %s — "
                        "use @no_write_lock instead",
                        request.method, request.url.path,
                    )
                    return response

                # Commit if there are changes
                has_changes = await manager.has_dirty_files()
                if has_changes:
                    await manager.commit_and_push(
                        api_path=f"{request.method} {request.url.path}",
                        pre_request_head=pre_request_head,
                    )

                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            except Exception as e:
                # Rollback any changes
                await manager.rollback(pre_request_head)
                if isinstance(e, GitSyncError):
                    status, message = self._map_error(e)
                    return Response(
                        content=json.dumps({"detail": message}),
                        status_code=status,
                        media_type="application/json",
                    )
                raise

    def _get_manager_for_request(self, request: Request) -> GitSyncManager | None:
        """Extract project_id from URL, return manager if auto-sync enabled."""
        # Parse /api/projects/{project_id}/... from request.url.path
        # Returns None for non-project routes (settings, etc.)
        ...
```

**No buffering overhead when sync is disabled:** If `_get_manager_for_request` returns `None`, or the request is a GET without `@write_lock`, the middleware calls `call_next` directly — no body buffering, streaming preserved.

**Route handling:** The middleware extracts `project_id` from the URL path. Routes without a project ID (settings, provider config, project creation) are passed through without wrapping.

**Registration:** Added in `desktop_server.py`'s `make_app()`, before CORS middleware.

### 2. GitSyncManager (`app/desktop/...`)

The core sync engine. One instance per git repository path (singleton by repo path). All pygit2 operations are funneled through a single-threaded executor for thread safety.

#### Class Structure

```python
# app/desktop/git_sync/git_sync_manager.py

class GitSyncManager:
    # Internal constants
    _GIT_EXECUTOR_TIMEOUT = 30.0  # seconds — timeout for pygit2 operations
    _WRITE_LOCK_TIMEOUT = 30.0    # seconds — timeout for write lock acquisition

    def __init__(self, repo_path: Path, remote_name: str = "origin"):
        self._repo_path = repo_path
        self._remote_name = remote_name

        # pygit2 executor — ALL pygit2 calls go through here
        self._git_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pygit2")

        # Write lock — acquired by middleware for mutating requests.
        # threading.Lock because writes run in threads (via asyncio.to_thread).
        self._write_lock = threading.Lock()

        # Background sync state
        self._sync_task: asyncio.Task | None = None
        self._last_sync: float = 0.0
```

#### pygit2 Thread Safety

pygit2 objects are C extensions and not thread-safe. ALL pygit2 operations — including reads like status checks — go through `_git_executor`:

```python
async def _run_git(self, fn: Callable[..., T], *args) -> T:
    """Run a pygit2 operation in the dedicated git thread.
    Raises TimeoutError if the operation exceeds _GIT_EXECUTOR_TIMEOUT."""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(self._git_executor, fn, *args),
        timeout=self._GIT_EXECUTOR_TIMEOUT,
    )
```

The pygit2 `Repository` object is created lazily within the executor thread and cached there. It is never accessed from any other thread.

#### Write Lock

```python
@asynccontextmanager
async def write_lock(self):
    """Acquire the write lock for the duration of a mutating request.
    Blocks until available (waits behind other requests in queue).
    Raises WriteLockTimeoutError after _WRITE_LOCK_TIMEOUT seconds."""
    # Run in thread to avoid blocking event loop
    acquired = await asyncio.to_thread(
        self._write_lock.acquire, timeout=self._WRITE_LOCK_TIMEOUT
    )
    if not acquired:
        raise WriteLockTimeoutError("Another save is in progress")
    try:
        yield
    finally:
        self._write_lock.release()
```

#### Key Operations

| Method | Description | Threading |
|--------|-------------|-----------|
| `write_lock()` | Async context manager for exclusive write access | Async, uses threading.Lock |
| `ensure_clean()` | Verify repo is clean, run recovery if dirty | Async, uses _git_executor |
| `ensure_fresh()` | Pull/rebase if last sync exceeds freshness threshold (15s) | Async, uses _git_executor |
| `ensure_fresh_for_read()` | Check freshness threshold; if stale, fetch + fast-forward under lock. Raises RemoteUnreachableError if stale and offline. | Async |
| `get_head()` | Return current HEAD commit ref | Async, uses _git_executor |
| `has_dirty_files()` | Check if git status shows changes | Async, uses _git_executor |
| `commit_and_push()` | Stage all dirty files, commit, push. Caller must hold write lock. | Async, uses _git_executor |
| `rollback()` | Stash dirty state, reset to given HEAD | Async, uses _git_executor |
| `fetch()` | Fetch from remote (no working tree changes) | Async, uses _git_executor |
| `can_fast_forward()` | Check if local can fast-forward to remote (no unpushed commits) | Async, uses _git_executor |
| `fast_forward()` | Update working tree to match fetched state | Async, uses _git_executor |
| `close()` | Shut down `_git_executor`, called during FastAPI lifespan shutdown | Async |

### 3. Commit and Push Flow

#### Happy Path (single API call)

```
Mutating request arrives
  → Middleware: async with manager.write_lock()
    → ensure_clean() — verify repo clean, recover if needed
    → ensure_fresh() — pull/rebase from remote
    → Capture pre_request_head
    → Handler runs, writes files normally (any filesystem operation)
    → Buffer response body
    → has_dirty_files() — check git status
    → If dirty: commit_and_push()
      1. git add -A (stage everything — it's all ours)
      2. git commit with auto-generated message
      3. git push
    → Release write lock
  → Response sent
```

#### Push Failure with Retry

```
Push fails (remote diverged)
  → Fetch remote
  → Rebase local commit onto fetched remote HEAD
  → If clean: push again (once)
    → If second push fails: rollback to pre_request_head, return 409
  → If rebase conflicts:
    → git rebase --abort
    → Rollback to pre_request_head
    → Return 409
```

#### Rollback

```python
async def rollback(self, pre_request_head: str) -> None:
    """Rollback all changes to pre-request state.
    Uses git stash to preserve dirty state recoverably."""

    has_changes = await self.has_dirty_files()
    if has_changes:
        # Stash everything (including untracked files) — recoverable
        await self._run_git(
            lambda: self._stash_all("[Kiln] Rollback stash")
        )

    # Reset to pre-request HEAD if we committed
    current_head = await self.get_head()
    if current_head != pre_request_head:
        await self._run_git(
            lambda: self._repo.reset(
                pre_request_head, pygit2.enums.ResetMode.HARD
            )
        )
```

### 4. Recovery (Crash Recovery)

Runs at the start of every write request, after lock acquisition:

```python
async def ensure_clean(self) -> None:
    """Ensure repo is in a clean state. Recover from crashes if needed."""
    if await self._is_clean():
        return

    # Dirty state in an isolated repo means a prior crash — recover immediately
    logger.warning("Repo dirty on write request — running crash recovery")

    # Stash all dirty state FIRST (including conflict markers from interrupted rebase)
    if await self.has_dirty_files():
        await self._run_git(
            lambda: self._stash_all(
                "[Kiln] Auto-recovery stash — dirty state from prior session"
            )
        )

    # Abort any in-progress rebase/merge
    state = await self._run_git(lambda: self._repo.state())
    if state != pygit2.enums.RepositoryState.NONE:
        logger.warning("Aborting in-progress rebase/merge")
        await self._run_git(lambda: self._repo.state_cleanup())

    # Reset unpushed local commits to match remote
    unpushed = await self._count_unpushed_commits()
    if unpushed > 0:
        logger.warning("Resetting %d unpushed commits to match remote", unpushed)
        remote_head = await self._get_remote_head()
        await self._run_git(
            lambda: self._repo.reset(remote_head, pygit2.enums.ResetMode.HARD)
        )

async def _is_clean(self) -> bool:
    """Check repo state: no dirty files, no in-progress rebase/merge."""
    state = await self._run_git(lambda: self._repo.state())
    if state != pygit2.enums.RepositoryState.NONE:
        return False
    return not await self.has_dirty_files()
```

### 5. Background Sync (`app/desktop/`)

```python
# app/desktop/git_sync/background_sync.py

class BackgroundSync:
    """Polls remote for changes. Two-phase: fetch without lock,
    fast-forward under lock.

    Pauses automatically when idle (no API requests) to avoid
    running indefinitely in the background.
    """

    def __init__(self, manager: GitSyncManager,
                 poll_interval: float = 10.0,
                 idle_pause_after: float = 300.0):
        self._manager = manager
        self._poll_interval = poll_interval
        self._idle_pause_after = idle_pause_after
        self._task: asyncio.Task | None = None
        self._last_request_time: float = 0.0
        self._wake_event: asyncio.Event = asyncio.Event()

    def notify_request(self) -> None:
        """Called by middleware on each request. Resets idle timer, wakes paused loop."""
        self._last_request_time = time.monotonic()
        self._wake_event.set()

    async def start(self):
        self._last_request_time = time.monotonic()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _poll_loop(self):
        while True:
            await asyncio.sleep(self._poll_interval)

            # Pause if no requests for idle_pause_after seconds
            idle_time = time.monotonic() - self._last_request_time
            if idle_time > self._idle_pause_after:
                logger.info("Background sync pausing — no requests for %.0fs", idle_time)
                self._wake_event.clear()
                await self._wake_event.wait()  # Sleep until next request
                continue

            try:
                # Phase 1: fetch (no lock — only updates remote tracking refs)
                await self._manager.fetch()

                # Phase 2: check if update needed
                if not await self._manager.has_new_remote_commits():
                    continue

                # Phase 3: fast-forward under write lock (skip if not FF-able)
                async with self._manager.write_lock():
                    if await self._manager.can_fast_forward():
                        await self._manager.fast_forward()

            except Exception:
                logger.warning("Background sync failed, will retry", exc_info=True)
```

**Lifecycle:** Started via the FastAPI lifespan context when auto-sync is enabled. Pauses automatically after 5 minutes with no API requests. Resumes on next request via `notify_request()`. Stopped fully on shutdown.

### 6. Manager Registry

```python
# app/desktop/git_sync/registry.py

class GitSyncRegistry:
    """Singleton registry of GitSyncManager instances, keyed by repo path."""

    _managers: dict[Path, GitSyncManager] = {}
    _background_syncs: dict[Path, BackgroundSync] = {}
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_manager(cls, repo_path: Path) -> GitSyncManager | None:
        return cls._managers.get(repo_path.resolve())

    @classmethod
    def register(cls, repo_path: Path, manager: GitSyncManager) -> None:
        cls._managers[repo_path.resolve()] = manager

    @classmethod
    def get_or_create(cls, repo_path: Path, remote_name: str = "origin") -> GitSyncManager:
        """Return existing manager or create a new one. Thread-safe."""
        resolved = repo_path.resolve()
        with cls._lock:
            if resolved not in cls._managers:
                manager = GitSyncManager(repo_path=resolved, remote_name=remote_name)
                cls._managers[resolved] = manager
            return cls._managers[resolved]

    @classmethod
    def reset(cls) -> None:
        """Clear all cached managers. For test teardown."""
        with cls._lock:
            for manager in cls._managers.values():
                # Shut down executors
                manager._git_executor.shutdown(wait=False)
            cls._managers.clear()
            cls._background_syncs.clear()
```

### 7. Configuration

**Settings storage** in `~/.kiln_ai/settings.yaml`:

```yaml
git_sync_projects:
  "project_id_abc":
    sync_mode: "auto"       # "auto" | "manual"
    remote_name: "origin"   # git remote name
    branch: "main"          # branch to sync
    clone_path: "/Users/x/Kiln Projects/.git-projects/abc - My Project"
```

Timing parameters (`poll_interval`, `idle_pause_after`, `git_executor_timeout`) are internal constants on `GitSyncManager`, not user-configurable.

**Config integration** via existing `Config` class using a TypedDict with validation on read:

```python
class GitSyncProjectConfig(TypedDict):
    sync_mode: str   # "auto" | "manual"
    remote_name: str
    branch: str
    clone_path: str | None

# New ConfigProperty on Config class — stores as plain dict (YAML-safe)
git_sync_projects: ConfigProperty(dict, default_lambda=lambda: {})

def get_git_sync_config(project_id: str) -> GitSyncProjectConfig | None:
    raw = config.git_sync_projects.get(project_id)
    if raw is None:
        return None
    return GitSyncProjectConfig(
        sync_mode=raw.get("sync_mode", "manual"),
        remote_name=raw.get("remote_name", "origin"),
        branch=raw.get("branch", "main"),
        clone_path=raw.get("clone_path"),
    )
```

## Error Handling

### Error Types

```python
class GitSyncError(Exception):
    """Base class for git sync errors."""
    pass

class SyncConflictError(GitSyncError):
    """Rebase conflict could not be auto-resolved."""
    pass

class RemoteUnreachableError(GitSyncError):
    """Cannot reach git remote."""
    pass

class WriteLockTimeoutError(GitSyncError):
    """Write lock acquisition timed out."""
    pass

class CorruptRepoError(GitSyncError):
    """Git repo is in unexpected state after recovery attempt."""
    pass
```

### Error → HTTP Status Mapping (in middleware)

| Error | HTTP Status | Message |
|-------|-------------|---------|
| `RemoteUnreachableError` | 503 | "Cannot sync with remote. Check your connection." |
| `SyncConflictError` | 409 | "There was a problem saving. Please try again." |
| `WriteLockTimeoutError` | 503 | "Another save is in progress. Please wait a moment and try again." |
| `CorruptRepoError` | 500 | "Git repository is in an unexpected state." |

### Recovery

- **All errors during write:** Rollback to pre-request state (stash + reset) before surfacing
- **Push conflict:** Automatic retry once (fetch/rebase/re-push)
- **Network errors:** Fail fast, let client retry
- **Crash state:** Auto-recovery on next write request (stash, reset)
- **Corrupt state (unrecoverable):** Refuse to operate, require manual intervention

## File Structure

```
app/desktop/
├── git_sync/
│   ├── __init__.py
│   ├── git_sync_manager.py     # Core manager (locking, pygit2, commit/push/rollback)
│   ├── middleware.py            # FastAPI middleware
│   ├── background_sync.py      # Polling background task
│   ├── registry.py             # Manager singleton registry
│   ├── commit_message.py       # Auto commit message generation
│   ├── errors.py               # Error types
│   └── config.py               # Git sync config helpers
├── desktop_server.py           # Modified: add middleware
└── ...
```

Note: compared to the earlier design, the following are **removed** — no longer needed:
- `libs/core/kiln_ai/datamodel/storage_writer.py` — no StorageWriter protocol
- `git_sync/storage_writer.py` — no GitSyncStorageWriter
- Changes to `basemodel.py` — zero modifications to libs/core

## Testing Strategy

### Unit Tests

**GitSyncManager:**
- `ensure_clean()`: detects dirty state, runs recovery
- `ensure_fresh()`: pulls/rebases to keep up-to-date
- `commit_and_push()`: stages all dirty files, commits, pushes
- `rollback()`: stashes dirty state, resets to pre-request HEAD
- Push retry: conflict → fetch → rebase → re-push
- Push failure after retry: rollback, surface error
- Recovery: abort rebase, stash dirty state, reset unpushed commits

**Middleware:**
- Mutating methods (POST/PATCH/DELETE) acquire write lock
- GET/HEAD pass through without lock
- `@write_lock` annotation forces lock on GET
- `@no_write_lock` annotation skips lock on POST
- Error mapping to HTTP status codes
- Dev-mode dirty state detection fires on unexpected changes
- Non-auto-sync routes pass through without buffering

**Background Sync:**
- Fetch phase runs without lock
- Fast-forward phase acquires lock
- Skips update when no new remote commits
- Idle pause after configured interval
- Resume on notify_request (no double-resume race)

**Registry:**
- Thread-safe get_or_create
- reset() clears all managers (test teardown)

### Integration Tests

- Full request lifecycle: API call → lock → commit → push → verify remote
- Concurrent requests: two writes → serialized via lock → both succeed
- Conflict simulation: modify remote between ensure_fresh and push → retry succeeds
- Recovery: dirty repo on startup → auto-recovery → next request succeeds
- Background sync: remote changes picked up within poll interval

### Test Approach for pygit2

Tests create temporary git repos (local bare repos as "remotes") using pygit2 directly. No network calls, no real remotes. Fast and deterministic.

```python
@pytest.fixture
def git_repos(tmp_path):
    """Create a bare 'remote' repo and a cloned 'local' repo."""
    remote = tmp_path / "remote.git"
    pygit2.init_repository(str(remote), bare=True)
    local = tmp_path / "local"
    pygit2.clone_repository(str(remote), str(local))
    return local, remote
```

### Test Teardown

Use a conftest fixture to reset the `GitSyncRegistry` after each test:

```python
@pytest.fixture(autouse=True)
def reset_git_sync_registry():
    yield
    GitSyncRegistry.reset()
```

## Design Decisions

### Why HTTP-method middleware lock, not StorageWriter protocol

An earlier design used a `StorageWriter` protocol injected into `KilnBaseModel` to track individual file writes. This was replaced because:

- **Dual tracking is fragile.** Maintaining our own file list alongside git's `git status` creates divergence when any write path isn't instrumented (attachments, delete_tree, future code paths).
- **Zero changes to libs/core.** The middleware approach requires no modifications to `KilnBaseModel`, no resolver pattern, no ClassVar interactions with Pydantic.
- **Any filesystem operation works.** No special writer needed — the middleware observes changes via `git status` after the fact.
- **Better footgun profile.** "Accidentally used wrong HTTP method" (detectable, rare) is better than "accidentally did filesystem I/O outside the writer" (silent, easy to do).

The isolated repo is the key enabler — since we fully control the repo, git status is a reliable single source of truth.

### Why full repo clone, not worktree

Worktrees share `.git` internals (reflog, stash, gc, index locks). Operations on one worktree can affect another. A full clone is truly isolated. The repos contain small `.kiln` JSON files, so disk usage is not a concern. (Shallow clones were considered but rejected — libgit2's shallow support is limited and conflicts with rebase, stash, and recovery operations.)

### Why rebase-only

Merge commits create non-linear history that's harder to reason about for automated rollback. Rebase keeps history linear: each commit is a clean, independent change. Rollback is simply resetting to a prior commit.

### Why single-threaded executor for pygit2

pygit2 wraps libgit2 C objects which are not thread-safe. Concurrent calls from different threads can cause segfaults. A single-threaded executor serializes all git operations safely. This includes read operations (status, log) — not just writes.

### Why git stash for rollback

`git stash -u` captures all dirty state (modified tracked files + untracked files) into a recoverable stash entry. This is better than `git checkout HEAD` + manual cleanup because:
- Handles all cases uniformly (modified, deleted, new files, directory trees)
- Preserves state recoverably (`git stash list`, `git stash pop`)
- Nothing is silently destroyed
- Single operation, no edge cases to enumerate

### Why asyncio.to_thread for sync operations

`save_to_file()` and other file I/O are sync operations. `asyncio.to_thread` runs them in a thread pool so they don't block the event loop. This has no performance penalty vs "real" async I/O — Python has no true async filesystem I/O. Libraries like `aiofiles` internally use thread pools too.
