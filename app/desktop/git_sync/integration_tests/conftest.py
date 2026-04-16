"""Integration test fixtures for git auto-sync.

Provides dual-mode test infrastructure (library + API), git state assertion
helpers, network failure simulation, and conflict helpers.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Generator
from typing import Callable, Protocol
from unittest.mock import patch

import pygit2
import pygit2.enums
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.conftest import (
    _test_sig,
    commit_in_repo,
    delete_in_repo,
    git_repos,
    push_from,
    reset_git_sync_registry,
)
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.middleware import GitSyncMiddleware

__all__ = [
    "_test_sig",
    "commit_in_repo",
    "delete_in_repo",
    "git_repos",
    "push_from",
    "reset_git_sync_registry",
]

PROJECT_ID = "integration_test_proj"
PROJECT_PATH = "/tmp/integration_test/project.kiln"


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WriteResult:
    status_code: int | None = None
    committed: bool = False
    pushed: bool = False
    error: str | None = None


@dataclass
class ReadResult:
    status_code: int | None = None
    body: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# WriteContext protocol and implementations
# ---------------------------------------------------------------------------


class WriteContext(Protocol):
    repo_path: Path

    async def do_write(
        self,
        write_fn: Callable[[Path], object],
        expect_error: bool = False,
    ) -> WriteResult: ...

    async def do_read(self) -> ReadResult: ...


class LibraryWriteContext:
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
            async with self.manager.write_lock():
                await self.manager.ensure_clean()
                await self.manager.ensure_fresh()
                pre_request_head = await self.manager.get_head()

                try:
                    write_fn(self.repo_path)

                    if await self.manager.has_dirty_files():
                        await self.manager.commit_and_push(
                            context="TEST library_mode",
                            pre_request_head=pre_request_head,
                        )
                        post_head = get_head_sync(self.repo_path)
                        pushed = remote_has_commit(self.remote_path, post_head)
                        return WriteResult(committed=True, pushed=pushed)

                    return WriteResult(committed=False, pushed=False)

                except Exception:
                    await self.manager.rollback(pre_request_head)
                    raise
        except Exception as e:
            if expect_error:
                return WriteResult(
                    committed=False,
                    pushed=False,
                    error=str(e),
                )
            raise

    async def do_read(self) -> ReadResult:
        return ReadResult(body={"status": "ok"})


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
        pre_request_head = get_head_sync(self.repo_path)
        try:
            async with self.manager.atomic_write("TEST atomic_write"):
                write_fn(self.repo_path)
        except Exception as e:
            if expect_error:
                return WriteResult(
                    committed=False,
                    pushed=False,
                    error=str(e),
                )
            raise

        post_head = get_head_sync(self.repo_path)
        committed = post_head != pre_request_head
        pushed = committed and remote_has_commit(self.remote_path, post_head)
        return WriteResult(committed=committed, pushed=pushed)

    async def do_read(self) -> ReadResult:
        return ReadResult(body={"status": "ok"})


class APIWriteContext:
    def __init__(
        self,
        client: TestClient,
        repo_path: Path,
        remote_path: Path,
        write_fn_slot: list,
    ):
        self.client = client
        self.repo_path = repo_path
        self.remote_path = remote_path
        self._write_fn_slot = write_fn_slot

    async def do_write(
        self,
        write_fn: Callable[[Path], object],
        expect_error: bool = False,
    ) -> WriteResult:
        self._write_fn_slot.clear()
        self._write_fn_slot.append(write_fn)

        pre_head = get_head_sync(self.repo_path)
        resp = self.client.post(
            f"/api/projects/{PROJECT_ID}/test_write",
            json={},
        )
        post_head = get_head_sync(self.repo_path)

        committed = post_head != pre_head
        pushed = committed and remote_has_commit(self.remote_path, post_head)

        error = None
        if resp.status_code >= 400:
            try:
                error = resp.json().get("detail")
            except Exception:
                error = resp.text

        return WriteResult(
            status_code=resp.status_code,
            committed=committed,
            pushed=pushed,
            error=error,
        )

    async def do_read(self) -> ReadResult:
        resp = self.client.get(f"/api/projects/{PROJECT_ID}/test_read")
        error = None
        body = None
        if resp.status_code >= 400:
            try:
                error = resp.json().get("detail")
            except Exception:
                error = resp.text
        else:
            try:
                body = resp.json()
            except Exception:
                pass
        return ReadResult(status_code=resp.status_code, body=body, error=error)


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


@contextmanager
def mock_git_sync_config(config: GitSyncProjectConfig | None):
    with (
        patch(
            "app.desktop.git_sync.middleware.project_path_from_id",
            return_value=PROJECT_PATH,
        ),
        patch(
            "app.desktop.git_sync.middleware.get_git_sync_config",
            return_value=config,
        ),
    ):
        yield


def build_test_app(
    local_path: Path,
    write_fn_slot: list,
    extra_routes: list | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

    @app.post(f"/api/projects/{PROJECT_ID}/test_write")
    def test_write():
        if write_fn_slot:
            write_fn_slot[0](local_path)
        return {"ok": True}

    @app.get(f"/api/projects/{PROJECT_ID}/test_read")
    def test_read():
        return {"status": "ok"}

    if extra_routes:
        for method, path, handler in extra_routes:
            getattr(app, method)(path)(handler)

    return app


# ---------------------------------------------------------------------------
# Git state assertion helpers
# ---------------------------------------------------------------------------


def get_head_sync(repo_path: Path) -> str:
    repo = pygit2.Repository(str(repo_path))
    return str(repo.head.target)


def remote_has_commit(remote_path: Path, commit_hex: str) -> bool:
    repo = pygit2.Repository(str(remote_path))
    try:
        obj = repo.get(pygit2.Oid(hex=commit_hex))
        return obj is not None
    except Exception:
        return False


def assert_remote_has_commit(remote_path: Path, commit_hex: str) -> None:
    assert remote_has_commit(remote_path, commit_hex), (
        f"Remote does not contain commit {commit_hex}"
    )


def assert_clean_working_tree(repo_path: Path) -> None:
    repo = pygit2.Repository(str(repo_path))
    status = repo.status()
    dirty = {
        f: flags
        for f, flags in status.items()
        if flags != pygit2.enums.FileStatus.IGNORED
        and flags != pygit2.enums.FileStatus.CURRENT
    }
    assert not dirty, f"Working tree is dirty: {dirty}"
    assert repo.state() == pygit2.enums.RepositoryState.NONE, (
        f"Repo in non-clean state: {repo.state()}"
    )


def assert_stash_contains(repo_path: Path, message_substring: str) -> None:
    stashes = get_stash_list(repo_path)
    matching = [s for s in stashes if message_substring in s]
    assert matching, (
        f"No stash entry containing '{message_substring}'. Stash list: {stashes}"
    )


def assert_commit_contains_files(
    repo_path: Path, commit_hex: str, filenames: list[str]
) -> None:
    repo = pygit2.Repository(str(repo_path))
    commit = repo.get(pygit2.Oid(hex=commit_hex))
    assert isinstance(commit, pygit2.Commit), f"{commit_hex} is not a commit"

    if commit.parents:
        diff = repo.diff(commit.parents[0].tree, commit.tree)  # type: ignore[call-overload]
    else:
        diff = commit.tree.diff_to_tree()

    changed = {patch.delta.new_file.path or patch.delta.old_file.path for patch in diff}
    expected = set(filenames)
    assert expected == changed, (
        f"Expected exactly {expected} in commit, but found {changed}"
    )


def assert_linear_history(repo_path: Path, count: int) -> None:
    repo = pygit2.Repository(str(repo_path))
    commits = list(repo.walk(repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL))
    assert len(commits) >= count, (
        f"Expected at least {count} commits, found {len(commits)}"
    )
    for c in commits[:count]:
        assert len(c.parents) <= 1, (
            f"Commit {c.id} has {len(c.parents)} parents (merge)"
        )


def get_stash_list(repo_path: Path) -> list[str]:
    repo = pygit2.Repository(str(repo_path))
    return [s.message for s in repo.listall_stashes()]


def assert_reflog_contains_commit_with_file(
    repo_path: Path, filename: str, ref: str = "refs/heads/main"
) -> None:
    """Assert that a reflog entry points to a commit whose tree includes the file.

    This proves the data is actually recoverable via reflog, not just that
    the reflog has entries.
    """
    repo = pygit2.Repository(str(repo_path))
    reference = repo.references.get(ref)
    assert reference is not None, f"Reference {ref} not found"
    reflog = list(reference.log())
    for entry in reflog:
        try:
            commit = repo.get(entry.oid_new)
            if not isinstance(commit, pygit2.Commit):
                continue
            tree = commit.peel(pygit2.Tree)
            if filename in [e.name for e in tree]:
                return
        except Exception:
            continue
    raise AssertionError(
        f"No reflog entry for {ref} points to a commit containing '{filename}'"
    )


def get_commit_count(repo_path: Path) -> int:
    repo = pygit2.Repository(str(repo_path))
    return sum(
        1 for _ in repo.walk(repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL)
    )


# ---------------------------------------------------------------------------
# Conflict helper
# ---------------------------------------------------------------------------


def create_remote_divergence(
    remote_path: Path,
    second_clone_path: Path,
    filename: str,
    content: str,
    message: str = "remote change",
) -> str:
    commit_in_repo(second_clone_path, filename, content, message)
    push_from(second_clone_path)
    return get_head_sync(second_clone_path)


# ---------------------------------------------------------------------------
# Network failure simulation
# ---------------------------------------------------------------------------


@dataclass
class NetworkFailure:
    name: str
    exception_factory: Callable[[], Exception] = field(repr=False)


NETWORK_FAILURES = [
    NetworkFailure(
        "connection_refused",
        lambda: pygit2.GitError("connection refused"),
    ),
    NetworkFailure(
        "auth_failure",
        lambda: pygit2.GitError("401 unauthorized"),
    ),
    NetworkFailure(
        "timeout",
        lambda: TimeoutError("operation timed out"),
    ),
]


@pytest.fixture(params=NETWORK_FAILURES, ids=lambda f: f.name)
def network_failure(request) -> NetworkFailure:
    return request.param


@pytest.fixture
def break_network(monkeypatch, network_failure):
    def failing_fetch(self):
        raise network_failure.exception_factory()

    def failing_push(self):
        raise network_failure.exception_factory()

    monkeypatch.setattr(GitSyncManager, "_fetch_sync", failing_fetch)
    monkeypatch.setattr(GitSyncManager, "_push_sync", failing_push)
    return network_failure


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def auto_config(clone_path: str) -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="auto",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=clone_path,
        git_url=None,
        pat_token=None,
    )


@pytest.fixture
def second_clone(git_repos, tmp_path) -> Path:
    _, remote_path = git_repos
    second_path = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_path))
    return second_path


@pytest.fixture
def manager(git_repos) -> Generator[GitSyncManager]:
    local_path, _ = git_repos
    mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
    yield mgr
    mgr._git_executor.shutdown(wait=False)


@pytest.fixture(params=["library", "api", "atomic_write"])
def write_ctx(request, git_repos):
    local_path, remote_path = git_repos
    config = auto_config(str(local_path))

    if request.param == "library":
        mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
        ctx = LibraryWriteContext(mgr, local_path, remote_path)
        with mock_git_sync_config(config):
            yield ctx
        mgr._git_executor.shutdown(wait=False)
    elif request.param == "atomic_write":
        mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
        ctx = AtomicWriteContext(mgr, local_path, remote_path)
        with mock_git_sync_config(config):
            yield ctx
        mgr._git_executor.shutdown(wait=False)
    else:
        write_fn_slot: list = []
        app = build_test_app(local_path, write_fn_slot)
        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                ctx = APIWriteContext(client, local_path, remote_path, write_fn_slot)
                yield ctx


@pytest.fixture
def library_ctx(git_repos):
    local_path, remote_path = git_repos
    config = auto_config(str(local_path))
    mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
    ctx = LibraryWriteContext(mgr, local_path, remote_path)
    with mock_git_sync_config(config):
        yield ctx
    mgr._git_executor.shutdown(wait=False)


@pytest.fixture
def api_ctx(git_repos):
    local_path, remote_path = git_repos
    config = auto_config(str(local_path))
    write_fn_slot: list = []
    app = build_test_app(local_path, write_fn_slot)
    with mock_git_sync_config(config):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield APIWriteContext(client, local_path, remote_path, write_fn_slot)


@pytest.fixture
def api_client(git_repos):
    local_path, remote_path = git_repos
    config = auto_config(str(local_path))
    write_fn_slot: list = []
    app = build_test_app(local_path, write_fn_slot)
    with mock_git_sync_config(config):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, local_path, remote_path, write_fn_slot
