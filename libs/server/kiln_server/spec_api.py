from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.spec import Spec, SpecPriority, SpecStatus, SpecType
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id


def spec_from_id(project_id: str, task_id: str, spec_id: str) -> Spec:
    parent_task = task_from_id(project_id, task_id)
    spec = Spec.from_id_and_parent_path(spec_id, parent_task.path)
    if spec:
        return spec

    raise HTTPException(
        status_code=404,
        detail=f"Spec not found. ID: {spec_id}",
    )


class SpecCreateRequest(BaseModel):
    name: str
    description: str
    type: SpecType
    priority: SpecPriority = SpecPriority.high
    status: SpecStatus = SpecStatus.not_started
    tags: List[str] = Field(default_factory=list)
    eval_id: str | None = None


class SpecUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    type: SpecType | None = None
    priority: SpecPriority | None = None
    status: SpecStatus | None = None
    tags: List[str] | None = None
    eval_id: str | None = None


def connect_spec_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec")
    async def create_spec(
        project_id: str, task_id: str, spec_data: SpecCreateRequest
    ) -> Spec:
        parent_task = task_from_id(project_id, task_id)

        spec = Spec(
            parent=parent_task,
            name=spec_data.name,
            description=spec_data.description,
            type=spec_data.type,
            priority=spec_data.priority,
            status=spec_data.status,
            tags=spec_data.tags,
            eval_id=spec_data.eval_id,
        )
        spec.save_to_file()
        return spec

    @app.get("/api/projects/{project_id}/tasks/{task_id}/specs")
    async def get_specs(project_id: str, task_id: str) -> List[Spec]:
        parent_task = task_from_id(project_id, task_id)
        return parent_task.specs()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def get_spec(project_id: str, task_id: str, spec_id: str) -> Spec:
        return spec_from_id(project_id, task_id, spec_id)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def update_spec(
        project_id: str, task_id: str, spec_id: str, spec_updates: SpecUpdateRequest
    ) -> Spec:
        spec = spec_from_id(project_id, task_id, spec_id)

        update_dict = spec_updates.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(spec, key, value)

        spec.save_to_file()
        return spec
