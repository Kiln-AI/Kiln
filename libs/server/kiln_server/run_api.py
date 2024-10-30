from asyncio import Lock
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.langchain_adapters import LangChainPromptAdapter
from kiln_ai.adapters.prompt_builders import prompt_builder_from_ui_name
from kiln_ai.datamodel import Task, TaskRun
from pydantic import BaseModel, ConfigDict

from kiln_server.project_api import project_from_id
from kiln_server.task_api import task_from_id

# Lock to prevent overwriting via concurrent updates. We use a load/update/write pattern that is not atomic.
update_run_lock = Lock()


def deep_update(
    source: Dict[str, Any] | None, update: Dict[str, Any | None]
) -> Dict[str, Any]:
    if source is None:
        return {k: v for k, v in update.items() if v is not None}
    for key, value in update.items():
        if value is None:
            source.pop(key, None)
        elif isinstance(value, dict):
            if key not in source or not isinstance(source[key], dict):
                source[key] = {}
            source[key] = deep_update(source[key], value)
        else:
            source[key] = value
    return {k: v for k, v in source.items() if v is not None}


class RunTaskRequest(BaseModel):
    model_name: str
    provider: str
    plaintext_input: str | None = None
    structured_input: Dict[str, Any] | None = None
    ui_prompt_method: str | None = None

    # Allows use of the model_name field (usually pydantic will reserve model_*)
    model_config = ConfigDict(protected_namespaces=())


def run_from_id(project_id: str, task_id: str, run_id: str) -> TaskRun:
    task, run = task_and_run_from_id(project_id, task_id, run_id)
    return run


def task_and_run_from_id(
    project_id: str, task_id: str, run_id: str
) -> tuple[Task, TaskRun]:
    task = task_from_id(project_id, task_id)
    for run in task.runs():
        if run.id == run_id:
            return task, run

    raise HTTPException(
        status_code=404,
        detail=f"Run not found. ID: {run_id}",
    )


def connect_run_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}")
    async def get_run(project_id: str, task_id: str, run_id: str) -> TaskRun:
        return run_from_id(project_id, task_id, run_id)

    @app.delete("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}")
    async def delete_run(project_id: str, task_id: str, run_id: str):
        run = run_from_id(project_id, task_id, run_id)
        run.delete()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/runs")
    async def get_runs(project_id: str, task_id: str) -> list[TaskRun]:
        task = task_from_id(project_id, task_id)
        return list(task.runs())

    @app.post("/api/projects/{project_id}/tasks/{task_id}/run")
    async def run_task(
        project_id: str, task_id: str, request: RunTaskRequest
    ) -> TaskRun:
        parent_project = project_from_id(project_id)
        task = next(
            (task for task in parent_project.tasks() if task.id == task_id), None
        )
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task not found. ID: {task_id}",
            )

        prompt_builder_class = prompt_builder_from_ui_name(
            request.ui_prompt_method or "basic"
        )
        if prompt_builder_class is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown prompt method: {request.ui_prompt_method}",
            )
        prompt_builder = prompt_builder_class(task)
        adapter = LangChainPromptAdapter(
            task,
            model_name=request.model_name,
            provider=request.provider,
            prompt_builder=prompt_builder,
        )

        input = request.plaintext_input
        if task.input_schema() is not None:
            input = request.structured_input

        if input is None:
            raise HTTPException(
                status_code=400,
                detail="No input provided. Ensure your provided the proper format (plaintext or structured).",
            )

        return await adapter.invoke(input)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}")
    async def update_run(
        project_id: str, task_id: str, run_id: str, run_data: Dict[str, Any]
    ) -> TaskRun:
        return await update_run_util(project_id, task_id, run_id, run_data)


async def update_run_util(
    project_id: str, task_id: str, run_id: str, run_data: Dict[str, Any]
) -> TaskRun:
    # Lock to prevent overwriting concurrent updates
    async with update_run_lock:
        parent_project = project_from_id(project_id)
        task = next(
            (task for task in parent_project.tasks() if task.id == task_id), None
        )
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=f"Task not found. ID: {task_id}",
            )

        run = next((run for run in task.runs() if run.id == run_id), None)
        if run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Run not found. ID: {run_id}",
            )

        # Update and save
        old_run_dumped = run.model_dump()
        merged = deep_update(old_run_dumped, run_data)
        updated_run = TaskRun.model_validate(merged)
        updated_run.path = run.path
        updated_run.save_to_file()
        return updated_run
