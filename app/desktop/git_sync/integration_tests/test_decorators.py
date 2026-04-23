"""Decorator integration tests for git auto-sync.

Scenarios 22-25: @write_lock on GET, @no_write_lock on POST,
streaming response under write lock, long lock hold warning.
"""

import logging
from unittest.mock import patch

import pygit2
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.desktop.git_sync.integration_tests.conftest import (
    PROJECT_ID,
    assert_clean_working_tree,
    assert_remote_has_commit,
    auto_config,
    get_commit_count,
    get_head_sync,
    mock_git_sync_config,
)
from app.desktop.git_sync.middleware import GitSyncMiddleware
from kiln_server.git_sync_decorators import no_write_lock, write_lock


class TestWriteLockDecoratorOnGet:
    """Scenario 22: GET endpoint with @write_lock acquires lock and commits."""

    @pytest.mark.asyncio
    async def test_write_lock_get_commits(self, git_repos):
        """GET with @write_lock triggers commit + push."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        @app.get(f"/api/projects/{PROJECT_ID}/write_get")
        @write_lock
        def write_get_endpoint():
            (local_path / "from_get.kiln").write_text("written by GET")
            return {"ok": True}

        @app.get(f"/api/projects/{PROJECT_ID}/test_read")
        def test_read():
            return {"status": "ok"}

        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                pre_head = get_head_sync(local_path)

                resp = client.get(f"/api/projects/{PROJECT_ID}/write_get")

                assert resp.status_code == 200
                post_head = get_head_sync(local_path)
                assert post_head != pre_head
                assert_remote_has_commit(remote_path, post_head)
                assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_write_lock_get_file_committed(self, git_repos):
        """File written by @write_lock GET appears in commit."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        @app.get(f"/api/projects/{PROJECT_ID}/write_get2")
        @write_lock
        def write_get_endpoint():
            (local_path / "get_file.kiln").write_text("GET content")
            return {"ok": True}

        @app.get(f"/api/projects/{PROJECT_ID}/test_read")
        def test_read():
            return {"status": "ok"}

        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                client.get(f"/api/projects/{PROJECT_ID}/write_get2")

                repo = pygit2.Repository(str(local_path))
                head = repo.revparse_single("HEAD")
                assert isinstance(head, pygit2.Commit)
                tree = head.peel(pygit2.Tree)
                assert "get_file.kiln" in [e.name for e in tree]


class TestNoWriteLockDecoratorOnPost:
    """Scenario 23: POST endpoint with @no_write_lock skips lock."""

    @pytest.mark.asyncio
    async def test_no_write_lock_post_no_commit(self, git_repos):
        """POST with @no_write_lock does not auto-commit."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        @app.post(f"/api/projects/{PROJECT_ID}/no_lock_post")
        @no_write_lock
        def no_lock_endpoint():
            (local_path / "no_lock_file.kiln").write_text("not committed")
            return {"ok": True}

        @app.get(f"/api/projects/{PROJECT_ID}/test_read")
        def test_read():
            return {"status": "ok"}

        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                pre_head = get_head_sync(local_path)
                pre_count = get_commit_count(local_path)

                resp = client.post(f"/api/projects/{PROJECT_ID}/no_lock_post")

                assert resp.status_code == 200
                assert get_head_sync(local_path) == pre_head
                assert get_commit_count(local_path) == pre_count


class TestStreamingResponseUnderLock:
    """Scenario 24: Streaming response under write lock should return 500."""

    @pytest.mark.asyncio
    async def test_streaming_under_lock_returns_500(self, git_repos):
        """SSE response under write lock should return 500 with @no_write_lock hint."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        async def event_stream():
            yield "data: hello\n\n"
            yield "data: world\n\n"

        @app.post(f"/api/projects/{PROJECT_ID}/test_stream")
        def stream_endpoint():
            return StreamingResponse(event_stream(), media_type="text/event-stream")

        @app.get(f"/api/projects/{PROJECT_ID}/test_read")
        def test_read():
            return {"status": "ok"}

        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(f"/api/projects/{PROJECT_ID}/test_stream")

                assert resp.status_code == 500
                assert "no_write_lock" in resp.json().get("detail", "").lower()


class TestLongLockHoldWarning:
    """Scenario 25: Warning logged when write lock held > 5 seconds."""

    @pytest.mark.asyncio
    async def test_long_lock_hold_warning(self, git_repos, caplog):
        """Warning is logged for slow POST endpoints."""
        local_path, remote_path = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        @app.post(f"/api/projects/{PROJECT_ID}/slow_post")
        def slow_endpoint():
            (local_path / "slow.kiln").write_text("slow write")
            return {"ok": True}

        @app.get(f"/api/projects/{PROJECT_ID}/test_read")
        def test_read():
            return {"status": "ok"}

        with mock_git_sync_config(config):
            with TestClient(app, raise_server_exceptions=False) as client:
                with patch("app.desktop.git_sync.middleware.time") as mock_time:
                    call_count = 0
                    base_time = 1000.0

                    def fake_monotonic():
                        nonlocal call_count
                        call_count += 1
                        if call_count == 1:
                            return base_time
                        return base_time + 6.0

                    mock_time.monotonic = fake_monotonic

                    with caplog.at_level(
                        logging.WARNING,
                        logger="app.desktop.git_sync.middleware",
                    ):
                        resp = client.post(f"/api/projects/{PROJECT_ID}/slow_post")

                assert resp.status_code == 200
                warning_messages = [
                    r.message for r in caplog.records if r.levelno >= logging.WARNING
                ]
                lock_warnings = [
                    m
                    for m in warning_messages
                    if "no_write_lock" in m.lower() or "lock held" in m.lower()
                ]
                assert len(lock_warnings) > 0, (
                    f"Expected a warning about long lock hold. Got warnings: {warning_messages}"
                )
