import asyncio
import logging
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.desktop.git_sync.config import AuthMode
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, TypeVar

import pygit2
import pygit2.enums

from app.desktop.git_sync.commit_message import generate_commit_message
from app.desktop.git_sync.errors import (
    CorruptRepoError,
    RemoteUnreachableError,
    SyncConflictError,
    WriteLockTimeoutError,
)

logger = logging.getLogger(__name__)

# Configure global libgit2 network timeouts (process-wide, not per-repo).
_settings = pygit2.Settings()
_settings.server_connect_timeout = 30
_settings.server_timeout = 30

T = TypeVar("T")

FRESHNESS_THRESHOLD = 15.0

_cached_committer_name: str | None = None
_cached_committer_email: str | None = None


def _git_config_value(key: str) -> str | None:
    """Try to read a value from git config (local then global)."""
    for cmd in (
        ["git", "config", key],
        ["git", "config", "--global", key],
    ):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
    return None


def get_committer_name() -> str:
    global _cached_committer_name
    if _cached_committer_name is None:
        username = _git_config_value("user.name")
        if not username:
            from kiln_ai.utils.config import Config

            username = Config.shared().user_id
        _cached_committer_name = f"Kiln AI for {username}"
    return _cached_committer_name


def get_committer_email() -> str:
    global _cached_committer_email
    if _cached_committer_email is None:
        email = _git_config_value("user.email")
        _cached_committer_email = email or "kiln@localhost"
    return _cached_committer_email


def reset_committer_cache() -> None:
    """Reset the cached committer name and email. Used for testing."""
    global _cached_committer_name, _cached_committer_email
    _cached_committer_name = None
    _cached_committer_email = None


