import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
            "https://github.com/private/repo.git", "ghp_test123"
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
                "app.desktop.git_sync.git_sync_api.compute_clone_path"
            ) as mock_compute,
        ):
            mock_path.return_value = str(tmp_path)
            expected_clone = tmp_path / ".git-projects" / "id - proj"
            mock_compute.return_value = expected_clone
            mock_clone.return_value = MagicMock()

            resp = api_client.post(
                "/api/git_sync/clone",
                json={
                    "git_url": "https://github.com/test/repo.git",
                    "branch": "main",
                    "project_name": "proj",
                    "project_id": "id",
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
                "app.desktop.git_sync.git_sync_api.compute_clone_path"
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


class TestTestWriteAccess:
    def test_success(self, api_client, tmp_path):
        with patch("app.desktop.git_sync.git_sync_api.test_write_access") as mock:
            mock.return_value = (True, "Write access confirmed")
            resp = api_client.post(
                "/api/git_sync/test_write_access",
                json={"clone_path": str(tmp_path)},
            )
        data = resp.json()
        assert data["success"] is True


class TestScanProjects:
    def test_finds_projects(self, api_client, tmp_path):
        project_data = {"name": "Test", "description": "desc", "id": "proj_abc"}
        (tmp_path / "project.kiln").write_text(json.dumps(project_data))

        resp = api_client.post(
            "/api/git_sync/scan_projects",
            json={"clone_path": str(tmp_path)},
        )
        data = resp.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "Test"
        assert data["projects"][0]["id"] == "proj_abc"

    def test_no_projects(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/git_sync/scan_projects",
            json={"clone_path": str(tmp_path)},
        )
        assert resp.json()["projects"] == []

    def test_invalid_path(self, api_client):
        resp = api_client.post(
            "/api/git_sync/scan_projects",
            json={"clone_path": "/nonexistent/path"},
        )
        assert resp.status_code == 400


class TestSaveAndGetConfig:
    def test_save_and_retrieve(self, api_client):
        with (
            patch("app.desktop.git_sync.git_sync_api.save_git_sync_config"),
            patch("app.desktop.git_sync.git_sync_api.add_project_to_config"),
        ):
            resp = api_client.post(
                "/api/git_sync/save_config",
                json={
                    "project_id": "proj1",
                    "project_path": "project.kiln",
                    "git_url": "https://github.com/test/repo.git",
                    "clone_path": "/tmp/clone",
                    "branch": "main",
                    "pat_token": "ghp_test",
                },
            )
        data = resp.json()
        assert data["sync_mode"] == "auto"
        assert data["has_pat_token"] is True
        assert "pat_token" not in data

    def test_save_adds_project_to_config(self, api_client):
        with (
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
                    "clone_path": "/tmp/clone",
                    "branch": "main",
                },
            )
        assert resp.status_code == 200
        mock_save.assert_called_once()
        saved_key = mock_save.call_args[0][0]
        assert saved_key == "/tmp/clone/subdir/project.kiln"
        mock_add.assert_called_once_with("/tmp/clone/subdir/project.kiln")

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
            resp = api_client.post(
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
            resp = api_client.post(
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
            resp = api_client.post(
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
            resp = api_client.post(
                "/api/git_sync/update_config/nonexistent",
                json={"sync_mode": "manual"},
            )
        assert resp.status_code == 404


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
