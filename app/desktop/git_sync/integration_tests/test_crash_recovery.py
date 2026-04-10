"""Crash recovery integration tests for git auto-sync.

Scenarios 10-13, 35-37: dirty state recovery, in-progress rebase recovery,
unpushed commits reset, unrecoverable state, all-three-combined,
remote force-push, and partial recovery failure.
"""

from unittest.mock import patch

import pygit2
import pygit2.enums
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_reflog_contains_commit_with_file,
    assert_stash_contains,
    get_head_sync,
    get_stash_list,
    remote_has_commit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def leave_dirty_files(repo_path, filenames=None):
    """Write untracked files to simulate a crash leaving dirty state."""
    if filenames is None:
        filenames = {"crash_leftover.txt": "data from prior crash"}
    for name, content in filenames.items():
        (repo_path / name).write_text(content)


def leave_rebase_state_clean(repo_path):
    """Leave the repo in a cherry-pick state WITHOUT conflicts.

    Creates a cherry-pick in progress by cherry-picking a commit that
    doesn't conflict with the current state. This simulates a crash
    mid-rebase where the cherry-pick was clean but not yet finalized.
    """
    local_commit_oid = commit_in_repo(
        repo_path,
        "cherrypicked.kiln",
        "cherry-pick content",
        "commit to cherry-pick",
    )

    repo = pygit2.Repository(str(repo_path))
    commit_obj = repo.get(local_commit_oid)
    assert isinstance(commit_obj, pygit2.Commit)
    parent_oid = commit_obj.parents[0].id
    repo.reset(parent_oid, pygit2.enums.ResetMode.HARD)

    repo.cherrypick(local_commit_oid)

    assert repo.state() != pygit2.enums.RepositoryState.NONE


def leave_rebase_state_conflicted(repo_path, second_clone_path, remote_path):
    """Leave the repo in a cherry-pick state WITH conflicts.

    Creates a conflict by having both local and remote modify the same file,
    then starts a cherry-pick that produces conflicts (simulating a crash
    mid-rebase with unresolvable conflicts).
    """
    commit_in_repo(
        second_clone_path,
        "conflict_file.kiln",
        "remote version of conflict",
        "remote conflict commit",
    )
    push_from(second_clone_path)

    local_commit_oid = commit_in_repo(
        repo_path,
        "conflict_file.kiln",
        "local version of conflict",
        "local conflict commit",
    )

    repo = pygit2.Repository(str(repo_path))
    remote = repo.remotes["origin"]
    remote.fetch()

    remote_ref = repo.references.get("refs/remotes/origin/main")
    assert remote_ref is not None
    remote_oid = remote_ref.target

    repo.reset(remote_oid, pygit2.enums.ResetMode.HARD)
    repo.cherrypick(local_commit_oid)

    has_conflicts = False
    if repo.index.conflicts is not None:
        for _ in repo.index.conflicts:
            has_conflicts = True
            break
    assert has_conflicts
    assert repo.state() != pygit2.enums.RepositoryState.NONE


def create_unpushed_commit(repo_path, filename="unpushed.kiln", content="unpushed"):
    """Create a local commit that is not pushed to remote."""
    return commit_in_repo(repo_path, filename, content, "unpushed local commit")


def force_push_rewrite(remote_path, second_clone_path):
    """Force-push to remote from second clone, rewriting history.

    Creates a new commit on the second clone then force-pushes, so the
    remote's history diverges from the local clone.
    """
    commit_in_repo(
        second_clone_path,
        "force_pushed.kiln",
        "force pushed content",
        "force push commit",
    )
    repo = pygit2.Repository(str(second_clone_path))
    remote = repo.remotes["origin"]
    branch = repo.head.shorthand
    remote.push([f"+refs/heads/{branch}"])


# ---------------------------------------------------------------------------
# Scenario 10: Dirty State on Write Request
# ---------------------------------------------------------------------------


