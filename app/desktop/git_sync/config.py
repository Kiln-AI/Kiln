from typing import TypedDict

from kiln_ai.utils.config import Config


class GitSyncProjectConfig(TypedDict):
    sync_mode: str  # "auto" | "manual"
    remote_name: str
    branch: str
    clone_path: str | None


def get_git_sync_config(project_id: str) -> GitSyncProjectConfig | None:
    config = Config.shared()
    raw = config.git_sync_projects
    if raw is None:
        return None

    project_raw = raw.get(project_id)
    if project_raw is None:
        return None

    return GitSyncProjectConfig(
        sync_mode=project_raw.get("sync_mode", "manual"),
        remote_name=project_raw.get("remote_name", "origin"),
        branch=project_raw.get("branch", "main"),
        clone_path=project_raw.get("clone_path"),
    )
