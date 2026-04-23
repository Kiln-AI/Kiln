import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.desktop.git_sync.background_sync import BackgroundSync
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.registry import GitSyncRegistry


def test_get_or_create_new(git_repos):
    local_path, _ = git_repos
    manager = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    assert isinstance(manager, GitSyncManager)


def test_get_or_create_returns_existing(git_repos):
    local_path, _ = git_repos
    m1 = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    m2 = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    assert m1 is m2


def test_get_manager_returns_none_for_unknown(tmp_path):
    assert GitSyncRegistry.get_manager(tmp_path / "nonexistent") is None


def test_register_and_get(git_repos):
    local_path, _ = git_repos
    manager = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
    GitSyncRegistry.register(local_path, manager)
    assert GitSyncRegistry.get_manager(local_path) is manager


def test_reset_clears_all(git_repos):
    local_path, _ = git_repos
    GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    assert GitSyncRegistry.get_manager(local_path) is not None

    GitSyncRegistry.reset()
    assert GitSyncRegistry.get_manager(local_path) is None


def test_get_or_create_clears_stale_tokens_on_subsequent_call(git_repos):
    local_path, _ = git_repos
    GitSyncRegistry.reset()
    m1 = GitSyncRegistry.get_or_create(
        local_path, auth_mode="pat_token", pat_token="ghp_stale"
    )
    assert m1._pat_token == "ghp_stale"
    assert m1._oauth_token is None
    assert m1._auth_mode == "pat_token"

    m2 = GitSyncRegistry.get_or_create(
        local_path,
        auth_mode="github_oauth",
        pat_token=None,
        oauth_token="ghu_fresh",
    )
    assert m1 is m2
    assert m2._pat_token is None
    assert m2._oauth_token == "ghu_fresh"
    assert m2._auth_mode == "github_oauth"


def test_thread_safety(git_repos):
    local_path, _ = git_repos
    results: list[GitSyncManager] = []
    barrier = threading.Barrier(4)

    def create():
        barrier.wait()
        results.append(
            GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
        )

    threads = [threading.Thread(target=create) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 4
    assert all(r is results[0] for r in results)


@pytest.mark.asyncio
async def test_unregister_stops_background_sync_and_removes_manager(git_repos):
    local_path, _ = git_repos
    manager = GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    assert GitSyncRegistry.get_manager(local_path) is manager

    bg_sync = MagicMock(spec=BackgroundSync)
    bg_sync.stop = AsyncMock()
    GitSyncRegistry.register_background_sync(local_path, bg_sync)

    await GitSyncRegistry.unregister(local_path)

    assert GitSyncRegistry.get_manager(local_path) is None
    assert GitSyncRegistry.get_background_sync(local_path) is None
    bg_sync.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_unregister_idempotent(git_repos):
    local_path, _ = git_repos
    GitSyncRegistry.get_or_create(local_path, auth_mode="system_keys")
    bg_sync = MagicMock(spec=BackgroundSync)
    bg_sync.stop = AsyncMock()
    GitSyncRegistry.register_background_sync(local_path, bg_sync)

    await GitSyncRegistry.unregister(local_path)
    await GitSyncRegistry.unregister(local_path)

    assert GitSyncRegistry.get_manager(local_path) is None


@pytest.mark.asyncio
async def test_unregister_unknown_path_is_noop(tmp_path):
    await GitSyncRegistry.unregister(tmp_path / "nonexistent")
