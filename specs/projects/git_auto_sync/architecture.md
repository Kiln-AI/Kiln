---
status: draft
---

# Architecture: Git Auto Sync

## Overview

Git Auto Sync adds transparent git-based synchronization to Kiln projects. The system is built as a general-purpose library in `app/desktop/...` with a clean integration layer into `libs/core/` via a thin write-interception pattern.

The architecture has four major components:
1. **StorageWriter** — Write-side abstraction in `libs/core/` (thin protocol, 3 methods)
2. **GitSyncManager** — Core sync engine in `app/desktop/...` (locking, pygit2, write_context)
3. **FastAPI Middleware** — Request-level write_context wrapper in `app/desktop/...`
4. **Background Sync** — Async poller keeping repos fresh

## Component Breakdown

### 1. StorageWriter Protocol (`libs/core/`)

A minimal write-interception layer. Reads are untouched — only the 3 existing write operations in `KilnBaseModel` are routed through this protocol.

```python
# libs/core/kiln_ai/datamodel/storage_writer.py

from pathlib import Path
from typing import Protocol, runtime_checkable

@runtime_checkable
class StorageWriter(Protocol):
    """Write-side storage abstraction. Sync-only interface.

    All logic lives in these sync methods. The async path
    (asave_to_file) calls these via asyncio.to_thread.
    """

    def write_file(self, path: Path, data: str) -> None: ...
    def delete_tree(self, path: Path) -> None: ...
    def copy_file(self, src: Path, dest: Path) -> None: ...


class FileStorageWriter:
    """Default writer — direct filesystem I/O. Current behavior, extracted."""

    def write_file(self, path: Path, data: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)

    def delete_tree(self, path: Path) -> None:
        import shutil
        shutil.rmtree(path)

    def copy_file(self, src: Path, dest: Path) -> None:
        import shutil
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
```

**Integration into KilnBaseModel:**

```python
# basemodel.py changes (minimal)

class KilnBaseModel(BaseModel):
    # Class-level writer, defaults to filesystem. Overridden per-project.
    _storage_writer: ClassVar[StorageWriter] = FileStorageWriter()
    # Resolver: given a file path, return the appropriate writer.
    # Default returns the class-level writer. Git sync sets this to
    # a function that checks project config and returns the git writer
    # for auto-sync projects, or the default writer otherwise.
    _storage_writer_resolver: ClassVar[Callable[[Path], StorageWriter] | None] = None

    def _get_writer(self, path: Path) -> StorageWriter:
        if self._storage_writer_resolver:
            return self._storage_writer_resolver(path)
        return self._storage_writer

    def save_to_file(self) -> None:
        """Sync save — works with all writers including git sync.
        All logic lives here. asave_to_file() delegates to this via asyncio.to_thread."""
        path = self.build_path()
        # ... existing validation ...
        json_data = self.model_dump_json(
            indent=2,
            exclude={"path"},
            context={
                "save_attachments": True,
                "dest_path": path.parent,
                "storage_writer": self._get_writer(path),
            },
        )
        self._get_writer(path).write_file(path, json_data)
        self.path = path
        ModelCache.shared().invalidate(path)

    async def asave_to_file(self) -> None:
        """Async save — runs save_to_file in a thread via asyncio.to_thread.
        Preferred in async contexts. Does not block the event loop."""
        await asyncio.to_thread(self.save_to_file)

    def delete(self) -> None:
        # ... existing validation ...
        self._get_writer(self.path).delete_tree(dir_path)
        ModelCache.shared().invalidate(self.path)
        self.path = None

    async def adelete(self) -> None:
        """Async delete — runs delete in a thread via asyncio.to_thread."""
        await asyncio.to_thread(self.delete)
```

```python
# KilnAttachmentModel changes

class KilnAttachmentModel(BaseModel):
    def copy_file_to(self, dest_folder: Path, filename_prefix: str | None = None,
                     storage_writer: StorageWriter | None = None) -> Path:
        # ... existing path logic ...
        writer = storage_writer or FileStorageWriter()
        writer.copy_file(self.input_path, target_path)
        return target_path
```

