"""Background sync integration tests for git auto-sync.

Scenarios 19-21: fetch + fast-forward, no-op when up to date,
skip when not fast-forwardable.
"""

import pytest

from app.desktop.git_sync.conftest import commit_in_repo, push_from
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    get_commit_count,
    get_head_sync,
)


class TestBackgroundSyncFetchAndFastForward:
    """Scenario 19: Background sync detects remote changes and applies them."""

    @pytest.mark.asyncio
    async def test_fetch_and_fast_forward(self, manager, git_repos, second_clone):
        """Fetch + fast-forward pulls new remote commits into local."""
        local_path, remote_path = git_repos

        commit_in_repo(
            second_clone,
            "bg_sync_file.kiln",
            "background sync content",
            "remote bg commit",
        )
        push_from(second_clone)

        pre_head = get_head_sync(local_path)

        await manager.fetch()
        assert await manager.has_new_remote_commits()
        assert await manager.can_fast_forward()

        async with manager.write_lock():
            await manager.fast_forward()

        post_head = get_head_sync(local_path)
        assert post_head != pre_head

        assert (local_path / "bg_sync_file.kiln").exists()
        assert (
            local_path / "bg_sync_file.kiln"
        ).read_text() == "background sync content"

    @pytest.mark.asyncio
    async def test_working_tree_updated(self, manager, git_repos, second_clone):
        """Working tree reflects content from fast-forwarded commits."""
        local_path, _ = git_repos

        commit_in_repo(
            second_clone,
            "tree_check.kiln",
            '{"synced": true}',
            "remote content check",
        )
        push_from(second_clone)

        await manager.fetch()
        assert await manager.can_fast_forward()
        async with manager.write_lock():
            await manager.fast_forward()

        assert (local_path / "tree_check.kiln").read_text() == '{"synced": true}'
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_multiple_remote_commits(self, manager, git_repos, second_clone):
        """Multiple remote commits are all pulled in via fast-forward."""
        local_path, _ = git_repos

        commit_in_repo(second_clone, "multi_1.kiln", "one", "commit 1")
        commit_in_repo(second_clone, "multi_2.kiln", "two", "commit 2")
        commit_in_repo(second_clone, "multi_3.kiln", "three", "commit 3")
        push_from(second_clone)

        pre_count = get_commit_count(local_path)

        await manager.fetch()
        async with manager.write_lock():
            if await manager.can_fast_forward():
                await manager.fast_forward()

        assert get_commit_count(local_path) == pre_count + 3
        assert (local_path / "multi_1.kiln").exists()
        assert (local_path / "multi_2.kiln").exists()
        assert (local_path / "multi_3.kiln").exists()


class TestBackgroundSyncNoOp:
    """Scenario 20: No-op when local and remote are already in sync."""

    @pytest.mark.asyncio
    async def test_no_op_when_in_sync(self, manager, git_repos):
        """No changes when local and remote are already in sync."""
        local_path, _ = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)

        await manager.fetch()
        has_new = await manager.has_new_remote_commits()

        assert not has_new
        assert get_head_sync(local_path) == pre_head
        assert get_commit_count(local_path) == pre_count

    @pytest.mark.asyncio
    async def test_no_op_head_unchanged(self, manager, git_repos):
        """HEAD is unchanged after a no-op background sync."""
        local_path, _ = git_repos
        pre_head = get_head_sync(local_path)

        await manager.fetch()
        if await manager.can_fast_forward():
            async with manager.write_lock():
                await manager.fast_forward()

        assert get_head_sync(local_path) == pre_head


class TestBackgroundSyncSkipsDiverged:
    """Scenario 21: Background sync skips fast-forward when local has diverged."""

    @pytest.mark.asyncio
    async def test_skips_when_diverged(self, manager, git_repos, second_clone):
        """Fast-forward is skipped when local has unpushed commits."""
        local_path, _ = git_repos

        commit_in_repo(local_path, "local_only.kiln", "local data", "local commit")

        commit_in_repo(
            second_clone,
            "remote_only.kiln",
            "remote data",
            "remote commit",
        )
        push_from(second_clone)

        pre_head = get_head_sync(local_path)

        await manager.fetch()

        assert await manager.has_new_remote_commits()
        can_ff = await manager.can_fast_forward()
        assert not can_ff, "Should not be fast-forwardable when local has diverged"

        assert get_head_sync(local_path) == pre_head
        assert (local_path / "local_only.kiln").exists()

    @pytest.mark.asyncio
    async def test_local_commit_preserved(self, manager, git_repos, second_clone):
        """Local unpushed commit is preserved when background sync skips."""
        local_path, _ = git_repos

        commit_in_repo(local_path, "preserve_me.kiln", "keep", "local change")
        local_head = get_head_sync(local_path)

        commit_in_repo(
            second_clone,
            "remote_new.kiln",
            "remote",
            "remote change",
        )
        push_from(second_clone)

        await manager.fetch()
        if await manager.can_fast_forward():
            async with manager.write_lock():
                await manager.fast_forward()

        assert get_head_sync(local_path) == local_head
        assert (local_path / "preserve_me.kiln").read_text() == "keep"
