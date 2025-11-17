from typing import List, Optional

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.spec import Spec, SpecPriority, SpecStatus, SpecType
from pydantic import BaseModel

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
    priority: Optional[SpecPriority] = None
    status: Optional[SpecStatus] = None
    tags: Optional[List[str]] = None
    eval_id: Optional[str] = None


class SpecUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
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

        spec_kwargs = {
            "parent": parent_task,
            "name": spec_data.name,
            "description": spec_data.description,
            "type": spec_data.type,
        }
        if spec_data.priority is not None:
            spec_kwargs["priority"] = spec_data.priority
        if spec_data.status is not None:
            spec_kwargs["status"] = spec_data.status
        if spec_data.tags is not None:
            spec_kwargs["tags"] = spec_data.tags
        if spec_data.eval_id is not None:
            spec_kwargs["eval_id"] = spec_data.eval_id

        spec = Spec(**spec_kwargs)
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