The `storage_writer` is passed through the serialization context so attachment copies during `model_dump_json` use the same writer as the parent `save_to_file()` call.

**Why this approach:**
- Only 3 methods to implement — not a full storage backend
- Reads (`load_from_file`, `load_from_folder`, `os.scandir`) untouched
- `ModelCache` untouched
- No changes to any model subclasses
- The resolver pattern allows per-project writer selection without the model knowing about git

### 2. GitSyncManager (`app/desktop/...`)

The core sync engine. One instance per git repository path (singleton by repo path). All pygit2 operations are funneled through a single-threaded executor for thread safety.

#### Class Structure

```python
# app/desktop/git_sync/git_sync_manager.py

class GitSyncManager:
    def __init__(self, repo_path: Path, remote_name: str = "origin",
                 branch: str | None = None, poll_interval: float = 10.0,
                 sync_freshness_threshold: float = 15.0):
        self._repo_path = repo_path
        self._remote_name = remote_name
        self._branch = branch  # None = current branch
        self._poll_interval = poll_interval
        self._sync_freshness_threshold = sync_freshness_threshold

        # pygit2 executor — ALL pygit2 calls go through here
        self._git_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pygit2")

        # Write lock — acquired lazily on first write within a context.
        # threading.Lock because writes run in threads (via asyncio.to_thread).
        # Async callers never block the event loop — they're in a thread when they acquire.
        # Sync callers block their thread briefly under contention (acceptable).
        self._write_lock = threading.Lock()

        # Active context tracking (per-task via contextvars)
        self._active_context: contextvars.ContextVar[WriteContext | None] = \
            contextvars.ContextVar("active_write_context", default=None)

        # Background sync state
        self._sync_task: asyncio.Task | None = None
        self._last_sync: float = 0.0
```

#### pygit2 Thread Safety

pygit2 objects are C extensions and not thread-safe. ALL pygit2 operations — including reads like status checks — go through `_git_executor`:

```python
async def _run_git(self, fn: Callable[..., T], *args) -> T:
    """Run a pygit2 operation in the dedicated git thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(self._git_executor, fn, *args)
```

The pygit2 `Repository` object is created lazily within the executor thread and cached there. It is never accessed from any other thread.

#### write_context

```python
@asynccontextmanager
async def write_context(self, push: bool = True, check_in_sync: bool = True):
    parent_ctx = self._active_context.get()

    if parent_ctx is not None and parent_ctx.has_writes:
        raise RuntimeError("Cannot nest write_context after parent already has writes")

    ctx = WriteContext(push=push, check_in_sync=check_in_sync, parent=parent_ctx)

    if parent_ctx is not None and parent_ctx.holds_lock:
        # Parent releases lock for nested context
        self._write_lock.release()
        parent_ctx.holds_lock = False

    if check_in_sync:
        await self._ensure_fresh()

    self._active_context.set(ctx)
    try:
        yield ctx
    except Exception:
        # Rollback any uncommitted writes in this context
        if ctx.has_writes:
            self._rollback_writes(ctx)
        raise
    else:
        # Success path: commit if writes occurred
        if ctx.has_writes:
            await self._commit_context(ctx)
    finally:
        if ctx.holds_lock:
            self._write_lock.release()
            ctx.holds_lock = False
        self._active_context.set(parent_ctx)

        # Parent exit: push all unpushed commits
        if parent_ctx is None and push:
            await self._push_with_retry()
```

#### WriteContext (internal)

```python
@dataclass
class WriteContext:
    push: bool
    check_in_sync: bool
    parent: WriteContext | None
    tracked_files: list[Path] = field(default_factory=list)
    original_contents: dict[Path, bytes | None] = field(default_factory=dict)
    # None value = file didn't exist before
    holds_lock: bool = False  # tracks whether this context owns the write lock

    @property
    def has_writes(self) -> bool:
        return len(self.tracked_files) > 0
```

