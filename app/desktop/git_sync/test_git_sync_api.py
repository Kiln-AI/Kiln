import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_ai.utils.config import Config
from kiln_ai.utils.project_utils import DuplicateProjectError

from app.desktop.git_sync.git_sync_api import connect_git_sync_api


@pytest.fixture
def app():
    app = FastAPI()
    connect_git_sync_api(app)
    return app


@pytest.fixture
def api_client(app):
    return TestClient(app)


class TestTestAccess:
    def test_success_system_keys(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.test_remote_access") as mock:
            mock.return_value = (True, "Access successful", "system_keys")
            resp = api_client.post(
                "/api/git_sync/test_access",
                json={"git_url": "https://github.com/test/repo.git"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["auth_required"] is False
        assert data["auth_method"] == "system_keys"

    def test_auth_required(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.test_remote_access") as mock:
            mock.return_value = (False, "Authentication failed", None)
            resp = api_client.post(
                "/api/git_sync/test_access",
                json={"git_url": "https://github.com/private/repo.git"},
            )
        data = resp.json()
        assert data["success"] is False
        assert data["auth_required"] is True
        assert data["auth_method"] is None

    def test_with_pat(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.test_remote_access") as mock:
            mock.return_value = (True, "Access successful", "pat_token")
            resp = api_client.post(
                "/api/git_sync/test_access",
                json={
                    "git_url": "https://github.com/private/repo.git",
                    "pat_token": "ghp_test123",
                },
            )
        data = resp.json()
        assert data["success"] is True
        assert data["auth_method"] == "pat_token"
        mock.assert_called_once_with(
            "https://github.com/private/repo.git",
            "ghp_test123",
            auth_mode="system_keys",
            oauth_token=None,
        )


class TestListBranches:
    def test_returns_branches(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.list_remote_branches") as mock:
            mock.return_value = (["main", "develop"], "main")
            resp = api_client.post(
                "/api/git_sync/list_branches",
                json={"git_url": "https://github.com/test/repo.git"},
            )
        data = resp.json()
        assert data["branches"] == ["main", "develop"]
        assert data["default_branch"] == "main"

    def test_with_default_branch(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.list_remote_branches") as mock:
            mock.return_value = (["main", "feature"], "main")
            resp = api_client.post(
                "/api/git_sync/list_branches",
                json={"git_url": "https://github.com/test/repo.git"},
            )
        assert resp.json()["default_branch"] == "main"

    def test_error_returns_400(self, api_client):
        with patch("app.desktop.git_sync.git_sync_api.list_remote_branches") as mock:
            mock.side_effect = Exception("network error")
            resp = api_client.post(
                "/api/git_sync/list_branches",
                json={"git_url": "https://bad-url.example.com"},
            )
        assert resp.status_code == 400


class TestClone:
    def test_success(self, api_client, tmp_path):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path"
            ) as mock_path,
            patch("app.desktop.git_sync.git_sync_api.clone_repo") as mock_clone,
            patch(
                "app.desktop.git_sync.git_sync_api.compute_temp_clone_path"
            ) as mock_compute,
        ):
            mock_path.return_value = str(tmp_path)
            expected_clone = tmp_path / "kiln_clone_abc123"
            mock_compute.return_value = expected_clone
            mock_clone.return_value = MagicMock()

            resp = api_client.post(
                "/api/git_sync/clone",
                json={
                    "git_url": "https://github.com/test/repo.git",
                    "branch": "main",
                },
            )
        data = resp.json()
        assert data["success"] is True
        assert data["clone_path"] == str(expected_clone)

    def test_auth_error_returns_401(self, api_client, tmp_path):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path"
            ) as mock_path,
            patch("app.desktop.git_sync.git_sync_api.clone_repo") as mock_clone,
            patch(
                "app.desktop.git_sync.git_sync_api.compute_temp_clone_path"
            ) as mock_compute,
        ):
            mock_path.return_value = str(tmp_path)
            mock_compute.return_value = tmp_path / "clone"
            mock_clone.side_effect = Exception("401 Unauthorized")
            resp = api_client.post(
                "/api/git_sync/clone",
                json={
                    "git_url": "https://github.com/private/repo.git",
                    "branch": "main",
                },
            )
        assert resp.status_code == 401

    def test_clone_failure_cleans_up_temp_dir(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_temp"
        clone_dir.mkdir()
        (clone_dir / "partial_file").write_text("partial")

        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path"
            ) as mock_path,
            patch("app.desktop.git_sync.git_sync_api.clone_repo") as mock_clone,
            patch(
                "app.desktop.git_sync.git_sync_api.compute_temp_clone_path"
            ) as mock_compute,
        ):
            mock_path.return_value = str(tmp_path)
            mock_compute.return_value = clone_dir
            mock_clone.side_effect = Exception("network timeout")
            resp = api_client.post(
                "/api/git_sync/clone",
                json={
                    "git_url": "https://github.com/test/repo.git",
                    "branch": "main",
                },
            )
        assert resp.status_code == 400
        assert "Clone failed" in resp.json()["detail"]
        assert not clone_dir.exists()

    def test_clone_auth_failure_cleans_up_temp_dir(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_temp"
        clone_dir.mkdir()

        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path"
            ) as mock_path,
            patch("app.desktop.git_sync.git_sync_api.clone_repo") as mock_clone,
            patch(
                "app.desktop.git_sync.git_sync_api.compute_temp_clone_path"
            ) as mock_compute,
        ):
            mock_path.return_value = str(tmp_path)
            mock_compute.return_value = clone_dir
            mock_clone.side_effect = Exception("403 Forbidden")
            resp = api_client.post(
                "/api/git_sync/clone",
                json={
                    "git_url": "https://github.com/test/repo.git",
                    "branch": "main",
                },
            )
        assert resp.status_code == 401
        assert not clone_dir.exists()


class TestTestWriteAccess:
    def test_success(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch("app.desktop.git_sync.git_sync_api.test_write_access") as mock,
        ):
            mock.return_value = (True, "Write access confirmed")
            resp = api_client.post(
                "/api/git_sync/test_write_access",
                json={"clone_path": str(clone_dir)},
            )
        data = resp.json()
        assert data["success"] is True


class TestScanProjects:
    def test_finds_projects(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        project_data = {"name": "Test", "description": "desc", "id": "proj_abc"}
        (clone_dir / "project.kiln").write_text(json.dumps(project_data))

        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path",
            return_value=str(tmp_path),
        ):
            resp = api_client.post(
                "/api/git_sync/scan_projects",
                json={"clone_path": str(clone_dir)},
            )
        data = resp.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "Test"
        assert data["projects"][0]["id"] == "proj_abc"

    def test_no_projects(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()

        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path",
            return_value=str(tmp_path),
        ):
            resp = api_client.post(
                "/api/git_sync/scan_projects",
                json={"clone_path": str(clone_dir)},
            )
        assert resp.json()["projects"] == []

    def test_invalid_path(self, api_client, tmp_path):
        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path",
            return_value=str(tmp_path),
        ):
            resp = api_client.post(
                "/api/git_sync/scan_projects",
                json={"clone_path": "/nonexistent/path"},
            )
        assert resp.status_code == 400


