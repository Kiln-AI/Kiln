"""Conflict integration tests for git auto-sync.

Scenarios 8-9, 38-41: push race + rebase succeeds, unresolvable rebase,
delete/modify conflict, add/add conflict, empty commit after rebase,
and ABA (second push fails during retry).
"""

from unittest.mock import patch

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, delete_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_linear_history,
    assert_reflog_contains_commit_with_file,
    get_head_sync,
    get_stash_list,
)


class TestPushConflictRebaseSucceeds:
    """Scenario 8: Push fails, fetch+rebase succeeds, retry push works."""

    @pytest.mark.asyncio
    async def test_rebase_and_retry(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos

        push_call_count = 0
        original_push = GitSyncManager._push_sync

        def push_with_divergence(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "other_file.kiln",
                    "other user's data",
                    "other user commit",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected: remote has new commits")
            original_push(self)

        with patch.object(GitSyncManager, "_push_sync", push_with_divergence):
            result = await write_ctx.do_write(
                lambda p: (p / "our_file.kiln").write_text("our data")
            )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

        assert_linear_history(remote_path, 3)

        remote_repo = pygit2.Repository(str(remote_path))
        head = remote_repo.revparse_single("HEAD")
        assert isinstance(head, pygit2.Commit)
        tree = head.peel(pygit2.Tree)
        filenames = [e.name for e in tree]
        assert "our_file.kiln" in filenames
        assert "other_file.kiln" in filenames

    @pytest.mark.asyncio
    async def test_both_changes_preserved(self, write_ctx, git_repos, second_clone):
        """Both the remote and local changes exist after successful rebase."""
        local_path, remote_path = git_repos

        push_call_count = 0
        original_push = GitSyncManager._push_sync

        def push_with_divergence(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "remote_data.kiln",
                    "remote content",
                    "remote commit",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected")
            original_push(self)

        with patch.object(GitSyncManager, "_push_sync", push_with_divergence):
            await write_ctx.do_write(
                lambda p: (p / "local_data.kiln").write_text("local content")
            )

        assert (local_path / "remote_data.kiln").read_text() == "remote content"
        assert (local_path / "local_data.kiln").read_text() == "local content"


class TestPushConflictRebaseFails:
    """Scenario 9: Rebase produces unresolvable conflict -> abort + rollback."""

    @pytest.mark.asyncio
    async def test_unresolvable_conflict_rolls_back(
        self, write_ctx, git_repos, second_clone
    ):
        local_path, remote_path = git_repos

        push_call_count = 0

        def push_with_conflict(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "contested.kiln",
                    "remote version of content",
                    "remote edit",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected")
            raise pygit2.GitError("should not reach second push")

        with patch.object(GitSyncManager, "_push_sync", push_with_conflict):
            result = await write_ctx.do_write(
                lambda p: (p / "contested.kiln").write_text("local version of content"),
                expect_error=True,
            )

        assert not result.pushed
        assert_clean_working_tree(local_path)
        # Changes are recoverable via reflog, not stash, because the working
        # tree is clean after a successful commit + failed rebase (rebase does
        # hard resets internally).
        assert len(get_stash_list(local_path)) == 0
        assert_reflog_contains_commit_with_file(local_path, "contested.kiln")

        repo = pygit2.Repository(str(local_path))
        assert repo.state() == pygit2.enums.RepositoryState.NONE

    @pytest.mark.asyncio
    async def test_unresolvable_conflict_api_409(
        self, api_ctx, git_repos, second_clone
    ):
        """API mode: unresolvable conflict returns 409."""
        local_path, _ = git_repos

        push_call_count = 0

        def push_with_conflict(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "contested.kiln",
                    "remote version",
                    "remote edit",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected")
            raise pygit2.GitError("unreachable")

        with patch.object(GitSyncManager, "_push_sync", push_with_conflict):
            result = await api_ctx.do_write(
                lambda p: (p / "contested.kiln").write_text("local version"),
                expect_error=True,
            )

        assert result.status_code == 409


class TestDeleteModifyConflict:
    """Scenario 38: Remote deletes file, local modifies it -> resolved cleanly.

    Git's cherry-pick auto-resolves delete/modify by keeping the local
    modification (re-adding the file). This is the desired "no data loss"
    outcome: the user's local edit is preserved and pushed to remote.
    """

    @pytest.mark.asyncio
    async def test_delete_modify_conflict(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos

        push_call_count = 0
        original_push = GitSyncManager._push_sync

        def push_with_delete_conflict(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "shared.kiln",
                    "original content",
                    "add shared",
                )
                push_from(second_clone)
                delete_in_repo(second_clone, "shared.kiln", "delete shared.kiln")
                push_from(second_clone)
                raise pygit2.GitError("push rejected: remote diverged")
            original_push(self)

        with patch.object(GitSyncManager, "_push_sync", push_with_delete_conflict):
            result = await write_ctx.do_write(
                lambda p: (p / "shared.kiln").write_text("modified locally"),
            )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

        remote_repo = pygit2.Repository(str(remote_path))
        head = remote_repo.revparse_single("HEAD")
        assert isinstance(head, pygit2.Commit)
        tree = head.peel(pygit2.Tree)
        filenames = [e.name for e in tree]
        assert "shared.kiln" in filenames, (
            "locally modified file should be preserved on remote after push"
        )


class TestAddAddConflict:
    """Scenario 39: Both sides create same file with different content."""

    @pytest.mark.asyncio
    async def test_add_add_conflict(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos

        push_call_count = 0

        def push_with_add_conflict(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "new_file.kiln",
                    "remote created this file first",
                    "remote adds new_file",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected")
            raise pygit2.GitError("should not retry after conflict")

        with patch.object(GitSyncManager, "_push_sync", push_with_add_conflict):
            result = await write_ctx.do_write(
                lambda p: (p / "new_file.kiln").write_text("local created this file"),
                expect_error=True,
            )

        assert not result.pushed
        assert_clean_working_tree(local_path)


class TestEmptyCommitAfterRebase:
    """Scenario 40: Rebase produces empty commit (identical changes)."""

    @pytest.mark.asyncio
    async def test_identical_changes_graceful(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos

        push_call_count = 0
        original_push = GitSyncManager._push_sync

        def push_with_identical_change(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "same.kiln",
                    "identical content",
                    "remote adds same.kiln",
                )
                push_from(second_clone)
                raise pygit2.GitError("push rejected")
            original_push(self)

        with patch.object(GitSyncManager, "_push_sync", push_with_identical_change):
            result = await write_ctx.do_write(
                lambda p: (p / "same.kiln").write_text("identical content"),
            )

        assert result.error is None
        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

        repo = pygit2.Repository(str(local_path))
        assert repo.state() == pygit2.enums.RepositoryState.NONE


class TestABASecondPushFails:
    """Scenario 41: Remote changes again between rebase and retry push."""

    @pytest.mark.asyncio
    async def test_aba_double_conflict(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)

        push_call_count = 0

        def push_always_diverging(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "other_a.kiln",
                    "first remote change",
                    "remote commit A",
                )
                push_from(second_clone)
            elif push_call_count == 2:
                pass
            raise pygit2.GitError(f"push rejected (attempt {push_call_count})")

        with patch.object(GitSyncManager, "_push_sync", push_always_diverging):
            result = await write_ctx.do_write(
                lambda p: (p / "our.kiln").write_text("our data"),
                expect_error=True,
            )

        assert not result.pushed
        assert_clean_working_tree(local_path)
        assert get_head_sync(local_path) == pre_head

    @pytest.mark.asyncio
    async def test_aba_api_returns_409(self, api_ctx, git_repos, second_clone):
        """API mode: ABA conflict returns 409."""
        local_path, _ = git_repos

        push_call_count = 0

        def push_always_fail(self):
            nonlocal push_call_count
            push_call_count += 1
            if push_call_count == 1:
                commit_in_repo(
                    second_clone,
                    "race.kiln",
                    "race data",
                    "race commit",
                )
                push_from(second_clone)
            raise pygit2.GitError("push rejected")

        with patch.object(GitSyncManager, "_push_sync", push_always_fail):
            result = await api_ctx.do_write(
                lambda p: (p / "our.kiln").write_text("our data"),
                expect_error=True,
            )

        assert result.status_code == 409
