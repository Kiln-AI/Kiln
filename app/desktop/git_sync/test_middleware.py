import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pygit2
import pygit2.enums
import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse, StreamingResponse

from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.errors import (
    CorruptRepoError,
    RemoteUnreachableError,
    SyncConflictError,
    WriteLockTimeoutError,
)
from app.desktop.git_sync.middleware import GitSyncMiddleware
from app.desktop.git_sync.registry import GitSyncRegistry
from kiln_server.git_sync_decorators import no_write_lock, write_lock

PROJECT_ID = "test_proj_123"
PROJECT_PATH = "/tmp/test/project.kiln"


@contextmanager
def mock_git_sync_config(config):
    """Mock both project_path_from_id and get_git_sync_config for middleware tests."""
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


def _auto_config(clone_path: str) -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="auto",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=clone_path,
    )


def _manual_config() -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="manual",
        auth_mode="system_keys",
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
    mgr = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
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

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")
        assert resp.status_code == 200


def test_sync_disabled_passes_through():
    config = _manual_config()
    app = _build_app()

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )
        assert resp.status_code == 200


def test_no_clone_path_passes_through():
    config = GitSyncProjectConfig(
        sync_mode="auto",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=None,
    )
    app = _build_app()

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == expected_status
    body = resp.json()
    assert body["detail"] == expected_detail


