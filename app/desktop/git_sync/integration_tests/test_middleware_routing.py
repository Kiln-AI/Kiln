"""Middleware routing integration tests for git auto-sync.

Scenarios 30-31: non-project routes pass through, manual mode unaffected.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.desktop.git_sync.integration_tests.conftest import (
    PROJECT_ID,
    build_test_app,
    get_commit_count,
    get_head_sync,
    mock_git_sync_config,
    auto_config,
)
from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.middleware import GitSyncMiddleware


class TestNonProjectRoutes:
    """Scenario 30: Non-project URLs are not affected by git sync."""

    def test_non_project_route_passes_through(self, git_repos):
        local_path, _ = git_repos
        config = auto_config(str(local_path))

        app = FastAPI()
        app.add_middleware(GitSyncMiddleware)  # type: ignore[invalid-argument-type]

        @app.get("/api/settings")
        def get_settings():
            return {"theme": "dark"}

        @app.post("/api/settings")
        def post_settings():
            return {"saved": True}

        with mock_git_sync_config(config):
            client = TestClient(app, raise_server_exceptions=False)
            pre_head = get_head_sync(local_path)
            pre_count = get_commit_count(local_path)

            get_resp = client.get("/api/settings")
            assert get_resp.status_code == 200
            assert get_resp.json() == {"theme": "dark"}

            post_resp = client.post("/api/settings")
            assert post_resp.status_code == 200
            assert post_resp.json() == {"saved": True}

            assert get_head_sync(local_path) == pre_head
            assert get_commit_count(local_path) == pre_count


class TestManualModeUnaffected:
    """Scenario 31: Manual-mode projects are not wrapped by middleware."""

    def test_manual_mode_no_commit(self, git_repos):
        local_path, remote_path = git_repos

        manual_config = GitSyncProjectConfig(
            sync_mode="manual",
            auth_mode="system_keys",
            remote_name="origin",
            branch="main",
            clone_path=str(local_path),
            git_url=None,
            pat_token=None,
            oauth_token=None,
        )

        write_fn_slot: list = []
        app = build_test_app(local_path, write_fn_slot)

        with mock_git_sync_config(manual_config):
            client = TestClient(app, raise_server_exceptions=False)

            pre_head = get_head_sync(local_path)
            pre_count = get_commit_count(local_path)

            write_fn_slot.clear()
            write_fn_slot.append(
                lambda p: (p / "manual_write.txt").write_text("should not commit")
            )

            resp = client.post(
                f"/api/projects/{PROJECT_ID}/test_write",
                json={},
            )
            assert resp.status_code == 200

            assert get_head_sync(local_path) == pre_head
            assert get_commit_count(local_path) == pre_count
            assert (local_path / "manual_write.txt").exists()