class TestSaveAndGetConfig:
    def test_save_and_retrieve(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch("app.desktop.git_sync.git_sync_api.save_git_sync_config"),
            patch("app.desktop.git_sync.git_sync_api.add_project_to_config"),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": str(clone_dir),
                    "branch": "main",
                    "pat_token": "ghp_test",
                },
            )
        data = resp.json()
        assert data["sync_mode"] == "auto"
        assert data["has_pat_token"] is True
        assert "pat_token" not in data

    def test_save_duplicate_same_path(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.check_duplicate_project_id",
                side_effect=DuplicateProjectError(
                    "This project is already imported.", same_path=True
                ),
            ),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": str(clone_dir),
                    "branch": "main",
                },
            )
        assert resp.status_code == 409
        assert "already imported" in resp.json()["detail"]

    def test_save_duplicate_different_path(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.check_duplicate_project_id",
                side_effect=DuplicateProjectError(
                    'You already have a project with this ID. You must remove project "Existing" before adding this.',
                    same_path=False,
                ),
            ),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": str(clone_dir),
                    "branch": "main",
                },
            )
        assert resp.status_code == 409
        assert "remove project" in resp.json()["detail"]

    def test_save_adds_project_to_config(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.save_git_sync_config"
            ) as mock_save,
            patch(
                "app.desktop.git_sync.git_sync_api.add_project_to_config"
            ) as mock_add,
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "subdir/project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": str(clone_dir),
                    "branch": "main",
                },
            )
        assert resp.status_code == 200
        mock_save.assert_called_once()
        saved_key = mock_save.call_args[0][0]
        expected = str((clone_dir / "subdir/project.kiln").resolve())
        assert saved_key == expected
        mock_add.assert_called_once_with(expected)

    def test_get_config_exists(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock,
        ):
            mock.return_value = {
                "sync_mode": "auto",
                "auth_mode": "system_keys",
                "remote_name": "origin",
                "branch": "main",
                "clone_path": "/tmp/clone",
                "git_url": "https://github.com/test/repo.git",
                "pat_token": "ghp_secret",
            }
            resp = api_client.get("/api/git_sync/config/proj1")
        data = resp.json()
        assert data["sync_mode"] == "auto"
        assert data["has_pat_token"] is True
        assert "pat_token" not in data
        mock.assert_called_once_with("/tmp/clone/project.kiln")

    def test_get_config_project_not_found(self, api_client):
        with patch(
            "app.desktop.git_sync.git_sync_api.project_path_from_id",
            return_value=None,
        ):
            resp = api_client.get("/api/git_sync/config/nonexistent")
        assert resp.status_code == 404

    def test_get_config_no_sync_config(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock,
        ):
            mock.return_value = None
            resp = api_client.get("/api/git_sync/config/proj1")
        assert resp.status_code == 404


