"""Validation tests for integration test infrastructure.

These tests prove that the fixtures, helpers, and WriteContext abstraction
work correctly before relying on them in scenario tests.
"""

import pygit2
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_commit_contains_files,
    assert_linear_history,
    assert_remote_has_commit,
    assert_stash_contains,
    create_remote_divergence,
    get_commit_count,
    get_head_sync,
    get_stash_list,
    remote_has_commit,
)


# ---------------------------------------------------------------------------
# Git repo fixtures
# ---------------------------------------------------------------------------


class TestGitRepoFixtures:
    def test_repos_exist(self, git_repos):
        local_path, remote_path = git_repos
        assert local_path.exists()
        assert remote_path.exists()

    def test_local_has_remote(self, git_repos):
        local_path, _ = git_repos
        repo = pygit2.Repository(str(local_path))
        assert "origin" in [r.name for r in repo.remotes]

    def test_initial_commit_present(self, git_repos):
        local_path, _ = git_repos
        repo = pygit2.Repository(str(local_path))
        head = repo.revparse_single("HEAD")
        assert isinstance(head, pygit2.Commit)

    def test_clean_after_creation(self, git_repos):
        local_path, _ = git_repos
        assert_clean_working_tree(local_path)


class TestCommitAndPush:
    def test_commit_creates_file(self, git_repos):
        local_path, _ = git_repos
        pre_head = get_head_sync(local_path)
        commit_in_repo(local_path, "test.txt", "content", "test commit")
        post_head = get_head_sync(local_path)
        assert pre_head != post_head
        assert (local_path / "test.txt").read_text() == "content"

    def test_push_reaches_remote(self, git_repos):
        local_path, remote_path = git_repos
        commit_in_repo(local_path, "pushed.txt", "data", "push test")
        push_from(local_path)
        post_head = get_head_sync(local_path)
        assert remote_has_commit(remote_path, post_head)

    def test_commit_count_increments(self, git_repos):
        local_path, _ = git_repos
        initial = get_commit_count(local_path)
        commit_in_repo(local_path, "a.txt", "a", "first")
        assert get_commit_count(local_path) == initial + 1
        commit_in_repo(local_path, "b.txt", "b", "second")
        assert get_commit_count(local_path) == initial + 2


class TestSecondClone:
    def test_second_clone_is_independent(self, git_repos, second_clone):
        local_path, _ = git_repos
        assert local_path != second_clone
        assert second_clone.exists()

    def test_second_clone_shares_remote(self, git_repos, second_clone):
        _, remote_path = git_repos
        repo = pygit2.Repository(str(second_clone))
        remote_url = repo.remotes["origin"].url
        assert remote_url is not None
        assert str(remote_path) in remote_url

    def test_second_clone_has_same_initial_commit(self, git_repos, second_clone):
        local_path, _ = git_repos
        assert get_head_sync(local_path) == get_head_sync(second_clone)


class TestCreateRemoteDivergence:
    def test_creates_divergence(self, git_repos, second_clone):
        local_path, remote_path = git_repos
        local_head_before = get_head_sync(local_path)
        remote_commit = create_remote_divergence(
            remote_path, second_clone, "diverge.txt", "diverged", "diverge"
        )
        assert remote_commit != local_head_before
        assert remote_has_commit(remote_path, remote_commit)
        assert not remote_has_commit(remote_path, "0" * 40)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


