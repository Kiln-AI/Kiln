"""Freshness integration tests for git auto-sync.

Scenarios 16, 18, 29: pull before write ensures fresh state,
stale read triggers update, freshness threshold prevents redundant fetches.
"""

from unittest.mock import patch

import pygit2
import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.integration_tests.conftest import (
    get_head_sync,
)


class TestPullBeforeWrite:
    """Scenario 16: Write request pulls remote changes before handler runs."""

    @pytest.mark.asyncio
    async def test_remote_changes_pulled_before_write(
        self, write_ctx, git_repos, second_clone
    ):
        """Remote commits are present locally before the handler writes."""
        local_path, remote_path = git_repos

        commit_in_repo(
            second_clone,
            "remote_update.kiln",
            "from another user",
            "remote user commit",
        )
        push_from(second_clone)

        files_seen_by_handler = []

        def write_fn(p):
            files_seen_by_handler.extend(
                [f.name for f in p.iterdir() if not f.name.startswith(".")]
            )
            (p / "our_write.kiln").write_text("our data")

        result = await write_ctx.do_write(write_fn)

        assert result.committed
        assert result.pushed
        assert "remote_update.kiln" in files_seen_by_handler

    @pytest.mark.asyncio
    async def test_handler_changes_on_top_of_pulled(
        self, write_ctx, git_repos, second_clone
    ):
        """Handler's commit is on top of pulled remote changes."""
        local_path, remote_path = git_repos

        commit_in_repo(second_clone, "base.kiln", "base content", "remote base")
        push_from(second_clone)

        result = await write_ctx.do_write(
            lambda p: (p / "on_top.kiln").write_text("on top")
        )

        assert result.committed
        assert result.pushed

        repo = pygit2.Repository(str(local_path))
        head = repo.revparse_single("HEAD")
        assert isinstance(head, pygit2.Commit)
        assert len(head.parents) == 1
        parent_tree = head.parents[0].peel(pygit2.Tree)
        assert "base.kiln" in [e.name for e in parent_tree]


class TestStaleReadUpdates:
    """Scenario 18: Stale read triggers fetch + fast-forward before serving."""

    @pytest.mark.asyncio
    async def test_stale_read_fetches_updates(self, api_ctx, git_repos, second_clone):
        """A stale read causes local repo to update from remote."""
        local_path, remote_path = git_repos

        commit_in_repo(
            second_clone,
            "read_update.kiln",
            "new content for reads",
            "remote for read",
        )
        push_from(second_clone)

        # Expire freshness so the read triggers ensure_fresh_for_read
        from app.desktop.git_sync.registry import GitSyncRegistry

        manager = GitSyncRegistry.get_or_create(
            repo_path=local_path, auth_mode="system_keys"
        )
        manager._last_sync = 0.0

        pre_head = get_head_sync(local_path)

        result = await api_ctx.do_read()

        assert result.status_code == 200

        post_head = get_head_sync(local_path)
        assert post_head != pre_head
        assert (local_path / "read_update.kiln").exists()


class TestFreshnessThresholdSkipsFetch:
    """Scenario 29: Recent sync skips fetch on next request."""

    @pytest.mark.asyncio
    async def test_second_write_skips_fetch(self, write_ctx, git_repos):
        """Second write within threshold does not fetch from remote."""
        local_path, remote_path = git_repos

        result1 = await write_ctx.do_write(
            lambda p: (p / "first.kiln").write_text("first write")
        )
        assert result1.committed

        fetch_called = False
        original_fetch_sync = GitSyncManager._fetch_sync

        def tracking_fetch(self):
            nonlocal fetch_called
            fetch_called = True
            original_fetch_sync(self)

        with patch.object(GitSyncManager, "_fetch_sync", tracking_fetch):
            result2 = await write_ctx.do_write(
                lambda p: (p / "second.kiln").write_text("second write")
            )

        assert result2.committed
        assert result2.pushed
        assert not fetch_called, (
            "Second write should skip fetch within freshness threshold"
        )

    @pytest.mark.asyncio
    async def test_fetch_resumes_after_threshold(self, write_ctx, git_repos):
        """After freshness threshold expires, fetch is called again."""
        local_path, remote_path = git_repos

        result1 = await write_ctx.do_write(
            lambda p: (p / "first.kiln").write_text("first write")
        )
        assert result1.committed

        # Expire the freshness by resetting _last_sync on the manager.
        # In library mode the manager is created directly (not via registry),
        # so access it from write_ctx.manager when available.
        if hasattr(write_ctx, "manager"):
            write_ctx.manager._last_sync = 0.0
        else:
            from app.desktop.git_sync.registry import GitSyncRegistry

            for mgr in GitSyncRegistry.all_managers():
                mgr._last_sync = 0.0

        fetch_called = False
        original_fetch_sync = GitSyncManager._fetch_sync

        def tracking_fetch(self):
            nonlocal fetch_called
            fetch_called = True
            original_fetch_sync(self)

        with patch.object(GitSyncManager, "_fetch_sync", tracking_fetch):
            result2 = await write_ctx.do_write(
                lambda p: (p / "after_expire.kiln").write_text("after expire")
            )

        assert result2.committed
        assert result2.pushed
        assert fetch_called, "Fetch should be called after freshness threshold expires"