#### GitSyncStorageWriter

```python
class GitSyncStorageWriter:
    """StorageWriter that routes writes through GitSyncManager.

    All methods are sync. Called either directly (save_to_file)
    or from a thread (asave_to_file via asyncio.to_thread).
    Both paths work — the threading.Lock handles either.
    """

    def __init__(self, manager: GitSyncManager):
        self._manager = manager

    def write_file(self, path: Path, data: str) -> None:
        self._manager.write_file(path, data)

    def delete_tree(self, path: Path) -> None:
        self._manager.delete_tree(path)

    def copy_file(self, src: Path, dest: Path) -> None:
        self._manager.copy_file(src, dest)
```

**Both sync and async callers work.** The manager's write methods are sync and use `threading.Lock`:
- **`asave_to_file()` path (preferred):** `asyncio.to_thread` runs `save_to_file` in a thread pool. `threading.Lock.acquire()` blocks that thread (not the event loop) during contention. Event loop stays responsive.
- **`save_to_file()` path (deprecated):** Called directly from the event loop thread. `threading.Lock.acquire()` blocks the event loop briefly during contention. Contention is rare (two parallel writes to same project) and brief (held only during file I/O — microseconds). Acceptable for backwards compat.

contextvars propagate into `asyncio.to_thread` automatically (Python 3.10+), so the `write_context` contextvar is visible in either path.

#### Key Operations

| Method | Description | Threading |
|--------|-------------|-----------|
| `write_context()` | Async context manager for atomic writes | Async |
| `write_file()` | Sync write + track + lazy lock | Sync, uses threading.Lock |
| `delete_tree()` | Sync delete + track | Sync, uses threading.Lock |
| `copy_file()` | Sync copy + track | Sync, uses threading.Lock |
| `push()` | Push unpushed commits (between contexts only) | Async, uses _git_executor |
| `is_fresh()` | Check if repo is up-to-date | Async, uses _git_executor |
| `is_clean()` | Check for unexpected dirty files | Async, uses _git_executor |
| `_ensure_fresh()` | Pull/rebase if stale | Async, uses _git_executor |
| `_commit_context()` | Stage tracked files + commit | Async, uses _git_executor |
| `_rollback_writes()` | Restore original file contents | Sync |
| `_push_with_retry()` | Push, retry once on conflict | Async, uses _git_executor |

### 3. FastAPI Middleware (`app/desktop/`)

```python
# app/desktop/git_sync/middleware.py

class GitSyncMiddleware:
    """Wraps each request in a write_context for auto-sync projects."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Determine project from request path
        project_id = self._extract_project_id(scope["path"])
        manager = self._get_manager_for_project(project_id)

        if manager is None:
            # No auto-sync for this project/route
            await self.app(scope, receive, send)
            return

        async with manager.write_context():
            await self.app(scope, receive, send)

    def _extract_project_id(self, path: str) -> str | None:
        """Extract project_id from /api/projects/{project_id}/... routes."""
        # Returns None for non-project routes (settings, etc.)
        ...

    def _get_manager_for_project(self, project_id: str | None) -> GitSyncManager | None:
        """Return manager if project has auto-sync enabled, else None."""
        ...
```

**Route handling:** The middleware extracts `project_id` from the URL path. Routes without a project ID (settings, provider config, etc.) are passed through without wrapping. This is clean because all data-mutating routes already include `project_id` in the path.

**Registration:** Added in `desktop_server.py`'s `make_app()`, before CORS middleware.

### 4. Background Sync (`app/desktop/`)

