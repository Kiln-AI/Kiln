import os
from pathlib import Path as FilePath
from typing import Annotated, Any, Dict

from fastapi import Body, FastAPI, HTTPException, Path, Query
from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config
from kiln_ai.utils.project_utils import (
    DuplicateProjectError,
    check_duplicate_project_id,
    remove_project_from_config,
)
from kiln_ai.utils.project_utils import (
    project_from_id as project_from_id_core,
)

from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)


def default_project_path():
    return os.path.join(FilePath.home(), "Kiln Projects")


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
    @app.post(
        "/api/projects",
        summary="Create Project",
        tags=["Projects"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_project(project: Project) -> Project:
        project_path = os.path.join(default_project_path(), project.name)
        if os.path.exists(project_path):
            raise HTTPException(
                status_code=400,
                detail="Project with this folder name already exists. Please choose a different name or rename the prior project's folder.",
            )

        os.makedirs(project_path)
        project_file = os.path.join(project_path, "project.kiln")
        project.path = FilePath(project_file)
        project.save_to_file()

        # add to projects list
        add_project_to_config(project_file)

        # Add path, which is usually excluded
        return project

    @app.patch(
        "/api/projects/{project_id}",
        summary="Update Project",
        tags=["Projects"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit project? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_project(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        project_updates: Annotated[
            Dict[str, Any], Body(description="Fields to update on the project.")
        ],
    ) -> Project:
        original_project = project_from_id(project_id)
        updated_project = original_project.model_copy(update=project_updates)
        # Force validation using model_validate()
        Project.model_validate(updated_project.model_dump())
        updated_project.save_to_file()
        return updated_project

    @app.get(
        "/api/projects",
        summary="List Projects",
        tags=["Projects"],
        openapi_extra=ALLOW_AGENT,
    )
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

    @app.get(
        "/api/projects/{project_id}",
        summary="Get Project",
        tags=["Projects"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_project(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> Project:
        return project_from_id(project_id)

    @app.post(
        "/api/import_project",
        summary="Import Project",
        tags=["Projects"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to import a project? Kiln projects can contain code that runs on your machine."
        ),
    )
    async def import_project(
        project_path: Annotated[
            str, Query(description="File path to the project.kiln file to import.")
        ],
        remove_conflicting_id: Annotated[
            bool,
            Query(
                description="When true and a duplicate project ID conflict is detected, "
                "remove the existing project registration before importing."
            ),
        ] = False,
        trusted: Annotated[
            bool,
            Query(
                description="Must be true to confirm trust before importing. "
                "Kiln projects can contain code that runs on your machine."
            ),
        ] = False,
    ) -> Project:
        if not trusted:
            raise HTTPException(
                status_code=400,
                detail="Import cancelled: you must confirm you trust this project before importing. Kiln projects can contain code that runs on your machine.",
            )
        if project_path is None or not os.path.exists(project_path):
            raise HTTPException(
                status_code=400,
                detail="Project not found. Check the path and try again.",
            )

        try:
            project = Project.load_from_file(FilePath(project_path))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load project. The file is invalid: {e}",
            )

        if project.id is not None:
            try:
                check_duplicate_project_id(project.id, project_path)
            except DuplicateProjectError as e:
                if not remove_conflicting_id:
                    raise HTTPException(status_code=409, detail=str(e))
                # Resolve and de-register the conflicting project before proceeding.
                # Layering caveat: libs/server cannot call GitSyncRegistry.unregister
                # (app layer), so if the removed project was git-synced and had a live
                # manager this session, its in-memory manager lingers until restart.
                conflicting = project_from_id_core(project.id)
                if conflicting is not None:
                    remove_project_from_config(str(conflicting.path))
                # If conflicting is None the project is already gone from
                # config (e.g. manually removed); safe to fall through to
                # add_project_to_config which will (re-)register the path.

        # add to projects list
        add_project_to_config(project_path)

        return project
