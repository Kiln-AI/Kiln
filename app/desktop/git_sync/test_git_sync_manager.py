import asyncio
import time
from pathlib import Path

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.conftest import SIG, commit_in_repo, push_from
from app.desktop.git_sync.errors import (
    SyncConflictError,
    WriteLockTimeoutError,
)
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
    """A second clone of the same remote, for simulating concurrent pushes."""
    _, remote_path = git_repos
    second_path = tmp_path / "second_clone"
    pygit2.clone_repository(str(remote_path), str(second_path))
    return second_path


def _write_file(repo_path: Path, name: str, content: str = "test") -> Path:
    f = repo_path / name
    f.write_text(content)
    return f


# --- has_dirty_files ---


@pytest.mark.asyncio
async def test_has_dirty_files_clean(manager):
    assert await manager.has_dirty_files() is False


@pytest.mark.asyncio
async def test_has_dirty_files_modified(manager, git_repos):
    local_path, _ = git_repos
    _write_file(local_path, "README.md", "modified")
    assert await manager.has_dirty_files() is True


@pytest.mark.asyncio
async def test_has_dirty_files_untracked(manager, git_repos):
    local_path, _ = git_repos
    _write_file(local_path, "new_file.txt")
    assert await manager.has_dirty_files() is True


# --- get_head ---


@pytest.mark.asyncio
async def test_get_head(manager, git_repos):
    local_path, _ = git_repos
    repo = pygit2.Repository(str(local_path))
    expected = str(repo.head.target)
    assert await manager.get_head() == expected


# --- commit_and_push ---


@pytest.mark.asyncio
async def test_commit_and_push_success(manager, git_repos):
    local_path, remote_path = git_repos
    pre_head = await manager.get_head()

    _write_file(local_path, "data.txt", "hello")

    await manager.commit_and_push(
        api_path="POST /api/projects/123/tasks",
        pre_request_head=pre_head,
    )

    assert await manager.has_dirty_files() is False

    new_head = await manager.get_head()
    assert new_head != pre_head

    remote_repo = pygit2.Repository(str(remote_path))
    remote_commit = remote_repo.revparse_single("refs/heads/main")
    assert str(remote_commit.id) == new_head


@pytest.mark.asyncio
async def test_commit_and_push_conflict_retry_success(manager, git_repos, second_clone):
    local_path, remote_path = git_repos
    pre_head = await manager.get_head()

    commit_in_repo(second_clone, "other.txt", "from second", "second commit")
    push_from(second_clone)

    _write_file(local_path, "data.txt", "from first")

    await manager.commit_and_push(
        api_path="POST /api/projects/123/tasks",
        pre_request_head=pre_head,
    )

    assert await manager.has_dirty_files() is False

    remote_repo = pygit2.Repository(str(remote_path))
    log = list(
        remote_repo.walk(remote_repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL)
    )
    assert len(log) == 3


@pytest.mark.asyncio
async def test_commit_and_push_conflict_same_file(manager, git_repos, second_clone):
    local_path, _ = git_repos
    pre_head = await manager.get_head()

    commit_in_repo(second_clone, "README.md", "conflict from second", "second")
    push_from(second_clone)

    _write_file(local_path, "README.md", "conflict from first")

    with pytest.raises(SyncConflictError):
        await manager.commit_and_push(
            api_path="POST /api/test",
            pre_request_head=pre_head,
        )

    assert await manager.get_head() == pre_head


# --- rollback ---


@pytest.mark.asyncio
async def test_rollback_dirty_files(manager, git_repos):
    local_path, _ = git_repos
    pre_head = await manager.get_head()

    _write_file(local_path, "dirty.txt", "dirty")

    await manager.rollback(pre_head)

    assert await manager.has_dirty_files() is False
    assert await manager.get_head() == pre_head


@pytest.mark.asyncio
async def test_rollback_committed_not_pushed(manager, git_repos):
    local_path, _ = git_repos
    pre_head = await manager.get_head()

    _write_file(local_path, "committed.txt", "committed")
    repo = pygit2.Repository(str(local_path))
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    repo.create_commit(
        repo.head.name, SIG, SIG, "local commit", tree, [repo.head.target]
    )

    assert await manager.get_head() != pre_head

    await manager.rollback(pre_head)
    assert await manager.get_head() == pre_head


# --- ensure_clean ---


@pytest.mark.asyncio
async def test_ensure_clean_when_clean(manager):
    await manager.ensure_clean()


@pytest.mark.asyncio
async def test_ensure_clean_dirty_recovery(manager, git_repos):
    local_path, _ = git_repos
    _write_file(local_path, "crash_artifact.txt", "leftover")

    await manager.ensure_clean()

    assert await manager.has_dirty_files() is False


@pytest.mark.asyncio
async def test_ensure_clean_unpushed_commits(manager, git_repos):
    local_path, _ = git_repos
    pre_head = await manager.get_head()

    commit_in_repo(local_path, "unpushed.txt", "data", "unpushed commit")
    assert await manager.get_head() != pre_head

    _write_file(local_path, "crash_leftover.txt", "dirty from crash")

    await manager.ensure_clean()

    assert await manager.get_head() == pre_head
    assert await manager.has_dirty_files() is False


# --- ensure_fresh ---