```python
# app/desktop/git_sync/background_sync.py

class BackgroundSync:
    """Polls remote for changes on a configurable interval.

    Pauses automatically when idle (no API requests) to avoid
    running indefinitely in the background.
    """

    def __init__(self, manager: GitSyncManager,
                 poll_interval: float = 10.0,
                 idle_pause_after: float = 300.0):  # 5 minutes
        self._manager = manager
        self._poll_interval = poll_interval
        self._idle_pause_after = idle_pause_after
        self._task: asyncio.Task | None = None
        self._last_request_time: float = 0.0
        self._paused: bool = False

    def notify_request(self) -> None:
        """Called by middleware on each request. Resets idle timer, resumes if paused."""
        self._last_request_time = time.monotonic()
        if self._paused and self._task is None:
            self._paused = False
            self._task = asyncio.create_task(self._poll_loop())

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
                self._paused = True
                self._task = None
                return

            try:
                # Respects write lock — waits if a write is in progress
                await self._manager.pull_if_needed()
            except Exception:
                logger.warning("Background sync failed, will retry", exc_info=True)
```

**Lifecycle:** Started via the FastAPI lifespan context when auto-sync is enabled. Pauses automatically after `idle_pause_after` seconds with no API requests (default: 5 minutes). Resumes on the next request via `notify_request()`. Stopped fully on shutdown.

**Freshness:** The middleware's `_ensure_fresh()` check uses `sync_freshness_threshold` (default: 15s) — if the last successful sync was within this window, the request proceeds without waiting. This is slightly longer than the poll interval (10s) to provide a buffer. If the repo is stale (e.g., polling was paused), the middleware blocks the request until a sync completes.

### 5. Manager Registry

```python
# app/desktop/git_sync/registry.py

class GitSyncRegistry:
    """Singleton registry of GitSyncManager instances, keyed by repo path."""

    _managers: dict[Path, GitSyncManager] = {}
    _background_syncs: dict[Path, BackgroundSync] = {}

    @classmethod
    def get_manager(cls, repo_path: Path) -> GitSyncManager | None:
        return cls._managers.get(repo_path.resolve())

    @classmethod
    def register(cls, repo_path: Path, manager: GitSyncManager) -> None:
        cls._managers[repo_path.resolve()] = manager

    @classmethod
    def get_or_create_for_project(cls, project_path: Path) -> GitSyncManager | None:
        """Given a project path, find its git repo root and return/create a manager."""
        repo_path = cls._find_repo_root(project_path)
        if repo_path is None:
            return None
        if repo_path not in cls._managers:
            manager = GitSyncManager(repo_path=repo_path)
            cls.register(repo_path, manager)
        return cls._managers[repo_path]
```

### 6. Configuration

**Settings storage** in `~/.kiln_ai/settings.yaml`:

```yaml
git_sync_projects:
  "project_id_abc":
    sync_mode: "auto"              # "auto" | "manual"
    remote_name: "origin"
    branch: null                   # null = current branch
    poll_interval: 10.0            # seconds between background syncs
    idle_pause_after: 300.0        # pause polling after 5 min with no requests
    sync_freshness_threshold: 15.0 # max age (seconds) of last sync before blocking
```

**Config integration** via existing `Config` class:

```python
# New ConfigProperty on Config class
git_sync_projects: ConfigProperty(dict, default_lambda=lambda: {})
```

**Writer resolver** — installed during app startup:

```python
# In desktop_server.py lifespan or startup

def resolve_writer(path: Path) -> StorageWriter:
    """Given a file path, determine which writer to use."""
    # Find the project that owns this path
    project_id = find_project_id_for_path(path)
    if project_id is None:
        return FileStorageWriter()

    config = Config.shared().git_sync_projects.get(project_id)
    if config is None or config.get("sync_mode") != "auto":
        return FileStorageWriter()

    manager = GitSyncRegistry.get_or_create_for_project(path)
    if manager is None:
        return FileStorageWriter()

    return GitSyncStorageWriter(manager)

KilnBaseModel._storage_writer_resolver = resolve_writer
```

This keeps `libs/core/` completely ignorant of git sync — the resolver is injected from `app/desktop/` at startup.

## Sync/Async Write Design

