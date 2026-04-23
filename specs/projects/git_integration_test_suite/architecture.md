---
status: complete
---

# Architecture: Git Integration Test Suite

## Overview

An integration test suite in `app/desktop/git_sync/integration_tests/` that validates the git auto-sync system's behavioral guarantees using real git repositories. Tests run at two levels — library (GitSyncManager directly) and API (TestClient through middleware) — via pytest parametrization.

## Directory Structure

```
app/desktop/git_sync/integration_tests/
├── __init__.py
├── conftest.py                  # Fixtures: git repos, WriteContext, test app
├── test_happy_path.py           # Scenarios 1–5: write/read/no-op/multi-file/arbitrary writes
├── test_rollback.py             # Scenarios 6–7, 34: handler error, push failure, rebase-then-fail
├── test_conflicts.py            # Scenarios 8–9, 38–41: push races, rebase conflicts, delete/modify, add/add, empty commit, ABA
├── test_crash_recovery.py       # Scenarios 10–13, 35–37: dirty state, rebase, unpushed, unrecoverable, combined, force-push, partial recovery
├── test_locking.py              # Scenarios 14–15, 45: serialization, timeout, non-reentrant deadlock
├── test_freshness.py            # Scenarios 16–18, 29: pull before write, stale reads, threshold
├── test_background_sync.py      # Scenarios 19–21: fetch+ff, no-op, skip diverged
├── test_decorators.py           # Scenarios 22–25: @write_lock, @no_write_lock, streaming, long hold
├── test_network_failure.py      # Scenarios 17, 26: parameterized network failure modes
├── test_middleware_routing.py   # Scenarios 30–31: non-project routes, manual mode
├── test_file_operations.py      # Scenarios 32–33, 42–43: deletions, .gitignore, mixed ops, net-zero
└── test_no_write_lock_batch.py  # Scenario 44: partial failure across iterations
```

## Core Abstraction: WriteContext

The key design challenge is running the same scenario at both library and API level. A `WriteContext` protocol abstracts the difference.

```python
from typing import Protocol, Callable, Awaitable
from pathlib import Path

class WriteContext(Protocol):
    """Abstraction over library-mode and API-mode write operations."""

    repo_path: Path

    async def do_write(
        self,
        write_fn: Callable[[Path], None],
        expect_error: bool = False,
    ) -> WriteResult:
        """Execute a write operation.

        In library mode: acquires write lock, calls write_fn(repo_path),
        then calls commit_and_push().
        In API mode: makes a POST request to a test endpoint whose
        handler calls write_fn(repo_path).

        Args:
            write_fn: A function that writes files to the repo. Receives
                      the repo path. May raise to simulate handler errors.
            expect_error: If True, the operation is expected to fail.
                         Suppresses assertion on error response.

        Returns:
            WriteResult with status_code, committed (bool), error details.
        """
        ...

    async def do_read(self) -> ReadResult:
        """Execute a read operation.

        In library mode: no-op (reads don't go through the manager).
        In API mode: makes a GET request to a test endpoint.
        """
        ...


class WriteResult:
    status_code: int | None    # None in library mode
    committed: bool            # Whether a commit was created
    pushed: bool               # Whether the commit reached remote
    error: str | None          # Error message if failed


class ReadResult:
    status_code: int | None
    error: str | None
```

### Library Mode Implementation

```python
class LibraryWriteContext:
    def __init__(self, manager: GitSyncManager, repo_path: Path):
        self.manager = manager
        self.repo_path = repo_path

    async def do_write(self, write_fn, expect_error=False):
        pre_head = await self.manager.get_head()
        async with self.manager.write_lock():
            await self.manager.ensure_clean()
            await self.manager.ensure_fresh()
            pre_request_head = await self.manager.get_head()

            try:
                write_fn(self.repo_path)

                if await self.manager.has_dirty_files():
                    await self.manager.commit_and_push(
                        api_path="TEST library_mode",
                        pre_request_head=pre_request_head,
                    )
                    return WriteResult(committed=True, pushed=True)

                return WriteResult(committed=False, pushed=False)

            except Exception as e:
                await self.manager.rollback(pre_request_head)
                if expect_error:
                    return WriteResult(committed=False, pushed=False, error=str(e))
                raise
```

### API Mode Implementation

