"""Happy path integration tests for git auto-sync.

Scenarios 1-5: write/commit/push, read passthrough, no-op write,
multi-file atomic commit, arbitrary disk writes captured.
"""

import pygit2
import pytest

from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_commit_contains_files,
    assert_remote_has_commit,
    get_commit_count,
    get_head_sync,
)


class TestWriteCommitPush:
    """Scenario 1: A mutating request writes files, commits, and pushes."""

    @pytest.mark.asyncio
    async def test_write_commit_push(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        pre_head = get_head_sync(local_path)
        result = await write_ctx.do_write(
            lambda p: (p / "data.kiln").write_text('{"key": "value"}')
        )

        assert result.committed
        assert result.pushed
        post_head = get_head_sync(local_path)
        assert post_head != pre_head
        assert_remote_has_commit(remote_path, post_head)
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_api_commit_message_contains_path(self, api_ctx, git_repos):
        """API mode: commit message includes API path and file count."""
        local_path, _ = git_repos

        await api_ctx.do_write(lambda p: (p / "msg_test.kiln").write_text("test"))

        repo = pygit2.Repository(str(local_path))
        head_commit = repo.revparse_single("HEAD")
        assert isinstance(head_commit, pygit2.Commit)
        assert "1 file" in head_commit.message
        assert "POST" in head_commit.message
        assert "test_write" in head_commit.message


class TestReadPassesThrough:
    """Scenario 2: GET/HEAD requests do not commit."""

    @pytest.mark.asyncio
    async def test_read_no_commit(self, api_ctx, git_repos):
        local_path, _ = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        result = await api_ctx.do_read()

        assert result.status_code == 200
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count


class TestNoOpWrite:
    """Scenario 3: A mutating request with no file changes produces no commit."""

    @pytest.mark.asyncio
    async def test_no_op_write_no_commit(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        result = await write_ctx.do_write(lambda p: None)

        assert not result.committed
        assert not result.pushed
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count


class TestMultiFileAtomicCommit:
    """Scenario 4: Multiple file changes are committed atomically."""

    @pytest.mark.asyncio
    async def test_multi_file_single_commit(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        def write_multiple(p):
            (p / "file_a.kiln").write_text("a")
            (p / "file_b.kiln").write_text("b")
            (p / "file_c.kiln").write_text("c")

        pre_count = get_commit_count(local_path)
        result = await write_ctx.do_write(write_multiple)

        assert result.committed
        assert result.pushed
        assert get_commit_count(local_path) == pre_count + 1

        post_head = get_head_sync(local_path)
        assert_commit_contains_files(
            local_path, post_head, ["file_a.kiln", "file_b.kiln", "file_c.kiln"]
        )
        assert_remote_has_commit(remote_path, post_head)


class TestArbitraryDiskWrites:
    """Scenario 5: Files written directly to disk are captured by git."""

    @pytest.mark.asyncio
    async def test_arbitrary_file_captured(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        result = await write_ctx.do_write(
            lambda p: (p / "random_notes.txt").write_text("not from data model")
        )

        assert result.committed
        assert result.pushed
        post_head = get_head_sync(local_path)
        assert_commit_contains_files(local_path, post_head, ["random_notes.txt"])
        assert_remote_has_commit(remote_path, post_head)
