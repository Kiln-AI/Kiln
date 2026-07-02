from __future__ import annotations

from pathlib import Path

from kiln_ai.utils.git_sync_protocols import SaveContext

from app.desktop.git_sync.config import get_git_sync_config, project_path_from_id
from app.desktop.git_sync.git_sync_manager import GitSyncManager
from app.desktop.git_sync.registry import GitSyncRegistry


def get_manager_for_project(project_id: str) -> GitSyncManager | None:
    """Resolve a project_id to its GitSyncManager when auto-sync is active.

    Request-free mirror of GitSyncMiddleware._get_manager_for_request (minus the
    URL parsing). Returns None for every "not active" branch: the project has no
    path, no git-sync config, sync_mode is not "auto", or no clone_path is set.

    Config is keyed by project_path; the manager is keyed by clone_path. The
    manager is always obtained via GitSyncRegistry.get_or_create so the single
    per-clone-path manager (and its executor + non-reentrant write lock) is
    shared with the HTTP path.
    """
    project_path = project_path_from_id(project_id)
    if project_path is None:
        return None

    config = get_git_sync_config(project_path)
    if config is None:
        return None

    if config["sync_mode"] != "auto":
        return None

    clone_path = config.get("clone_path")
    if clone_path is None:
        return None

    return GitSyncRegistry.get_or_create(
        repo_path=Path(clone_path),
        remote_name=config["remote_name"],
        pat_token=config.get("pat_token"),
        oauth_token=config.get("oauth_token"),
        auth_mode=config["auth_mode"],
    )


def save_context_for_project(project_id: str, context: str) -> SaveContext | None:
    """Return a SaveContext wrapping writes in manager.atomic_write(context=...),
    or None when git sync is not active for this project.

    Mirrors build_save_context(request) for callers that have only a project_id
    (e.g. background job workers). Runners coalesce None to a no-op context.
    """
    manager = get_manager_for_project(project_id)
    if manager is None:
        return None

    bg_sync = GitSyncRegistry.get_background_sync(manager.repo_path)
    if bg_sync is not None:
        bg_sync.notify_request()

    def factory():
        return manager.atomic_write(context=context)

    return factory
