from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from kiln_ai.datamodel import Feedback, TaskRun
from kiln_ai.datamodel.datamodel_enums import FeedbackSource
from pydantic import BaseModel, Field

from kiln_server.task_api import task_from_id
from kiln_server.utils.agent_checks.policy import ALLOW_AGENT


class CreateFeedbackRequest(BaseModel):
    """Request body for creating feedback on a task run."""

    feedback: str = Field(
        min_length=1,
        description="Free-form text feedback on the task run.",
    )
    source: FeedbackSource = Field(
        description="Where this feedback originated.",
    )


def _run_from_ids(project_id: str, task_id: str, run_id: str) -> TaskRun:
    task = task_from_id(project_id, task_id)
    run = TaskRun.from_id_and_parent_path(run_id, task.path)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task run not found. ID: {run_id}",
        )
    return run


def connect_feedback_api(app: FastAPI):
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback",
        summary="List Feedback",
        tags=["Feedback"],
        openapi_extra=ALLOW_AGENT,
    )
    async def list_feedback(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_id: Annotated[
            str, Path(description="The unique identifier of the task run.")
        ],
    ) -> list[Feedback]:
        run = _run_from_ids(project_id, task_id, run_id)
        return run.feedback(readonly=True)

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback",
        summary="Create Feedback",
        tags=["Feedback"],
        openapi_extra=ALLOW_AGENT,
    )
    async def create_feedback(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_id: Annotated[
            str, Path(description="The unique identifier of the task run.")
        ],
        body: CreateFeedbackRequest,
    ) -> Feedback:
        run = _run_from_ids(project_id, task_id, run_id)
        fb = Feedback(
            feedback=body.feedback,
            source=body.source,
            parent=run,
        )
        fb.save_to_file()
        return fb

    @app.delete(
        "/api/projects/{project_id}/tasks/{task_id}/runs/{run_id}/feedback/{feedback_id}",
        summary="Delete Feedback",
        tags=["Feedback"],
        openapi_extra=ALLOW_AGENT,
    )
    async def delete_feedback(
        project_id: Annotated[
            str, Path(description="The unique identifier of the project.")
        ],
        task_id: Annotated[
            str,
            Path(description="The unique identifier of the task within the project."),
        ],
        run_id: Annotated[
            str, Path(description="The unique identifier of the task run.")
        ],
        feedback_id: Annotated[
            str, Path(description="The unique identifier of the feedback.")
        ],
    ) -> None:
        run = _run_from_ids(project_id, task_id, run_id)
        fb = Feedback.from_id_and_parent_path(feedback_id, run.path)
        if fb is None:
            raise HTTPException(
                status_code=404,
                detail=f"Feedback not found. ID: {feedback_id}",
            )
        fb.delete()
