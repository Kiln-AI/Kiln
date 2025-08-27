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
