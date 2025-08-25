from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config


def all_projects() -> list[Project]:
    project_paths = Config.shared().projects
    if project_paths is None:
        return []
    projects = []
    for project_path in project_paths:
        try:
            projects.append(Project.load_from_file(project_path))
        except Exception:
            # deleted files are possible continue with the rest
            continue
    return projects
