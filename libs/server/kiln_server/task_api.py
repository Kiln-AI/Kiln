import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import Task, TaskRequirement
from pydantic import BaseModel

from kiln_server.project_api import project_from_id

logger = logging.getLogger(__name__)


def task_from_id(project_id: str, task_id: str) -> Task:
    parent_project = project_from_id(project_id)
    task = Task.from_id_and_parent_path(task_id, parent_project.path)
    if task:
        return task

    raise HTTPException(
        status_code=404,
        detail=f"Task not found. ID: {task_id}",
    )


class RatingOption(BaseModel):
    requirement: TaskRequirement
    show_for_all: bool
    show_for_tags: List[str]


class RatingOptionResponse(BaseModel):
    options: List[RatingOption]


def connect_task_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/task")
    async def create_task(project_id: str, task_data: Dict[str, Any]) -> Task:
        if "id" in task_data:
            raise HTTPException(
                status_code=400,
                detail="Task ID cannot be set by client.",
            )
        parent_project = project_from_id(project_id)

        task = Task.validate_and_save_with_subrelations(
            task_data, parent=parent_project
        )
        if task is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to create task.",
            )
        if not isinstance(task, Task):
            raise HTTPException(
                status_code=500,
                detail="Failed to create task.",
            )

        return task

    @app.patch("/api/projects/{project_id}/task/{task_id}")
    async def update_task(
        project_id: str, task_id: str, task_updates: Dict[str, Any]
    ) -> Task:
        if "input_json_schema" in task_updates or "output_json_schema" in task_updates:
            raise HTTPException(
                status_code=400,
                detail="Input and output JSON schemas cannot be updated.",
            )
        if "id" in task_updates and task_updates["id"] != task_id:
            raise HTTPException(
                status_code=400,
                detail="Task ID cannot be changed by client in a patch.",
            )
        original_task = task_from_id(project_id, task_id)
        updated_task_data = original_task.model_copy(update=task_updates)
        updated_task = Task.validate_and_save_with_subrelations(
            updated_task_data.model_dump(), parent=original_task.parent
        )
        if updated_task is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to create task.",
            )
        if not isinstance(updated_task, Task):
            raise HTTPException(
                status_code=500,
                detail="Failed to patch task.",
            )

        return updated_task

    @app.delete("/api/projects/{project_id}/task/{task_id}")
    async def delete_task(project_id: str, task_id: str) -> None:
        task = task_from_id(project_id, task_id)
        task.delete()

    @app.get("/api/projects/{project_id}/tasks")
    async def get_tasks(project_id: str) -> List[Task]:
        parent_project = project_from_id(project_id)
        return parent_project.tasks()

    @app.get("/api/projects/{project_id}/tasks/{task_id}")
    async def get_task(project_id: str, task_id: str) -> Task:
        return task_from_id(project_id, task_id)

    @app.get("/api/projects/{project_id}/tasks/{task_id}/rating_options")
    async def get_rating_options(project_id: str, task_id: str) -> RatingOptionResponse:
        """
        Generates an object which determines which rating options should be shown for a given dataset item.
        """
        task = task_from_id(project_id, task_id)
        results: List[RatingOption] = []

        # First add all task requirements. We want these to be shown for all items.
        for requirement in task.requirements:
            results.append(
                RatingOption(
                    requirement=requirement,
                    show_for_all=True,
                    show_for_tags=[],
                )
            )

        # Then add eval requirements. We want these to be shown for all items in the eval's golden set filter.
        for eval in task.evals(readonly=True):
            if not eval.eval_configs_filter_id.startswith("tag::"):
                logger.warning(
                    "Eval '%s' has non-tag filter '%s'. This isn't compatible with the web UI for automatic rating visibility.",
                    eval.id,
                    eval.eval_configs_filter_id,
                )
                continue
            golden_set_tag = eval.eval_configs_filter_id[len("tag::") :]

            for output_score in eval.output_scores:
                # Skip overall rating. It's added by default.
                if output_score.name == "Overall Rating":
                    continue

                # Check for existing requirement with this name
                existing_req = next(
                    (r for r in results if r.requirement.name == output_score.name),
                    None,
                )
                if existing_req:
                    # warn for type mismatch
                    if existing_req.requirement.type != output_score.type:
                        logger.warning(
                            "The rating option for '%s' has conflicting types: '%s' and '%s'. You shouldn't use the same name for goals of different rating types.",
                            output_score.name,
                            output_score.type,
                            existing_req.requirement.type,
                        )

                    if golden_set_tag not in existing_req.show_for_tags:
                        # Add the golden set tag to the existing requirement instead of creating a new one (unless that tag is already there)
                        existing_req.show_for_tags.append(golden_set_tag)
                    continue

                # Map eval requirements to task requirements
                requirement = TaskRequirement(
                    id="named::" + output_score.name,
                    name=output_score.name,
                    instruction=output_score.instruction or "No instructions provided",
                    type=output_score.type,
                )
                results.append(
                    RatingOption(
                        requirement=requirement,
                        show_for_all=False,
                        show_for_tags=[golden_set_tag],
                    )
                )

        return RatingOptionResponse(options=results)
