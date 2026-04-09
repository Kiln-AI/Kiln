import asyncio
import time
from pathlib import Path

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.errors import (
    SyncConflictError,
    WriteLockTimeoutError,
)
from app.desktop.git_sync.git_sync_manager import (
    KILN_COMMITTER_EMAIL,
    KILN_COMMITTER_NAME,
    GitSyncManager,
)

SIG = pygit2.Signature(KILN_COMMITTER_NAME, KILN_COMMITTER_EMAIL)


def _make_initial_commit(repo: pygit2.Repository, message: str = "init") -> pygit2.Oid:
    """Create an initial commit with a dummy file in the given repo."""
    blob_oid = repo.create_blob(b"initial content")
    tb = repo.TreeBuilder()
    tb.insert("README.md", blob_oid, pygit2.enums.FileMode.BLOB)
    tree = tb.write()
    return repo.create_commit("refs/heads/main", SIG, SIG, message, tree, [])


@pytest.fixture
def git_repos(tmp_path: Path):
    """Create a bare 'remote' repo and a cloned 'local' repo with an initial commit."""
    remote_path = tmp_path / "remote.git"
    remote_repo = pygit2.init_repository(str(remote_path), bare=True)

    _make_initial_commit(remote_repo, "Initial commit")

    remote_repo.set_head("refs/heads/main")

    local_path = tmp_path / "local"
    local_repo = pygit2.clone_repository(str(remote_path), str(local_path))

    local_repo.remotes.set_url("origin", str(remote_path))

    return local_path, remote_path


@pytest.fixture
def manager(git_repos):
    local_path, _ = git_repos
    mgr = GitSyncManager(repo_path=local_path)
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


def _commit_in_repo(
    repo_path: Path, filename: str, content: str, message: str
) -> pygit2.Oid:
    repo = pygit2.Repository(str(repo_path))
    filepath = repo_path / filename
    filepath.write_text(content)
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    parents = [repo.head.target]
    oid = repo.create_commit(repo.head.name, SIG, SIG, message, tree, parents)
    return oid


def _push_from(repo_path: Path) -> None:
    repo = pygit2.Repository(str(repo_path))
    remote = repo.remotes["origin"]
    branch = repo.head.shorthand
    remote.push([f"refs/heads/{branch}"])


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

    _commit_in_repo(second_clone, "other.txt", "from second", "second commit")
    _push_from(second_clone)

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

    _commit_in_repo(second_clone, "README.md", "conflict from second", "second")
    _push_from(second_clone)

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

    _commit_in_repo(local_path, "unpushed.txt", "data", "unpushed commit")
    assert await manager.get_head() != pre_head

    _write_file(local_path, "crash_leftover.txt", "dirty from crash")

    await manager.ensure_clean()

    assert await manager.get_head() == pre_head
    assert await manager.has_dirty_files() is False


# --- ensure_fresh ---


@pytest.mark.asyncio
async def test_ensure_fresh_fetches_and_forwards(manager, git_repos, second_clone):
    local_path, _ = git_repos

    _commit_in_repo(second_clone, "remote_file.txt", "from remote", "remote commit")
    _push_from(second_clone)

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


# --- fetch ---


@pytest.mark.asyncio
async def test_fetch(manager, git_repos, second_clone):
    _, remote_path = git_repos

    _commit_in_repo(second_clone, "fetched.txt", "data", "remote")
    _push_from(second_clone)

    old_head = await manager.get_head()
    await manager.fetch()

    assert await manager.get_head() == old_head
    assert await manager.has_new_remote_commits() is True


# --- can_fast_forward / fast_forward ---


@pytest.mark.asyncio
async def test_can_fast_forward_true(manager, git_repos, second_clone):
    _commit_in_repo(second_clone, "ff.txt", "data", "ff commit")
    _push_from(second_clone)

    await manager.fetch()
    assert await manager.can_fast_forward() is True


@pytest.mark.asyncio
async def test_can_fast_forward_false_when_up_to_date(manager):
    assert await manager.can_fast_forward() is False


@pytest.mark.asyncio
async def test_can_fast_forward_false_when_diverged(manager, git_repos, second_clone):
    local_path, _ = git_repos

    _commit_in_repo(second_clone, "remote.txt", "remote", "remote")
    _push_from(second_clone)

    _commit_in_repo(local_path, "local.txt", "local", "local")

    await manager.fetch()
    assert await manager.can_fast_forward() is False


@pytest.mark.asyncio
async def test_fast_forward(manager, git_repos, second_clone):
    local_path, _ = git_repos

    _commit_in_repo(second_clone, "ff_file.txt", "fast forward content", "ff")
    _push_from(second_clone)

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
    _commit_in_repo(second_clone, "new.txt", "data", "new commit")
    _push_from(second_clone)

    await manager.fetch()
    assert await manager.has_new_remote_commits() is True


# --- close ---


@pytest.mark.asyncio
async def test_close(manager):
    await manager.close()
    assert manager._repo is None
    with pytest.raises(RuntimeError):
        manager._git_executor.submit(lambda: None)
