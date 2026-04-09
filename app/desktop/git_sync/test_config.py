from unittest.mock import patch

from app.desktop.git_sync.config import GitSyncProjectConfig, get_git_sync_config


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
    assert result["remote_name"] == "origin"
    assert result["branch"] == "main"
    assert result["clone_path"] is None


def test_git_sync_project_config_type():
    config = GitSyncProjectConfig(
        sync_mode="auto",
        remote_name="origin",
        branch="main",
        clone_path=None,
    )
    assert config["sync_mode"] == "auto"
    assert config["clone_path"] is None