class TestUpdateConfig:
    def test_toggle_mode(self, api_client):
        existing = {
            "sync_mode": "auto",
            "auth_mode": "system_keys",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://example.com",
            "pat_token": None,
        }
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock_get,
            patch(
                "app.desktop.git_sync.git_sync_api.save_git_sync_config"
            ) as mock_save,
        ):
            mock_get.return_value = existing
            resp = api_client.patch(
                "/api/git_sync/update_config/proj1",
                json={"sync_mode": "manual"},
            )
        data = resp.json()
        assert data["sync_mode"] == "manual"
        mock_save.assert_called_once()
        saved_key = mock_save.call_args[0][0]
        assert saved_key == "/tmp/clone/project.kiln"

    def test_update_pat_token(self, api_client):
        existing = {
            "sync_mode": "auto",
            "auth_mode": "system_keys",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://example.com",
            "pat_token": None,
        }
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock_get,
            patch("app.desktop.git_sync.git_sync_api.save_git_sync_config"),
        ):
            mock_get.return_value = existing
            resp = api_client.patch(
                "/api/git_sync/update_config/proj1",
                json={"pat_token": "ghp_new_token"},
            )
        data = resp.json()
        assert data["has_pat_token"] is True

    def test_update_project_not_found(self, api_client):
        with patch(
            "app.desktop.git_sync.git_sync_api.project_path_from_id",
            return_value=None,
        ):
            resp = api_client.patch(
                "/api/git_sync/update_config/nonexistent",
                json={"sync_mode": "manual"},
            )
        assert resp.status_code == 404

    def test_update_no_sync_config(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock,
        ):
            mock.return_value = None
            resp = api_client.patch(
                "/api/git_sync/update_config/nonexistent",
                json={"sync_mode": "manual"},
            )
        assert resp.status_code == 404


