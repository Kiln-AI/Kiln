import asyncio
import io
import logging
import tempfile
from pathlib import Path

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs import (
    check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get,
    get_job_status_v1_jobs_job_type_job_id_status_get,
    get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get,
    start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.body_start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post import (
    BodyStartPromptOptimizationJobV1JobsPromptOptimizationJobStartPost,
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
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import FastAPI, HTTPException
from kiln_ai.cli.commands.package_project import (
    PackageForTrainingConfig,
    package_project_for_training,
)
from kiln_ai.datamodel import Prompt, PromptOptimizationJob
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


class PublicPromptOptimizationJobResultResponse(BaseModel):
    """Public response model for prompt optimization job result containing only the optimized prompt."""

    optimized_prompt: str


class PublicPromptOptimizationJobStatusResponse(BaseModel):
    """Public response model for prompt optimization job status."""

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


class StartPromptOptimizationJobRequest(BaseModel):
    target_run_config_id: str
    eval_ids: list[str]


def prompt_optimization_job_from_id(
    project_id: str, task_id: str, prompt_optimization_job_id: str
) -> PromptOptimizationJob:
    """Get a PromptOptimizationJob from its ID, raising HTTPException if not found."""
    task = task_from_id(project_id, task_id)
    prompt_optimization_job = PromptOptimizationJob.from_id_and_parent_path(
        prompt_optimization_job_id, task.path
    )
    if prompt_optimization_job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt Optimization job with ID '{prompt_optimization_job_id}' not found",
        )
    return prompt_optimization_job


def create_prompt_from_optimization(
    prompt_optimization_job: PromptOptimizationJob, task, optimized_prompt_text: str
) -> Prompt:
    """
    Create a prompt from an optimization job result. Does not guarantee idempotence so
    make sure you have a proper locking mechanism around calling this function.
    """
    prompt = Prompt(
        name=prompt_optimization_job.name,
        generator_id="kiln_prompt_optimizer",
        prompt=optimized_prompt_text,
        parent=task,
    )
    prompt.save_to_file()

    return prompt


def create_run_config_from_optimization(
    prompt_optimization_job: PromptOptimizationJob, task, prompt: Prompt
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
        parent_project.id, task.id, prompt_optimization_job.target_run_config_id
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
    artifact: Prompt | TaskRunConfig | None,
    artifact_type: str,
    prompt_optimization_job_id: str,
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
            f"for Prompt Optimization job {prompt_optimization_job_id}: {cleanup_error}",
            exc_info=True,
        )


async def _create_artifacts_for_succeeded_job(
    prompt_optimization_job: PromptOptimizationJob,
    task,
    server_client: AuthenticatedClient,
) -> None:
    """
    Create prompt and run config artifacts for a newly succeeded prompt optimization job.
    Assumes caller has acquired the job lock. Modifies prompt_optimization_job in place.
    """
    parent_project = task.parent_project()
    if (
        not parent_project
        or not parent_project.id
        or not task.id
        or not prompt_optimization_job.id
    ):
        raise ValueError("Cannot reload Prompt Optimization job: missing required IDs")

    # reload the job in case artifacts were created by another request while waiting for the lock
    reloaded_job = prompt_optimization_job_from_id(
        parent_project.id,
        task.id,
        prompt_optimization_job.id,
    )

    # check if artifacts already exist
    if reloaded_job.created_prompt_id:
        prompt_optimization_job.created_prompt_id = reloaded_job.created_prompt_id
        prompt_optimization_job.created_run_config_id = (
            reloaded_job.created_run_config_id
        )
        prompt_optimization_job.optimized_prompt = reloaded_job.optimized_prompt
        return

    detailed_response = await get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed(
        job_id=prompt_optimization_job.job_id,
        client=server_client,
    )
    result_response = unwrap_response(
        detailed_response,
        default_detail="Failed to get Prompt Optimization job result.",
    )

    if result_response.output and result_response.output.optimized_prompt:
        optimized_prompt_text = result_response.output.optimized_prompt
        prompt_optimization_job.optimized_prompt = optimized_prompt_text

        prompt: Prompt | None = None
        run_config: TaskRunConfig | None = None

        try:
            prompt = create_prompt_from_optimization(
                prompt_optimization_job, task, optimized_prompt_text
            )
            prompt_optimization_job.created_prompt_id = f"id::{prompt.id}"

            run_config = create_run_config_from_optimization(
                prompt_optimization_job, task, prompt
            )
            prompt_optimization_job.created_run_config_id = run_config.id

        except Exception as e:
            logger.error(
                f"Failed to create artifacts for Prompt Optimization job {prompt_optimization_job.job_id}: {e}. "
                f"Cleaning up any created artifacts to allow retry on next invocation.",
                exc_info=True,
            )
            _cleanup_artifact(prompt, "prompt", prompt_optimization_job.job_id)
            _cleanup_artifact(run_config, "run config", prompt_optimization_job.job_id)
            prompt_optimization_job.created_prompt_id = None
            prompt_optimization_job.created_run_config_id = None


async def update_prompt_optimization_job_and_create_artifacts(
    prompt_optimization_job: PromptOptimizationJob, server_client: AuthenticatedClient
) -> PromptOptimizationJob:
    """
    Update the status of a PromptOptimizationJob from the remote server.
    If the job has succeeded for the first time, create a prompt and run config from the result.
    Uses per-job locking to ensure the success transition is handled atomically.
    """
    task = prompt_optimization_job.parent_task()
    if task is None:
        raise HTTPException(
            status_code=500, detail="PromptOptimizationJob has no parent task"
        )

    try:
        detailed_response = (
            await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed(
                job_type=JobType.GEPA_JOB,
                job_id=prompt_optimization_job.job_id,
                client=server_client,
            )
        )
        status_response = unwrap_response(
            detailed_response,
            default_detail=f"Could not fetch status for Prompt Optimization job {prompt_optimization_job.job_id}",
        )

        new_status = str(status_response.status.value)

        async with shared_async_lock_manager.acquire(prompt_optimization_job.job_id):
            previous_status = prompt_optimization_job.latest_status
            prompt_optimization_job.latest_status = new_status

            if (
                previous_status != JobStatus.SUCCEEDED
                and new_status == JobStatus.SUCCEEDED
            ):
                await _create_artifacts_for_succeeded_job(
                    prompt_optimization_job, task, server_client
                )

            prompt_optimization_job.save_to_file()

    except Exception as e:
        logger.error(
            f"Error updating Prompt Optimization job status: {e}", exc_info=True
        )

    return prompt_optimization_job


def connect_prompt_optimization_job_api(app: FastAPI):
    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config"
    )
    async def check_run_config(
        project_id: str, task_id: str, run_config_id: str
    ) -> CheckRunConfigResponse:
        """
        Check if a run config is valid for a Prompt Optimization job by validating the model is supported.
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

            detailed_response = await check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed(
                client=server_client,
                model_name=model_name,
                model_provider_name=model_provider.value,
            )
            response = unwrap_response(detailed_response)

            return CheckRunConfigResponse(is_supported=response.is_model_supported)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error checking run config: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to check run config: {str(e)}"
            )

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval"
    )
    async def check_eval(
        project_id: str, task_id: str, eval_id: str
    ) -> CheckEvalResponse:
        """
        Check if an eval is valid for a Prompt Optimization job.
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
            detailed_response = await check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed(
                client=server_client,
                model_name=model_name,
                model_provider_name=model_provider,
            )
            response = unwrap_response(detailed_response)

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

    @app.post(
        "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start"
    )
    async def start_prompt_optimization_job(
        project_id: str,
        task_id: str,
        request: StartPromptOptimizationJobRequest,
    ) -> PromptOptimizationJob:
        """
        Start a prompt optimization job by zipping the project and sending it to the Kiln server.
        Creates and saves a PromptOptimizationJob datamodel to track the job.
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
                    detail="Prompt Optimization does not support run configurations with tools",
                )
            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            with tempfile.TemporaryDirectory(
                prefix="kiln_prompt_optimization_"
            ) as tmpdir:
                tmp_file = Path(tmpdir) / "kiln_prompt_optimization_project.zip"
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

                project_zip_file = File(
                    payload=io.BytesIO(zip_bytes),
                    file_name="project.zip",
                    mime_type="application/zip",
                )

            # Create the request body
            body = BodyStartPromptOptimizationJobV1JobsPromptOptimizationJobStartPost(
                task_id=task_id,
                target_run_config_id=request.target_run_config_id,
                project_zip=project_zip_file,
                eval_ids=request.eval_ids,
            )

            detailed_response = await start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed(
                client=server_client, body=body
            )
            response = unwrap_response(detailed_response)

            prompt_optimization_job = PromptOptimizationJob(
                name=generate_memorable_name(),
                job_id=response.job_id,
                target_run_config_id=request.target_run_config_id,
                latest_status=JobStatus.PENDING,
                eval_ids=request.eval_ids,
                parent=task,
            )
            prompt_optimization_job.save_to_file()

            return prompt_optimization_job

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting Prompt Optimization job: {e}", exc_info=True)

            # Provide more specific error messages
            if "ReadError" in str(type(e).__name__) or "timeout" in str(e).lower():
                raise HTTPException(
                    status_code=500,
                    detail="Connection error while uploading project. The project may be too large or the server may be unreachable. Please try again.",
                )

            raise HTTPException(
                status_code=500,
                detail=f"Failed to start Prompt Optimization job: {str(e)}",
            )

    @app.get("/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs")
    async def list_prompt_optimization_jobs(
        project_id: str, task_id: str, update_status: bool = False
    ) -> list[PromptOptimizationJob]:
        """
        List all Prompt Optimization jobs for a task.
        Optionally update the status of non-final jobs from the remote server.
        """
        task = task_from_id(project_id, task_id)
        prompt_optimization_jobs = task.prompt_optimization_jobs()

        if update_status:
            try:
                server_client = get_authenticated_client(_get_api_key())
                if isinstance(server_client, AuthenticatedClient):
                    # Filter jobs that need status updates
                    jobs_to_update = [
                        job
                        for job in prompt_optimization_jobs
                        if not is_job_status_final(job.latest_status)
                    ]

                    # Update in batches of 5 in parallel
                    batch_size = 5
                    for i in range(0, len(jobs_to_update), batch_size):
                        batch = jobs_to_update[i : i + batch_size]

                        # this swallows the exceptions from each call, which is fine
                        await asyncio.gather(
                            *[
                                update_prompt_optimization_job_and_create_artifacts(
                                    job, server_client
                                )
                                for job in batch
                            ],
                            return_exceptions=True,
                        )
            except Exception as e:
                logger.error(
                    f"Error updating Prompt Optimization job statuses: {e}",
                    exc_info=True,
                )

        return prompt_optimization_jobs

    @app.get(
        "/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
    )
    async def get_prompt_optimization_job(
        project_id: str, task_id: str, prompt_optimization_job_id: str
    ) -> PromptOptimizationJob:
        """
        Get a specific Prompt Optimization job and update its status from the remote server.
        If the job has succeeded, create a prompt if one doesn't exist yet.
        If the job is already in a settled state (succeeded, failed, cancelled),
        skip the status update and return the cached model.
        """
        prompt_optimization_job = prompt_optimization_job_from_id(
            project_id, task_id, prompt_optimization_job_id
        )

        # Skip status update if job is already in a final state
        if is_job_status_final(prompt_optimization_job.latest_status):
            return prompt_optimization_job

        try:
            server_client = get_authenticated_client(_get_api_key())
            if isinstance(server_client, AuthenticatedClient):
                prompt_optimization_job = (
                    await update_prompt_optimization_job_and_create_artifacts(
                        prompt_optimization_job, server_client
                    )
                )
        except Exception as e:
            logger.error(
                f"Error updating Prompt Optimization job status: {e}", exc_info=True
            )

        return prompt_optimization_job

    @app.get("/api/prompt_optimization_jobs/{job_id}/status")
    async def get_prompt_optimization_job_status(
        job_id: str,
    ) -> PublicPromptOptimizationJobStatusResponse:
        """
        Get the status of a Prompt Optimization job.
        """
        try:
            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            detailed_response = await get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed(
                job_type=JobType.GEPA_JOB,
                job_id=job_id,
                client=server_client,
            )
            response = unwrap_response(
                detailed_response,
                default_detail=f"Prompt Optimization job {job_id} not found",
            )

            return PublicPromptOptimizationJobStatusResponse(
                job_id=response.job_id, status=response.status
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Error getting prompt optimization job status: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get Prompt Optimization job status: {str(e)}",
            )

    @app.get("/api/prompt_optimization_jobs/{job_id}/result")
    async def get_prompt_optimization_job_result(
        job_id: str,
    ) -> PublicPromptOptimizationJobResultResponse:
        """
        Get the result of a prompt optimization job (includes status and output if completed).
        """
        try:
            server_client = get_authenticated_client(_get_api_key())
            if not isinstance(server_client, AuthenticatedClient):
                raise HTTPException(
                    status_code=500, detail="Server client not authenticated"
                )

            detailed_response = await get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed(
                job_id=job_id,
                client=server_client,
            )
            response = unwrap_response(
                detailed_response,
                default_detail=f"Prompt Optimization job {job_id} result not found",
            )

            if not response.output or not hasattr(response.output, "optimized_prompt"):
                raise HTTPException(
                    status_code=500,
                    detail=f"Prompt Optimization job {job_id} completed but has no output",
                )

            return PublicPromptOptimizationJobResultResponse(
                optimized_prompt=response.output.optimized_prompt
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Error getting prompt optimization job result: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get Prompt Optimization job result: {str(e)}",
            )
