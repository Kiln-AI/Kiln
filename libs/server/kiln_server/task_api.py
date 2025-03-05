from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import Task

from kiln_server.project_api import project_from_id


def task_from_id(project_id: str, task_id: str) -> Task:
    parent_project = project_from_id(project_id)
    task = Task.from_id_and_parent_path(task_id, parent_project.path)
    if task:
        return task

    raise HTTPException(
        status_code=404,
        detail=f"Task not found. ID: {task_id}",
    )


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
