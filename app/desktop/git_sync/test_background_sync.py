import asyncio
from pathlib import Path

import pygit2
import pytest

from app.desktop.git_sync.background_sync import BackgroundSync
from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager


@pytest.fixture
def manager(git_repos):
    local_path, _ = git_repos
    mgr = GitSyncManager(repo_path=local_path, auth_mode="system_keys")
    yield mgr
    mgr._git_executor.shutdown(wait=True)
    if mgr._repo is not None:
        mgr._repo.free()
        mgr._repo = None


@pytest.fixture
def second_clone(git_repos, tmp_path: Path):
    _, remote_path = git_repos
    second_path = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_path))
    return second_path


@pytest.mark.asyncio
async def test_poll_loop_fetches_and_fast_forwards(manager, git_repos, second_clone):
    local_path, _ = git_repos

    commit_in_repo(second_clone, "bg_file.txt", "from remote", "remote commit")
    push_from(second_clone)

    old_head = await manager.get_head()

    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    try:
        await asyncio.sleep(0.3)
    finally:
        await bg.stop()

    new_head = await manager.get_head()
    assert new_head != old_head

    assert (local_path / "bg_file.txt").exists()
    assert (local_path / "bg_file.txt").read_text() == "from remote"


@pytest.mark.asyncio
async def test_poll_loop_no_new_commits_no_fast_forward(manager):
    old_head = await manager.get_head()

    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        await bg.stop()

    assert await manager.get_head() == old_head


@pytest.mark.asyncio
async def test_idle_pause_and_resume(manager, git_repos, second_clone):
    local_path, _ = git_repos

    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=0.1)
    await bg.start()

    await asyncio.sleep(0.3)

    commit_in_repo(second_clone, "after_idle.txt", "data", "after idle")
    push_from(second_clone)

    old_head = await manager.get_head()
    assert not (local_path / "after_idle.txt").exists()

    bg.notify_request()
    await asyncio.sleep(0.3)

    await bg.stop()

    new_head = await manager.get_head()
    assert new_head != old_head
    assert (local_path / "after_idle.txt").exists()


@pytest.mark.asyncio
async def test_stop_cancels_task(manager):
    bg = BackgroundSync(manager, poll_interval=0.05)
    await bg.start()
    assert bg._task is not None
    assert not bg._task.done()

    await bg.stop()
    assert bg._task is None


@pytest.mark.asyncio
async def test_start_is_idempotent(manager):
    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    first_task = bg._task
    assert first_task is not None

    await bg.start()
    assert bg._task is first_task

    await bg.stop()


@pytest.mark.asyncio
async def test_start_stop_start_cycle(manager):
    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    first_task = bg._task
    assert first_task is not None

    await bg.stop()
    assert bg._task is None

    await bg.start()
    second_task = bg._task
    assert second_task is not None
    assert second_task is not first_task

    await bg.stop()


@pytest.mark.asyncio
async def test_fast_forward_skipped_when_not_ff_able(manager, git_repos, second_clone):
    """When local has diverged (unpushed commits), background sync skips fast-forward."""
    local_path, _ = git_repos

    commit_in_repo(second_clone, "remote.txt", "remote", "remote")
    push_from(second_clone)

    commit_in_repo(local_path, "local.txt", "local", "local")

    old_head = await manager.get_head()

    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    try:
        await asyncio.sleep(0.3)
    finally:
        await bg.stop()

    assert await manager.get_head() == old_head


@pytest.mark.asyncio
async def test_fetch_failure_logs_and_retries(manager, git_repos, second_clone, caplog):
    """Network error during fetch logs warning, next cycle retries successfully."""
    local_path, remote_path = git_repos

    commit_in_repo(second_clone, "retry_file.txt", "data", "retry commit")
    push_from(second_clone)

    call_count = 0
    original_fetch = manager._fetch_sync

    def flaky_fetch():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise pygit2.GitError("simulated network error")
        return original_fetch()

    manager._fetch_sync = flaky_fetch  # type: ignore[assignment]

    bg = BackgroundSync(manager, poll_interval=0.05, idle_pause_after=60.0)
    await bg.start()
    try:
        await asyncio.sleep(0.4)
    finally:
        await bg.stop()

    assert call_count >= 2
    assert (local_path / "retry_file.txt").exists()
