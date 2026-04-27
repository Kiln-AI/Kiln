"""Network failure integration tests for git auto-sync.

Scenarios 17, 26: parameterized network failure modes on reads and writes.
Tests connection refused, auth failure, and timeout across both
pre-write fetch and post-write push failure points.
"""

import pytest

from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.integration_tests.conftest import (
    NETWORK_FAILURES,
    assert_clean_working_tree,
    assert_reflog_contains_commit_with_file,
    get_commit_count,
    get_head_sync,
    get_stash_list,
)


def _make_failing_fn(failure):
    def _fail(self):
        raise failure.exception_factory()

    return _fail


class TestNetworkFailureOnStaleRead:
    """Scenario 17: Stale read + network failure -> error."""

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_stale_read_network_failure(
        self, api_ctx, git_repos, network_failure, monkeypatch
    ):
        local_path, remote_path = git_repos

        monkeypatch.setattr(
            GitSyncManager,
            "_fetch_sync",
            _make_failing_fn(network_failure),
        )

        result = await api_ctx.do_read()

        assert result.status_code == 503
        assert result.error is not None

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_stale_read_no_corruption(
        self, api_ctx, git_repos, network_failure, monkeypatch
    ):
        """Network failure on read does not corrupt local state."""
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)

        monkeypatch.setattr(
            GitSyncManager,
            "_fetch_sync",
            _make_failing_fn(network_failure),
        )

        await api_ctx.do_read()

        assert get_head_sync(local_path) == pre_head
        assert_clean_working_tree(local_path)


class TestNetworkFailureOnWrite:
    """Scenario 26: Network failure during write (fetch or push)."""

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_fetch_failure_on_write(
        self, write_ctx, git_repos, network_failure, monkeypatch
    ):
        """Failure during pre-write ensure_fresh fetch."""
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        monkeypatch.setattr(
            GitSyncManager,
            "_fetch_sync",
            _make_failing_fn(network_failure),
        )

        result = await write_ctx.do_write(
            lambda p: (p / "should_not_commit.txt").write_text("data"),
            expect_error=True,
        )

        assert result.error is not None
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count
        assert_clean_working_tree(local_path)

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_push_failure_on_write(
        self, write_ctx, git_repos, network_failure, monkeypatch
    ):
        """Failure during post-write push."""
        local_path, remote_path = git_repos

        result = await write_ctx.do_write(lambda p: (p / "seed.txt").write_text("seed"))
        assert result.committed

        monkeypatch.setattr(
            GitSyncManager,
            "_push_sync",
            _make_failing_fn(network_failure),
        )

        result = await write_ctx.do_write(
            lambda p: (p / "will_fail_push.txt").write_text("data"),
            expect_error=True,
        )

        assert not result.pushed
        assert result.error is not None
        assert_clean_working_tree(local_path)
        # After a successful commit + failed push, rollback resets HEAD.
        # The working tree is clean post-commit so there is nothing to stash.
        # The committed changes are recoverable via the reflog entry created
        # by the reset that rolls back HEAD.
        assert len(get_stash_list(local_path)) == 0
        assert_reflog_contains_commit_with_file(local_path, "will_fail_push.txt")

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_recovery_after_network_failure(
        self, write_ctx, git_repos, network_failure, monkeypatch
    ):
        """Next request succeeds after connectivity is restored."""
        local_path, remote_path = git_repos

        monkeypatch.setattr(
            GitSyncManager,
            "_push_sync",
            _make_failing_fn(network_failure),
        )

        await write_ctx.do_write(
            lambda p: (p / "fail.txt").write_text("fail"),
            expect_error=True,
        )

        monkeypatch.undo()

        result = await write_ctx.do_write(
            lambda p: (p / "success.txt").write_text("success")
        )

        assert result.committed
        assert result.pushed
        assert_clean_working_tree(local_path)

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_no_partial_push(
        self, write_ctx, git_repos, network_failure, monkeypatch
    ):
        """Push failure leaves no partial commits on remote."""
        local_path, remote_path = git_repos

        result = await write_ctx.do_write(lambda p: (p / "seed.txt").write_text("seed"))
        assert result.committed

        post_seed_remote_head = get_head_sync(remote_path)

        monkeypatch.setattr(
            GitSyncManager,
            "_push_sync",
            _make_failing_fn(network_failure),
        )

        await write_ctx.do_write(
            lambda p: (p / "partial.txt").write_text("should not appear on remote"),
            expect_error=True,
        )

        assert get_head_sync(remote_path) == post_seed_remote_head


class TestNetworkFailureAPIStatusCodes:
    """API-mode specific status code checks for network failures."""

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_write_fetch_failure_api_status(
        self, api_ctx, git_repos, network_failure, monkeypatch
    ):
        """Fetch failure on write returns 503."""
        local_path, _ = git_repos

        monkeypatch.setattr(
            GitSyncManager,
            "_fetch_sync",
            _make_failing_fn(network_failure),
        )

        result = await api_ctx.do_write(
            lambda p: (p / "test.txt").write_text("test"),
            expect_error=True,
        )

        assert result.status_code == 503

    @pytest.mark.parametrize(
        "network_failure",
        NETWORK_FAILURES,
        ids=lambda f: f.name,
    )
    @pytest.mark.asyncio
    async def test_read_failure_api_status(
        self, api_ctx, git_repos, network_failure, monkeypatch
    ):
        """Read failure when stale returns appropriate error status."""
        local_path, _ = git_repos

        monkeypatch.setattr(
            GitSyncManager,
            "_fetch_sync",
            _make_failing_fn(network_failure),
        )

        result = await api_ctx.do_read()

        assert result.status_code == 503
