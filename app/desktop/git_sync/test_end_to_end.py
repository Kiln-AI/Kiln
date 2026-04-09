"""End-to-end integration tests for git auto sync.

These tests exercise the full stack: middleware + manager + real git repos.
"""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pygit2
import pygit2.enums
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop.git_sync.background_sync import BackgroundSync
from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.middleware import GitSyncMiddleware

PROJECT_ID = "e2e_proj"


def _auto_config(clone_path: str) -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="auto",
        remote_name="origin",
        branch="main",
        clone_path=clone_path,
    )


def _build_app(local_path: Path, post_endpoint=None, get_endpoint=None):
    app = FastAPI()
    app.add_middleware(GitSyncMiddleware)

    if get_endpoint is None:

        @app.get(f"/api/projects/{PROJECT_ID}/items")
        def default_get():
            return {"status": "ok"}

    else:
        app.get(f"/api/projects/{PROJECT_ID}/items")(get_endpoint)

    if post_endpoint is None:

        @app.post(f"/api/projects/{PROJECT_ID}/items")
        def default_post():
            (local_path / "default_write.txt").write_text("default")
            return {"created": True}

    else:
        app.post(f"/api/projects/{PROJECT_ID}/items")(post_endpoint)

    return app


# --- Full lifecycle ---


def test_full_write_lifecycle(git_repos):
    """POST -> lock -> handler writes -> commit -> push -> verify in remote."""
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    def post_writes_file():
        (local_path / "lifecycle.txt").write_text("end-to-end")
        return {"ok": True}

    app = _build_app(local_path, post_endpoint=post_writes_file)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) != head_before

    remote_commit = remote_repo.revparse_single("refs/heads/main")
    assert isinstance(remote_commit, pygit2.Commit)
    assert "[Kiln]" in remote_commit.message


def test_concurrent_writes_serialized(git_repos):
    """Two writes are serialized via the write lock; both succeed."""
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    call_order: list[str] = []

    def post_write_a():
        call_order.append("a")
        (local_path / "file_a.txt").write_text("a")
        return {"writer": "a"}

    def post_write_b():
        call_order.append("b")
        (local_path / "file_b.txt").write_text("b")
        return {"writer": "b"}

    app = FastAPI()
    app.add_middleware(GitSyncMiddleware)

    @app.post(f"/api/projects/{PROJECT_ID}/items/a")
    def endpoint_a():
        return post_write_a()

    @app.post(f"/api/projects/{PROJECT_ID}/items/b")
    def endpoint_b():
        return post_write_b()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp_a = client.post(f"/api/projects/{PROJECT_ID}/items/a", json={})
        resp_b = client.post(f"/api/projects/{PROJECT_ID}/items/b", json={})

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    log = list(
        remote_repo.walk(remote_repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL)
    )
    assert len(log) == 3


def test_conflict_retry_succeeds(git_repos, tmp_path):
    """Remote diverges after ensure_fresh, push fails, retry succeeds."""
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    second_clone = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_clone))

    pushed_during_request = False

    def post_that_triggers_conflict():
        nonlocal pushed_during_request
        (local_path / "my_file.txt").write_text("my change")

        if not pushed_during_request:
            commit_in_repo(
                second_clone, "other_file.txt", "concurrent", "concurrent commit"
            )
            push_from(second_clone)
            pushed_during_request = True

        return {"ok": True}

    app = _build_app(local_path, post_endpoint=post_that_triggers_conflict)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    log = list(
        remote_repo.walk(remote_repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL)
    )
    assert len(log) >= 3


def test_crash_recovery_on_next_write(git_repos):
    """Dirty repo (simulating crash) is auto-recovered on next write."""
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    (local_path / "crash_artifact.txt").write_text("leftover from crash")

    def post_clean_write():
        (local_path / "after_recovery.txt").write_text("new data")
        return {"ok": True}

    app = _build_app(local_path, post_endpoint=post_clean_write)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    remote_head = remote_repo.revparse_single("refs/heads/main")
    assert isinstance(remote_head, pygit2.Commit)

    local_repo = pygit2.Repository(str(local_path))
    status = local_repo.status()
    dirty = any(
        f != pygit2.enums.FileStatus.IGNORED and f != pygit2.enums.FileStatus.CURRENT
        for f in status.values()
    )
    assert not dirty


@pytest.mark.asyncio
async def test_background_sync_picks_up_remote_changes(git_repos, tmp_path):
    """Remote changes appear in local within a background sync poll cycle."""
    local_path, remote_path = git_repos

    second_clone = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_clone))

    manager = GitSyncManager(repo_path=local_path)
    try:
        bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
        await bg.start()

        commit_in_repo(second_clone, "bg_change.txt", "background data", "bg commit")
        push_from(second_clone)

        await asyncio.sleep(0.3)

        await bg.stop()

        assert (local_path / "bg_change.txt").exists()
        assert (local_path / "bg_change.txt").read_text() == "background data"
    finally:
        manager._git_executor.shutdown(wait=True)
        if manager._repo is not None:
            manager._repo.free()
