from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.eval import Eval
from kiln_ai.datamodel.spec import Spec, SpecStatus, TaskSample
from kiln_ai.datamodel.spec_properties import SpecProperties
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id


class UpdateSpecRequest(BaseModel):
    name: FilenameString | None = None
    definition: str | None = None
    properties: SpecProperties | None = Field(
        default=None,
        discriminator="spec_type",
    )
    priority: Priority | None = None
    status: SpecStatus | None = None
    tags: List[str] | None = None


def spec_from_id(project_id: str, task_id: str, spec_id: str) -> Spec:
    parent_task = task_from_id(project_id, task_id)
    spec = Spec.from_id_and_parent_path(spec_id, parent_task.path)
    if spec:
        return spec

    raise HTTPException(
        status_code=404,
        detail=f"Spec not found. ID: {spec_id}",
    )


class SpecCreationRequest(BaseModel):
    name: FilenameString
    definition: str
    properties: SpecProperties = Field(
        discriminator="spec_type",
    )
    priority: Priority
    status: SpecStatus
    tags: List[str]
    eval_id: str
    task_sample: TaskSample | None = None


# TODO: this endpoint doesn't make the eval with the eval tags etc. like we did with the other endpoint. Need to fix.
# Probably just remove this endpoint and use the other endpoint instead. And add back "use copilot"?
# Or wait we probably need to expose this as a public API so people can use it?
def connect_spec_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec")
    async def create_spec(
        project_id: str, task_id: str, spec_data: SpecCreationRequest
    ) -> Spec:
        task = task_from_id(project_id, task_id)
        spec = Spec(
            parent=task,
            name=spec_data.name,
            definition=spec_data.definition,
            properties=spec_data.properties,
            priority=spec_data.priority,
            status=spec_data.status,
            tags=spec_data.tags,
            eval_id=spec_data.eval_id,
            task_sample=spec_data.task_sample,
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
        project_id: str, task_id: str, spec_id: str, request: UpdateSpecRequest
    ) -> Spec:
        spec = spec_from_id(project_id, task_id, spec_id)

        # Update all provided fields
        if request.name is not None:
            spec.name = request.name
        if request.definition is not None:
            spec.definition = request.definition
        if request.properties is not None:
            spec.properties = request.properties
        if request.priority is not None:
            spec.priority = request.priority
        if request.status is not None:
            spec.status = request.status
        if request.tags is not None:
            spec.tags = request.tags

        spec.save_to_file()
        return spec

    @app.delete("/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}")
    async def delete_spec(project_id: str, task_id: str, spec_id: str) -> None:
        spec = spec_from_id(project_id, task_id, spec_id)

        # Delete associated eval if it exists
        if spec.eval_id:
            parent_task = task_from_id(project_id, task_id)
            eval = Eval.from_id_and_parent_path(spec.eval_id, parent_task.path)
            if eval:
                eval.delete()

        spec.delete()