class TestDirtyStateRecovery:
    """Scenario 10: Dirty state from prior crash is auto-recovered."""

    @pytest.mark.asyncio
    async def test_dirty_state_stashed_on_write(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        leave_dirty_files(local_path)
        pre_stash_count = len(get_stash_list(local_path))

        result = await write_ctx.do_write(
            lambda p: (p / "new_data.kiln").write_text("new write")
        )

        assert result.committed
        assert result.pushed
        stashes = get_stash_list(local_path)
        assert len(stashes) > pre_stash_count
        assert_stash_contains(local_path, "Kiln")

    @pytest.mark.asyncio
    async def test_dirty_state_stash_has_recovery_message(self, write_ctx, git_repos):
        local_path, _ = git_repos
        leave_dirty_files(local_path)

        await write_ctx.do_write(
            lambda p: (p / "new_data.kiln").write_text("new write")
        )

        assert_stash_contains(local_path, "Auto-recovery stash")

    @pytest.mark.asyncio
    async def test_dirty_state_new_write_succeeds(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        leave_dirty_files(local_path)

        result = await write_ctx.do_write(
            lambda p: (p / "recovery_write.kiln").write_text("recovered")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)
        post_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, post_head)

    @pytest.mark.asyncio
    async def test_dirty_state_old_data_in_stash(self, write_ctx, git_repos):
        """The stashed content matches what was written (dirty files preserved)."""
        local_path, _ = git_repos
        leave_dirty_files(local_path, {"precious.txt": "important data"})

        await write_ctx.do_write(lambda p: (p / "new.kiln").write_text("new"))

        repo = pygit2.Repository(str(local_path))
        stash_ref = repo.references.get("refs/stash")
        assert stash_ref is not None
        stash_commit = repo.get(stash_ref.target)
        assert isinstance(stash_commit, pygit2.Commit)
        # Stash includes untracked files in a special parent commit
        # The untracked files are in the third parent's tree
        assert len(stash_commit.parents) >= 3
        untracked_tree = stash_commit.parents[2].peel(pygit2.Tree)
        assert "precious.txt" in [e.name for e in untracked_tree]


# ---------------------------------------------------------------------------
# Scenario 11: In-Progress Rebase Recovery
# ---------------------------------------------------------------------------


class TestInProgressRebaseRecovery:
    """Scenario 11: In-progress rebase from prior crash is aborted and recovered."""

    @pytest.mark.asyncio
    async def test_in_progress_rebase_aborted(self, write_ctx, git_repos):
        """Clean cherry-pick state (no conflicts) is recovered successfully."""
        local_path, remote_path = git_repos
        leave_rebase_state_clean(local_path)

        repo = pygit2.Repository(str(local_path))
        assert repo.state() != pygit2.enums.RepositoryState.NONE

        result = await write_ctx.do_write(
            lambda p: (p / "after_rebase.kiln").write_text("post-recovery write")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

        repo2 = pygit2.Repository(str(local_path))
        assert repo2.state() == pygit2.enums.RepositoryState.NONE

    @pytest.mark.asyncio
    async def test_in_progress_rebase_dirty_state_stashed(self, write_ctx, git_repos):
        """Cherry-picked changes are stashed during recovery."""
        local_path, remote_path = git_repos
        leave_rebase_state_clean(local_path)
        pre_stash_count = len(get_stash_list(local_path))

        result = await write_ctx.do_write(
            lambda p: (p / "normal.kiln").write_text("works normally")
        )

        assert result.committed
        assert result.pushed
        stashes = get_stash_list(local_path)
        assert len(stashes) > pre_stash_count
        assert_stash_contains(local_path, "Kiln")

    @pytest.mark.asyncio
    async def test_in_progress_rebase_new_write_succeeds(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        leave_rebase_state_clean(local_path)

        result = await write_ctx.do_write(
            lambda p: (p / "normal.kiln").write_text("works normally")
        )

        assert result.committed
        assert result.pushed
        post_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, post_head)

    @pytest.mark.xfail(
        reason="state_cleanup() clears the cherry-pick state marker but leaves "
        "conflict entries in the index. The subsequent stash fails with "
        "'cannot create a tree from a not fully merged index'.",
        strict=True,
    )
    @pytest.mark.asyncio
    async def test_conflicted_rebase_recovery_succeeds(
        self, write_ctx, git_repos, second_clone
    ):
        """Conflicted cherry-pick state should be recoverable like clean state."""
        local_path, remote_path = git_repos
        leave_rebase_state_conflicted(local_path, second_clone, remote_path)

        result = await write_ctx.do_write(
            lambda p: (p / "after_rebase.kiln").write_text("post-recovery write"),
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)


# ---------------------------------------------------------------------------
# Scenario 12: Unpushed Local Commits
# ---------------------------------------------------------------------------


class TestUnpushedCommitsRecovery:
    """Scenario 12: Unpushed commits from prior crash are reset to match remote."""

    @pytest.mark.asyncio
    async def test_unpushed_commits_reset(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        remote_head_before = get_head_sync(remote_path)
        create_unpushed_commit(local_path)

        assert get_head_sync(local_path) != remote_head_before

        result = await write_ctx.do_write(
            lambda p: (p / "fresh.kiln").write_text("fresh data")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_unpushed_commits_in_reflog(self, write_ctx, git_repos):
        """Orphaned commit is still in reflog (not truly lost)."""
        local_path, _ = git_repos
        create_unpushed_commit(local_path)

        await write_ctx.do_write(lambda p: (p / "fresh.kiln").write_text("fresh data"))

        assert_reflog_contains_commit_with_file(local_path, "unpushed.kiln")

    @pytest.mark.asyncio
    async def test_unpushed_commits_new_write_succeeds(self, write_ctx, git_repos):
        local_path, remote_path = git_repos
        create_unpushed_commit(local_path)

        result = await write_ctx.do_write(
            lambda p: (p / "after_reset.kiln").write_text("post-reset write")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)
        post_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, post_head)


# ---------------------------------------------------------------------------
# Scenario 13: Unrecoverable State
# ---------------------------------------------------------------------------


class TestUnrecoverableState:
    """Scenario 13: Unrecoverable repo state -> error, no partial commits."""

    @pytest.mark.asyncio
    async def test_unrecoverable_state_returns_error(self, write_ctx, git_repos):
        local_path, _ = git_repos

        original_is_clean = GitSyncManager._is_clean

        call_count = 0

        async def mock_is_clean(self):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return False
            return await original_is_clean(self)

        with patch.object(GitSyncManager, "_is_clean", mock_is_clean):
            result = await write_ctx.do_write(
                lambda p: (p / "should_not_commit.kiln").write_text("nope"),
                expect_error=True,
            )

        assert result.error is not None
        assert (
            "unexpected state" in result.error.lower()
            or "corrupt" in result.error.lower()
        )

    @pytest.mark.asyncio
    async def test_unrecoverable_state_no_partial_commits(self, write_ctx, git_repos):
        _, remote_path = git_repos
        pre_remote_head = get_head_sync(remote_path)

        async def always_dirty(self):
            return False

        with patch.object(GitSyncManager, "_is_clean", always_dirty):
            await write_ctx.do_write(
                lambda p: (p / "nope.kiln").write_text("nope"),
                expect_error=True,
            )

        assert get_head_sync(remote_path) == pre_remote_head

    @pytest.mark.asyncio
    async def test_unrecoverable_state_api_returns_500(self, api_ctx, git_repos):
        """API mode: unrecoverable state returns 500."""

        async def always_dirty(self):
            return False

        with patch.object(GitSyncManager, "_is_clean", always_dirty):
            result = await api_ctx.do_write(
                lambda p: (p / "nope.kiln").write_text("nope"),
                expect_error=True,
            )

        assert result.status_code == 500


# ---------------------------------------------------------------------------
# Scenario 35: All Three Conditions Simultaneously
# ---------------------------------------------------------------------------


class TestAllThreeSimultaneous:
    """Scenario 35: Dirty files + in-progress rebase + unpushed commits all at once.

    Uses the clean (non-conflicting) cherry-pick state since conflicted
    cherry-pick recovery is a known bug documented in
    TestInProgressRebaseRecovery.test_conflicted_rebase_recovery_fails.
    """

    @pytest.mark.asyncio
    async def test_all_three_simultaneous_recovery(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        create_unpushed_commit(local_path, "unpushed_extra.kiln", "unpushed data")
        leave_rebase_state_clean(local_path)
        leave_dirty_files(local_path, {"extra_dirty.txt": "extra dirty data"})

        pre_stash_count = len(get_stash_list(local_path))

        result = await write_ctx.do_write(
            lambda p: (p / "recovered.kiln").write_text("all three recovered")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

        repo = pygit2.Repository(str(local_path))
        assert repo.state() == pygit2.enums.RepositoryState.NONE

        stashes = get_stash_list(local_path)
        assert len(stashes) > pre_stash_count

    @pytest.mark.asyncio
    async def test_all_three_branch_matches_remote(self, write_ctx, git_repos):
        """After recovery, local branch matches remote HEAD (unpushed commit reset)."""
        local_path, remote_path = git_repos

        create_unpushed_commit(local_path, "unpushed_verify.kiln", "unpushed data")
        leave_rebase_state_clean(local_path)
        leave_dirty_files(local_path, {"verify_dirty.txt": "dirty data"})

        result = await write_ctx.do_write(
            lambda p: (p / "verify.kiln").write_text("verify recovery")
        )

        assert result.committed
        assert result.pushed
        local_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, local_head)

    @pytest.mark.asyncio
    async def test_all_three_new_write_succeeds(self, write_ctx, git_repos):
        local_path, remote_path = git_repos

        create_unpushed_commit(local_path, "unpushed_extra2.kiln", "unpushed")
        leave_rebase_state_clean(local_path)
        leave_dirty_files(local_path)

        result1 = await write_ctx.do_write(
            lambda p: (p / "first.kiln").write_text("first")
        )
        assert result1.committed
        assert result1.pushed

        result2 = await write_ctx.do_write(
            lambda p: (p / "second.kiln").write_text("second")
        )
        assert result2.committed
        assert result2.pushed
        assert_clean_working_tree(local_path)


# ---------------------------------------------------------------------------
# Scenario 36: Remote Force-Push (History Rewrite)
# ---------------------------------------------------------------------------


class TestRemoteForcePush:
    """Scenario 36: Recovery succeeds when remote has been force-pushed."""

    @pytest.mark.asyncio
    async def test_force_push_recovery(self, write_ctx, git_repos, second_clone):
        local_path, remote_path = git_repos

        create_unpushed_commit(local_path, "local_diverged.kiln", "local diverged")

        force_push_rewrite(remote_path, second_clone)

        result = await write_ctx.do_write(
            lambda p: (p / "after_force_push.kiln").write_text("post force-push")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_force_push_new_write_succeeds(
        self, write_ctx, git_repos, second_clone
    ):
        local_path, remote_path = git_repos

        create_unpushed_commit(local_path)
        force_push_rewrite(remote_path, second_clone)

        result = await write_ctx.do_write(
            lambda p: (p / "normal.kiln").write_text("normal write")
        )

        assert result.committed
        assert result.pushed
        post_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, post_head)
        assert_clean_working_tree(local_path)


# ---------------------------------------------------------------------------
# Scenario 37: Recovery Itself Fails Partway
# ---------------------------------------------------------------------------


class TestPartialRecoveryFailure:
    """Scenario 37: If recovery fails partway, next attempt succeeds."""

    @pytest.mark.asyncio
    async def test_partial_recovery_first_fails_second_succeeds(
        self, write_ctx, git_repos
    ):
        """First recovery attempt fails, second attempt succeeds normally."""
        local_path, remote_path = git_repos
        leave_dirty_files(local_path)

        original_stash_all = GitSyncManager._stash_all
        stash_call_count = 0

        def stash_fails_once(self, message):
            nonlocal stash_call_count
            stash_call_count += 1
            if stash_call_count == 1:
                raise pygit2.GitError("stash failed: index locked")
            original_stash_all(self, message)

        with patch.object(GitSyncManager, "_stash_all", stash_fails_once):
            first_result = await write_ctx.do_write(
                lambda p: (p / "attempt1.kiln").write_text("first attempt"),
                expect_error=True,
            )

            assert first_result.error is not None

            result = await write_ctx.do_write(
                lambda p: (p / "attempt2.kiln").write_text("second attempt"),
            )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)
