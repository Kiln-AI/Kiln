from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.desktop.desktop_server import _start_background_syncs


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear the GitSyncRegistry between tests."""
    from app.desktop.git_sync.registry import GitSyncRegistry

    GitSyncRegistry._managers.clear()
    GitSyncRegistry._background_syncs.clear()
    yield
    GitSyncRegistry._managers.clear()
    GitSyncRegistry._background_syncs.clear()


def _make_config(
    *,
    pat_token: str | None = None,
    oauth_token: str | None = None,
    auth_mode: str = "system_keys",
) -> dict:
    return {
        "sync_mode": "auto",
        "auth_mode": auth_mode,
        "remote_name": "origin",
        "branch": "main",
        "clone_path": "/tmp/fake_clone",
        "git_url": "https://github.com/example/repo.git",
        "pat_token": pat_token,
        "oauth_token": oauth_token,
    }


@pytest.mark.asyncio
async def test_start_background_syncs_passes_oauth_token(tmp_path: Path):
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    project_config = _make_config(
        oauth_token="ghp_oauth_test_token",
        auth_mode="github_oauth",
    )
    project_config["clone_path"] = str(clone_dir)

    mock_manager = MagicMock()
    mock_bg_sync = MagicMock()
    mock_bg_sync.start = AsyncMock()

    with (
        patch("app.desktop.desktop_server.Config.shared") as mock_config_shared,
        patch(
            "app.desktop.desktop_server.get_git_sync_config",
            return_value=project_config,
        ),
        patch(
            "app.desktop.desktop_server.GitSyncRegistry.get_or_create",
            return_value=mock_manager,
        ) as mock_get_or_create,
        patch(
            "app.desktop.desktop_server.BackgroundSync",
            return_value=mock_bg_sync,
        ),
        patch(
            "app.desktop.desktop_server.GitSyncRegistry.register_background_sync",
        ),
    ):
        mock_config = MagicMock()
        mock_config.git_sync_projects = {"/some/project": {}}
        mock_config_shared.return_value = mock_config

        await _start_background_syncs()

        mock_get_or_create.assert_called_once_with(
            repo_path=clone_dir,
            remote_name="origin",
            pat_token=None,
            oauth_token="ghp_oauth_test_token",
            auth_mode="github_oauth",
        )


@pytest.mark.asyncio
async def test_start_background_syncs_passes_pat_token(tmp_path: Path):
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()

    project_config = _make_config(
        pat_token="ghp_pat_test_token",
        auth_mode="pat",
    )
    project_config["clone_path"] = str(clone_dir)

    mock_manager = MagicMock()
    mock_bg_sync = MagicMock()
    mock_bg_sync.start = AsyncMock()

    with (
        patch("app.desktop.desktop_server.Config.shared") as mock_config_shared,
        patch(
            "app.desktop.desktop_server.get_git_sync_config",
            return_value=project_config,
        ),
        patch(
            "app.desktop.desktop_server.GitSyncRegistry.get_or_create",
            return_value=mock_manager,
        ) as mock_get_or_create,
        patch(
            "app.desktop.desktop_server.BackgroundSync",
            return_value=mock_bg_sync,
        ),
        patch(
            "app.desktop.desktop_server.GitSyncRegistry.register_background_sync",
        ),
    ):
        mock_config = MagicMock()
        mock_config.git_sync_projects = {"/some/project": {}}
        mock_config_shared.return_value = mock_config

        await _start_background_syncs()

        mock_get_or_create.assert_called_once_with(
            repo_path=clone_dir,
            remote_name="origin",
            pat_token="ghp_pat_test_token",
            oauth_token=None,
            auth_mode="pat",
        )
