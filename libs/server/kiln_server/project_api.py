import os
from pathlib import Path as FilePath
from typing import Annotated, Any, Dict

from fastapi import Body, FastAPI, HTTPException, Path, Query
from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config
from kiln_ai.utils.project_utils import (
    DuplicateProjectError,
    check_duplicate_project_id,
)
from kiln_ai.utils.project_utils import (
    project_from_id as project_from_id_core,
)
from pydantic import BaseModel

from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    agent_policy_require_approval,
)


class EntitySummary(BaseModel):
    id: str | None
    name: str
    description: str | None = None


class EvalSummary(EntitySummary):
    config_count: int


class TaskSummary(EntitySummary):
    run_count: int
    evals: list[EvalSummary]
    prompts: list[EntitySummary]
    finetunes: list[EntitySummary]
    run_configs: list[EntitySummary]
    dataset_splits: list[EntitySummary]
    prompt_optimization_jobs: list[EntitySummary]
    specs: list[EntitySummary]


class ProjectContext(BaseModel):
    id: str | None
    name: str
    description: str | None = None
    tasks: list[TaskSummary]
    skills: list[EntitySummary]
    documents: list[EntitySummary]
    extractor_configs: list[EntitySummary]
    chunker_configs: list[EntitySummary]
    embedding_configs: list[EntitySummary]
    rag_configs: list[EntitySummary]
    vector_store_configs: list[EntitySummary]
    external_tool_servers: list[EntitySummary]
    reranker_configs: list[EntitySummary]


def _summarize(item: Any) -> EntitySummary:
    return EntitySummary(
        id=item.id,
        name=item.name,
        description=getattr(item, "description", None),
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

    @app.get(
        "/api/projects/{project_id}/context",
        summary="Project Context Dump",
        tags=["Projects"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_project_context(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
    ) -> ProjectContext:
        project = project_from_id(project_id)

        tasks: list[TaskSummary] = []
        for t in project.tasks(readonly=True):
            evals = [
                EvalSummary(
                    id=e.id,
                    name=e.name,
                    description=getattr(e, "description", None),
                    config_count=len(e.configs(readonly=True)),
                )
                for e in t.evals(readonly=True)
            ]
            tasks.append(
                TaskSummary(
                    id=t.id,
                    name=t.name,
                    description=getattr(t, "description", None),
                    run_count=len(t.runs(readonly=True)),
                    evals=evals,
                    prompts=[_summarize(p) for p in t.prompts(readonly=True)],
                    finetunes=[_summarize(f) for f in t.finetunes(readonly=True)],
                    run_configs=[_summarize(rc) for rc in t.run_configs(readonly=True)],
                    dataset_splits=[
                        _summarize(d) for d in t.dataset_splits(readonly=True)
                    ],
                    prompt_optimization_jobs=[
                        _summarize(j) for j in t.prompt_optimization_jobs(readonly=True)
                    ],
                    specs=[_summarize(s) for s in t.specs(readonly=True)],
                )
            )

        return ProjectContext(
            id=project.id,
            name=project.name,
            description=project.description,
            tasks=tasks,
            skills=[_summarize(s) for s in project.skills(readonly=True)],
            documents=[_summarize(d) for d in project.documents(readonly=True)],
            extractor_configs=[
                _summarize(x) for x in project.extractor_configs(readonly=True)
            ],
            chunker_configs=[
                _summarize(x) for x in project.chunker_configs(readonly=True)
            ],
            embedding_configs=[
                _summarize(x) for x in project.embedding_configs(readonly=True)
            ],
            rag_configs=[_summarize(x) for x in project.rag_configs(readonly=True)],
            vector_store_configs=[
                _summarize(x) for x in project.vector_store_configs(readonly=True)
            ],
            external_tool_servers=[
                _summarize(x) for x in project.external_tool_servers(readonly=True)
            ],
            reranker_configs=[
                _summarize(x) for x in project.reranker_configs(readonly=True)
            ],
        )

    @app.post(
        "/api/import_project",
        summary="Import Project",
        tags=["Projects"],
        openapi_extra=ALLOW_AGENT,
    )
    async def import_project(
        project_path: Annotated[
            str, Query(description="File path to the project.kiln file to import.")
        ],
    ) -> Project:
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
                raise HTTPException(status_code=409, detail=str(e))

        # add to projects list
        add_project_to_config(project_path)

        return project