```python
class APIWriteContext:
    def __init__(self, client: TestClient, repo_path: Path, project_id: str):
        self.client = client
        self.repo_path = repo_path
        self.project_id = project_id
        # The test app registers endpoints that accept a write_fn
        # via a shared mutable slot (set before each request).
        self._pending_write_fn: Callable | None = None

    async def do_write(self, write_fn, expect_error=False):
        # Store the write_fn so the test endpoint can call it
        self._pending_write_fn = write_fn

        pre_head = get_head_sync(self.repo_path)
        resp = self.client.post(
            f"/api/projects/{self.project_id}/test_write",
            json={},
        )
        post_head = get_head_sync(self.repo_path)

        committed = post_head != pre_head
        pushed = committed and remote_has_commit(self.repo_path, post_head)

        return WriteResult(
            status_code=resp.status_code,
            committed=committed,
            pushed=pushed,
            error=resp.json().get("detail") if resp.status_code >= 400 else None,
        )
```

### Parametrization

```python
@pytest.fixture(params=["library", "api"])
async def write_ctx(request, git_repos, ...) -> WriteContext:
    local_path, remote_path = git_repos
    if request.param == "library":
        manager = GitSyncManager(repo_path=local_path, ...)
        yield LibraryWriteContext(manager, local_path)
        await manager.close()
    else:
        app = build_test_app(local_path, ...)
        client = TestClient(app, raise_server_exceptions=False)
        yield APIWriteContext(client, local_path, PROJECT_ID)
```

Tests that apply to both modes use `write_ctx`. Tests that are API-only (decorators, routing, streaming) use a dedicated `api_client` fixture instead.

## Test App Factory

For API-mode tests, a minimal FastAPI app with the git sync middleware:

```python
def build_test_app(
    repo_path: Path,
    remote_name: str = "origin",
    extra_routes: list | None = None,
    sync_mode: str = "auto",
) -> FastAPI:
    """Build a minimal FastAPI app with GitSyncMiddleware for testing.

    Registers:
    - POST /api/projects/{project_id}/test_write — calls the pending write_fn
    - GET  /api/projects/{project_id}/test_read  — returns 200
    - Any extra_routes provided (for decorator tests, etc.)
    """
    app = FastAPI()
    # Configure git sync for the test project
    # Patch config to return the test repo path and sync_mode
    app.add_middleware(GitSyncMiddleware)
    # Register routes
    ...
    return app
```

## Fixtures

### conftest.py

The integration test conftest imports shared helpers from the parent conftest (`git_repos`, `commit_in_repo`, `push_from`, `SIG`) and adds integration-specific fixtures:

```python
# Re-export from parent conftest (these are pure git helpers, no design leakage)
from app.desktop.git_sync.conftest import (
    git_repos,
    commit_in_repo,
    push_from,
    SIG,
)

@pytest.fixture
def second_clone(git_repos, tmp_path):
    """A second clone of the same remote, for simulating another user."""
    _, remote_path = git_repos
    second_path = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_path))
    return second_path

@pytest.fixture
def manager(git_repos) -> AsyncGenerator[GitSyncManager, None]:
    """A GitSyncManager pointed at the local test repo."""
    local_path, _ = git_repos
    mgr = GitSyncManager(repo_path=local_path, auth_mode=AuthMode.NONE)
    yield mgr
    # teardown handled by reset_git_sync_registry autouse fixture

@pytest.fixture(params=["library", "api"])
def write_ctx(request, git_repos, ...) -> WriteContext:
    """Parametrized fixture: runs each test in both library and API mode."""
    ...
```

### Git State Assertion Helpers

Shared helper functions for verifying git state (not fixtures — plain functions):

```python
def assert_remote_has_commit(remote_path: Path, commit_hex: str) -> None:
    """Assert the remote repo contains a commit with this OID."""
    ...

def assert_clean_working_tree(repo_path: Path) -> None:
    """Assert the repo has no dirty files and no in-progress rebase/merge."""
    ...

def assert_stash_contains(repo_path: Path, message_substring: str) -> None:
    """Assert git stash list contains an entry matching the substring."""
    ...

def assert_commit_contains_files(repo_path: Path, commit_hex: str, filenames: list[str]) -> None:
    """Assert a commit's diff contains exactly these filenames."""
    ...

def assert_linear_history(repo_path: Path, count: int) -> None:
    """Assert the last N commits form a linear chain (no merges)."""
    ...

def get_head_sync(repo_path: Path) -> str:
    """Return current HEAD OID hex string."""
    ...

def get_stash_list(repo_path: Path) -> list[str]:
    """Return list of stash entry messages."""
    ...

def remote_has_commit(repo_path: Path, commit_hex: str) -> bool:
    """Check if the remote tracking ref includes this commit."""
    ...
```

## Network Failure Simulation

Parameterized across failure types using a fixture:

