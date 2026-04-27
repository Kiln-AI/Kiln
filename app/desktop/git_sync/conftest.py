from pathlib import Path

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.git_sync_manager import (
    get_committer_email,
    get_committer_name,
)
from app.desktop.git_sync.registry import GitSyncRegistry


def _test_sig() -> pygit2.Signature:
    return pygit2.Signature(get_committer_name(), get_committer_email())


@pytest.fixture(autouse=True)
def reset_git_sync_registry():
    yield
    GitSyncRegistry.reset()


def _make_initial_commit(repo: pygit2.Repository, message: str = "init") -> pygit2.Oid:
    blob_oid = repo.create_blob(b"initial content")
    tb = repo.TreeBuilder()
    tb.insert("README.md", blob_oid, pygit2.enums.FileMode.BLOB)
    tree = tb.write()
    return repo.create_commit(
        "refs/heads/main", _test_sig(), _test_sig(), message, tree, []
    )


@pytest.fixture
def git_repos(tmp_path: Path):
    """Create a bare 'remote' repo and a cloned 'local' repo with an initial commit."""
    remote_path = tmp_path / "remote.git"
    remote_repo = pygit2.init_repository(str(remote_path), bare=True)
    _make_initial_commit(remote_repo, "Initial commit")
    remote_repo.set_head("refs/heads/main")

    local_path = tmp_path / "local"
    pygit2.clone_repository(str(remote_path), str(local_path))

    return local_path, remote_path


def commit_in_repo(
    repo_path: Path, filename: str, content: str, message: str
) -> pygit2.Oid:
    """Create a commit adding/updating a file in the given repo."""
    repo = pygit2.Repository(str(repo_path))
    filepath = repo_path / filename
    filepath.write_text(content)
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    parents = [repo.head.target]
    return repo.create_commit(
        repo.head.name, _test_sig(), _test_sig(), message, tree, parents
    )


def delete_in_repo(repo_path: Path, filename: str, message: str) -> pygit2.Oid:
    """Create a commit that deletes a file in the given repo."""
    repo = pygit2.Repository(str(repo_path))
    filepath = repo_path / filename
    filepath.unlink()
    index = repo.index
    index.remove(filename)
    index.add_all()
    index.write()
    tree = index.write_tree()
    parents = [repo.head.target]
    return repo.create_commit(
        repo.head.name, _test_sig(), _test_sig(), message, tree, parents
    )


def push_from(repo_path: Path) -> None:
    """Push the current branch of the repo at repo_path to origin."""
    repo = pygit2.Repository(str(repo_path))
    remote = repo.remotes["origin"]
    branch = repo.head.shorthand
    remote.push([f"refs/heads/{branch}"])
