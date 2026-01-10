import io
import logging
import zipfile
from pathlib import Path
from typing import Literal, cast

from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.body_start_gepa_job_v1_jobs_gepa_job_start_post import (
    BodyStartGepaJobV1JobsGepaJobStartPost,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.body_start_gepa_job_v1_jobs_gepa_job_start_post_token_budget import (
    BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.http_validation_error import (
    HTTPValidationError,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_type import (
    JobType,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import File
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel import Project
from kiln_ai.utils.config import Config
from kiln_server.task_api import task_from_id
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """Get the Kiln Copilot API key from config, raising an error if not set."""
    api_key = Config.shared().kiln_copilot_api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Kiln Copilot API key not configured. Please connect your API key in settings.",
        )
    return api_key


class StartGepaJobRequest(BaseModel):
    token_budget: Literal["light", "medium", "heavy"]
    target_run_config_id: str


def zip_project(project: Project) -> bytes:
    """
    Create a ZIP file of the entire project directory.
    Returns the ZIP file as bytes.
    """
    if not project.path:
        raise ValueError("Project path is not set")
    project_path = Path(project.path).parent

    # Skip common directories that shouldn't be included
    skip_patterns = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "venv",
        ".DS_Store",
        ".vscode",
        ".idea",
    }

    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in project_path.rglob("*"):
            # Skip if any parent directory matches skip patterns
            if any(skip_dir in file_path.parts for skip_dir in skip_patterns):
                continue

            if file_path.is_file():
                arcname = file_path.relative_to(project_path)
                try:
                    zip_file.write(file_path, arcname=arcname)
                    file_count += 1
                except Exception as e:
                    logger.warning(f"Skipping file {file_path}: {e}")

    buffer.seek(0)
    zip_bytes = buffer.getvalue()
    logger.info(
        f"Created project ZIP with {file_count} files, total size: {len(zip_bytes)} bytes"
    )
    return zip_bytes


def connect_gepa_job_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/start")
    async def start_gepa_job(
        project_id: str,
        task_id: str,
        request: StartGepaJobRequest,
    ) -> dict:
        """
        Start a GEPA job by zipping the project and sending it to the Kiln server.
        """
        task = task_from_id(project_id, task_id)
        if not task.parent:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            # Create ZIP file of the project
            project_zip_bytes = zip_project(cast(Project, task.parent))

            # Create the File object for the SDK
            project_zip_file = File(
                payload=io.BytesIO(project_zip_bytes),
                file_name="project.zip",
                mime_type="application/zip",
            )

            # Create the request body
            body = BodyStartGepaJobV1JobsGepaJobStartPost(
                token_budget=BodyStartGepaJobV1JobsGepaJobStartPostTokenBudget(
                    request.token_budget
                ),
                task_id=task_id,
                target_run_config_id=request.target_run_config_id,
                project_zip=project_zip_file,
            )

            # Call the SDK to start the job
            from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
                start_gepa_job_v1_jobs_gepa_job_start_post,
            )

            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            logger.info(
                f"Starting GEPA job upload for task {task_id}, project ZIP size: {len(project_zip_bytes)} bytes"
            )

            response = await start_gepa_job_v1_jobs_gepa_job_start_post.asyncio(
                client=server_client, body=body
            )

            if isinstance(response, HTTPValidationError):
                error_detail = (
                    str(response.detail)
                    if hasattr(response, "detail")
                    else "Validation error"
                )
                raise HTTPException(status_code=422, detail=error_detail)

            if response is None:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to start GEPA job: No response from server",
                )

            return {"job_id": response.job_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting GEPA job: {e}", exc_info=True)

            # Provide more specific error messages
            if "ReadError" in str(type(e).__name__) or "timeout" in str(e).lower():
                raise HTTPException(
                    status_code=500,
                    detail="Connection error while uploading project. The project may be too large or the server may be unreachable. Please try again.",
                )

            raise HTTPException(
                status_code=500, detail=f"Failed to start GEPA job: {str(e)}"
            )

    @app.get("/api/gepa_jobs/{job_id}/status")
    async def get_gepa_job_status(job_id: str) -> dict:
        """
        Get the status of a GEPA job.
        """
        try:
            from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
                get_job_status_v1_jobs_job_type_job_id_status_get,
            )

            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            response = await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio(
                job_type=JobType.GEPA_JOB,
                job_id=job_id,
                client=server_client,
            )

            if response is None or isinstance(response, HTTPValidationError):
                raise HTTPException(
                    status_code=404, detail=f"GEPA job {job_id} not found"
                )

            return {"job_id": response.job_id, "status": response.status.value}

        except Exception as e:
            logger.error(f"Error getting GEPA job status: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get GEPA job status: {str(e)}",
            )

    @app.get("/api/gepa_jobs/{job_id}/result")
    async def get_gepa_job_result(job_id: str) -> dict:
        """
        Get the result of a GEPA job (includes status and output if completed).
        """
        try:
            from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
                get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get,
            )

            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            response = (
                await get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio(
                    job_id=job_id,
                    client=server_client,
                )
            )

            if response is None or isinstance(response, HTTPValidationError):
                raise HTTPException(
                    status_code=404, detail=f"GEPA job {job_id} result not found"
                )

            return response.to_dict()

        except Exception as e:
            logger.error(f"Error getting GEPA job result: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get GEPA job result: {str(e)}",
            )
