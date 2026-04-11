from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from app.desktop.git_sync.config import AuthMode
from app.desktop.git_sync.git_sync_manager import GitSyncManager

if TYPE_CHECKING:
    from app.desktop.git_sync.background_sync import BackgroundSync

logger = logging.getLogger(__name__)


class GitSyncRegistry:
    """Singleton registry of GitSyncManager instances, keyed by repo path."""

    # Class-level mutable state: intentional singleton pattern.
    # All instances share one registry; access is guarded by _lock.
    _managers: dict[Path, GitSyncManager] = {}
    _background_syncs: dict[Path, BackgroundSync] = {}
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_manager(cls, repo_path: Path) -> GitSyncManager | None:
        # No lock needed: CPython's GIL makes dict.get atomic, and this is
        # a read-only lookup. Mutations go through _lock-guarded methods.
        return cls._managers.get(repo_path.resolve())

    @classmethod
    def register(cls, repo_path: Path, manager: GitSyncManager) -> None:
        with cls._lock:
            cls._managers[repo_path.resolve()] = manager

    @classmethod
    def get_or_create(
        cls,
        repo_path: Path,
        auth_mode: AuthMode,
        remote_name: str = "origin",
        pat_token: str | None = None,
        oauth_token: str | None = None,
    ) -> GitSyncManager:
        """Return existing manager or create a new one. Thread-safe."""
        resolved = repo_path.resolve()
        with cls._lock:
            if resolved not in cls._managers:
                manager = GitSyncManager(
                    repo_path=resolved,
                    remote_name=remote_name,
                    pat_token=pat_token,
                    oauth_token=oauth_token,
                    auth_mode=auth_mode,
                )
                cls._managers[resolved] = manager
            else:
                existing = cls._managers[resolved]
                if existing._remote_name != remote_name:
                    logger.debug(
                        "get_or_create called with remote_name=%r but existing "
                        "manager uses remote_name=%r for %s",
                        remote_name,
                        existing._remote_name,
                        resolved,
                    )
                if pat_token is not None and existing._pat_token != pat_token:
                    existing._pat_token = pat_token
                if oauth_token is not None and existing._oauth_token != oauth_token:
                    existing._oauth_token = oauth_token
                if existing._auth_mode != auth_mode:
                    existing._auth_mode = auth_mode
            return cls._managers[resolved]

    @classmethod
    def get_background_sync(cls, repo_path: Path) -> BackgroundSync | None:
        return cls._background_syncs.get(repo_path.resolve())

    @classmethod
    def register_background_sync(cls, repo_path: Path, bg_sync: BackgroundSync) -> None:
        with cls._lock:
            cls._background_syncs[repo_path.resolve()] = bg_sync

    @classmethod
    def all_background_syncs(cls) -> list[BackgroundSync]:
        """Return a snapshot of all registered background syncs."""
        return list(cls._background_syncs.values())

    @classmethod
    def all_managers(cls) -> list[GitSyncManager]:
        """Return a snapshot of all registered managers."""
        return list(cls._managers.values())

    @classmethod
    def reset(cls) -> None:
        """Clear all cached managers. For test teardown."""
        with cls._lock:
            for manager in cls._managers.values():
                manager._git_executor.shutdown(wait=False)
            cls._managers.clear()
            cls._background_syncs.clear()