The design is simple: all write logic is sync. The async path (`asave_to_file`) just wraps it with `asyncio.to_thread`.

**The write flow (both paths share the same code):**

```python
# In GitSyncManager

def write_file(self, path: Path, data: str) -> None:
    """Sync write: check context, acquire lock, write, track.
    Called directly by save_to_file(), or from a thread by asave_to_file()."""
    ctx = self._active_context.get()
    if ctx is None:
        raise NotInWriteContextError("write_file called outside write_context")

    # Lazy lock acquisition on first write
    if not ctx.has_writes:
        acquired = self._write_lock.acquire(timeout=30)
        if not acquired:
            raise WriteLockTimeoutError("Timed out waiting for write lock")
        ctx.holds_lock = True

    # Save original for rollback
    if path not in ctx.original_contents:
        ctx.original_contents[path] = path.read_bytes() if path.exists() else None

    # Actual filesystem write
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data)

    ctx.tracked_files.append(path)
```

**How both paths work:**
- **`await model.asave_to_file()` (preferred):** `asyncio.to_thread(self.save_to_file)` runs in a thread pool. `threading.Lock.acquire()` blocks that thread, not the event loop. Other requests proceed normally during contention.
- **`model.save_to_file()` (deprecated, backwards compat):** Runs directly on the event loop thread. `threading.Lock.acquire()` blocks the event loop briefly during contention. Contention is rare and brief — acceptable for third-party callers who haven't migrated yet.

contextvars propagate into `asyncio.to_thread` automatically (Python 3.10+), so the `write_context` contextvar is visible in either path. No special handling needed.

**Migration plan:** ~54 API handler call sites and ~30 `libs/core/` adapter calls — almost all already in async methods. Mechanical change: `model.save_to_file()` → `await model.asave_to_file()`. Our code migrates fully; third-party callers continue working via the sync path.

## Commit and Push Flow

### Happy Path (single API call)

```
Request arrives
  → Middleware: async with manager.write_context(push=True, check_in_sync=True)
    → Entry: await _ensure_fresh() (pull/rebase)
    → Handler runs, calls await model.asave_to_file() one or more times
      → asyncio.to_thread(save_to_file) — runs in thread pool
        → First write: threading.Lock.acquire() (blocks thread, not event loop)
        → Save original contents for rollback
        → Each write: filesystem write + track path
    → Exit (success):
      1. Check for out-of-band changes (dirty files not in tracked set)
      2. git add tracked files
      3. git commit with auto-generated message
      4. git push
      5. Release write lock
  → Response sent
```

### Push Failure with Retry

```
Push fails (remote diverged)
  → Revert local commit (keep working tree)
  → git pull --rebase
  → If clean: re-commit, re-push (once)
  → If conflict: git rebase --abort, rollback files, return 409
```

### Rollback on Error

```
Exception during handler
  → For each tracked file:
    → If original_contents[path] is None: delete file
    → Else: restore original bytes
  → Release write lock
  → Re-raise exception
```

## Out-of-Band Change Detection

Before committing, the manager compares `git status` dirty files against the write context's tracked files:

```python
async def _check_out_of_band(self, ctx: WriteContext) -> None:
    dirty_files = await self._run_git(self._get_dirty_files)
    tracked_set = {p.resolve() for p in ctx.tracked_files}
    unexpected = {f for f in dirty_files if f.resolve() not in tracked_set}
    if unexpected:
        raise OutOfBandChangesError(unexpected)
```

This is safe from background-sync interference because the background poller respects the write lock — it cannot modify the working tree while a write context holds the lock.

## Commit Messages

Auto-generated from tracked files and change type:

