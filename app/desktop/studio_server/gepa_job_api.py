import asyncio
import io
import logging
import tempfile
from pathlib import Path
from typing import Literal

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
    check_model_supported_v1_jobs_gepa_job_check_model_supported_get,
    get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get,
    get_job_status_v1_jobs_job_type_job_id_status_get,
    start_gepa_job_v1_jobs_gepa_job_start_post,
)
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
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_status import (
    JobStatus,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_type import (
    JobType,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import File
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.eval_api import (
    eval_config_from_id,
    eval_from_id,
    task_run_config_from_id,
)
from app.desktop.studio_server.utils.copilot_utils import check_response_error
from fastapi import FastAPI, HTTPException
from kiln_ai.cli.commands.package_project import (
    PackageForTrainingConfig,
    package_project_for_training,
)
from kiln_ai.datamodel import GepaJob, Prompt
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.utils.config import Config
from kiln_ai.utils.lock import shared_async_lock_manager
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def is_job_status_final(status: str) -> bool:
    """
    Check if a job status is final (succeeded, failed, or cancelled).
    Final statuses don't need status updates from the server.
    """
    return status in [
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ]


class PublicGEPAJobResultResponse(BaseModel):
    """Public response model for GEPA job result containing only the optimized prompt."""

    optimized_prompt: str


class PublicGEPAJobStatusResponse(BaseModel):
    """Public response model for GEPA job status."""

    job_id: str
    status: JobStatus


class CheckRunConfigResponse(BaseModel):
    """Response model for check_run_config endpoint."""

    is_supported: bool


class CheckEvalResponse(BaseModel):
    """Response model for check_eval endpoint."""

    has_default_config: bool
    has_train_set: bool
    model_is_supported: bool


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
    eval_ids: list[str]


def gepa_job_from_id(project_id: str, task_id: str, gepa_job_id: str) -> GepaJob:
    """Get a GepaJob from its ID, raising HTTPException if not found."""
    task = task_from_id(project_id, task_id)
    gepa_job = GepaJob.from_id_and_parent_path(gepa_job_id, task.path)
    if gepa_job is None:
        raise HTTPException(
            status_code=404,
            detail=f"GEPA job with ID '{gepa_job_id}' not found",
        )
    return gepa_job


def create_prompt_from_optimization(
    gepa_job: GepaJob, task, optimized_prompt_text: str
) -> Prompt:
    """
    Create a prompt from an optimization job result. Does not guarantee idempotence so
    make sure you have a proper locking mechanism around calling this function.
    """
    prompt = Prompt(
        name=gepa_job.name,
        generator_id="kiln_prompt_optimizer",
        prompt=optimized_prompt_text,
        parent=task,
    )
    prompt.save_to_file()

    return prompt


def create_run_config_from_optimization(
    gepa_job: GepaJob, task, prompt: Prompt
) -> TaskRunConfig:
    """
    Create a run config from an optimization job result. Does not guarantee idempotence so
    make sure you have a proper locking mechanism around calling this function.
    Raises exceptions on failure.
    """
    parent_project = task.parent_project()
    if parent_project is None:
        raise HTTPException(status_code=500, detail="Task has no parent project")

    if not parent_project.id or not task.id:
        raise HTTPException(
            status_code=500, detail="Task has no parent project or task"
        )

    if not prompt.id:
        raise HTTPException(status_code=500, detail="Prompt has no ID")

    # get the original target run config that we optimized for in the job
    target_run_config = task_run_config_from_id(
        parent_project.id, task.id, gepa_job.target_run_config_id
    )

    # create new run config with the same properties but new prompt
    new_run_config_properties = target_run_config.run_config_properties.model_copy()

    # point the run config properties to the new prompt - need id:: prefix because
    # we point to a standalone prompt, not a frozen prompt
    new_run_config_properties.prompt_id = f"id::{prompt.id}"

    new_run_config = TaskRunConfig(
        parent=task,
        name=generate_memorable_name(),
        run_config_properties=new_run_config_properties,
    )

    new_run_config.save_to_file()

    return new_run_config


def _cleanup_artifact(
    artifact: Prompt | TaskRunConfig | None, artifact_type: str, gepa_job_id: str
) -> None:
    """
    Attempt to delete an artifact, logging errors if deletion fails.
    """
    if artifact is None:
        return

    try:
        artifact.delete()
        artifact_id = getattr(artifact, "id", "unknown")
    except Exception as cleanup_error:
        artifact_id = getattr(artifact, "id", "unknown")
        logger.error(
            f"Failed to clean up {artifact_type} artifact {artifact_id} "
            f"for GEPA job {gepa_job_id}: {cleanup_error}",
            exc_info=True,
        )


async def _create_artifacts_for_succeeded_job(
    gepa_job: GepaJob,
    task,
    server_client: AuthenticatedClient,
) -> None:
    """
    Create prompt and run config artifacts for a newly succeeded GEPA job.
    Assumes caller has acquired the job lock. Modifies gepa_job in place.
    """
    parent_project = task.parent_project()
    if not parent_project or not parent_project.id or not task.id or not gepa_job.id:
        raise ValueError("Cannot reload GEPA job: missing required IDs")

    # reload the job in case artifacts were created by another request while waiting for the lock
    reloaded_job = gepa_job_from_id(
        parent_project.id,
        task.id,
        gepa_job.id,
    )

    # check if artifacts already exist
    if reloaded_job.created_prompt_id:
        gepa_job.created_prompt_id = reloaded_job.created_prompt_id
        gepa_job.created_run_config_id = reloaded_job.created_run_config_id
        gepa_job.optimized_prompt = reloaded_job.optimized_prompt
        return

    result_response = (
        await get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio(
            job_id=gepa_job.job_id,
            client=server_client,
        )
    )

    if (
        result_response
        and not isinstance(result_response, HTTPValidationError)
        and result_response.output
        and hasattr(result_response.output, "optimized_prompt")
    ):
        optimized_prompt_text = result_response.output.optimized_prompt
        gepa_job.optimized_prompt = optimized_prompt_text

        prompt: Prompt | None = None
        run_config: TaskRunConfig | None = None

        try:
            prompt = create_prompt_from_optimization(
                gepa_job, task, optimized_prompt_text
            )
            gepa_job.created_prompt_id = f"id::{prompt.id}"

            run_config = create_run_config_from_optimization(gepa_job, task, prompt)
            gepa_job.created_run_config_id = run_config.id

        except Exception as e:
            logger.error(
                f"Failed to create artifacts for GEPA job {gepa_job.job_id}: {e}. "
                f"Cleaning up any created artifacts to allow retry on next invocation.",
                exc_info=True,
            )
            _cleanup_artifact(prompt, "prompt", gepa_job.job_id)
            _cleanup_artifact(run_config, "run config", gepa_job.job_id)
            gepa_job.created_prompt_id = None
            gepa_job.created_run_config_id = None


async def update_gepa_job_and_create_artifacts(
    gepa_job: GepaJob, server_client: AuthenticatedClient
) -> GepaJob:
    """
    Update the status of a GepaJob from the remote server.
    If the job has succeeded for the first time, create a prompt and run config from the result.
    Uses per-job locking to ensure the success transition is handled atomically.
    """
    task = gepa_job.parent_task()
    if task is None:
        raise HTTPException(status_code=500, detail="GepaJob has no parent task")

    try:
        status_response = (
            await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio(
                job_type=JobType.GEPA_JOB,
                job_id=gepa_job.job_id,
                client=server_client,
            )
        )

        if status_response is None or isinstance(status_response, HTTPValidationError):
            logger.warning(f"Could not fetch status for GEPA job {gepa_job.job_id}")
            return gepa_job

        new_status = str(status_response.status.value)

        async with shared_async_lock_manager.acquire(gepa_job.job_id):
            previous_status = gepa_job.latest_status
            gepa_job.latest_status = new_status

            if (
                previous_status != JobStatus.SUCCEEDED
                and new_status == JobStatus.SUCCEEDED
            ):
                await _create_artifacts_for_succeeded_job(gepa_job, task, server_client)

            gepa_job.save_to_file()

    except Exception as e:
        logger.error(f"Error updating GEPA job status: {e}", exc_info=True)

    return gepa_job


def connect_gepa_job_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/check_run_config")
    async def check_run_config(
        project_id: str, task_id: str, run_config_id: str
    ) -> CheckRunConfigResponse:
        """
        Check if a run config is valid for a GEPA job by validating the model is supported.
        """
        try:
            run_config = task_run_config_from_id(project_id, task_id, run_config_id)

            # Extract model info from run config
            run_config_props = run_config.run_config_properties

            if (
                run_config_props.tools_config
                and run_config_props.tools_config.tools
                and len(run_config_props.tools_config.tools) > 0
            ):
                return CheckRunConfigResponse(is_supported=False)

            model_name = run_config_props.model_name
            model_provider = run_config_props.model_provider_name

            if not model_name or not model_provider:
                return CheckRunConfigResponse(is_supported=False)

            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            response = await check_model_supported_v1_jobs_gepa_job_check_model_supported_get.asyncio(
                client=server_client,
                model_name=model_name,
                model_provider_name=model_provider.value,
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
                    detail="Failed to check run config: No response from server",
                )

            return CheckRunConfigResponse(is_supported=response.is_model_supported)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking run config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to check run config: {str(e)}"
            )

    @app.get("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/check_eval")
    async def check_eval(
        project_id: str, task_id: str, eval_id: str
    ) -> CheckEvalResponse:
        """
        Check if an eval is valid for a GEPA job.
        Validates that the eval has a default config and that the model is supported.
        """
        try:
            eval = eval_from_id(project_id, task_id, eval_id)

            # Check if eval has a default config
            if not eval.current_config_id:
                return CheckEvalResponse(
                    has_default_config=False,
                    has_train_set=bool(eval.train_set_filter_id),
                    model_is_supported=False,
                )

            # Try to load the current config
            try:
                config = eval_config_from_id(
                    project_id, task_id, eval_id, eval.current_config_id
                )
            except HTTPException:
                return CheckEvalResponse(
                    has_default_config=False,
                    has_train_set=bool(eval.train_set_filter_id),
                    model_is_supported=False,
                )

            # Extract model info from config
            model_name = config.model_name
            model_provider = config.model_provider

            if not model_name or not model_provider:
                return CheckEvalResponse(
                    has_default_config=True,
                    has_train_set=bool(eval.train_set_filter_id),
                    model_is_supported=False,
                )

            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            # EvalConfig.model_provider is already a string, no need for .value
            response = await check_model_supported_v1_jobs_gepa_job_check_model_supported_get.asyncio(
                client=server_client,
                model_name=model_name,
                model_provider_name=model_provider,
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
                    detail="Failed to check eval: No response from server",
                )

            return CheckEvalResponse(
                has_default_config=True,
                has_train_set=bool(eval.train_set_filter_id),
                model_is_supported=response.is_model_supported,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking eval: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to check eval: {str(e)}"
            )

    @app.post("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/start")
    async def start_gepa_job(
        project_id: str,
        task_id: str,
        request: StartGepaJobRequest,
    ) -> GepaJob:
        """
        Start a GEPA job by zipping the project and sending it to the Kiln server.
        Creates and saves a GepaJob datamodel to track the job.
        """
        task = task_from_id(project_id, task_id)
        project = task.parent_project()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            # Validate the run config doesn't use tools
            run_config = task_run_config_from_id(
                project_id, task_id, request.target_run_config_id
            )
            if (
                run_config.run_config_properties.tools_config
                and run_config.run_config_properties.tools_config.tools
                and len(run_config.run_config_properties.tools_config.tools) > 0
            ):
                raise HTTPException(
                    status_code=400,
                    detail="GEPA does not support run configurations with tools",
                )
            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            with tempfile.NamedTemporaryFile(
                suffix=".zip", prefix="kiln_gepa_", delete=True
            ) as tmp:
                tmp_file = Path(tmp.name)
                package_project_for_training(
                    project=project,
                    task_ids=[task_id],
                    run_config_id=request.target_run_config_id,
                    eval_ids=request.eval_ids,
                    output=tmp_file,
                    config=PackageForTrainingConfig(
                        include_documents=False,
                        exclude_task_runs=False,
                        exclude_eval_config_runs=True,
                    ),
                )
                zip_bytes = tmp_file.read_bytes()
                logger.info(
                    f"Created project ZIP, total size: {len(zip_bytes)} bytes and file name: {tmp_file.name}"
                )

                # Create the File object for the SDK
                project_zip_file = File(
                    payload=io.BytesIO(zip_bytes),
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
                eval_ids=request.eval_ids,
            )

            detailed_response = (
                await start_gepa_job_v1_jobs_gepa_job_start_post.asyncio_detailed(
                    client=server_client, body=body
                )
            )
            check_response_error(
                detailed_response,
                default_detail="Failed to start GEPA job: unexpected error from server",
            )

            response = detailed_response.parsed
            if response is None or isinstance(response, HTTPValidationError):
                raise HTTPException(
                    status_code=500,
                    detail="Failed to start GEPA job: unexpected response from server",
                )

            gepa_job = GepaJob(
                name=generate_memorable_name(),
                job_id=response.job_id,
                token_budget=request.token_budget,
                target_run_config_id=request.target_run_config_id,
                latest_status=JobStatus.PENDING,
                eval_ids=request.eval_ids,
                parent=task,
            )
            gepa_job.save_to_file()

            return gepa_job

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

    @app.get("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs")
    async def list_gepa_jobs(
        project_id: str, task_id: str, update_status: bool = False
    ) -> list[GepaJob]:
        """
        List all GEPA jobs for a task.
        Optionally update the status of non-final jobs from the remote server.
        """
        task = task_from_id(project_id, task_id)
        gepa_jobs = task.gepa_jobs()

        if update_status:
            try:
                server_client = get_authenticated_client(_get_api_key())
                if isinstance(server_client, AuthenticatedClient):
                    # Filter jobs that need status updates
                    jobs_to_update = [
                        job
                        for job in gepa_jobs
                        if not is_job_status_final(job.latest_status)
                    ]

                    # Update in batches of 5 in parallel
                    batch_size = 5
                    for i in range(0, len(jobs_to_update), batch_size):
                        batch = jobs_to_update[i : i + batch_size]
                        await asyncio.gather(
                            *[
                                update_gepa_job_and_create_artifacts(job, server_client)
                                for job in batch
                            ]
                        )
            except Exception as e:
                logger.error(f"Error updating GEPA job statuses: {e}", exc_info=True)

        return gepa_jobs

    @app.get("/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}")
    async def get_gepa_job(project_id: str, task_id: str, gepa_job_id: str) -> GepaJob:
        """
        Get a specific GEPA job and update its status from the remote server.
        If the job has succeeded, create a prompt if one doesn't exist yet.
        If the job is already in a settled state (succeeded, failed, cancelled),
        skip the status update and return the cached model.
        """
        gepa_job = gepa_job_from_id(project_id, task_id, gepa_job_id)

        # Skip status update if job is already in a final state
        if is_job_status_final(gepa_job.latest_status):
            return gepa_job

        try:
            server_client = get_authenticated_client(_get_api_key())
            if isinstance(server_client, AuthenticatedClient):
                gepa_job = await update_gepa_job_and_create_artifacts(
                    gepa_job, server_client
                )
        except Exception as e:
            logger.error(f"Error updating GEPA job status: {e}", exc_info=True)

        return gepa_job

    @app.get("/api/gepa_jobs/{job_id}/status")
    async def get_gepa_job_status(job_id: str) -> PublicGEPAJobStatusResponse:
        """
        Get the status of a GEPA job.
        """
        try:
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

            return PublicGEPAJobStatusResponse(
                job_id=response.job_id, status=response.status
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting GEPA job status: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get GEPA job status: {str(e)}",
            )

    @app.get("/api/gepa_jobs/{job_id}/result")
    async def get_gepa_job_result(job_id: str) -> PublicGEPAJobResultResponse:
        """
        Get the result of a GEPA job (includes status and output if completed).
        """
        try:
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

            if not response.output or not hasattr(response.output, "optimized_prompt"):
                raise HTTPException(
                    status_code=500,
                    detail=f"GEPA job {job_id} completed but has no output",
                )

            return PublicGEPAJobResultResponse(
                optimized_prompt=response.output.optimized_prompt
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting GEPA job result: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get GEPA job result: {str(e)}",
            )