class TestAssertionHelpers:
    def test_assert_clean_working_tree_passes_on_clean(self, git_repos):
        local_path, _ = git_repos
        assert_clean_working_tree(local_path)

    def test_assert_clean_working_tree_fails_on_dirty(self, git_repos):
        local_path, _ = git_repos
        (local_path / "dirty.txt").write_text("dirty")
        with pytest.raises(AssertionError, match="dirty"):
            assert_clean_working_tree(local_path)

    def test_assert_remote_has_commit_passes(self, git_repos):
        local_path, remote_path = git_repos
        commit_in_repo(local_path, "x.txt", "x", "x")
        push_from(local_path)
        head = get_head_sync(local_path)
        assert_remote_has_commit(remote_path, head)

    def test_assert_remote_has_commit_fails(self, git_repos):
        _, remote_path = git_repos
        with pytest.raises(AssertionError, match="Remote does not contain"):
            assert_remote_has_commit(remote_path, "a" * 40)

    def test_assert_commit_contains_files(self, git_repos):
        local_path, _ = git_repos
        commit_in_repo(local_path, "tracked.txt", "data", "add tracked")
        head = get_head_sync(local_path)
        assert_commit_contains_files(local_path, head, ["tracked.txt"])

    def test_assert_linear_history(self, git_repos):
        local_path, _ = git_repos
        commit_in_repo(local_path, "a.txt", "a", "a")
        commit_in_repo(local_path, "b.txt", "b", "b")
        assert_linear_history(local_path, 3)

    def test_get_stash_list_empty(self, git_repos):
        local_path, _ = git_repos
        assert get_stash_list(local_path) == []

    def test_stash_and_assert(self, git_repos):
        local_path, _ = git_repos
        (local_path / "stash_me.txt").write_text("stash content")
        repo = pygit2.Repository(str(local_path))
        sig = pygit2.Signature("Test", "test@test.com")
        repo.stash(sig, "[Kiln] Test stash", include_untracked=True)
        assert_stash_contains(local_path, "[Kiln]")
        assert_stash_contains(local_path, "Test stash")

    def test_assert_stash_contains_fails_when_missing(self, git_repos):
        local_path, _ = git_repos
        with pytest.raises(AssertionError, match="No stash entry"):
            assert_stash_contains(local_path, "nonexistent")


# ---------------------------------------------------------------------------
# WriteContext (dual-mode)
# ---------------------------------------------------------------------------


class TestWriteContextLibraryMode:
    @pytest.mark.asyncio
    async def test_write_commits_and_pushes(self, git_repos, library_ctx):
        local_path, _ = git_repos
        result = await library_ctx.do_write(
            lambda p: (p / "lib_test.txt").write_text("lib data")
        )
        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_read_returns_ok(self, library_ctx):
        result = await library_ctx.do_read()
        assert result.body == {"status": "ok"}


class TestWriteContextAPIMode:
    @pytest.mark.asyncio
    async def test_write_commits_and_pushes(self, git_repos, api_ctx):
        local_path, _ = git_repos
        result = await api_ctx.do_write(
            lambda p: (p / "api_test.txt").write_text("api data")
        )
        assert result.committed
        assert result.pushed
        assert result.status_code == 200
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_read_returns_ok(self, api_ctx):
        result = await api_ctx.do_read()
        assert result.status_code == 200
        assert result.body == {"status": "ok"}


class TestWriteContextDualMode:
    @pytest.mark.asyncio
    async def test_write_commits_and_pushes(self, git_repos, write_ctx):
        local_path, remote_path = git_repos
        result = await write_ctx.do_write(
            lambda p: (p / "dual_test.txt").write_text("dual data")
        )
        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)
        head = get_head_sync(local_path)
        assert_remote_has_commit(remote_path, head)

    @pytest.mark.asyncio
    async def test_no_op_write_no_commit(self, git_repos, write_ctx):
        local_path, _ = git_repos
        pre_head = get_head_sync(local_path)
        result = await write_ctx.do_write(lambda p: None)
        assert not result.committed
        assert not result.pushed
        assert get_head_sync(local_path) == pre_head


# ---------------------------------------------------------------------------
# Network failure fixtures
# ---------------------------------------------------------------------------


class TestNetworkFailure:
    @pytest.mark.asyncio
    async def test_break_network_causes_fetch_failure(
        self, git_repos, manager, break_network
    ):
        from app.desktop.git_sync.errors import RemoteUnreachableError

        with pytest.raises((RemoteUnreachableError, pygit2.GitError, TimeoutError)):
            await manager.fetch()

    @pytest.mark.asyncio
    async def test_break_network_causes_push_failure(
        self, git_repos, manager, break_network
    ):
        local_path, _ = git_repos
        commit_in_repo(local_path, "push_test.txt", "data", "test")

        with pytest.raises((pygit2.GitError, TimeoutError)):
            await manager._run_git(manager._push_sync)