```python
class NetworkFailure:
    """Descriptor for a simulated network failure."""
    name: str
    exception: Exception  # What to raise from fetch/push

NETWORK_FAILURES = [
    NetworkFailure("connection_refused", pygit2.GitError("connection refused")),
    NetworkFailure("auth_failure", pygit2.GitError("401 unauthorized")),
    NetworkFailure("timeout", TimeoutError("operation timed out")),
]

@pytest.fixture(params=NETWORK_FAILURES, ids=lambda f: f.name)
def network_failure(request) -> NetworkFailure:
    return request.param

@pytest.fixture
def break_network(monkeypatch, network_failure):
    """Monkeypatch GitSyncManager to simulate network failure on fetch/push."""
    def failing_fetch(self):
        raise network_failure.exception
    def failing_push(self):
        raise network_failure.exception
    monkeypatch.setattr(GitSyncManager, "_fetch_sync", failing_fetch)
    monkeypatch.setattr(GitSyncManager, "_push_sync", failing_push)
```

## Conflict Simulation

For conflict scenarios, a helper that creates divergence:

```python
def create_remote_divergence(
    remote_path: Path,
    second_clone_path: Path,
    filename: str,
    content: str,
    message: str = "remote change",
) -> str:
    """Push a commit to remote from a second clone, creating divergence.

    Returns the OID of the pushed commit.
    """
    commit_in_repo(second_clone_path, filename, content, message)
    push_from(second_clone_path)
    return get_head_sync(second_clone_path)
```

For scenarios where push must fail on the first attempt but the remote already has commits, we monkeypatch `_push_sync` to fail once, then restore the real implementation.

## Test Patterns

### Typical Dual-Mode Test

```python
@pytest.mark.asyncio
async def test_write_commit_push(write_ctx: WriteContext, git_repos):
    """Scenario 1: Happy path write → commit → push."""
    local_path, remote_path = git_repos

    def write_files(repo_path: Path):
        (repo_path / "data.kiln").write_text('{"key": "value"}')

    pre_head = get_head_sync(local_path)
    result = await write_ctx.do_write(write_files)

    assert result.committed
    assert result.pushed
    post_head = get_head_sync(local_path)
    assert post_head != pre_head
    assert_remote_has_commit(remote_path, post_head)
    assert_clean_working_tree(local_path)
```

### API-Only Test

```python
@pytest.mark.asyncio
async def test_streaming_response_under_lock(api_client):
    """Scenario 24: SSE response under write lock returns 500."""
    resp = api_client.post(f"/api/projects/{PROJECT_ID}/test_stream")
    assert resp.status_code == 500
    assert "no_write_lock" in resp.json()["detail"]
```

### Conflict Test Pattern

```python
@pytest.mark.asyncio
async def test_push_conflict_rebase_succeeds(write_ctx, git_repos, second_clone):
    """Scenario 8: Push conflict → rebase → retry succeeds."""
    local_path, remote_path = git_repos

    # Make push fail once by creating divergence after ensure_fresh
    # but before push
    divergence_created = False

    original_push = GitSyncManager._push_sync
    def push_with_divergence(self):
        nonlocal divergence_created
        if not divergence_created:
            # Simulate another user pushing between our commit and push
            commit_in_repo(second_clone, "other.kiln", "other data", "other user")
            push_from(second_clone)
            divergence_created = True
        original_push(self)

    with patch.object(GitSyncManager, "_push_sync", push_with_divergence):
        result = await write_ctx.do_write(
            lambda p: (p / "our.kiln").write_text("our data")
        )

    assert result.committed
    assert result.pushed
    assert_linear_history(remote_path, 3)  # init + other + ours
    assert_clean_working_tree(local_path)
```

## Design Decisions

### Why WriteContext Protocol, Not a Base Class

A protocol + fixture parametrize is more pytest-idiomatic than class inheritance. It composes naturally with other fixtures (git_repos, second_clone, network_failure) and doesn't force tests into a class hierarchy.

### Why Monkeypatch for Network Failures

Real network failures against local bare repos are impossible (there's no network layer). Monkeypatching `_fetch_sync` and `_push_sync` is the narrowest possible mock — we're only faking the transport, not the git logic. Everything above those methods (rebase, rollback, stash, lock management) runs for real.

### Why a Separate Test App Factory

The real app (`make_app()`) has many routes, middleware, and startup logic unrelated to git sync. A minimal test app with only the git sync middleware and test endpoints isolates the behavior under test and avoids flaky coupling to unrelated app changes.

### API-Only vs Dual-Mode Categorization

Scenarios that test middleware-specific behavior (decorator routing, HTTP status codes, streaming detection, non-project routes, manual mode) are API-only — they don't have a meaningful library-mode equivalent. All other scenarios run in both modes.