def test_write_lock_timeout_from_lock_acquisition(git_repos):
    """WriteLockTimeoutError raised inside atomic_write() __aenter__ (lock
    acquisition) must be caught and mapped to 503, not bubble as a 500.

    The real timeout originates from threading.Lock.acquire(timeout=30) inside
    atomic_write's body, so the exception surfaces via __aenter__. Mocking
    atomic_write itself as a sync MagicMock with side_effect would fire on
    .call rather than __aenter__, exercising the wrong boundary. Instead we
    return a real async context manager whose __aenter__ raises.
    """
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    app = _build_app()

    class _TimingOutAtomicWrite:
        async def __aenter__(self):
            raise WriteLockTimeoutError("lock timed out")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    mock_manager = MagicMock(repo_path=local_path)
    mock_manager.atomic_write = MagicMock(return_value=_TimingOutAtomicWrite())

    with (
        mock_git_sync_config(config),
        patch.object(
            GitSyncRegistry,
            "get_or_create",
            return_value=mock_manager,
        ),
        patch(
            "app.desktop.git_sync.middleware.GitSyncRegistry.get_background_sync",
            return_value=None,
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/api/projects/{PROJECT_ID}/items",
            json={},
        )

    assert resp.status_code == 503
    body = resp.json()
    assert (
        body["detail"]
        == "Another save is in progress. Please wait a moment and try again."
    )


# --- Integration: lock held across lifecycle ---


def test_middleware_holds_lock_across_lifecycle(git_repos):
    local_path, _ = git_repos
    config = _auto_config(str(local_path))
    manager = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")

    lock_held_during_handler = []

    def post_endpoint_checks_lock():
        lock_held_during_handler.append(manager._write_lock.locked())
        return {"ok": True}

    app = _build_app(post_endpoint=post_endpoint_checks_lock)

    with mock_git_sync_config(config):
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
            "app.desktop.git_sync.middleware.project_path_from_id",
            return_value=PROJECT_PATH,
        ),
        patch(
            "app.desktop.git_sync.middleware.get_git_sync_config",
            return_value=config,
        ),
        patch.object(
            GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys"),
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

    with mock_git_sync_config(config):
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

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    assert resp.status_code == 200
    mock_bg.notify_request.assert_called()


# --- request.state manager attachment for read path ---


def test_manager_attached_to_request_state_for_read(git_repos):
    """Middleware sets request.state.git_sync_manager on read requests so
    @no_write_lock endpoints can build a SaveContext."""
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    expected_manager = GitSyncRegistry.get_or_create(
        local_path, auth_mode="system_keys"
    )

    seen_manager: list = []

    def get_endpoint(request: FastAPIRequest):
        seen_manager.append(getattr(request.state, "git_sync_manager", None))
        return {"status": "ok"}

    app = _build_app(get_endpoint=get_endpoint)

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    assert len(seen_manager) == 1
    assert seen_manager[0] is expected_manager


# --- Dev-mode dirty check ---


def test_dev_mode_dirty_read_returns_500(git_repos, monkeypatch, caplog):
    """Dev mode + GET that writes without lock -> 500 with diagnostic detail."""
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    def get_endpoint_that_writes():
        (local_path / "leaked_write.txt").write_text("oops, no lock")
        return {"status": "ok"}

    app = _build_app(get_endpoint=get_endpoint_that_writes)

    with mock_git_sync_config(config), caplog.at_level(logging.ERROR):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 500
    body = resp.json()
    assert "Dev mode" in body["detail"]
    assert "without holding a write lock" in body["detail"]
    rendered = [r.getMessage() for r in caplog.records]
    assert any("DEV MODE: Request left repo dirty" in m for m in rendered)
    assert any("leaked_write.txt" in m for m in rendered)


def test_dev_mode_clean_read_passes(git_repos, monkeypatch):
    """Dev mode + GET that doesn't write -> normal 200 response."""
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    app = _build_app()

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_dev_mode_off_dirty_read_passes(git_repos, monkeypatch):
    """Dev mode off + GET that writes -> original 200 response (no 500)."""
    monkeypatch.delenv("KILN_DEV_MODE", raising=False)
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    def get_endpoint_that_writes():
        (local_path / "leaked_in_prod.txt").write_text("would leak")
        return {"status": "ok"}

    app = _build_app(get_endpoint=get_endpoint_that_writes)

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_dev_mode_no_write_lock_skips_dirty_check(git_repos, monkeypatch):
    """Dev mode on + @no_write_lock GET that writes -> no 500 (skipped).

    The `git_repos` fixture is function-scoped (fresh tmp_path per test), so
    the leaked dirty file does not affect other tests and no cleanup is needed.
    """
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    @no_write_lock
    def get_endpoint_self_managed():
        (local_path / "self_managed_write.txt").write_text("self managed")
        return {"status": "ok"}

    app = _build_app(get_endpoint=get_endpoint_self_managed)

    with mock_git_sync_config(config):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_dev_mode_sse_without_no_write_lock_logs_error(git_repos, monkeypatch, caplog):
    """Dev mode on + SSE response without @no_write_lock -> log error, pass through."""
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    local_path, _ = git_repos
    config = _auto_config(str(local_path))

    def sse_endpoint():
        async def gen():
            yield b"data: hello\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app = _build_app(get_endpoint=sse_endpoint)

    with mock_git_sync_config(config), caplog.at_level(logging.ERROR):
        client = TestClient(app)
        resp = client.get(f"/api/projects/{PROJECT_ID}/items")

    assert resp.status_code == 200
    assert any(
        "DEV MODE: SSE endpoint missing @no_write_lock" in r.getMessage()
        for r in caplog.records
    )


def test_dev_mode_dirty_check_skipped_for_write_lock_path(
    git_repos, monkeypatch, caplog
):
    """Dev mode on + POST (write-locked) -> dev-mode dirty check does not run.

    The write path commits via atomic_write so the dirty check is unnecessary.
    """
    monkeypatch.setenv("KILN_DEV_MODE", "true")
    local_path, remote_path = git_repos
    config = _auto_config(str(local_path))

    def post_endpoint_that_writes():
        (local_path / "write_path_file.txt").write_text("via POST")
        return {"created": True}

    app = _build_app(post_endpoint=post_endpoint_that_writes)

    remote_repo = pygit2.Repository(str(remote_path))
    head_before = str(remote_repo.head.target)

    with mock_git_sync_config(config), caplog.at_level(logging.ERROR):
        client = TestClient(app)
        resp = client.post(f"/api/projects/{PROJECT_ID}/items", json={})

    # Normal 200 + commit pushed; no dev-mode 500 detail.
    assert resp.status_code == 200
    assert resp.json() == {"created": True}
    remote_repo = pygit2.Repository(str(remote_path))
    assert str(remote_repo.head.target) != head_before

    # Assert the dev-mode dirty check did not run on the write-lock path
    # (no "DEV MODE:" log messages emitted during the request).
    rendered = [r.getMessage() for r in caplog.records]
    assert not any("DEV MODE:" in m for m in rendered), (
        f"Dev-mode check should be skipped on write path, got logs: {rendered}"
    )
