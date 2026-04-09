from typing import Literal, TypedDict

from kiln_ai.utils.config import Config

AuthMode = Literal["system_keys", "pat_token"]


class GitSyncProjectConfig(TypedDict):
    sync_mode: str  # "auto" | "manual"
    auth_mode: AuthMode
    remote_name: str
    branch: str
    clone_path: str | None
    git_url: str | None
    pat_token: str | None


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
        auth_mode=project_raw.get("auth_mode", "system_keys"),
        remote_name=project_raw.get("remote_name", "origin"),
        branch=project_raw.get("branch", "main"),
        clone_path=project_raw.get("clone_path"),
        git_url=project_raw.get("git_url"),
        pat_token=project_raw.get("pat_token"),
    )


def save_git_sync_config(project_id: str, project_config: GitSyncProjectConfig) -> None:
    config = Config.shared()
    raw = config.git_sync_projects or {}
    raw[project_id] = dict(project_config)
    config.git_sync_projects = raw


def delete_git_sync_config(project_id: str) -> None:
    config = Config.shared()
    raw = config.git_sync_projects or {}
    raw.pop(project_id, None)
    config.git_sync_projects = raw
