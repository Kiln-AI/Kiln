from pathlib import Path

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.git_sync_manager import (
    KILN_COMMITTER_EMAIL,
    KILN_COMMITTER_NAME,
)
from app.desktop.git_sync.registry import GitSyncRegistry

SIG = pygit2.Signature(KILN_COMMITTER_NAME, KILN_COMMITTER_EMAIL)


@pytest.fixture(autouse=True)
def reset_git_sync_registry():
    yield
    GitSyncRegistry.reset()


def _make_initial_commit(repo: pygit2.Repository, message: str = "init") -> pygit2.Oid:
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
    pygit2.clone_repository(str(remote_path), str(local_path))

    return local_path, remote_path