```python
def _generate_commit_message(self, ctx: WriteContext) -> str:
    """Generate descriptive commit message from tracked changes."""
    # Analyze tracked files to determine:
    # - Model types affected (Task, Document, TaskRun, etc.)
    # - Nature of change (create vs update — based on original_contents)
    # - Names/identifiers where available
    #
    # Format: "[Kiln] <action> <summary>"
    # Examples:
    #   [Kiln] Create task 'Summarize articles'
    #   [Kiln] Update prompt for task 'Translation'
    #   [Kiln] Eval run: 15 results for task 'QA'
    #   [Kiln] Delete document 'Old reference'
    ...
```

The commit message generator reads the `.kiln` JSON files being committed to extract model type and name fields. For multi-file commits, it groups by model type and summarizes.

## Error Handling Strategy

### Error Types

```python
class GitSyncError(Exception):
    """Base class for git sync errors."""
    pass

class NotInWriteContextError(GitSyncError):
    """Write attempted outside write_context."""
    pass

class WriteLockTimeoutError(GitSyncError):
    """Write lock acquisition timed out."""
    pass

class OutOfBandChangesError(GitSyncError):
    """Unexpected file changes detected."""
    pass

class SyncConflictError(GitSyncError):
    """Rebase conflict could not be auto-resolved."""
    pass

class RemoteUnreachableError(GitSyncError):
    """Cannot reach git remote."""
    pass

class CorruptRepoError(GitSyncError):
    """Git repo is in unexpected state."""
    pass
```

### Error → HTTP Status Mapping (in middleware)

| Error | HTTP Status | Message |
|-------|-------------|---------|
| `RemoteUnreachableError` | 503 | "Cannot sync with remote. Check your connection." |
| `WriteLockTimeoutError` | 503 | "Server busy. Please retry." |
| `SyncConflictError` | 409 | "Conflict detected. Please retry." |
| `OutOfBandChangesError` | 400 | "Unexpected file changes detected outside of API." |
| `CorruptRepoError` | 500 | "Git repository is in an unexpected state." |
| `NotInWriteContextError` | 500 | Internal error (bug — should never reach client) |

### Recovery

- **All errors during write:** Rollback tracked files to pre-write state before surfacing
- **Push conflict:** Automatic retry once (pull/rebase/re-commit/re-push)
- **Network errors:** No retry in middleware — fail fast, let client retry
- **Corrupt state:** Refuse to operate, require manual intervention

## File Structure

```
app/desktop/
├── git_sync/
│   ├── __init__.py
│   ├── git_sync_manager.py     # Core manager + WriteContext
│   ├── storage_writer.py       # GitSyncStorageWriter
│   ├── middleware.py            # FastAPI middleware
│   ├── background_sync.py      # Polling background task
│   ├── registry.py             # Manager singleton registry
│   ├── commit_message.py       # Auto commit message generation
│   ├── errors.py               # Error types
│   └── config.py               # Git sync config helpers
├── desktop_server.py           # Modified: add middleware, writer resolver
└── ...

libs/core/kiln_ai/datamodel/
├── storage_writer.py           # StorageWriter protocol + FileStorageWriter
├── basemodel.py                # Modified: use StorageWriter for writes
└── ...
```

## Testing Strategy

### Unit Tests

**StorageWriter (libs/core/):**
- `FileStorageWriter` correctly writes/deletes/copies
- `save_to_file()` and `asave_to_file()` delegate to writer
- `delete()` and `adelete()` delegate to writer
- `asave_to_file()` runs `save_to_file` via `asyncio.to_thread`
- Attachment copies go through writer
- Writer resolver selects correct writer per project

**GitSyncManager:**
- `write_context` lifecycle: enter → write → commit → push → exit
- Lazy lock: read-only contexts never acquire lock
- Nesting: parent releases lock, child acquires, parent pushes on exit
- Mixing error: parent has writes + nested context = immediate error
- Rollback: exception during writes restores originals
- Out-of-band detection: untracked dirty files cause error
- Push retry: conflict → pull/rebase → re-push
- Push failure: rollback commit, surface error
- Context enforcement: write outside context raises

**Middleware:**
- Project ID extraction from various URL patterns
- Auto-sync projects get wrapped, manual projects pass through
- Non-project routes pass through
- Error mapping to HTTP status codes

