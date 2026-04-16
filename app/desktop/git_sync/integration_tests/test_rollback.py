"""Rollback integration tests for git auto-sync.

Scenarios 6-7, 34: handler error rollback, push failure rollback,
and rebase-then-fail reflog recovery.
"""

from unittest.mock import patch

import pygit2
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_reflog_contains_commit_with_file,
    assert_stash_contains,
    get_commit_count,
    get_head_sync,
    get_stash_list,
)


class TestRollbackOnHandlerError:
    """Scenario 6: Handler raises exception -> changes rolled back, stashed."""

    @pytest.mark.asyncio
    async def test_handler_error_no_commit(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        def write_then_crash(p):
            (p / "doomed.txt").write_text("this will be rolled back")
            raise ValueError("handler exploded")

        result = await write_ctx.do_write(write_then_crash, expect_error=True)

        assert not result.committed
        assert not result.pushed
        assert result.error is not None
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_handler_error_stashes_dirty_files(self, write_ctx, git_repos):
        local_path, _ = git_repos
        pre_stash_count = len(get_stash_list(local_path))

        def write_then_crash(p):
            (p / "important_data.txt").write_text("must not be lost")
            raise RuntimeError("crash!")

        await write_ctx.do_write(write_then_crash, expect_error=True)

        stashes = get_stash_list(local_path)
        assert len(stashes) > pre_stash_count
        assert_stash_contains(local_path, "Kiln")
        assert_clean_working_tree(local_path)

        repo = pygit2.Repository(str(local_path))
        stash_commit = repo.get(repo.listall_stashes()[0].commit_id)
        assert isinstance(stash_commit, pygit2.Commit)
        untracked_tree = stash_commit.parents[2].tree
        blob = repo[untracked_tree["important_data.txt"].id]
        assert blob.data == b"must not be lost"

    @pytest.mark.asyncio
    async def test_handler_error_api_returns_error(self, api_ctx, git_repos):
        """API mode: error response returned to client."""
        local_path, _ = git_repos

        def write_then_crash(p):
            (p / "doomed.txt").write_text("gone")
            raise ValueError("handler exploded")

        result = await api_ctx.do_write(write_then_crash, expect_error=True)
        assert result.status_code is not None
        assert result.status_code >= 400

    @pytest.mark.asyncio
    async def test_next_write_succeeds_after_error(self, write_ctx, git_repos):
        """System recovers and next request works normally."""
        local_path, remote_path = git_repos

        def crashing_write(p):
            (p / "crash.txt").write_text("boom")
            raise RuntimeError("fail")

        await write_ctx.do_write(crashing_write, expect_error=True)

        result = await write_ctx.do_write(
            lambda p: (p / "recovery.txt").write_text("works again")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)


class TestRollbackOnPushFailure:
    """Scenario 7: Push fails on both attempts -> rollback + stash."""

    @pytest.mark.asyncio
    async def test_push_failure_rolls_back(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)

        def failing_push(self):
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", failing_push):
            result = await write_ctx.do_write(
                lambda p: (p / "will_fail.txt").write_text("push will fail"),
                expect_error=True,
            )

        assert not result.pushed
        assert get_head_sync(local_path) == pre_head
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_push_failure_preserves_changes_in_reflog(self, write_ctx, git_repos):
        """Changes are recoverable via reflog after push failure rollback.

        After commit + failed push, rollback resets HEAD. The working tree
        is clean post-commit so there's nothing to stash — the changes
        live in the reflog of the reset.
        """
        local_path, _ = git_repos

        def failing_push(self):
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", failing_push):
            await write_ctx.do_write(
                lambda p: (p / "stashed_data.txt").write_text("preserve me"),
                expect_error=True,
            )

        # Spec says "dirty state stashed (recoverable)" but after a successful
        # commit the working tree is already clean, so there is nothing to stash.
        # The committed changes are instead recoverable via the reflog entry
        # created by the reset that rolls back HEAD.
        assert len(get_stash_list(local_path)) == 0
        assert_reflog_contains_commit_with_file(local_path, "stashed_data.txt")

    @pytest.mark.asyncio
    async def test_push_failure_api_returns_409(self, api_ctx, git_repos):
        """API mode: push failure returns 409 conflict."""
        local_path, _ = git_repos

        def failing_push(self):
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", failing_push):
            result = await api_ctx.do_write(
                lambda p: (p / "conflict.txt").write_text("conflict data"),
                expect_error=True,
            )

        assert result.status_code == 409

    @pytest.mark.asyncio
    async def test_next_write_succeeds_after_push_failure(self, write_ctx, git_repos):
        """System recovers after push failure."""
        local_path, remote_path = git_repos

        def failing_push(self):
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", failing_push):
            await write_ctx.do_write(
                lambda p: (p / "fail.txt").write_text("fail"),
                expect_error=True,
            )

        result = await write_ctx.do_write(
            lambda p: (p / "success.txt").write_text("works")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)


class TestRollbackAfterFailedRebase:
    """Scenario 34: Push fails, rebase succeeds, second push fails -> reflog recovery."""

    @pytest.mark.asyncio
    async def test_rebase_then_push_fail_reflog(
        self, write_ctx, git_repos, second_clone
    ):
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)

        push_call_count = 0

        def push_fail_then_diverge_then_fail(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "remote_file.kiln",
                    "remote content",
                    "remote push",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected: remote changed")
            raise pygit2.GitError("push rejected again")

        with patch.object(
            GitSyncManager, "_push_sync", push_fail_then_diverge_then_fail
        ):
            result = await write_ctx.do_write(
                lambda p: (p / "our_file.kiln").write_text("our content"),
                expect_error=True,
            )

        assert not result.pushed
        assert get_head_sync(local_path) == pre_head
        assert_clean_working_tree(local_path)

        assert_reflog_contains_commit_with_file(local_path, "our_file.kiln")

    @pytest.mark.asyncio
    async def test_rebase_then_push_fail_repo_clean(
        self, write_ctx, git_repos, second_clone
    ):
        """After rollback, repo is fully clean (no conflict markers, no rebase)."""
        local_path, remote_path = git_repos

        push_call_count = 0

        def push_always_fail(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "other.kiln",
                    "other data",
                    "other user",
                )
                push_from(second_clone)
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", push_always_fail):
            await write_ctx.do_write(
                lambda p: (p / "our.kiln").write_text("our data"),
                expect_error=True,
            )

        assert_clean_working_tree(local_path)
        repo = pygit2.Repository(str(local_path))
        assert repo.state() == pygit2.enums.RepositoryState.NONE
