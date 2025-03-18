import logging
import os
import tempfile
from asyncio import Lock
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from kiln_ai.adapters.adapter_registry import adapter_for_task
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.datamodel import (
    PromptId,
    Task,
    TaskOutputRating,
    TaskOutputRatingType,
    TaskRun,
)
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.utils.dataset_import import (
    DatasetFileImporter,
    DatasetImportFormat,
    ImportConfig,
    KilnInvalidImportFormat,
)
from pydantic import BaseModel, ConfigDict

from kiln_server.task_api import task_from_id

logger = logging.getLogger(__name__)

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
    ui_prompt_method: PromptId | None = None
    tags: list[str] | None = None

    # Allows use of the model_name field (usually pydantic will reserve model_*)
    model_config = ConfigDict(protected_namespaces=())


class RunSummary(BaseModel):
    id: ID_TYPE
    rating: TaskOutputRating | None = None
    created_at: datetime
    input_preview: str | None = None
    output_preview: str | None = None
    repair_state: str | None = None
    model_name: str | None = None
    input_source: str | None = None
    tags: list[str] | None = None

    @classmethod
    def format_preview(cls, text: str | None, max_length: int = 100) -> str | None:
        if text is None:
            return None
        if len(text) > max_length:
            return text[:max_length] + "…"
        return text

    @classmethod
    def repair_status_display_name(cls, run: TaskRun) -> str:
        if run.repair_instructions:
            return "Repaired"
        elif run.output and not run.output.rating:
            return "Rating needed"
        elif not run.output or not run.output.output:
            return "No output"
        elif (
            run.output.rating
            and run.output.rating.value == 5.0
            and run.output.rating.type == TaskOutputRatingType.five_star
        ):
            return "No repair needed"
        elif (
            run.output.rating
            and run.output.rating.type != TaskOutputRatingType.five_star
        ):
            return "Unknown"
        elif run.output.output:
            return "Repair needed"
        return "Unknown"

    @classmethod
    def from_run(cls, run: TaskRun) -> "RunSummary":
        model_name = (
            run.output.source.properties.get("model_name")
            if run.output and run.output.source and run.output.source.properties
            else None
        )
        if not isinstance(model_name, str):
            model_name = None
        output = run.output.output if run.output and run.output.output else None

        return RunSummary(
            id=run.id,
            rating=run.output.rating,
            tags=run.tags,
            input_preview=RunSummary.format_preview(run.input),
            output_preview=RunSummary.format_preview(output),
            created_at=run.created_at,
            repair_state=RunSummary.repair_status_display_name(run),
            model_name=model_name,
            input_source=run.input_source.type if run.input_source else None,
        )


class BulkUploadResponse(BaseModel):
    success: bool
    filename: str
    imported_count: int


def run_from_id(project_id: str, task_id: str, run_id: str) -> TaskRun:
    task, run = task_and_run_from_id(project_id, task_id, run_id)
    return run


def task_and_run_from_id(
    project_id: str, task_id: str, run_id: str
) -> tuple[Task, TaskRun]:
    task = task_from_id(project_id, task_id)
    run = TaskRun.from_id_and_parent_path(run_id, task.path)
    if run:
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
        return list(task.runs(readonly=True))

    @app.get("/api/projects/{project_id}/tasks/{task_id}/runs_summaries")
    async def get_runs_summary(project_id: str, task_id: str) -> list[RunSummary]:
        task = task_from_id(project_id, task_id)
        # Readonly since we are not mutating the runs. Faster as we don't need to copy them.
        runs = task.runs(readonly=True)
        run_summaries: list[RunSummary] = []
        for run in runs:
            summary = RunSummary.from_run(run)
            run_summaries.append(summary)
        return run_summaries

    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/delete")
    async def delete_runs(project_id: str, task_id: str, run_ids: list[str]):
        task = task_from_id(project_id, task_id)
        failed_runs: list[str] = []
        last_error: Exception | None = None
        for run_id in run_ids:
            try:
                run = TaskRun.from_id_and_parent_path(run_id, task.path)
                if run:
                    run.delete()
                else:
                    failed_runs.append(run_id)
                    last_error = Exception("Run not found")
            except Exception as e:
                last_error = e
                failed_runs.append(run_id)
        if failed_runs:
            raise HTTPException(
                status_code=500,
                detail={
                    "failed_runs": failed_runs,
                    "error": str(last_error) if last_error else "Unknown error",
                },
            )
        return {"success": True}

    @app.post("/api/projects/{project_id}/tasks/{task_id}/run")
    async def run_task(
        project_id: str, task_id: str, request: RunTaskRequest
    ) -> TaskRun:
        task = task_from_id(project_id, task_id)

        adapter = adapter_for_task(
            task,
            model_name=request.model_name,
            provider=model_provider_from_string(request.provider),
            prompt_id=request.ui_prompt_method or "simple_prompt_builder",
            base_adapter_config=AdapterConfig(default_tags=request.tags),
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

    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/edit_tags")
    async def edit_tags(
        project_id: str,
        task_id: str,
        run_ids: list[str],
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
    ):
        task = task_from_id(project_id, task_id)
        failed_runs: list[str] = []
        for run_id in run_ids:
            run = TaskRun.from_id_and_parent_path(run_id, task.path)
            if not run:
                failed_runs.append(run_id)
            else:
                modified = False
                if remove_tags and any(tag in (run.tags or []) for tag in remove_tags):
                    run.tags = list(
                        set(tag for tag in (run.tags or []) if tag not in remove_tags)
                    )
                    modified = True
                if add_tags and any(tag not in (run.tags or []) for tag in add_tags):
                    run.tags = list(set((run.tags or []) + add_tags))
                    modified = True
                if modified:
                    run.save_to_file()

        if failed_runs:
            raise HTTPException(
                status_code=500,
                detail={
                    "failed_runs": failed_runs,
                    "error": "Runs not found",
                },
            )
        return {"success": True}

    @app.post("/api/projects/{project_id}/tasks/{task_id}/runs/bulk_upload")
    async def bulk_upload(
        project_id: str,
        task_id: str,
        file: UploadFile = File(...),
    ) -> BulkUploadResponse:
        task = task_from_id(project_id, task_id)

        # store the file in temp directory
        file_name = file.filename if file.filename else "untitled"
        file_path = os.path.join(
            tempfile.gettempdir(),
            file_name,
        )
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        imported_count = 0
        try:
            importer = DatasetFileImporter(
                task,
                ImportConfig(
                    dataset_type=DatasetImportFormat.CSV,
                    dataset_path=file_path,
                    dataset_name=file_name,
                ),
            )
            imported_count = importer.create_runs_from_file()
        except KilnInvalidImportFormat as e:
            logger.error(
                f"Invalid import format in {file_name}: {str(e)}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=422,
                detail=str(e),
            )

        return BulkUploadResponse(
            success=True,
            filename=file_name,
            imported_count=imported_count,
        )


async def update_run_util(
    project_id: str, task_id: str, run_id: str, run_data: Dict[str, Any]
) -> TaskRun:
    # Lock to prevent overwriting concurrent updates
    async with update_run_lock:
        task = task_from_id(project_id, task_id)

        run = TaskRun.from_id_and_parent_path(run_id, task.path)
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


def model_provider_from_string(provider: str) -> ModelProviderName:
    if not provider or provider not in ModelProviderName.__members__:
        raise ValueError(f"Unsupported provider: {provider}")
    return ModelProviderName(provider)