**Background Sync:**
- Polls at configured interval
- Skips when write lock held
- Recovers from network errors

### Integration Tests

- Full request lifecycle: API call → write_context → commit → push → verify remote
- Concurrent requests: two writes to different files → both succeed
- Conflict simulation: modify remote between write and push → retry succeeds
- Nested contexts: eval-style loop with periodic push

### Test Approach for pygit2

Tests create temporary git repos (local bare repos as "remotes") using pygit2 directly. No network calls, no real remotes. This makes tests fast and deterministic.

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

## Design Decisions

### Why StorageWriter protocol, not full StorageBackend

The functional spec discussed a `StorageBackend` with `save()` and `load()`. We narrowed to write-only because:
- Only 3 write operations exist in basemodel.py
- Reads don't need interception (freshness is handled by middleware/background sync)
- A full backend would require abstracting `load_from_file`, `load_from_folder`, `os.scandir` iteration, `ModelCache` — massive scope
- The write-only approach achieves all functional goals with minimal changes to `libs/core/`

### Why asyncio.to_thread for async path

`asave_to_file()` is a one-liner: `await asyncio.to_thread(self.save_to_file)`. This means:
- All write logic lives in one place (sync `save_to_file`)
- No dual interfaces on `StorageWriter` (sync-only protocol)
- No async/sync bridging hacks
- `threading.Lock` just works — the async caller is in a real thread when it acquires
- contextvars propagate automatically (Python 3.10+)

The sync `save_to_file()` is deprecated but fully functional in git sync mode. Third-party callers who haven't migrated to the async path will block the event loop briefly during lock contention, but this is rare and brief.

**Important: this has no performance penalty vs "real" async I/O.** This design looks like a shortcut — wrapping sync I/O in a thread instead of using proper async file I/O — but it's not. Python has no true async filesystem I/O. Libraries like `aiofiles` appear async but internally use thread pools (typically `asyncio.to_thread` or `loop.run_in_executor`) to run the same sync `open()`/`write()` calls. There is no kernel-level async file I/O API exposed to Python (unlike network sockets, which do have real async via `select`/`epoll`/`kqueue`). So `asyncio.to_thread(save_to_file)` does exactly what `aiofiles` would do, minus a dependency and an extra layer of abstraction. **Add a concise comment in the code** explaining this (e.g., on `asave_to_file` or the `StorageWriter` module). Specs aren't always referenced — this is a key technical decision that needs to be visible where the code lives.

### Why threading.Lock, not asyncio.Lock

Writes run in threads (via `asyncio.to_thread`), so `threading.Lock` is the natural choice:
- Async callers (`asave_to_file`) are in a thread pool — `threading.Lock` blocks that thread, event loop stays responsive
- Sync callers (`save_to_file`) block their thread directly — works correctly, brief contention is acceptable for the deprecated path
- `asyncio.Lock` would require all callers to be async, preventing backwards-compatible sync `save_to_file`

### Why contextvars for active context tracking

The write context needs to be visible to `write_file()` which is called deep in the `save_to_file()` call stack. Options:
- **Thread-local:** Doesn't work — `asyncio.to_thread` runs in a different thread than where the contextvar was set. contextvars propagate correctly; thread-locals don't.
- **Pass context through call stack:** Would require changing `save_to_file()` signature and every caller
- **contextvars:** Designed for exactly this — per-task context in asyncio, propagates into `asyncio.to_thread` automatically (Python 3.10+)

### Why single-threaded executor for pygit2

pygit2 wraps libgit2 C objects which are not thread-safe. Concurrent calls from different threads can cause segfaults. A single-threaded executor serializes all git operations safely. This includes read operations (status, log) — not just writes.

### Why rebase-only

Merge commits create non-linear history that's harder to reason about for automated rollback. Rebase keeps history linear: each commit is a clean, independent change. Rollback is simply resetting to a prior commit.
