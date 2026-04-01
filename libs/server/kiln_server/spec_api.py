import logging
from typing import List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import Priority
from kiln_ai.datamodel.eval import Eval
from kiln_ai.datamodel.spec import Spec, SpecStatus, TaskSample
from kiln_ai.datamodel.spec_properties import SpecProperties
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id
from kiln_server.utils.spec_utils import (
    generate_spec_eval_filter_ids,
    generate_spec_eval_tags,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_template,
)

logger = logging.getLogger(__name__)


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
    priority: Priority = Field(default=Priority.p1)
    status: SpecStatus = Field(default=SpecStatus.active)
    tags: List[str] = Field(default_factory=list)
    evaluate_full_trace: bool = Field(default=False)
    task_sample: TaskSample | None = None


def connect_spec_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/spec")
    async def create_spec(
        project_id: str, task_id: str, spec_data: SpecCreationRequest
    ) -> Spec:
        task = task_from_id(project_id, task_id)

        spec_type = spec_data.properties["spec_type"]

        eval_tag, train_tag, golden_tag = generate_spec_eval_tags(spec_data.name)
        eval_set_filter_id, train_set_filter_id, eval_configs_filter_id = (
            generate_spec_eval_filter_ids(eval_tag, train_tag, golden_tag)
        )

        template = spec_eval_template(spec_type)
        output_scores = [spec_eval_output_score(spec_data.name)]
        evaluation_data_type = spec_eval_data_type(
            spec_type, spec_data.evaluate_full_trace
        )

        eval_model = Eval(
            parent=task,
            name=spec_data.name,
            description=None,
            template=template,
            output_scores=output_scores,
            eval_set_filter_id=eval_set_filter_id,
            train_set_filter_id=train_set_filter_id,
            eval_configs_filter_id=eval_configs_filter_id,
            template_properties=None,
            evaluation_data_type=evaluation_data_type,
        )

        spec = Spec(
            parent=task,
            name=spec_data.name,
            definition=spec_data.definition,
            properties=spec_data.properties,
            priority=spec_data.priority,
            status=spec_data.status,
            tags=spec_data.tags,
            eval_id=eval_model.id,
            task_sample=spec_data.task_sample,
        )

        eval_model.save_to_file()
        try:
            spec.save_to_file()
        except Exception:
            eval_model.delete()
            raise

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
