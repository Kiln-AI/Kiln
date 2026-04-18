"""File operation integration tests for git auto-sync.

Scenarios 32-33, 42-43: file deletions, .gitignore behavior,
mixed create+delete, and net-zero write operations.
"""

import os

import pygit2
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_commit_contains_files,
    assert_remote_has_commit,
    get_commit_count,
    get_head_sync,
)


class TestFileDeletion:
    """Scenario 32: File deletions are committed and pushed."""

    @pytest.mark.asyncio
    async def test_file_deletion_committed(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        commit_in_repo(local_path, "to_delete.kiln", "will be deleted", "add file")
        push_from(local_path)

        assert (local_path / "to_delete.kiln").exists()

        def delete_file(p):
            os.remove(p / "to_delete.kiln")

        result = await write_ctx.do_write(delete_file)

        assert result.committed
        assert result.pushed
        assert not (local_path / "to_delete.kiln").exists()

        post_head = get_head_sync(local_path)
        assert_commit_contains_files(local_path, post_head, ["to_delete.kiln"])
        assert_remote_has_commit(remote_path, post_head)

        remote_repo = pygit2.Repository(str(remote_path))
        remote_head = remote_repo.revparse_single("HEAD")
        assert isinstance(remote_head, pygit2.Commit)
        tree = remote_head.peel(pygit2.Tree)
        assert "to_delete.kiln" not in [e.name for e in tree]


class TestGitignoreFiles:
    """Scenario 33: Files matching .gitignore are NOT committed (known gap)."""

    @pytest.mark.asyncio
    async def test_gitignore_files_not_committed(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        commit_in_repo(local_path, ".gitignore", "*.tmp\n", "add gitignore")
        push_from(local_path)

        pre_count = get_commit_count(local_path)

        result = await write_ctx.do_write(
            lambda p: (p / "ignored_file.tmp").write_text("should be ignored")
        )

        assert not result.committed
        assert not result.pushed
        assert get_commit_count(local_path) == pre_count
        assert (local_path / "ignored_file.tmp").exists()


class TestMixedCreateAndDelete:
    """Scenario 42: Creates and deletes in same request produce single commit."""

    @pytest.mark.asyncio
    async def test_create_and_delete_atomic(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        commit_in_repo(local_path, "old_file.kiln", "old content", "add old file")
        push_from(local_path)

        def mixed_ops(p):
            os.remove(p / "old_file.kiln")
            (p / "new_file.kiln").write_text("new content")

        pre_count = get_commit_count(local_path)
        result = await write_ctx.do_write(mixed_ops)

        assert result.committed
        assert result.pushed
        assert get_commit_count(local_path) == pre_count + 1

        assert not (local_path / "old_file.kiln").exists()
        assert (local_path / "new_file.kiln").exists()

        post_head = get_head_sync(local_path)
        assert_remote_has_commit(remote_path, post_head)
        assert_commit_contains_files(
            local_path, post_head, ["old_file.kiln", "new_file.kiln"]
        )
        assert_clean_working_tree(local_path)


class TestNetZeroWrite:
    """Scenario 43: Create then delete in same request produces no commit."""

    @pytest.mark.asyncio
    async def test_net_zero_no_commit(self, write_ctx, git_repos):
        local_path, _ = git_repos

        def create_and_delete(p):
            temp = p / "temp_artifact.txt"
            temp.write_text("temporary")
            os.remove(temp)

        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        result = await write_ctx.do_write(create_and_delete)

        assert not result.committed
        assert not result.pushed
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count