class TestRenameClone:
    def test_success(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        (clone_dir / "project.kiln").write_text("{}")

        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path"
        ) as mock_path:
            mock_path.return_value = str(tmp_path)
            resp = api_client.post(
                "/api/git_sync/rename_clone",
                json={
                    "clone_path": str(clone_dir),
                    "project_name": "My Project",
                    "project_id": "proj_123",
                },
            )
        data = resp.json()
        assert data["success"] is True
        assert "proj_123 - My Project" in data["new_clone_path"]
        assert not clone_dir.exists()

    def test_path_traversal_project_id_returns_400(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        (clone_dir / "project.kiln").write_text("{}")

        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path"
        ) as mock_path:
            mock_path.return_value = str(tmp_path)
            resp = api_client.post(
                "/api/git_sync/rename_clone",
                json={
                    "clone_path": str(clone_dir),
                    "project_name": "Test",
                    "project_id": "../../escape",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert ".." not in data["new_clone_path"]
        assert ".git-projects" in data["new_clone_path"]

    def test_nonexistent_path_returns_400(self, api_client, tmp_path):
        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path"
        ) as mock_path:
            mock_path.return_value = str(tmp_path)
            resp = api_client.post(
                "/api/git_sync/rename_clone",
                json={
                    "clone_path": "/nonexistent/path",
                    "project_name": "Test",
                    "project_id": "id1",
                },
            )
        assert resp.status_code == 400


class TestDeleteConfig:
    def test_delete_success(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.delete_git_sync_config") as mock,
        ):
            resp = api_client.delete("/api/git_sync/config/proj1")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Config deleted"
        mock.assert_called_once_with("/tmp/clone/project.kiln")

    def test_delete_project_not_found(self, api_client):
        with patch(
            "app.desktop.git_sync.git_sync_api.project_path_from_id",
            return_value=None,
        ):
            resp = api_client.delete("/api/git_sync/config/nonexistent")
        assert resp.status_code == 404


class TestOAuthStart:
    def test_success_public_repo(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=123,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=456,
            ),
        ):
            resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/Kiln-AI/kiln.git"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["owner_name"] == "Kiln-AI"
        assert data["repo_name"] == "kiln"
        assert data["owner_pre_selected"] is True
        assert data["repo_pre_selected"] is True
        assert "state" in data
        assert "install_url" in data
        assert "authorize_url" in data
        assert "suggested_target_id=123" in data["install_url"]
        assert "github.com/login/oauth/authorize" in data["authorize_url"]
        assert data["state"] in data["authorize_url"]
        assert "client_id=" in data["authorize_url"]
        assert "code_challenge_method=S256" in data["authorize_url"]

    def test_private_repo(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=123,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/private-repo.git"},
            )
        data = resp.json()
        assert data["owner_pre_selected"] is True
        assert data["repo_pre_selected"] is False

    def test_non_github_url(self, api_client):
        resp = api_client.post(
            "/api/git_sync/oauth/start",
            json={"git_url": "https://gitlab.com/owner/repo.git"},
        )
        assert resp.status_code == 400


