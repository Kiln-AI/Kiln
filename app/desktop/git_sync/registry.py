import logging
import threading
from pathlib import Path

from app.desktop.git_sync.git_sync_manager import GitSyncManager

logger = logging.getLogger(__name__)


class GitSyncRegistry:
    """Singleton registry of GitSyncManager instances, keyed by repo path."""

    # Class-level mutable state: intentional singleton pattern.
    # All instances share one registry; access is guarded by _lock.
    _managers: dict[Path, GitSyncManager] = {}
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
        cls, repo_path: Path, remote_name: str = "origin"
    ) -> GitSyncManager:
        """Return existing manager or create a new one. Thread-safe."""
        resolved = repo_path.resolve()
        with cls._lock:
            if resolved not in cls._managers:
                manager = GitSyncManager(repo_path=resolved, remote_name=remote_name)
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
            return cls._managers[resolved]

    @classmethod
    def reset(cls) -> None:
        """Clear all cached managers. For test teardown."""
        with cls._lock:
            for manager in cls._managers.values():
                manager._git_executor.shutdown(wait=False)
            cls._managers.clear()
