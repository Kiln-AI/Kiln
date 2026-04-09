from unittest.mock import MagicMock, patch

import pygit2
import pygit2.enums
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.decorators import no_write_lock, write_lock
from app.desktop.git_sync.errors import (
    CorruptRepoError,
    RemoteUnreachableError,
    SyncConflictError,
    WriteLockTimeoutError,
)
from app.desktop.git_sync.middleware import GitSyncMiddleware
from app.desktop.git_sync.registry import GitSyncRegistry

PROJECT_ID = "test_proj_123"


def _auto_config(clone_path: str) -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="auto",
        remote_name="origin",
        branch="main",
        clone_path=clone_path,
    )


def _manual_config() -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="manual",
        remote_name="origin",
        branch="main",
        clone_path=None,
    )


def _build_app(
    git_repos=None,
    config_override=None,
    get_endpoint=None,
    post_endpoint=None,
):
    """Build a minimal FastAPI app with GitSyncMiddleware for testing."""
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
            return {"created": True}

    else:
        app.post(f"/api/projects/{PROJECT_ID}/items")(post_endpoint)

    @app.get("/ping")
    def ping():
        return "pong"

    return app


@pytest.fixture
def manager(git_repos):
    local_path, _ = git_repos
    mgr = GitSyncRegistry.get_or_create(local_path)
    yield mgr


# --- Pass-through tests ---


def test_non_project_route_passes_through():
    app = _build_app()
    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config", return_value=None
    ):
        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == "pong"


def test_get_request_passes_through_without_lock(git_repos):
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    app = _build_app()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")
        assert resp.status_code == 200


def test_sync_disabled_passes_through():
    config = _manual_config()
    app = _build_app()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )
        assert resp.status_code == 200


def test_no_clone_path_passes_through():
    config = GitSyncProjectConfig(
        sync_mode="auto",
        remote_name="origin",
        branch="main",
        clone_path=None,
    )
    app = _build_app()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )
        assert resp.status_code == 200


# --- Mutating request tests ---


def test_mutating_request_no_changes_no_commit(git_repos):
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    app = _build_app()

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) == head_before


def test_mutating_request_commits_and_pushes(git_repos):
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    def post_endpoint_that_writes():
        (local_path / "new_file.txt").write_text("hello from handler")
        return {"created": True}

    app = _build_app(post_endpoint=post_endpoint_that_writes)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) != head_before


def test_mutating_request_error_rolls_back(git_repos):
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    def post_endpoint_that_errors():
        (local_path / "should_rollback.txt").write_text("oops")
        raise ValueError("handler error")

    app = _build_app(post_endpoint=post_endpoint_that_errors)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 500

    local_repo = pygit2.Repository(str(local_path))
    status = local_repo.status()
    dirty = any(
        f != pygit2.enums.FileStatus.IGNORED and f != pygit2.enums.FileStatus.CURRENT
        for f in status.values()
    )
    assert not dirty


def test_mutating_request_handler_4xx_commits_changes(git_repos):
    """Handler 4xx responses are not rolled back -- only exceptions trigger rollback.

    A handler may intentionally write files and return 4xx (e.g. partial save
    with validation error). Per spec, rollback only happens on exceptions.
    """
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    def post_endpoint_that_returns_error():
        (local_path / "partial_save.txt").write_text("partial data")
        return JSONResponse(status_code=422, content={"detail": "validation error"})

    app = _build_app(post_endpoint=post_endpoint_that_returns_error)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 422

    # Changes should have been committed and pushed (no rollback on 4xx)
    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) != head_before


# --- Decorator tests ---


def test_write_lock_decorator_on_get(git_repos):
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    @write_lock
    def get_endpoint_with_write():
        (local_path / "written_by_get.txt").write_text("via GET")
        return {"ok": True}

    app = _build_app(get_endpoint=get_endpoint_with_write)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) != head_before


def test_no_write_lock_decorator_on_post(git_repos):
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    @no_write_lock
    def post_endpoint_no_lock():
        (local_path / "no_lock_write.txt").write_text("untracked")
        return {"ok": True}

    app = _build_app(post_endpoint=post_endpoint_no_lock)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 200

    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) == head_before


# --- Error mapping tests ---


@pytest.mark.parametrize(
    "error_class,expected_status,expected_detail",
    [
        (
            RemoteUnreachableError,
            503,
            "Cannot sync with remote. Check your connection.",
        ),
        (SyncConflictError, 409, "There was a problem saving. Please try again."),
        (
            WriteLockTimeoutError,
            503,
            "Another save is in progress. Please wait a moment and try again.",
        ),
        (CorruptRepoError, 500, "Git repository is in an unexpected state."),
    ],
)
def test_error_mapping(git_repos, error_class, expected_status, expected_detail):
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    def post_endpoint_that_raises():
        raise error_class("test error")

    app = _build_app(post_endpoint=post_endpoint_that_raises)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == expected_status
    body = resp.json()
    assert body["detail"] == expected_detail


# --- Integration: lock held across lifecycle ---


def test_middleware_holds_lock_across_lifecycle(git_repos):
    local_path, _ = git_repos
    config = _auto_config(str(local_path))
    manager = GitSyncRegistry.get_or_create(local_path)

    lock_held_during_handler = []

    def post_endpoint_checks_lock():
        lock_held_during_handler.append(manager._write_lock.locked())
        return {"ok": True}

    app = _build_app(post_endpoint=post_endpoint_checks_lock)

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 200
    assert lock_held_during_handler == [True]


# --- Freshness check for reads ---


def test_get_request_checks_freshness(git_repos):
    """GET requests call ensure_fresh_for_read on the manager."""
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    app = _build_app()

    with (
        patch(
            "app.desktop.git_sync.middleware.get_git_sync_config",
            return_value=config,
        ),
        patch.object(
            GitSyncRegistry.get_or_create(local_path),
            "ensure_fresh_for_read",
        ) as mock_fresh,
    ):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    mock_fresh.assert_called_once()


# --- Background sync notify ---


def test_notify_request_called_on_read(git_repos):
    """Middleware calls notify_request on background sync for read requests."""
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    mock_bg = MagicMock()
    GitSyncRegistry.register_background_sync(local_path, mock_bg)

    app = _build_app()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    mock_bg.notify_request.assert_called()


def test_notify_request_called_on_write(git_repos):
    """Middleware calls notify_request on background sync for write requests."""
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    mock_bg = MagicMock()
    GitSyncRegistry.register_background_sync(local_path, mock_bg)

    app = _build_app()

    with patch(
        "app.desktop.git_sync.middleware.get_git_sync_config",
        return_value=config,
    ):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    assert resp.status_code == 200
    mock_bg.notify_request.assert_called()
