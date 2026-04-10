"""Write lock integration tests for git auto-sync.

Scenarios 14-15, 45: serialization of concurrent writes, lock timeout,
and non-reentrant deadlock detection.
"""

import asyncio
import threading

import pytest

from app.desktop.git_sync.errors import WriteLockTimeoutError
from app.desktop.git_sync.integration_tests.conftest import (
    assert_clean_working_tree,
    assert_remote_has_commit,
    get_commit_count,
    get_head_sync,
)


class TestWriteLockSerialization:
    """Scenario 14: Concurrent write requests are serialized."""

    @pytest.mark.asyncio
    async def test_concurrent_writes_both_succeed(self, write_ctx, git_repos):
        """Two writes started concurrently both succeed (serialized by lock)."""
        local_path, remote_path = git_repos
        pre_count = get_commit_count(local_path)

        result1, result2 = await asyncio.gather(
            write_ctx.do_write(
                lambda p: (p / "concurrent_a.kiln").write_text("data a")
            ),
            write_ctx.do_write(
                lambda p: (p / "concurrent_b.kiln").write_text("data b")
            ),
        )

        assert result1.committed
        assert result1.pushed
        assert result2.committed
        assert result2.pushed
        assert get_commit_count(local_path) == pre_count + 2
        assert_clean_working_tree(local_path)

    @pytest.mark.asyncio
    async def test_concurrent_writes_no_corruption(self, write_ctx, git_repos):
        """Both files exist after concurrent writes with no corruption."""
        local_path, remote_path = git_repos

        await asyncio.gather(
            write_ctx.do_write(lambda p: (p / "file_one.kiln").write_text("one")),
            write_ctx.do_write(lambda p: (p / "file_two.kiln").write_text("two")),
        )

        assert (local_path / "file_one.kiln").read_text() == "one"
        assert (local_path / "file_two.kiln").read_text() == "two"
        assert_clean_working_tree(local_path)

        post_head = get_head_sync(local_path)
        assert_remote_has_commit(remote_path, post_head)

    @pytest.mark.asyncio
    async def test_concurrent_writes_on_remote(self, write_ctx, git_repos):
        """Both commits appear on remote after concurrent writes."""
        local_path, remote_path = git_repos
        pre_count = get_commit_count(remote_path)

        await asyncio.gather(
            write_ctx.do_write(lambda p: (p / "remote_a.kiln").write_text("a")),
            write_ctx.do_write(lambda p: (p / "remote_b.kiln").write_text("b")),
        )

        assert get_commit_count(remote_path) == pre_count + 2


class TestWriteLockTimeout:
    """Scenario 15: Write lock timeout when another operation holds the lock."""

    @pytest.mark.asyncio
    async def test_lock_timeout_fails(self, manager, git_repos):
        """Request fails with WriteLockTimeoutError when lock is held."""
        manager._WRITE_LOCK_TIMEOUT = 0.1

        lock_held = threading.Event()
        release = threading.Event()

        def hold_lock():
            manager._write_lock.acquire()
            lock_held.set()
            release.wait(timeout=5)
            manager._write_lock.release()

        holder = threading.Thread(target=hold_lock)
        holder.start()
        lock_held.wait()

        try:
            with pytest.raises(WriteLockTimeoutError, match="Another save"):
                async with manager.write_lock():
                    pass
        finally:
            release.set()
            holder.join(timeout=5)

    @pytest.mark.asyncio
    async def test_lock_timeout_no_state_changes(self, manager, git_repos):
        """No commits or state changes when lock times out."""
        local_path, remote_path = git_repos
        pre_head = get_head_sync(local_path)
        pre_count = get_commit_count(local_path)
        manager._WRITE_LOCK_TIMEOUT = 0.1

        lock_held = threading.Event()
        release = threading.Event()

        def hold_lock():
            manager._write_lock.acquire()
            lock_held.set()
            release.wait(timeout=5)
            manager._write_lock.release()

        holder = threading.Thread(target=hold_lock)
        holder.start()
        lock_held.wait()

        try:
            with pytest.raises(WriteLockTimeoutError):
                async with manager.write_lock():
                    pass

            assert get_head_sync(local_path) == pre_head
            assert get_commit_count(local_path) == pre_count
        finally:
            release.set()
            holder.join(timeout=5)

    @pytest.mark.asyncio
    async def test_lock_timeout_api_returns_error(self, api_client, git_repos):
        """API mode: lock timeout returns 500.

        WriteLockTimeoutError is raised from `manager.write_lock()` which
        is outside the middleware's inner try/except that maps
        GitSyncErrors to HTTP status codes. As a result, the error
        propagates as an unhandled 500 rather than the ideal 503. This
        test documents the actual behavior.
        """
        from app.desktop.git_sync.registry import GitSyncRegistry

        client, local_path, remote_path, write_fn_slot = api_client

        manager = GitSyncRegistry.get_or_create(
            repo_path=local_path, auth_mode="system_keys"
        )
        manager._WRITE_LOCK_TIMEOUT = 0.1

        lock_held = threading.Event()
        release = threading.Event()

        def hold_lock():
            manager._write_lock.acquire()
            lock_held.set()
            release.wait(timeout=5)
            manager._write_lock.release()

        holder = threading.Thread(target=hold_lock)
        holder.start()
        lock_held.wait()

        try:
            write_fn_slot.clear()
            write_fn_slot.append(lambda p: (p / "timeout.kiln").write_text("nope"))
            resp = client.post(
                "/api/projects/integration_test_proj/test_write", json={}
            )
            assert resp.status_code == 500
        finally:
            release.set()
            holder.join(timeout=5)


class TestNonReentrantDeadlockDetection:
    """Scenario 45: Re-acquiring the write lock from within times out."""

    @pytest.mark.asyncio
    async def test_inner_lock_times_out(self, manager, git_repos):
        """Inner lock acquisition times out, not a silent deadlock."""
        manager._WRITE_LOCK_TIMEOUT = 0.2

        async with manager.write_lock():
            with pytest.raises(WriteLockTimeoutError, match="Another save"):
                async with manager.write_lock():
                    pass

    @pytest.mark.asyncio
    async def test_outer_lock_still_usable_after_inner_timeout(
        self, manager, git_repos
    ):
        """Outer lock scope remains usable after inner timeout."""
        local_path, _ = git_repos
        manager._WRITE_LOCK_TIMEOUT = 0.2

        async with manager.write_lock():
            with pytest.raises(WriteLockTimeoutError):
                async with manager.write_lock():
                    pass

            # Outer lock still works: can still use manager operations
            has_dirty = await manager.has_dirty_files()
            assert not has_dirty
