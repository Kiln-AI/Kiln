import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import Project
from kiln_ai.datamodel.registry import project_from_id as project_from_id_core
from kiln_ai.utils.config import Config


def default_project_path():
    return os.path.join(Path.home(), "Kiln Projects")


def project_from_id(project_id: str) -> Project:
    project = project_from_id_core(project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project not found. ID: {project_id}",
        )
    return project


def add_project_to_config(project_path: str):
    projects = Config.shared().projects
    if not isinstance(projects, list):
        projects = []
    if project_path not in projects:
        projects.append(project_path)
        Config.shared().save_setting("projects", projects)


def connect_project_api(app: FastAPI):
    @app.post("/api/project")
    async def create_project(project: Project) -> Project:
        project_path = os.path.join(default_project_path(), project.name)
        if os.path.exists(project_path):
            raise HTTPException(
                status_code=400,
                detail="Project with this folder name already exists. Please choose a different name or rename the prior project's folder.",
            )

        os.makedirs(project_path)
        project_file = os.path.join(project_path, "project.kiln")
        project.path = Path(project_file)
        project.save_to_file()

        # add to projects list
        add_project_to_config(project_file)

        # Add path, which is usually excluded
        return project

    @app.patch("/api/project/{project_id}")
    async def update_project(
        project_id: str, project_updates: Dict[str, Any]
    ) -> Project:
        original_project = project_from_id(project_id)
        updated_project = original_project.model_copy(update=project_updates)
        # Force validation using model_validate()
        Project.model_validate(updated_project.model_dump())
        updated_project.save_to_file()
        return updated_project

    @app.get("/api/projects")
    async def get_projects() -> list[Project]:
        project_paths = Config.shared().projects
        projects = []
        for project_path in project_paths if project_paths is not None else []:
            try:
                project = Project.load_from_file(project_path)
                json_project = project.model_dump()
                json_project["path"] = project_path
                projects.append(json_project)
            except Exception:
                # deleted files are possible continue with the rest
                continue

        return projects

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> Project:
        return project_from_id(project_id)

    # Removes the project, but does not delete the files from disk
    @app.delete("/api/projects/{project_id}")
    async def delete_project(project_id: str) -> dict:
        project = project_from_id(project_id)

        # Remove from config
        projects_before = Config.shared().projects
        projects_after = [p for p in projects_before if p != str(project.path)]
        Config.shared().save_setting("projects", projects_after)

        return {"message": f"Project removed. ID: {project_id}"}

    @app.post("/api/import_project")
    async def import_project(project_path: str) -> Project:
        if project_path is None or not os.path.exists(project_path):
            raise HTTPException(
                status_code=400,
                detail="Project not found. Check the path and try again.",
            )

        try:
            project = Project.load_from_file(Path(project_path))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load project. The file be invalid: {e}",
            )

        # add to projects list
        add_project_to_config(project_path)

        return project
