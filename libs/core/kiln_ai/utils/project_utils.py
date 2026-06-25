from pathlib import Path

from kiln_ai.datamodel.project import Project
from kiln_ai.utils.config import Config


def project_from_id(project_id: str) -> Project | None:
    project_paths = Config.shared().projects
    if project_paths is not None:
        for project_path in project_paths:
            try:
                project = Project.load_from_file(project_path)
                if project.id == project_id:
                    return project
            except Exception:
                # deleted files are possible continue with the rest
                continue

    return None


def remove_project_from_config(project_path: str) -> str | None:
    """Remove a project from Kiln config. Does NOT delete files from disk.

    Returns the git-sync clone_path if the project was git-synced, else None.
    """
    projects = Config.shared().projects or []
    Config.shared().save_setting("projects", [p for p in projects if p != project_path])

    git_sync = Config.shared().git_sync_projects or {}
    clone_path = None
    if project_path in git_sync:
        clone_path = git_sync[project_path].get("clone_path")
        git_sync.pop(project_path)
        Config.shared().save_setting("git_sync_projects", git_sync)
    return clone_path


class DuplicateProjectError(Exception):
    """Raised when trying to import a project whose ID is already registered."""

    def __init__(self, message: str, same_path: bool):
        super().__init__(message)
        self.same_path = same_path


def check_duplicate_project_id(project_id: str, new_project_path: str) -> None:
    """Check if a project with the given ID already exists in the config.

    Args:
        project_id: The ID of the project being imported.
        new_project_path: The filesystem path to the project.kiln file.

    Raises:
        DuplicateProjectError: If a project with the same ID is already imported.
    """
    project_paths = Config.shared().projects
    if project_paths is None:
        return

    new_resolved = str(Path(new_project_path).resolve())

    for existing_path in project_paths:
        try:
            project = Project.load_from_file(existing_path)
        except Exception:
            continue

        if project.id != project_id:
            continue

        existing_resolved = str(Path(existing_path).resolve())
        if existing_resolved == new_resolved:
            raise DuplicateProjectError(
                "This project is already imported.",
                same_path=True,
            )
        else:
            raise DuplicateProjectError(
                f'You already have a project with this ID. You must remove project "{project.name}" before adding this.',
                same_path=False,
            )
