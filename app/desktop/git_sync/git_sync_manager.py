import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

T = TypeVar("T")

FRESHNESS_THRESHOLD = 15.0
KILN_COMMITTER_NAME = "Kiln AI"
KILN_COMMITTER_EMAIL = "sync@kiln.ai"


class GitSyncManager:
    _GIT_EXECUTOR_TIMEOUT = 30.0
    _WRITE_LOCK_TIMEOUT = 30.0

    def __init__(self, repo_path: Path, remote_name: str = "origin"):
        self._repo_path = repo_path
        self._remote_name = remote_name
        self._git_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pygit2"
        )
        self._write_lock = threading.Lock()
        self._repo: pygit2.Repository | None = None
        self._last_sync: float = 0.0

    def _get_repo(self) -> pygit2.Repository:
        if self._repo is None:
            self._repo = pygit2.Repository(str(self._repo_path))
        return self._repo

    async def _run_git(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._git_executor, fn, *args),
            timeout=self._GIT_EXECUTOR_TIMEOUT,
        )

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

    async def ensure_clean(self) -> None:
        if await self._is_clean():
            return

        logger.warning("Repo dirty on write request -- running crash recovery")

        if await self.has_dirty_files():
            await self._run_git(
                self._stash_all,
                "[Kiln] Auto-recovery stash -- dirty state from prior session",
            )

        state = await self._run_git(self._get_repo_state)
        if state != pygit2.enums.RepositoryState.NONE:
            logger.warning("Aborting in-progress rebase/merge")
            await self._run_git(self._state_cleanup)

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

    async def get_head(self) -> str:
        return await self._run_git(self._get_head_oid_hex)

    async def has_dirty_files(self) -> bool:
        return await self._run_git(self._has_dirty_files_sync)

    async def commit_and_push(self, api_path: str, pre_request_head: str) -> None:
        commit_oid = await self._run_git(self._create_commit, api_path)
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
        if await self.has_dirty_files():
            await self._run_git(self._stash_all, "[Kiln] Rollback stash")

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

    def _get_repo_state(self) -> pygit2.enums.RepositoryState:
        repo = self._get_repo()
        return repo.state()

    def _state_cleanup(self) -> None:
        repo = self._get_repo()
        repo.state_cleanup()

    def _stash_all(self, message: str) -> None:
        repo = self._get_repo()
        sig = pygit2.Signature(KILN_COMMITTER_NAME, KILN_COMMITTER_EMAIL)
        repo.stash(sig, message, include_untracked=True)

    def _hard_reset(self, oid: pygit2.Oid) -> None:
        repo = self._get_repo()
        repo.reset(oid, pygit2.enums.ResetMode.HARD)

    def _hard_reset_from_hex(self, hex_str: str) -> None:
        oid = pygit2.Oid(hex=hex_str)
        self._hard_reset(oid)

    def _create_commit(self, api_path: str) -> pygit2.Oid:
        repo = self._get_repo()

        status = repo.status()
        file_count = sum(
            1
            for flags in status.values()
            if flags != pygit2.enums.FileStatus.IGNORED
            and flags != pygit2.enums.FileStatus.CURRENT
        )
        if file_count == 0:
            logger.warning("_create_commit called with no dirty files")
            file_count = 1

        index = repo.index
        index.add_all()
        index.write()
        tree = index.write_tree()

        message = generate_commit_message(file_count, api_path)
        sig = pygit2.Signature(KILN_COMMITTER_NAME, KILN_COMMITTER_EMAIL)

        parents = [repo.head.target]
        return repo.create_commit(repo.head.name, sig, sig, message, tree, parents)

    def _push_sync(self) -> None:
        repo = self._get_repo()
        remote = repo.remotes[self._remote_name]
        branch_name = repo.head.shorthand

        push_errors: list[str] = []

        class PushCallbacks(pygit2.RemoteCallbacks):
            def push_update_reference(self, refname: str, message: str | None) -> None:
                if message is not None:
                    push_errors.append(f"Push rejected for {refname}: {message}")

        callbacks = PushCallbacks()
        remote.push([f"refs/heads/{branch_name}"], callbacks=callbacks)

        if push_errors:
            raise pygit2.GitError("; ".join(push_errors))

    def _fetch_sync(self) -> None:
        repo = self._get_repo()
        remote = repo.remotes[self._remote_name]
        remote.fetch()

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
            sig = pygit2.Signature(KILN_COMMITTER_NAME, KILN_COMMITTER_EMAIL)
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
        except pygit2.GitError:
            try:
                repo.state_cleanup()
                repo.reset(remote_target, pygit2.enums.ResetMode.HARD)
            except Exception:
                pass
            return False