class TestOAuthCallback:
    def test_success_renders_success_page(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        with patch(
            "app.desktop.git_sync.git_sync_api.exchange_code_for_token",
            return_value="ghu_token",
        ):
            resp = api_client.get(
                f"/api/git_sync/oauth/callback?state={state}&code=auth_code",
            )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Authorization Complete" in resp.text
        assert "Return to Kiln" in resp.text

    def test_missing_state_renders_error_page(self, api_client):
        resp = api_client.get("/api/git_sync/oauth/callback?code=auth_code")
        assert resp.status_code == 400
        assert "text/html" in resp.headers["content-type"]
        assert "Authorization Failed" in resp.text
        assert "Missing state" in resp.text

    def test_invalid_state_renders_error_page(self, api_client):
        resp = api_client.get(
            "/api/git_sync/oauth/callback?state=invalid&code=auth_code"
        )
        assert resp.status_code == 400
        assert "Authorization Failed" in resp.text
        assert "expired" in resp.text

    def test_error_from_github(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        resp = api_client.get(
            f"/api/git_sync/oauth/callback?state={state}&error=access_denied&error_description=User+denied",
        )
        assert resp.status_code == 400
        assert "Authorization Failed" in resp.text
        assert "User denied" in resp.text

    def test_missing_code_renders_error_page(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        resp = api_client.get(
            f"/api/git_sync/oauth/callback?state={state}&code=",
        )
        assert resp.status_code == 400
        assert "text/html" in resp.headers["content-type"]
        assert "Authorization Failed" in resp.text
        assert "Missing authorization code" in resp.text

    def test_token_exchange_failure(self, api_client):
        from app.desktop.git_sync.oauth import OAuthError

        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        with patch(
            "app.desktop.git_sync.git_sync_api.exchange_code_for_token",
            side_effect=OAuthError("Exchange failed"),
        ):
            resp = api_client.get(
                f"/api/git_sync/oauth/callback?state={state}&code=bad_code",
            )
        assert resp.status_code == 400
        assert "Authorization Failed" in resp.text
        assert "Exchange failed" in resp.text


class TestOAuthInstalled:
    def test_returns_install_complete_page(self, api_client):
        resp = api_client.get("/api/git_sync/oauth/authorize")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Install Complete" in resp.text


class TestOAuthStatus:
    def test_pending(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        resp = api_client.get(f"/api/git_sync/oauth/status/{state}")
        data = resp.json()
        assert data["complete"] is False
        assert data["oauth_token"] is None

    def test_complete(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        with patch(
            "app.desktop.git_sync.git_sync_api.exchange_code_for_token",
            return_value="ghu_token",
        ):
            api_client.get(
                f"/api/git_sync/oauth/callback?state={state}&code=code",
            )

        resp = api_client.get(f"/api/git_sync/oauth/status/{state}")
        data = resp.json()
        assert data["complete"] is True
        assert data["oauth_token"] == "ghu_token"

    def test_consumed_flow_not_available_again(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_owner_id",
                return_value=None,
            ),
            patch(
                "app.desktop.git_sync.git_sync_api.resolve_github_repo_id",
                return_value=None,
            ),
        ):
            start_resp = api_client.post(
                "/api/git_sync/oauth/start",
                json={"git_url": "https://github.com/owner/repo.git"},
            )
        state = start_resp.json()["state"]

        with patch(
            "app.desktop.git_sync.git_sync_api.exchange_code_for_token",
            return_value="ghu_token",
        ):
            api_client.get(
                f"/api/git_sync/oauth/callback?state={state}&code=code",
            )

        api_client.get(f"/api/git_sync/oauth/status/{state}")
        resp = api_client.get(f"/api/git_sync/oauth/status/{state}")
        data = resp.json()
        assert data["complete"] is False
        assert data["error"] == "Session expired or not found."

    def test_nonexistent_state(self, api_client):
        resp = api_client.get("/api/git_sync/oauth/status/nonexistent")
        data = resp.json()
        assert data["complete"] is False
        assert data["error"] is not None


class TestOAuthTokenInConfig:
    def test_save_config_with_oauth_token(self, api_client, tmp_path):
        clone_dir = tmp_path / "kiln_clone_abc"
        clone_dir.mkdir()
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.default_project_path",
                return_value=str(tmp_path),
            ),
            patch("app.desktop.git_sync.git_sync_api.save_git_sync_config"),
            patch("app.desktop.git_sync.git_sync_api.add_project_to_config"),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": str(clone_dir),
                    "branch": "main",
                    "auth_mode": "github_oauth",
                    "oauth_token": "ghu_token",
                },
            )
        data = resp.json()
        assert data["auth_mode"] == "github_oauth"
        assert data["has_oauth_token"] is True
        assert "oauth_token" not in data

    def test_get_config_with_oauth_token(self, api_client):
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock,
        ):
            mock.return_value = {
                "sync_mode": "auto",
                "auth_mode": "github_oauth",
                "remote_name": "origin",
                "branch": "main",
                "clone_path": "/tmp/clone",
                "git_url": "https://github.com/test/repo.git",
                "pat_token": None,
                "oauth_token": "ghu_secret",
            }
            resp = api_client.get("/api/git_sync/config/proj1")
        data = resp.json()
        assert data["has_oauth_token"] is True
        assert data["has_pat_token"] is False
        assert "oauth_token" not in data

    def test_update_config_with_oauth_token(self, api_client):
        existing = {
            "sync_mode": "auto",
            "auth_mode": "pat_token",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://github.com/test/repo.git",
            "pat_token": "ghp_old",
            "oauth_token": None,
        }
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock_get,
            patch(
                "app.desktop.git_sync.git_sync_api.save_git_sync_config"
            ) as mock_save,
        ):
            mock_get.return_value = existing
            resp = api_client.patch(
                "/api/git_sync/update_config/proj1",
                json={
                    "oauth_token": "ghu_new",
                    "auth_mode": "github_oauth",
                },
            )
        data = resp.json()
        assert data["has_oauth_token"] is True
        assert data["has_pat_token"] is False
        assert data["auth_mode"] == "github_oauth"
        saved_config = mock_save.call_args[0][1]
        assert saved_config["pat_token"] is None
        assert saved_config["oauth_token"] == "ghu_new"

    def test_switch_from_oauth_to_pat_clears_oauth_token(self, api_client):
        existing = {
            "sync_mode": "auto",
            "auth_mode": "github_oauth",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://github.com/test/repo.git",
            "pat_token": None,
            "oauth_token": "ghu_old",
        }
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock_get,
            patch(
                "app.desktop.git_sync.git_sync_api.save_git_sync_config"
            ) as mock_save,
        ):
            mock_get.return_value = existing
            resp = api_client.patch(
                "/api/git_sync/update_config/proj1",
                json={
                    "pat_token": "ghp_new",
                    "auth_mode": "pat_token",
                },
            )
        data = resp.json()
        assert data["auth_mode"] == "pat_token"
        assert data["has_pat_token"] is True
        assert data["has_oauth_token"] is False
        saved_config = mock_save.call_args[0][1]
        assert saved_config["oauth_token"] is None
        assert saved_config["pat_token"] == "ghp_new"

    def test_switch_to_system_keys_clears_both_tokens(self, api_client):
        existing = {
            "sync_mode": "auto",
            "auth_mode": "github_oauth",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://github.com/test/repo.git",
            "pat_token": "ghp_stale",
            "oauth_token": "ghu_stale",
        }
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_path_from_id",
                return_value="/tmp/clone/project.kiln",
            ),
            patch("app.desktop.git_sync.git_sync_api.get_git_sync_config") as mock_get,
            patch(
                "app.desktop.git_sync.git_sync_api.save_git_sync_config"
            ) as mock_save,
        ):
            mock_get.return_value = existing
            resp = api_client.patch(
                "/api/git_sync/update_config/proj1",
                json={"auth_mode": "system_keys"},
            )
        data = resp.json()
        assert data["auth_mode"] == "system_keys"
        assert data["has_pat_token"] is False
        assert data["has_oauth_token"] is False
        saved_config = mock_save.call_args[0][1]
        assert saved_config["pat_token"] is None
        assert saved_config["oauth_token"] is None


