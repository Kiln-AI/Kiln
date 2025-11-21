from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.spec import Spec, SpecStatus, SpecType
from kiln_ai.datamodel.spec_properties import SpecProperties
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


class SpecUpsertRequest(BaseModel):
    name: FilenameString
    description: str
    properties: SpecProperties | None
    type: SpecType
    priority: Priority
    status: SpecStatus
    tags: List[str]
    eval_id: str | None


def connect_spec_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec")
    async def create_spec(
        project_id: str, task_id: str, spec_data: SpecUpsertRequest
    ) -> Spec:
        task = task_from_id(project_id, task_id)
        spec = Spec(
            parent=task,
            name=spec_data.name,
            description=spec_data.description,
            properties=spec_data.properties,
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
        return parent_task.specs(readonly=True)

    @app.get("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def get_spec(project_id: str, task_id: str, spec_id: str) -> Spec:
        return spec_from_id(project_id, task_id, spec_id)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def update_spec(
        project_id: str, task_id: str, spec_id: str, spec_data: SpecUpsertRequest
    ) -> Spec:
        spec = spec_from_id(project_id, task_id, spec_id)

        spec.name = spec_data.name
        spec.description = spec_data.description
        spec.type = spec_data.type
        spec.properties = spec_data.properties
        spec.priority = spec_data.priority
        spec.status = spec_data.status
        spec.tags = spec_data.tags
        spec.eval_id = spec_data.eval_id

        spec.save_to_file()
        return spec
