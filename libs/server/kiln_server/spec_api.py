import logging
from typing import Annotated, List

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel.basemodel import FilenameString
from kiln_ai.datamodel.datamodel_enums import EvalStatus, Priority
from kiln_ai.datamodel.eval import Eval
from kiln_ai.datamodel.spec import Spec, SpecStatus, TaskSample
from kiln_ai.datamodel.spec_properties import SpecProperties
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import (
    ALLOW_AGENT,
    DENY_AGENT,
    agent_policy_require_approval,
)
from kiln_server.utils.spec_utils import (
    generate_spec_eval_filter_ids,
    generate_spec_eval_tags,
    spec_eval_data_type,
    spec_eval_output_score,
    spec_eval_template,
)

logger = logging.getLogger(__name__)


class UpdateSpecRequest(BaseModel):
    """Request to update a spec."""

    name: FilenameString | None = Field(default=None, description="The updated name.")
    definition: str | None = Field(default=None, description="The updated definition.")
    properties: SpecProperties | None = Field(
        default=None,
        description="The updated spec properties.",
        discriminator="spec_type",
    )
    priority: Priority | None = Field(default=None, description="The updated priority.")
    status: SpecStatus | None = Field(default=None, description="The updated status.")
    tags: List[str] | None = Field(default=None, description="The updated tags.")


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
    """Request to create a new spec."""

    name: FilenameString = Field(description="The name of the spec.")
    definition: str = Field(
        description="A detailed definition of the spec.", min_length=1
    )
    properties: SpecProperties = Field(
        description="The properties of the spec.",
        discriminator="spec_type",
    )
    priority: Priority = Field(
        default=Priority.p1, description="The priority of the spec."
    )
    status: SpecStatus = Field(
        default=SpecStatus.active, description="The status of the spec."
    )
    tags: List[str] = Field(default_factory=list, description="The tags of the spec.")
    evaluate_full_trace: bool = Field(
        default=False,
        description="Whether to evaluate the full trace instead of the final answer.",
    )
    task_sample: TaskSample | None = Field(
        default=None, description="An example task input/output pair."
    )


def connect_spec_api(app: FastAPI):
    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        summary="Create Spec",
        tags=["Specs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_spec(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        spec_data: SpecCreationRequest,
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

        # Priority and status live on the eval. They're also written to the spec
        # below so the spec file stays truthful, but the eval is the source of
        # truth for reads and later edits.
        eval = Eval(
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
            priority=spec_data.priority,
            status=spec_data.status,
        )

        spec = Spec(
            parent=task,
            name=spec_data.name,
            definition=spec_data.definition,
            properties=spec_data.properties,
            priority=spec_data.priority,
            status=spec_data.status,
            tags=spec_data.tags,
            eval_id=eval.id,
            task_sample=spec_data.task_sample,
        )

        eval.save_to_file()
        try:
            spec.save_to_file()
        except Exception:
            eval.delete()
            raise

        return spec

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        summary="List Specs",
        tags=["Specs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_specs(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
    ) -> List[Spec]:
        parent_task = task_from_id(project_id, task_id)
        return parent_task.specs(readonly=True)

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        summary="Get Spec",
        tags=["Specs"],
        openapi_extra=ALLOW_AGENT,
    )
    async def get_spec(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        spec_id: Annotated[str, Path(description="The unique identifier of the spec.")],
    ) -> Spec:
        return spec_from_id(project_id, task_id, spec_id)

    @app.patch(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        summary="Update Spec",
        tags=["Specs"],
        openapi_extra=agent_policy_require_approval(
            "Allow agent to edit spec? Ensure you backup your project before allowing agentic edits."
        ),
    )
    async def update_spec(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        spec_id: Annotated[str, Path(description="The unique identifier of the spec.")],
        request: UpdateSpecRequest,
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

        # Sync the linked eval when name, priority, or status change: name so
        # the two files stay coherent, priority/status because they live on the
        # eval (the spec's copies are only legacy fallbacks).
        eval: Eval | None = None
        # (previous value, so the eval can be rolled back if the spec save fails)
        name_rollback: tuple[str] | None = None
        priority_rollback: tuple[Priority | None] | None = None
        status_rollback: tuple[EvalStatus | None] | None = None
        needs_eval_sync = (
            request.name is not None
            or request.priority is not None
            or request.status is not None
        )
        if needs_eval_sync and spec.eval_id:
            parent_task = task_from_id(project_id, task_id)
            eval = Eval.from_id_and_parent_path(spec.eval_id, parent_task.path)
            if eval:
                if request.name is not None and eval.name != request.name:
                    name_rollback = (eval.name,)
                    eval.name = request.name
                if request.priority is not None and eval.priority != request.priority:
                    priority_rollback = (eval.priority,)
                    eval.priority = request.priority
                if request.status is not None and eval.status != request.status:
                    status_rollback = (eval.status,)
                    eval.status = request.status
                if name_rollback or priority_rollback or status_rollback:
                    eval.save_to_file()

        try:
            spec.save_to_file()
        except Exception:
            if eval is not None and (
                name_rollback or priority_rollback or status_rollback
            ):
                try:
                    if name_rollback is not None:
                        eval.name = name_rollback[0]
                    if priority_rollback is not None:
                        eval.priority = priority_rollback[0]
                    if status_rollback is not None:
                        eval.status = status_rollback[0]
                    eval.save_to_file()
                except Exception:
                    logger.exception("Failed to roll back eval after spec save failure")
            raise

        return spec

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        summary="Delete Spec",
        tags=["Specs"],
        openapi_extra=DENY_AGENT,
    )
    async def delete_spec(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        spec_id: Annotated[str, Path(description="The unique identifier of the spec.")],
    ) -> None:
        spec = spec_from_id(project_id, task_id, spec_id)

        # Delete associated eval if it exists
        if spec.eval_id:
            parent_task = task_from_id(project_id, task_id)
            eval: Eval | None = Eval.from_id_and_parent_path(
                spec.eval_id, parent_task.path
            )
            if eval:
                eval.delete()

        spec.delete()
