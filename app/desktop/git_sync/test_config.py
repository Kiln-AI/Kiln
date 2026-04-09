from unittest.mock import patch

from app.desktop.git_sync.config import (
    GitSyncProjectConfig,
    delete_git_sync_config,
    get_git_sync_config,
    save_git_sync_config,
)


def test_get_git_sync_config_returns_config():
    mock_projects = {
        "proj_123": {
            "sync_mode": "auto",
            "remote_name": "upstream",
            "branch": "develop",
            "clone_path": "/tmp/clone",
        }
    }

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = mock_projects
        result = get_git_sync_config("proj_123")

    assert result is not None
    assert result["sync_mode"] == "auto"
    assert result["remote_name"] == "upstream"
    assert result["branch"] == "develop"
    assert result["clone_path"] == "/tmp/clone"


def test_get_git_sync_config_returns_none_for_missing_project():
    mock_projects = {"other_project": {"sync_mode": "auto"}}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = mock_projects
        result = get_git_sync_config("nonexistent")

    assert result is None


def test_get_git_sync_config_returns_none_when_no_projects():
    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = None
        result = get_git_sync_config("proj_123")

    assert result is None


def test_get_git_sync_config_uses_defaults():
    mock_projects = {"proj_456": {}}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = mock_projects
        result = get_git_sync_config("proj_456")

    assert result is not None
    assert result["sync_mode"] == "manual"
    assert result["auth_mode"] == "system_keys"
    assert result["remote_name"] == "origin"
    assert result["branch"] == "main"
    assert result["clone_path"] is None


def test_get_git_sync_config_includes_new_fields():
    mock_projects = {
        "proj_789": {
            "sync_mode": "auto",
            "remote_name": "origin",
            "branch": "main",
            "clone_path": "/tmp/clone",
            "git_url": "https://github.com/test/repo.git",
            "pat_token": "ghp_secret",
        }
    }

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = mock_projects
        result = get_git_sync_config("proj_789")

    assert result is not None
    assert result["git_url"] == "https://github.com/test/repo.git"
    assert result["pat_token"] == "ghp_secret"


def test_get_git_sync_config_defaults_new_fields():
    mock_projects = {"proj_456": {}}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        mock_shared.return_value.git_sync_projects = mock_projects
        result = get_git_sync_config("proj_456")

    assert result is not None
    assert result["git_url"] is None
    assert result["pat_token"] is None


def test_save_git_sync_config():
    mock_raw = {}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        instance = mock_shared.return_value
        instance.git_sync_projects = mock_raw
        config = GitSyncProjectConfig(
            sync_mode="auto",
            auth_mode="system_keys",
            remote_name="origin",
            branch="main",
            clone_path="/tmp/clone",
            git_url="https://github.com/test/repo.git",
            pat_token="ghp_test",
        )
        save_git_sync_config("proj_new", config)

        # save_git_sync_config sets config.git_sync_projects = updated_dict
        # The mock captures this as a property assignment
        # Verify via the mock's attribute setting
        saved_value = instance.git_sync_projects
        assert "proj_new" in saved_value
        assert saved_value["proj_new"]["sync_mode"] == "auto"


def test_delete_git_sync_config():
    mock_raw = {"proj_del": {"sync_mode": "auto"}}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        instance = mock_shared.return_value
        instance.git_sync_projects = mock_raw
        delete_git_sync_config("proj_del")

    assert "proj_del" not in mock_raw


def test_delete_nonexistent_config():
    mock_raw = {}

    with patch("app.desktop.git_sync.config.Config.shared") as mock_shared:
        instance = mock_shared.return_value
        instance.git_sync_projects = mock_raw
        delete_git_sync_config("nonexistent")

    assert mock_raw == {}


def test_git_sync_project_config_type():
    config = GitSyncProjectConfig(
        sync_mode="auto",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=None,
        git_url=None,
        pat_token=None,
    )
    assert config["sync_mode"] == "auto"
    assert config["clone_path"] is None