class TestSaveConfigClonePathValidation:
    def test_rejects_clone_path_outside_project_directory(self, api_client, tmp_path):
        with patch(
            "app.desktop.git_sync.git_sync_api.default_project_path",
            return_value=str(tmp_path),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": "/some/arbitrary/path",
                    "branch": "main",
                    "auth_mode": "system_keys",
                },
            )
        assert resp.status_code == 400
        assert (
            "clone_path must be within the project directory" in resp.json()["detail"]
        )


class TestDeleteProject:
    def test_delete_project_success(self, api_client):
        mock_project = MagicMock(path="/path/to/project.kiln")
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_from_id",
                return_value=mock_project,
            ),
            patch.object(Config, "shared") as mock_config,
            patch(
                "app.desktop.git_sync.git_sync_api.GitSyncRegistry.unregister",
                new_callable=AsyncMock,
            ) as mock_unregister,
        ):
            mock_config.return_value.projects = [
                "/path/to/project.kiln",
                "/path/to/other_project.kiln",
            ]
            mock_config.return_value.git_sync_projects = None
            mock_config.return_value.save_setting = MagicMock()

            response = api_client.delete("/api/delete_project/test-id")

        assert response.status_code == 200
        assert response.json() == {"message": "Project removed. ID: test-id"}
        mock_config.return_value.save_setting.assert_called_once_with(
            "projects", ["/path/to/other_project.kiln"]
        )
        mock_unregister.assert_not_awaited()

    def test_delete_project_cleans_up_git_sync(self, api_client):
        mock_project = MagicMock(path="/path/to/project.kiln")
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_from_id",
                return_value=mock_project,
            ),
            patch.object(Config, "shared") as mock_config,
            patch(
                "app.desktop.git_sync.git_sync_api.GitSyncRegistry.unregister",
                new_callable=AsyncMock,
            ) as mock_unregister,
        ):
            mock_config.return_value.projects = [
                "/path/to/project.kiln",
                "/path/to/other_project.kiln",
            ]
            mock_config.return_value.git_sync_projects = {
                "/path/to/project.kiln": {
                    "sync_mode": "auto",
                    "branch": "main",
                    "clone_path": "/path/to/clone",
                },
                "/path/to/other_project.kiln": {
                    "sync_mode": "manual",
                    "branch": "dev",
                },
            }
            mock_config.return_value.save_setting = MagicMock()

            response = api_client.delete("/api/delete_project/test-id")

        assert response.status_code == 200
        assert response.json() == {"message": "Project removed. ID: test-id"}
        assert mock_config.return_value.save_setting.call_count == 2
        mock_config.return_value.save_setting.assert_any_call(
            "projects", ["/path/to/other_project.kiln"]
        )
        mock_config.return_value.save_setting.assert_any_call(
            "git_sync_projects",
            {"/path/to/other_project.kiln": {"sync_mode": "manual", "branch": "dev"}},
        )
        mock_unregister.assert_awaited_once_with(Path("/path/to/clone"))

    def test_delete_project_not_found(self, api_client):
        with patch(
            "app.desktop.git_sync.git_sync_api.project_from_id",
            side_effect=HTTPException(
                status_code=404, detail="Project not found. ID: non-existent-id"
            ),
        ):
            response = api_client.delete("/api/delete_project/non-existent-id")

        assert response.status_code == 404

    def test_delete_non_git_synced_project(self, api_client):
        mock_project = MagicMock(path="/path/to/project.kiln")
        with (
            patch(
                "app.desktop.git_sync.git_sync_api.project_from_id",
                return_value=mock_project,
            ),
            patch.object(Config, "shared") as mock_config,
            patch(
                "app.desktop.git_sync.git_sync_api.GitSyncRegistry.unregister",
                new_callable=AsyncMock,
            ) as mock_unregister,
        ):
            mock_config.return_value.projects = ["/path/to/project.kiln"]
            mock_config.return_value.git_sync_projects = {
                "/path/to/other.kiln": {"sync_mode": "auto", "branch": "main"},
            }
            mock_config.return_value.save_setting = MagicMock()

            response = api_client.delete("/api/delete_project/test-id")

        assert response.status_code == 200
        mock_config.return_value.save_setting.assert_called_once_with("projects", [])
        mock_unregister.assert_not_awaited()