class GitSyncManager:
    _GIT_EXECUTOR_TIMEOUT = 30.0
    _WRITE_LOCK_TIMEOUT = 30.0

    def __init__(
        self,
        repo_path: Path,
        auth_mode: AuthMode,
        remote_name: str = "origin",
        pat_token: str | None = None,
    ):
        self._repo_path = repo_path
        self._remote_name = remote_name
        self._pat_token = pat_token
        self._auth_mode = auth_mode
        self._git_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pygit2"
        )
        self._write_lock = threading.Lock()
        self._repo: pygit2.Repository | None = None
        self._last_sync: float = 0.0

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    def _get_repo(self) -> pygit2.Repository:
        if self._repo is None:
            self._repo = pygit2.Repository(str(self._repo_path))
        return self._repo

    async def _run_git(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._git_executor, fn, *args),
                timeout=self._GIT_EXECUTOR_TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise RemoteUnreachableError(
                "Git operation timed out. Check your connection."
            ) from None

    @asynccontextmanager
    async def write_lock(self):
        acquired = await asyncio.to_thread(
            self._write_lock.acquire, timeout=self._WRITE_LOCK_TIMEOUT
        )
        if not acquired:
            raise WriteLockTimeoutError("Another save is in progress")
        try:
            yield
        finally:
            self._write_lock.release()

    @asynccontextmanager
    async def atomic_write(self, context: str):
        """Context manager for atomic file writes with git sync.

        Acquires the write lock, ensures the repo is clean and fresh, then
        yields for the caller to perform file writes. On clean exit, dirty
        files (if any) are committed and pushed. On exception, all writes
        made within the block are rolled back to the pre-yield HEAD and the
        exception re-raises.

        Not re-entrant. The underlying write lock wraps a non-reentrant
        threading.Lock, so nested atomic_write calls on the same manager
        will block on acquisition and raise WriteLockTimeoutError. Runner
        save_context callables are invoked from the regular read path or
        @no_write_lock endpoints -- never from inside an outer atomic_write
        -- so nesting should not occur in practice.

        Args:
            context: Descriptive string used in the commit message. Examples:
                "POST /api/projects/123/tasks", "extraction job for doc 456".
        """
        async with self.write_lock():
            await self.ensure_clean()
            await self.ensure_fresh()
            pre_head = await self.get_head()
            try:
                yield
                if await self.has_dirty_files():
                    await self.commit_and_push(
                        context=context,
                        pre_request_head=pre_head,
                    )
            except Exception:
                await self.rollback(pre_head)
                raise

    async def ensure_clean(self) -> None:
        if await self._is_clean():
            return

        logger.warning("Repo dirty on write request -- running crash recovery")

        # Abort in-progress rebase/merge FIRST -- stash fails if the index
        # has unresolved conflict entries from a mid-rebase crash.
        # _state_cleanup() clears state and hard-resets to HEAD to resolve
        # any conflict entries in the index before stashing.
        state = await self._run_git(self._get_repo_state)
        if state != pygit2.enums.RepositoryState.NONE:
            logger.warning("Aborting in-progress rebase/merge")
            await self._run_git(self._state_cleanup)

        if await self.has_dirty_files():
            await self._run_git(
                self._stash_all,
                "[Kiln] Auto-recovery stash -- dirty state from prior session",
            )

        unpushed = await self._count_unpushed_commits()
        if unpushed > 0:
            logger.warning("Resetting %d unpushed commits to match remote", unpushed)
            remote_head = await self._get_remote_head_oid()
            await self._run_git(self._hard_reset, remote_head)

        if not await self._is_clean():
            raise CorruptRepoError(
                "Git repository is in an unexpected state after recovery"
            )

    async def ensure_fresh(self) -> None:
        now = time.monotonic()
        if now - self._last_sync < FRESHNESS_THRESHOLD:
            return

        try:
            await self.fetch()
        except RemoteUnreachableError:
            raise
        except Exception as e:
            raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e

        if await self.can_fast_forward():
            await self.fast_forward()

        self._last_sync = time.monotonic()

    async def ensure_fresh_for_read(self) -> None:
        """Check freshness for read requests. Fetch + fast-forward if stale.

        Unlike ensure_fresh(), this acquires the write lock only for the
        fast-forward step (not the fetch), since reads don't already hold
        the lock.
        """
        now = time.monotonic()
        if now - self._last_sync < FRESHNESS_THRESHOLD:
            return

        try:
            await self.fetch()
        except RemoteUnreachableError:
            raise
        except Exception as e:
            raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e

        if await self.can_fast_forward():
            async with self.write_lock():
                if await self.can_fast_forward():
                    await self.fast_forward()

        self._last_sync = time.monotonic()

    async def get_head(self) -> str:
        return await self._run_git(self._get_head_oid_hex)

    async def has_dirty_files(self) -> bool:
        return await self._run_git(self._has_dirty_files_sync)

    async def get_dirty_file_paths(self) -> list[str]:
        return await self._run_git(self._get_dirty_file_paths_sync)

    async def commit_and_push(self, context: str, pre_request_head: str) -> None:
        commit_oid = await self._run_git(self._create_commit, context)
        try:
            await self._run_git(self._push_sync)
        except Exception as first_push_error:
            logger.warning(
                "Push failed, attempting fetch+rebase+retry: %s",
                first_push_error,
            )
            try:
                await self.fetch()
            except Exception as fetch_err:
                raise RemoteUnreachableError(
                    f"Cannot sync with remote: {fetch_err}"
                ) from fetch_err

            rebase_ok = await self._run_git(self._rebase_onto_remote, commit_oid)
            if not rebase_ok:
                await self.rollback(pre_request_head)
                raise SyncConflictError("There was a problem saving. Please try again.")

            try:
                await self._run_git(self._push_sync)
            except Exception:
                await self.rollback(pre_request_head)
                raise SyncConflictError("There was a problem saving. Please try again.")

        self._last_sync = time.monotonic()

    async def rollback(self, pre_request_head: str) -> None:
        state = await self._run_git(self._get_repo_state)
        if state != pygit2.enums.RepositoryState.NONE:
            try:
                await self._run_git(self._state_cleanup_no_reset)
            except Exception:
                logger.warning("state_cleanup failed during rollback", exc_info=True)

        try:
            if await self.has_dirty_files():
                await self._run_git(self._stash_all, "[Kiln] Rollback stash")
        except Exception:
            logger.warning(
                "Stash failed during rollback, proceeding to reset", exc_info=True
            )

        current_head = await self.get_head()
        if current_head != pre_request_head:
            await self._run_git(self._hard_reset_from_hex, pre_request_head)

    async def fetch(self) -> None:
        try:
            await self._run_git(self._fetch_sync)
        except pygit2.GitError as e:
            raise RemoteUnreachableError(f"Cannot sync with remote: {e}") from e

    async def has_new_remote_commits(self) -> bool:
        return await self._run_git(self._has_new_remote_commits_sync)

    async def can_fast_forward(self) -> bool:
        return await self._run_git(self._can_fast_forward_sync)

    async def fast_forward(self) -> None:
        await self._run_git(self._fast_forward_sync)
        self._last_sync = time.monotonic()

    async def close(self) -> None:
        self._git_executor.shutdown(wait=True)
        if self._repo is not None:
            self._repo.free()
            self._repo = None

    def _make_remote_callbacks(self) -> pygit2.RemoteCallbacks:
        """Create RemoteCallbacks that never prompt for credentials.

        Always returns callbacks -- with PAT auth if configured, or with a
        credentials callback that raises an error.  This prevents pygit2
        from falling through to system credential helpers which may prompt
        on stdin (fatal for a headless server process).
        """
        from app.desktop.git_sync.clone import make_credentials

        return make_credentials(self._pat_token, self._auth_mode)

    # --- Synchronous helpers (run inside _git_executor) ---

    def _get_head_oid_hex(self) -> str:
        repo = self._get_repo()
        return str(repo.head.target)

    def _has_dirty_files_sync(self) -> bool:
        repo = self._get_repo()
        status = repo.status()
        for flags in status.values():
            if flags == pygit2.enums.FileStatus.IGNORED:
                continue
            if flags == pygit2.enums.FileStatus.CURRENT:
                continue
            return True
        return False

    def _get_dirty_file_paths_sync(self) -> list[str]:
        repo = self._get_repo()
        status = repo.status()
        paths: list[str] = []
        for path, flags in status.items():
            if flags == pygit2.enums.FileStatus.IGNORED:
                continue
            if flags == pygit2.enums.FileStatus.CURRENT:
                continue
            paths.append(path)
        return paths

    def _get_repo_state(self) -> pygit2.enums.RepositoryState:
        repo = self._get_repo()
        return repo.state()

    def _state_cleanup(self) -> None:
        repo = self._get_repo()
        repo.state_cleanup()
        repo.reset(repo.head.target, pygit2.enums.ResetMode.HARD)

    def _state_cleanup_no_reset(self) -> None:
        repo = self._get_repo()
        repo.state_cleanup()

    def _stash_all(self, message: str) -> None:
        repo = self._get_repo()
        sig = pygit2.Signature(get_committer_name(), get_committer_email())
        repo.stash(sig, message, include_untracked=True)

    def _hard_reset(self, oid: pygit2.Oid) -> None:
        repo = self._get_repo()
        repo.reset(oid, pygit2.enums.ResetMode.HARD)

    def _hard_reset_from_hex(self, hex_str: str) -> None:
        oid = pygit2.Oid(hex=hex_str)
        self._hard_reset(oid)

    def _create_commit(self, context: str) -> pygit2.Oid:
        repo = self._get_repo()

        status = repo.status()
        file_count = sum(
            1
            for flags in status.values()
            if flags != pygit2.enums.FileStatus.IGNORED
            and flags != pygit2.enums.FileStatus.CURRENT
        )
        if file_count == 0:
            raise CorruptRepoError(
                "_create_commit called with no dirty files -- this is a bug"
            )

        index = repo.index
        index.add_all()
        index.write()
        tree = index.write_tree()

        message = generate_commit_message(file_count, context)
        sig = pygit2.Signature(get_committer_name(), get_committer_email())

        parents = [repo.head.target]
        return repo.create_commit(repo.head.name, sig, sig, message, tree, parents)

    def _push_sync(self) -> None:
        from app.desktop.git_sync.clone import make_push_callbacks

        repo = self._get_repo()
        remote = repo.remotes[self._remote_name]
        branch_name = repo.head.shorthand

        push_errors: list[str] = []
        cred_callbacks = self._make_remote_callbacks()
        callbacks = make_push_callbacks(cred_callbacks, push_errors)
        remote.push([f"refs/heads/{branch_name}"], callbacks=callbacks)

        if push_errors:
            raise pygit2.GitError("; ".join(push_errors))

    def _fetch_sync(self) -> None:
        repo = self._get_repo()
        remote = repo.remotes[self._remote_name]
        callbacks = self._make_remote_callbacks()
        remote.fetch(callbacks=callbacks)

    async def _get_remote_head_oid(self) -> pygit2.Oid:
        return await self._run_git(self._get_remote_head_oid_sync)

    def _get_remote_head_oid_sync(self) -> pygit2.Oid:
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        ref = repo.references.get(remote_ref_name)
        if ref is None:
            raise CorruptRepoError(f"Remote tracking ref {remote_ref_name} not found")
        target = ref.target
        if not isinstance(target, pygit2.Oid):
            ref = ref.resolve()
            target = ref.target
            if not isinstance(target, pygit2.Oid):
                raise CorruptRepoError(
                    f"Remote tracking ref {remote_ref_name} is not a direct reference"
                )
        return target

    async def _count_unpushed_commits(self) -> int:
        return await self._run_git(self._count_unpushed_commits_sync)

    def _count_unpushed_commits_sync(self) -> int:
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        ref = repo.references.get(remote_ref_name)
        if ref is None:
            return 0

        local_oid = repo.head.target
        remote_oid = ref.target

        if local_oid == remote_oid:
            return 0

        ahead, _ = repo.ahead_behind(local_oid, remote_oid)
        return ahead

    async def _is_clean(self) -> bool:
        state = await self._run_git(self._get_repo_state)
        if state != pygit2.enums.RepositoryState.NONE:
            return False
        return not await self.has_dirty_files()

    def _has_new_remote_commits_sync(self) -> bool:
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        ref = repo.references.get(remote_ref_name)
        if ref is None:
            return False

        local_oid = repo.head.target
        remote_oid = ref.target

        if local_oid == remote_oid:
            return False

        _, behind = repo.ahead_behind(local_oid, remote_oid)
        return behind > 0

    def _can_fast_forward_sync(self) -> bool:
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        ref = repo.references.get(remote_ref_name)
        if ref is None:
            return False

        local_oid = repo.head.target
        remote_oid = ref.target

        if local_oid == remote_oid:
            return False

        ahead, behind = repo.ahead_behind(local_oid, remote_oid)
        return ahead == 0 and behind > 0

    def _fast_forward_sync(self) -> None:
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        ref = repo.references.get(remote_ref_name)
        if ref is None:
            logger.warning(
                "Fast-forward skipped: remote ref %s not found", remote_ref_name
            )
            return

        remote_oid = ref.target
        branch_ref = repo.references.get(f"refs/heads/{branch_name}")
        if branch_ref is None:
            logger.warning(
                "Fast-forward skipped: local branch ref refs/heads/%s not found",
                branch_name,
            )
            return

        branch_ref.set_target(remote_oid)
        repo.checkout_head(strategy=pygit2.enums.CheckoutStrategy.FORCE)

    def _rebase_onto_remote(self, local_commit_oid: pygit2.Oid) -> bool:
        """Rebase a single local commit onto the remote HEAD using cherrypick.

        We use cherrypick for single-commit rebase for simplicity:
        1. Reset branch to remote HEAD
        2. Cherrypick the local commit
        3. If no conflicts, create a new commit with the same message
        """
        repo = self._get_repo()
        branch_name = repo.head.shorthand
        remote_ref_name = f"refs/remotes/{self._remote_name}/{branch_name}"
        remote_ref = repo.references.get(remote_ref_name)
        if remote_ref is None:
            return False

        remote_target = remote_ref.target
        if not isinstance(remote_target, pygit2.Oid):
            return False

        local_commit = repo.get(local_commit_oid)
        if local_commit is None or not isinstance(local_commit, pygit2.Commit):
            return False

        try:
            repo.reset(remote_target, pygit2.enums.ResetMode.HARD)

            repo.cherrypick(local_commit_oid)

            if repo.index.conflicts:
                repo.state_cleanup()
                repo.reset(remote_target, pygit2.enums.ResetMode.HARD)
                return False

            tree = repo.index.write_tree()
            sig = pygit2.Signature(get_committer_name(), get_committer_email())
            repo.create_commit(
                f"refs/heads/{branch_name}",
                sig,
                sig,
                local_commit.message,
                tree,
                [remote_target],
            )
            repo.state_cleanup()
            repo.checkout_head(strategy=pygit2.enums.CheckoutStrategy.FORCE)
            return True
        except Exception:
            try:
                repo.state_cleanup()
                repo.reset(remote_target, pygit2.enums.ResetMode.HARD)
            except Exception:
                pass
            return False