@pytest.mark.asyncio
async def test_ensure_fresh_fetches_and_forwards(manager, git_repos, second_clone):
    local_path, _ = git_repos

    commit_in_repo(second_clone, "remote_file.txt", "from remote", "remote commit")
    push_from(second_clone)

    old_head = await manager.get_head()

    manager._last_sync = 0.0
    await manager.ensure_fresh()

    new_head = await manager.get_head()
    assert new_head != old_head

    local_file = local_path / "remote_file.txt"
    assert local_file.exists()
    assert local_file.read_text() == "from remote"


@pytest.mark.asyncio
async def test_ensure_fresh_skips_when_recent(manager):
    manager._last_sync = time.monotonic()
    old_head = await manager.get_head()
    await manager.ensure_fresh()
    assert await manager.get_head() == old_head


# --- ensure_fresh_for_read ---


@pytest.mark.asyncio
async def test_ensure_fresh_for_read_when_fresh(manager):
    manager._last_sync = time.monotonic()
    old_head = await manager.get_head()
    await manager.ensure_fresh_for_read()
    assert await manager.get_head() == old_head


@pytest.mark.asyncio
async def test_ensure_fresh_for_read_fetches_when_stale(
    manager, git_repos, second_clone
):
    local_path, _ = git_repos

    commit_in_repo(second_clone, "read_fresh.txt", "from remote", "remote commit")
    push_from(second_clone)

    old_head = await manager.get_head()
    manager._last_sync = 0.0

    await manager.ensure_fresh_for_read()

    new_head = await manager.get_head()
    assert new_head != old_head
    assert (local_path / "read_fresh.txt").exists()


@pytest.mark.asyncio
async def test_ensure_fresh_for_read_raises_when_unreachable(
    manager, git_repos, tmp_path
):
    """When stale and remote is unreachable, raises RemoteUnreachableError."""
    from app.desktop.git_sync.errors import RemoteUnreachableError

    manager._last_sync = 0.0

    def broken_fetch():
        raise pygit2.GitError("simulated network error")

    manager._fetch_sync = broken_fetch  # type: ignore[assignment]

    with pytest.raises(RemoteUnreachableError):
        await manager.ensure_fresh_for_read()


# --- fetch ---


@pytest.mark.asyncio
async def test_fetch(manager, git_repos, second_clone):
    _, remote_path = git_repos

    commit_in_repo(second_clone, "fetched.txt", "data", "remote")
    push_from(second_clone)

    old_head = await manager.get_head()
    await manager.fetch()

    assert await manager.get_head() == old_head
    assert await manager.has_new_remote_commits() is True


# --- can_fast_forward / fast_forward ---


@pytest.mark.asyncio
async def test_can_fast_forward_true(manager, git_repos, second_clone):
    commit_in_repo(second_clone, "ff.txt", "data", "ff commit")
    push_from(second_clone)

    await manager.fetch()
    assert await manager.can_fast_forward() is True


@pytest.mark.asyncio
async def test_can_fast_forward_false_when_up_to_date(manager):
    assert await manager.can_fast_forward() is False


@pytest.mark.asyncio
async def test_can_fast_forward_false_when_diverged(manager, git_repos, second_clone):
    local_path, _ = git_repos

    commit_in_repo(second_clone, "remote.txt", "remote", "remote")
    push_from(second_clone)

    commit_in_repo(local_path, "local.txt", "local", "local")

    await manager.fetch()
    assert await manager.can_fast_forward() is False


@pytest.mark.asyncio
async def test_fast_forward(manager, git_repos, second_clone):
    local_path, _ = git_repos

    commit_in_repo(second_clone, "ff_file.txt", "fast forward content", "ff")
    push_from(second_clone)

    await manager.fetch()
    assert await manager.can_fast_forward() is True

    await manager.fast_forward()

    ff_file = local_path / "ff_file.txt"
    assert ff_file.exists()
    assert ff_file.read_text() == "fast forward content"
    assert await manager.can_fast_forward() is False


# --- write_lock ---


@pytest.mark.asyncio
async def test_write_lock_timeout(manager):
    manager._WRITE_LOCK_TIMEOUT = 0.1
    manager._write_lock.acquire()

    try:
        with pytest.raises(WriteLockTimeoutError):
            async with manager.write_lock():
                pass
    finally:
        manager._write_lock.release()


@pytest.mark.asyncio
async def test_write_lock_serialization(manager):
    order = []

    async def task(label: str, delay: float):
        async with manager.write_lock():
            order.append(f"{label}_start")
            await asyncio.sleep(delay)
            order.append(f"{label}_end")

    await asyncio.gather(task("a", 0.1), task("b", 0.05))

    assert order[0] == "a_start"
    assert order[1] == "a_end"
    assert order[2] == "b_start"
    assert order[3] == "b_end"


# --- has_new_remote_commits ---


@pytest.mark.asyncio
async def test_has_new_remote_commits_false_when_up_to_date(manager):
    assert await manager.has_new_remote_commits() is False


@pytest.mark.asyncio
async def test_has_new_remote_commits_true(manager, git_repos, second_clone):
    commit_in_repo(second_clone, "new.txt", "data", "new commit")
    push_from(second_clone)

    await manager.fetch()
    assert await manager.has_new_remote_commits() is True


# --- close ---


@pytest.mark.asyncio
async def test_close(manager):
    await manager.close()
    assert manager._repo is None
    with pytest.raises(RuntimeError):
        manager._git_executor.submit(lambda: None)
