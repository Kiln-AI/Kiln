from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.desktop.git_sync.config import GitSyncProjectConfig
from app.desktop.git_sync.save_context import (
    get_manager_for_project,
    save_context_for_project,
)

PROJECT_ID = "project_abc"
PROJECT_PATH = "/tmp/test/project.kiln"
CLONE_PATH = "/tmp/test/clone"


def _auto_config(clone_path: str | None = CLONE_PATH) -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="auto",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=clone_path,
        git_url=None,
        pat_token=None,
        oauth_token=None,
    )


def _manual_config() -> GitSyncProjectConfig:
    return GitSyncProjectConfig(
        sync_mode="manual",
        auth_mode="system_keys",
        remote_name="origin",
        branch="main",
        clone_path=CLONE_PATH,
        git_url=None,
        pat_token=None,
        oauth_token=None,
    )


class _FakeManager:
    """Minimal AtomicWriteCapable stand-in that records atomic_write calls."""

    def __init__(self, repo_path: Path = Path(CLONE_PATH)):
        self.repo_path = repo_path
        self.calls: list[str] = []
        self.entered = False

    @asynccontextmanager
    async def atomic_write(self, context: str):
        self.calls.append(context)
        self.entered = True
        yield


def _patch_resolution(project_path, config, manager=None, bg_sync=None):
    """Patch the config + registry calls used by the helper.

    project_path_from_id and get_git_sync_config are looked up in the
    save_context module namespace, so patch them there.
    """
    stack = ExitStack()
    stack.enter_context(
        patch(
            "app.desktop.git_sync.save_context.project_path_from_id",
            return_value=project_path,
        )
    )
    stack.enter_context(
        patch(
            "app.desktop.git_sync.save_context.get_git_sync_config",
            return_value=config,
        )
    )
    stack.enter_context(
        patch(
            "app.desktop.git_sync.save_context.GitSyncRegistry.get_or_create",
            return_value=manager,
        )
    )
    stack.enter_context(
        patch(
            "app.desktop.git_sync.save_context.GitSyncRegistry.get_background_sync",
            return_value=bg_sync,
        )
    )
    return stack


# -- None branches -----------------------------------------------------------


def test_returns_none_when_no_project_path():
    with _patch_resolution(project_path=None, config=None):
        assert save_context_for_project(PROJECT_ID, context="ctx") is None
        assert get_manager_for_project(PROJECT_ID) is None


def test_returns_none_when_no_git_sync_config():
    with _patch_resolution(project_path=PROJECT_PATH, config=None):
        assert save_context_for_project(PROJECT_ID, context="ctx") is None
        assert get_manager_for_project(PROJECT_ID) is None


def test_returns_none_when_sync_mode_not_auto():
    with _patch_resolution(project_path=PROJECT_PATH, config=_manual_config()):
        assert save_context_for_project(PROJECT_ID, context="ctx") is None
        assert get_manager_for_project(PROJECT_ID) is None


def test_returns_none_when_clone_path_missing():
    with _patch_resolution(
        project_path=PROJECT_PATH, config=_auto_config(clone_path=None)
    ):
        assert save_context_for_project(PROJECT_ID, context="ctx") is None
        assert get_manager_for_project(PROJECT_ID) is None


# -- active branches ---------------------------------------------------------


def test_get_manager_uses_registry_with_config_values():
    manager = _FakeManager()
    with (
        patch(
            "app.desktop.git_sync.save_context.project_path_from_id",
            return_value=PROJECT_PATH,
        ),
        patch(
            "app.desktop.git_sync.save_context.get_git_sync_config",
            return_value=_auto_config(),
        ),
        patch(
            "app.desktop.git_sync.save_context.GitSyncRegistry.get_or_create",
            return_value=manager,
        ) as mock_get_or_create,
    ):
        result = get_manager_for_project(PROJECT_ID)

    assert result is manager
    mock_get_or_create.assert_called_once_with(
        repo_path=Path(CLONE_PATH),
        remote_name="origin",
        pat_token=None,
        oauth_token=None,
        auth_mode="system_keys",
    )


async def test_save_context_enters_atomic_write_with_label():
    manager = _FakeManager()
    with _patch_resolution(
        project_path=PROJECT_PATH, config=_auto_config(), manager=manager
    ):
        save_context = save_context_for_project(PROJECT_ID, context="eval job e1/r1")

    assert save_context is not None
    assert manager.entered is False  # built lazily, not yet entered

    async with save_context():
        pass

    assert manager.calls == ["eval job e1/r1"]


def test_save_context_notifies_background_sync():
    manager = _FakeManager()
    bg_sync = MagicMock()
    with _patch_resolution(
        project_path=PROJECT_PATH,
        config=_auto_config(),
        manager=manager,
        bg_sync=bg_sync,
    ):
        save_context = save_context_for_project(PROJECT_ID, context="ctx")

    assert save_context is not None
    bg_sync.notify_request.assert_called_once()


def test_save_context_no_background_sync_is_fine():
    manager = _FakeManager()
    with _patch_resolution(
        project_path=PROJECT_PATH,
        config=_auto_config(),
        manager=manager,
        bg_sync=None,
    ):
        save_context = save_context_for_project(PROJECT_ID, context="ctx")

    assert save_context is not None


# -- error propagation -------------------------------------------------------


def test_propagates_when_config_lookup_raises():
    # A corrupt/raising config lookup must surface (failing the job) rather than
    # be swallowed to None, which would silently skip commits for an auto-sync
    # project — the very bug this resolver exists to prevent.
    with (
        patch(
            "app.desktop.git_sync.save_context.project_path_from_id",
            return_value=PROJECT_PATH,
        ),
        patch(
            "app.desktop.git_sync.save_context.get_git_sync_config",
            side_effect=RuntimeError("corrupt config"),
        ),
    ):
        with pytest.raises(RuntimeError, match="corrupt config"):
            get_manager_for_project(PROJECT_ID)
        with pytest.raises(RuntimeError, match="corrupt config"):
            save_context_for_project(PROJECT_ID, context="ctx")
