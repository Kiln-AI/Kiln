import asyncio
import json
import zipfile
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.client import (
    AuthenticatedClient,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_start_response import (
    JobStartResponse,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_status import (
    JobStatus,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_status_response import (
    JobStatusResponse,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.prompt_optimization_job_output import (
    PromptOptimizationJobOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.prompt_optimization_job_result_response import (
    PromptOptimizationJobResultResponse,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as SdkResponse,
)
from app.desktop.studio_server.prompt_optimization_job_api import (
    PublicPromptOptimizationJobResultResponse,
    PublicPromptOptimizationJobStatusResponse,
    connect_prompt_optimization_job_api,
    is_job_status_final,
    prompt_optimization_job_from_id,
    update_prompt_optimization_job_and_create_artifacts,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors
from kiln_ai.cli.commands.package_project import PackageForTrainingConfig
from kiln_ai.datamodel import Project, PromptOptimizationJob, Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.task import TaskRunConfig


def _mock_package_project_for_training(**kwargs):
    """Mock that writes a minimal valid zip file to the output path."""
    output = kwargs.get("output")
    if output is None:
        return
    with zipfile.ZipFile(output, "w") as z:
        z.writestr("project.kiln", "{}")


def _make_sdk_response(
    parsed=None,
    status_code: HTTPStatus = HTTPStatus.OK,
    content: bytes = b"{}",
) -> SdkResponse:
    return SdkResponse(
        status_code=status_code,
        content=content,
        headers={},
        parsed=parsed,
    )


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_prompt_optimization_job_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.Config.shared"
        ) as mock_config,
        patch("kiln_ai.datamodel.basemodel.Config.shared") as mock_basemodel_config,
    ):
        mock_config_instance = mock_config.return_value
        mock_config_instance.kiln_copilot_api_key = "test_api_key"
        mock_config_instance.user_id = "test_user"

        mock_basemodel_config_instance = mock_basemodel_config.return_value
        mock_basemodel_config_instance.user_id = "test_user"

        yield mock_config_instance


def test_get_prompt_optimization_job_result_success(client, mock_api_key):
    """Test successfully getting a Prompt Optimization job result."""
    job_id = "test-job-123"
    expected_prompt = "This is the optimized prompt"

    mock_output = PromptOptimizationJobOutput(optimized_prompt=expected_prompt)
    mock_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED, output=mock_output
    )

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(parsed=mock_response),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 200
        assert response.json() == {"optimized_prompt": expected_prompt}

        result = PublicPromptOptimizationJobResultResponse(**response.json())
        assert result.optimized_prompt == expected_prompt


def test_get_prompt_optimization_job_result_not_found(client, mock_api_key):
    """Test getting a Prompt Optimization job result that doesn't exist."""
    job_id = "nonexistent-job"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(
            status_code=HTTPStatus.NOT_FOUND,
            content=b'{"message": "Not found"}',
        ),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 404


def test_get_prompt_optimization_job_result_no_output(client, mock_api_key):
    """Test getting a Prompt Optimization job result that has no output."""
    job_id = "test-job-no-output"

    mock_response = PromptOptimizationJobResultResponse(
        status=JobStatus.RUNNING, output=None
    )

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(parsed=mock_response),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 500
        assert "has no output" in response.json()["message"]


def test_get_prompt_optimization_job_result_api_error(client, mock_api_key):
    """Test handling of API errors when getting Prompt Optimization job result."""
    job_id = "test-job-error"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
        new_callable=AsyncMock,
        side_effect=Exception("API connection failed"),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 500
        assert (
            "Failed to get Prompt Optimization job result" in response.json()["message"]
        )


def test_get_prompt_optimization_job_status_success(client, mock_api_key):
    """Test successfully getting Prompt Optimization job status."""
    job_id = "test-job-123"

    mock_response = JobStatusResponse(job_id=job_id, status=JobStatus.RUNNING)

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(parsed=mock_response),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/status")

        assert response.status_code == 200
        assert response.json() == {"job_id": job_id, "status": "running"}

        result = PublicPromptOptimizationJobStatusResponse(**response.json())
        assert result.job_id == job_id
        assert result.status == JobStatus.RUNNING


def test_get_prompt_optimization_job_status_not_found(client, mock_api_key):
    """Test getting status for a job that doesn't exist."""
    job_id = "nonexistent-job"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(
            status_code=HTTPStatus.NOT_FOUND,
            content=b'{"message": "Not found"}',
        ),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/status")

        assert response.status_code == 404


def test_get_prompt_optimization_job_result_no_api_key(client):
    """Test getting Prompt Optimization job result without API key configured."""
    job_id = "test-job-123"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.Config.shared"
    ) as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.kiln_copilot_api_key = None

        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 401
        assert "API key not configured" in response.json()["message"]


def test_get_prompt_optimization_job_result_validation_error(client, mock_api_key):
    """Test getting Prompt Optimization job result with validation error from server."""
    job_id = "test-job-123"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
        new_callable=AsyncMock,
        return_value=_make_sdk_response(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            content=b'{"message": "Validation error"}',
        ),
    ):
        response = client.get(f"/api/prompt_optimization_jobs/{job_id}/result")

        assert response.status_code == 422


def test_public_prompt_optimization_job_result_response_model():
    """Test the PublicPromptOptimizationJobResultResponse Pydantic model."""
    prompt = "Test optimized prompt"
    model = PublicPromptOptimizationJobResultResponse(optimized_prompt=prompt)

    assert model.optimized_prompt == prompt
    assert model.model_dump() == {"optimized_prompt": prompt}

    json_str = model.model_dump_json()
    assert prompt in json_str

    parsed = PublicPromptOptimizationJobResultResponse.model_validate_json(json_str)
    assert parsed.optimized_prompt == prompt


def test_public_prompt_optimization_job_status_response_model():
    """Test the PublicPromptOptimizationJobStatusResponse Pydantic model."""
    job_id = "test-job-123"
    status = JobStatus.RUNNING
    model = PublicPromptOptimizationJobStatusResponse(job_id=job_id, status=status)

    assert model.job_id == job_id
    assert model.status == JobStatus.RUNNING
    assert model.model_dump() == {"job_id": job_id, "status": status}

    json_str = model.model_dump_json()
    assert job_id in json_str
    assert "running" in json_str

    parsed = PublicPromptOptimizationJobStatusResponse.model_validate_json(json_str)
    assert parsed.job_id == job_id
    assert parsed.status == JobStatus.RUNNING


def test_start_prompt_optimization_job_creates_datamodel(
    client, mock_api_key, tmp_path
):
    """Test that starting a Prompt Optimization job creates and saves a PromptOptimizationJob datamodel."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=_mock_package_project_for_training,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                parsed=JobStartResponse(job_id="remote-job-123")
            ),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": ["eval-1", "eval-2"],
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert result["job_id"] == "remote-job-123"
        assert result["target_run_config_id"] == "test-run-config-id"
        assert result["latest_status"] == "pending"
        assert result["eval_ids"] == ["eval-1", "eval-2"]
        assert "id" in result
        assert "name" in result

        prompt_optimization_jobs = task.prompt_optimization_jobs()
        assert len(prompt_optimization_jobs) == 1
        assert prompt_optimization_jobs[0].job_id == "remote-job-123"
        assert prompt_optimization_jobs[0].eval_ids == ["eval-1", "eval-2"]


def test_start_prompt_optimization_job_calls_package_with_correct_params(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job calls package_project_for_training with the correct arguments."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    mock_packager = MagicMock(side_effect=_mock_package_project_for_training)

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            mock_packager,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                parsed=JobStartResponse(job_id="remote-job-456")
            ),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "rc-123",
                "eval_ids": ["eval-a", "eval-b"],
            },
        )

        assert response.status_code == 200

        mock_packager.assert_called_once()
        call_kwargs = mock_packager.call_args.kwargs

        assert call_kwargs["project"] is project
        assert call_kwargs["task_ids"] == [task_id]
        assert call_kwargs["run_config_id"] == "rc-123"
        assert call_kwargs["eval_ids"] == ["eval-a", "eval-b"]
        assert isinstance(call_kwargs["config"], PackageForTrainingConfig)
        assert call_kwargs["config"].include_documents is False
        assert call_kwargs["config"].exclude_task_runs is False
        assert call_kwargs["config"].exclude_eval_config_runs is True


def test_list_prompt_optimization_jobs(client, mock_api_key, tmp_path):
    """Test listing all Prompt Optimization jobs for a task."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job_1 = PromptOptimizationJob(
        name="Job 1",
        job_id="remote-job-1",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job_1.save_to_file()

    prompt_optimization_job_2 = PromptOptimizationJob(
        name="Job 2",
        job_id="remote-job-2",
        target_run_config_id="config-2",
        latest_status="succeeded",
        parent=task,
    )
    prompt_optimization_job_2.save_to_file()

    project_id = project.id
    task_id = task.id

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
        return_value=task,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs",
            params={"update_status": False},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 2
        job_names = {job["name"] for job in result}
        assert job_names == {"Job 1", "Job 2"}
        job_ids = {job["job_id"] for job in result}
        assert job_ids == {"remote-job-1", "remote-job-2"}


def test_get_prompt_optimization_job_detail(client, mock_api_key, tmp_path):
    """Test getting Prompt Optimization job detail."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.RUNNING
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Test Job"
        assert result["job_id"] == "remote-job-123"
        assert result["latest_status"] == "running"


def test_prompt_optimization_job_creates_prompt_on_success(
    client, mock_api_key, tmp_path
):
    """Test that a prompt is created when a Prompt Optimization job succeeds."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"
        assert result["optimized_prompt"] == optimized_prompt

        prompts = task.prompts()
        assert len(prompts) == 1
        assert prompts[0].prompt == optimized_prompt
        assert prompts[0].name == prompt_optimization_job.name
        assert result["created_prompt_id"] == f"id::{prompts[0].id}"


def test_prompt_optimization_job_only_creates_prompt_once(
    client, mock_api_key, tmp_path
):
    """Test that a prompt is only created once even if status is checked multiple times."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
    ):
        response_1 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )
        assert response_1.status_code == 200

        response_2 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )
        assert response_2.status_code == 200

        prompts = task.prompts()
        assert len(prompts) == 1


def test_get_prompt_optimization_job_skips_update_when_succeeded(
    client, mock_api_key, tmp_path
):
    """Test that getting a job that's already succeeded skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="succeeded",
        optimized_prompt="Already optimized",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"
        assert result["optimized_prompt"] == "Already optimized"

        mock_status.assert_not_called()
        mock_result.assert_not_called()


def test_get_prompt_optimization_job_skips_update_when_failed(
    client, mock_api_key, tmp_path
):
    """Test that getting a job that's already failed skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="failed",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "failed"

        mock_status.assert_not_called()
        mock_result.assert_not_called()


def test_get_prompt_optimization_job_skips_update_when_cancelled(
    client, mock_api_key, tmp_path
):
    """Test that getting a job that's already cancelled skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="cancelled",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "cancelled"

        mock_status.assert_not_called()
        mock_result.assert_not_called()


def test_is_job_status_final():
    """Test the is_job_status_final helper function."""
    assert is_job_status_final(JobStatus.SUCCEEDED.value) is True
    assert is_job_status_final(JobStatus.FAILED.value) is True
    assert is_job_status_final(JobStatus.CANCELLED.value) is True

    assert is_job_status_final(JobStatus.PENDING.value) is False
    assert is_job_status_final(JobStatus.RUNNING.value) is False

    assert is_job_status_final("succeeded") is True
    assert is_job_status_final("failed") is True
    assert is_job_status_final("cancelled") is True
    assert is_job_status_final("pending") is False
    assert is_job_status_final("running") is False


def test_list_prompt_optimization_jobs_updates_statuses_in_parallel_batches(
    client, mock_api_key, tmp_path
):
    """Test that list_prompt_optimization_jobs updates statuses in parallel batches of 5."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create 12 jobs with non-final statuses and 3 with final statuses
    for i in range(12):
        PromptOptimizationJob(
            name=f"Job {i}",
            job_id=f"remote-job-{i}",
            target_run_config_id="config-1",
            latest_status=JobStatus.PENDING.value
            if i % 2 == 0
            else JobStatus.RUNNING.value,
            parent=task,
        ).save_to_file()

    for i in range(12, 15):
        PromptOptimizationJob(
            name=f"Job {i}",
            job_id=f"remote-job-{i}",
            target_run_config_id="config-1",
            latest_status=JobStatus.SUCCEEDED.value,
            parent=task,
        ).save_to_file()

    project_id = project.id
    task_id = task.id

    # Track calls to the update function
    update_calls = []

    async def mock_update(prompt_optimization_job, client):
        update_calls.append(prompt_optimization_job.job_id)
        return prompt_optimization_job

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.update_prompt_optimization_job_and_create_artifacts",
            new_callable=AsyncMock,
            side_effect=mock_update,
        ) as mock_update_fn,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs",
            params={"update_status": True},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 15

        # Should only update the 12 non-final jobs, not the 3 succeeded ones
        assert mock_update_fn.call_count == 12
        assert len(update_calls) == 12

        # Verify none of the succeeded jobs were updated
        succeeded_job_ids = {f"remote-job-{i}" for i in range(12, 15)}
        for job_id in update_calls:
            assert job_id not in succeeded_job_ids


def test_list_prompt_optimization_jobs_skips_final_status_updates(
    client, mock_api_key, tmp_path
):
    """Test that list_prompt_optimization_jobs skips updating jobs with final statuses."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create jobs with final statuses
    PromptOptimizationJob(
        name="Succeeded Job",
        job_id="remote-job-succeeded",
        target_run_config_id="config-1",
        latest_status=JobStatus.SUCCEEDED.value,
        parent=task,
    ).save_to_file()

    PromptOptimizationJob(
        name="Failed Job",
        job_id="remote-job-failed",
        target_run_config_id="config-1",
        latest_status=JobStatus.FAILED.value,
        parent=task,
    ).save_to_file()

    PromptOptimizationJob(
        name="Cancelled Job",
        job_id="remote-job-cancelled",
        target_run_config_id="config-1",
        latest_status=JobStatus.CANCELLED.value,
        parent=task,
    ).save_to_file()

    project_id = project.id
    task_id = task.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.update_prompt_optimization_job_and_create_artifacts",
            new_callable=AsyncMock,
        ) as mock_update,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs",
            params={"update_status": True},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 3

        # Should not call update for any of the jobs since they're all final
        mock_update.assert_not_called()


def test_prompt_optimization_job_from_id_not_found(client, tmp_path):
    """Test that prompt_optimization_job_from_id raises HTTPException when job not found."""

    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id
    nonexistent_job_id = "nonexistent-job-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        pytest.raises(Exception) as exc_info,
    ):
        prompt_optimization_job_from_id(project_id, task_id, nonexistent_job_id)

    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value.detail)


def test_update_prompt_optimization_job_status_no_parent_task(mock_api_key):
    """Test update_prompt_optimization_job_and_create_artifacts when job has no parent task."""

    prompt_optimization_job = PromptOptimizationJob(
        name="Orphan Job",
        job_id="remote-job-orphan",
        target_run_config_id="config-1",
        latest_status="pending",
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

    assert exc_info.value.status_code == 500
    assert "no parent task" in str(exc_info.value.detail)


def test_update_prompt_optimization_job_status_response_none(
    client, mock_api_key, tmp_path
):
    """Test update_prompt_optimization_job_and_create_artifacts when status response is None."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content=b'{"message": "Server error"}',
            ),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "pending"


def test_update_prompt_optimization_job_status_response_validation_error(
    client, mock_api_key, tmp_path
):
    """Test update_prompt_optimization_job_and_create_artifacts when status response is HTTPValidationError."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                content=b'{"message": "Validation error"}',
            ),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "pending"


def test_update_prompt_optimization_job_status_exception_during_update(
    client, mock_api_key, tmp_path
):
    """Test that update_prompt_optimization_job_and_create_artifacts handles exceptions during status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "pending"


def test_list_prompt_optimization_jobs_exception_during_update(
    client, mock_api_key, tmp_path
):
    """Test that list_prompt_optimization_jobs handles exceptions during status updates gracefully."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.update_prompt_optimization_job_and_create_artifacts",
            new_callable=AsyncMock,
            side_effect=Exception("Update failed"),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs",
            params={"update_status": True},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 1


def test_check_run_config_with_tools(client, mock_api_key, tmp_path):
    """Test that check_run_config returns False when run config has tools."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties.tools_config = MagicMock()
    mock_run_config.run_config_properties.tools_config.tools = [
        "kiln_tool::add_numbers"
    ]

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
        return_value=mock_run_config,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["is_supported"] is False


def test_check_run_config_missing_model_name(client, mock_api_key, tmp_path):
    """Test that check_run_config returns False when model_name is missing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None
    mock_run_config.run_config_properties.model_name = None
    mock_run_config.run_config_properties.model_provider_name = "openai"

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
        return_value=mock_run_config,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["is_supported"] is False


def test_check_run_config_missing_model_provider(client, mock_api_key, tmp_path):
    """Test that check_run_config returns False when model_provider is missing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None
    mock_run_config.run_config_properties.model_name = "gpt-4"
    mock_run_config.run_config_properties.model_provider_name = None

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
        return_value=mock_run_config,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["is_supported"] is False


def test_check_run_config_server_validation_error(client, mock_api_key, tmp_path):
    """Test that check_run_config handles HTTPValidationError from server."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None
    mock_run_config.run_config_properties.model_name = "gpt-4"
    mock_run_config.run_config_properties.model_provider_name = MagicMock()
    mock_run_config.run_config_properties.model_provider_name.value = "openai"

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                content=b'{"message": "Invalid model"}',
            ),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 422


def test_check_run_config_server_none_response(client, mock_api_key, tmp_path):
    """Test that check_run_config handles None response from server."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None
    mock_run_config.run_config_properties.model_name = "gpt-4"
    mock_run_config.run_config_properties.model_provider_name = MagicMock()
    mock_run_config.run_config_properties.model_provider_name.value = "openai"

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=None),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 500
        assert "unknown error" in response.json()["message"].lower()


def test_check_run_config_exception(client, mock_api_key, tmp_path):
    """Test that check_run_config handles general exceptions."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id
    run_config_id = "test-config-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
        side_effect=Exception("Database error"),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_run_config",
            params={"run_config_id": run_config_id},
        )

        assert response.status_code == 500
        assert "Failed to check run config" in response.json()["message"]


def test_check_eval_no_current_config(client, mock_api_key, tmp_path):
    """Test that check_eval returns False when eval has no current_config_id."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = None
    mock_eval.train_set_filter_id = None

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
        return_value=mock_eval,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_default_config"] is False
        assert result["has_train_set"] is False
        assert result["model_is_supported"] is False


def test_check_eval_config_not_found(client, mock_api_key, tmp_path):
    """Test that check_eval handles HTTPException when loading config."""

    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = None

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            side_effect=HTTPException(status_code=404, detail="Config not found"),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_default_config"] is False
        assert result["has_train_set"] is False
        assert result["model_is_supported"] is False


def test_check_eval_missing_model_name(client, mock_api_key, tmp_path):
    """Test that check_eval returns False when model_name is missing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = None

    mock_config = MagicMock()
    mock_config.model_name = None
    mock_config.model_provider = "openai"

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            return_value=mock_config,
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_default_config"] is True
        assert result["has_train_set"] is False
        assert result["model_is_supported"] is False


def test_check_eval_missing_model_provider(client, mock_api_key, tmp_path):
    """Test that check_eval returns False when model_provider is missing."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = None

    mock_config = MagicMock()
    mock_config.model_name = "gpt-4"
    mock_config.model_provider = None

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            return_value=mock_config,
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_default_config"] is True
        assert result["has_train_set"] is False
        assert result["model_is_supported"] is False


def test_check_eval_server_validation_error(client, mock_api_key, tmp_path):
    """Test that check_eval handles HTTPValidationError from server."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = None

    mock_config = MagicMock()
    mock_config.model_name = "gpt-4"
    mock_config.model_provider = "openai"

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                content=b'{"message": "Invalid model"}',
            ),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 422


def test_check_eval_server_none_response(client, mock_api_key, tmp_path):
    """Test that check_eval handles None response from server."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = None

    mock_config = MagicMock()
    mock_config.model_name = "gpt-4"
    mock_config.model_provider = "openai"

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=None),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 500
        assert "unknown error" in response.json()["message"].lower()


def test_check_eval_exception(client, mock_api_key, tmp_path):
    """Test that check_eval handles general exceptions."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
        side_effect=Exception("Database error"),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 500
        assert "Failed to check eval" in response.json()["message"]


@pytest.mark.parametrize(
    "train_set_filter_id,expected_has_train_set",
    [("tag::train", True), (None, False)],
)
def test_check_eval_success_train_set(
    client, mock_api_key, tmp_path, train_set_filter_id, expected_has_train_set
):
    """Test that check_eval returns correct has_train_set from eval.train_set_filter_id."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    mock_eval = MagicMock()
    mock_eval.current_config_id = "config-123"
    mock_eval.train_set_filter_id = train_set_filter_id

    mock_config = MagicMock()
    mock_config.model_name = "gpt-4"
    mock_config.model_provider = "openai"

    mock_check_response = MagicMock()
    mock_check_response.is_model_supported = True

    project_id = project.id
    task_id = task.id
    eval_id = "test-eval-id"

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_from_id",
            return_value=mock_eval,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.eval_config_from_id",
            return_value=mock_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.check_prompt_optimization_model_supported_v1_jobs_prompt_optimization_job_check_model_supported_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_check_response),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/check_eval",
            params={"eval_id": eval_id},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["has_default_config"] is True
        assert result["has_train_set"] is expected_has_train_set
        assert result["model_is_supported"] is True


def test_start_prompt_optimization_job_no_parent_project(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job raises HTTPException when task has no parent."""
    task = Task(
        name="Orphan Task",
        instruction="Test instruction",
    )

    project_id = "test-project-id"
    task_id = "test-task-id"

    with patch(
        "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
        return_value=task,
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 404
        assert "Project not found" in response.json()["message"]


def test_start_prompt_optimization_job_with_tools_in_run_config(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job raises HTTPException when run config has tools."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = MagicMock()
    mock_run_config.run_config_properties.tools_config.tools = ["tool1", "tool2"]

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 400
        assert "does not support" in response.json()["message"]
        assert "tools" in response.json()["message"]


def test_start_prompt_optimization_job_server_not_authenticated(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job raises HTTPException when server client is not authenticated."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.get_authenticated_client",
            return_value=MagicMock(spec=str),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 500
        assert "not authenticated" in response.json()["message"]


def test_start_prompt_optimization_job_server_validation_error(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job surfaces upstream validation errors via check_response_error."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=_mock_package_project_for_training,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                content=json.dumps({"message": "Upstream validation error"}).encode(),
            ),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 422
        assert "Upstream validation error" in response.json()["message"]


def test_start_prompt_optimization_job_server_none_response(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job handles None parsed response from server."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=_mock_package_project_for_training,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=None),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 500
        assert "unknown error" in response.json()["message"].lower()


def test_start_prompt_optimization_job_connection_error(client, mock_api_key, tmp_path):
    """Test that start_prompt_optimization_job handles connection errors with specific message."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    class ReadError(Exception):
        pass

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=_mock_package_project_for_training,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            side_effect=ReadError("Connection lost"),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 500
        assert "Connection error" in response.json()["message"]
        assert "too large" in response.json()["message"]


def test_start_prompt_optimization_job_timeout_error(client, mock_api_key, tmp_path):
    """Test that start_prompt_optimization_job handles timeout errors with specific message."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=_mock_package_project_for_training,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_prompt_optimization_job_v1_jobs_prompt_optimization_job_start_post.asyncio_detailed",
            new_callable=AsyncMock,
            side_effect=Exception("Request timeout occurred"),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 500
        assert "Connection error" in response.json()["message"]


def test_start_prompt_optimization_job_general_exception(
    client, mock_api_key, tmp_path
):
    """Test that start_prompt_optimization_job handles general exceptions."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_run_config = MagicMock()
    mock_run_config.run_config_properties = MagicMock(spec=KilnAgentRunConfigProperties)
    mock_run_config.run_config_properties.tools_config = None

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=mock_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.package_project_for_training",
            side_effect=Exception("Unexpected error"),
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start",
            json={
                "target_run_config_id": "test-run-config-id",
                "eval_ids": [],
            },
        )

        assert response.status_code == 500
        assert "Failed to start Prompt Optimization job" in response.json()["message"]


def test_prompt_optimization_job_creates_run_config_on_success(
    client, mock_api_key, tmp_path
):
    """Test that a run config is created when a Prompt Optimization job succeeds."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create a target run config
    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    assert target_run_config.id is not None

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"
        assert result["optimized_prompt"] == optimized_prompt

        # Check that exactly 1 prompt was created
        prompts = task.prompts()
        assert len(prompts) == 1
        assert prompts[0].prompt == optimized_prompt
        assert prompts[0].name == prompt_optimization_job.name

        # Check that exactly 1 new run config was created (2 total including target)
        run_configs = task.run_configs()
        assert len(run_configs) == 2
        new_run_config = [rc for rc in run_configs if rc.id != target_run_config.id][0]

        assert new_run_config.name
        assert new_run_config.name != target_run_config.name

        # Verify prompt is referenced by ID, not frozen
        assert new_run_config.prompt is None
        assert new_run_config.run_config_properties.prompt_id == f"id::{prompts[0].id}"

        # Verify other properties match target run config
        assert (
            new_run_config.run_config_properties.model_name
            == target_run_config.run_config_properties.model_name
        )
        assert (
            new_run_config.run_config_properties.model_provider_name
            == target_run_config.run_config_properties.model_provider_name
        )

        # Check that the prompt optimization job has the created run config ID
        assert result["created_run_config_id"] == new_run_config.id


def test_prompt_optimization_job_only_creates_run_config_once(
    client, mock_api_key, tmp_path
):
    """Test that a run config is only created once even if status is checked multiple times."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    assert target_run_config.id is not None

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
    ):
        response_1 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )
        assert response_1.status_code == 200

        response_2 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )
        assert response_2.status_code == 200

        # Should only create one run config and one prompt
        prompts = task.prompts()
        assert len(prompts) == 1

        run_configs = task.run_configs()
        assert len(run_configs) == 2


def test_prompt_optimization_job_run_config_handles_missing_target_config(
    client, mock_api_key, tmp_path
):
    """Test that run config creation handles missing target config gracefully."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="nonexistent-config-id",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"

        # Prompt should be cleaned up when run config creation fails
        prompts = task.prompts()
        assert len(prompts) == 0

        # Run config should not be created due to error
        run_configs = task.run_configs()
        assert len(run_configs) == 0
        assert result["created_run_config_id"] is None
        # created_prompt_id should also be None after cleanup
        assert result["created_prompt_id"] is None


def test_cleanup_artifact_deletes_prompt_successfully(mock_api_key, tmp_path):
    """Test that _cleanup_artifact successfully deletes a prompt."""
    from app.desktop.studio_server.prompt_optimization_job_api import _cleanup_artifact

    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create a prompt
    from kiln_ai.datamodel import Prompt

    prompt = Prompt(
        name="Test Prompt",
        description="Test",
        generator_id="test",
        prompt="Test prompt text",
        parent=task,
    )
    prompt.save_to_file()

    # Verify prompt exists
    prompts = task.prompts()
    assert len(prompts) == 1

    # Cleanup the prompt
    _cleanup_artifact(prompt, "prompt", "test-job-id")

    # Verify prompt is deleted
    prompts = task.prompts()
    assert len(prompts) == 0


def test_cleanup_artifact_deletes_run_config_successfully(mock_api_key, tmp_path):
    """Test that _cleanup_artifact successfully deletes a run config."""
    from app.desktop.studio_server.prompt_optimization_job_api import _cleanup_artifact

    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create a run config
    run_config = TaskRunConfig(
        parent=task,
        name="Test Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    run_config.save_to_file()

    # Verify run config exists
    run_configs = task.run_configs()
    assert len(run_configs) == 1

    # Cleanup the run config
    _cleanup_artifact(run_config, "run config", "test-job-id")

    # Verify run config is deleted
    run_configs = task.run_configs()
    assert len(run_configs) == 0


def test_cleanup_artifact_handles_none_gracefully(mock_api_key):
    """Test that _cleanup_artifact handles None without error."""
    from app.desktop.studio_server.prompt_optimization_job_api import _cleanup_artifact

    # Should not raise an exception
    _cleanup_artifact(None, "prompt", "test-job-id")


def test_cleanup_artifact_handles_deletion_error_gracefully(mock_api_key, tmp_path):
    """Test that _cleanup_artifact logs but doesn't raise when deletion fails."""
    from app.desktop.studio_server.prompt_optimization_job_api import _cleanup_artifact

    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    from kiln_ai.datamodel import Prompt

    prompt = Prompt(
        name="Test Prompt",
        description="Test",
        generator_id="test",
        prompt="Test prompt text",
        parent=task,
    )
    prompt.save_to_file()

    # Mock shutil.rmtree (which delete() uses internally) to raise an error
    with patch(
        "kiln_ai.datamodel.basemodel.shutil.rmtree",
        side_effect=Exception("Delete failed"),
    ):
        # Should not raise an exception, just log
        _cleanup_artifact(prompt, "prompt", "test-job-id")


def test_prompt_optimization_job_cleanup_prompt_when_prompt_creation_fails(
    client, mock_api_key, tmp_path
):
    """Test that artifacts are cleaned up when prompt creation fails."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    project_id = project.id
    task_id = task.id
    prompt_optimization_job_id = prompt_optimization_job.id

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.create_prompt_from_optimization",
            side_effect=Exception("Prompt creation failed"),
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/{prompt_optimization_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"

        # No artifacts should be created
        prompts = task.prompts()
        assert len(prompts) == 0

        run_configs = task.run_configs()
        assert len(run_configs) == 0

        # IDs should be None to allow retry
        assert result["created_prompt_id"] is None
        assert result["created_run_config_id"] is None


def test_prompt_optimization_job_cleanup_both_artifacts_when_run_config_fails_after_prompt_created(
    mock_api_key, tmp_path
):
    """Test that both prompt and run config are cleaned up when run config creation fails."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.prompt_optimization_job_from_id",
            return_value=prompt_optimization_job,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.create_run_config_from_optimization",
            side_effect=Exception("Run config creation failed"),
        ),
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

        # Job should show succeeded status
        assert updated_job.latest_status == JobStatus.SUCCEEDED.value

        # But no artifacts should remain due to cleanup
        prompts = task.prompts()
        assert len(prompts) == 0

        run_configs = task.run_configs()
        assert len(run_configs) == 1  # Only the original target config

        # IDs should be None to allow retry
        assert updated_job.created_prompt_id is None
        assert updated_job.created_run_config_id is None


def test_prompt_optimization_job_retry_after_cleanup(mock_api_key, tmp_path):
    """Test that artifact creation can be retried after cleanup from a previous failure."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    # First attempt: run config creation fails
    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.create_run_config_from_optimization",
            side_effect=Exception("Temporary failure"),
        ),
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

        # Verify cleanup happened
        assert updated_job.created_prompt_id is None
        assert updated_job.created_run_config_id is None
        prompts = task.prompts()
        assert len(prompts) == 0

    # Reload job from disk to simulate a fresh invocation
    prompt_optimization_job_reloaded = PromptOptimizationJob.from_id_and_parent_path(
        prompt_optimization_job.id, task.path
    )
    assert prompt_optimization_job_reloaded.created_prompt_id is None

    # Second attempt: should succeed because cleanup cleared the IDs
    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.prompt_optimization_job_from_id",
            return_value=prompt_optimization_job_reloaded,
        ),
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job_reloaded, mock_client
            )
        )

        # Now artifacts should be created successfully
        assert updated_job.created_prompt_id is not None
        assert updated_job.created_run_config_id is not None

        prompts = task.prompts()
        assert len(prompts) == 1
        assert prompts[0].prompt == optimized_prompt

        run_configs = task.run_configs()
        assert len(run_configs) == 2  # Original + new


def test_prompt_optimization_job_prevents_race_condition_on_artifact_creation(
    mock_api_key, tmp_path
):
    """Test that concurrent updates don't create duplicate artifacts due to locking."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status="pending",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    async def concurrent_updates():
        """Run two concurrent update calls to test locking."""
        with (
            patch(
                "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
                new_callable=AsyncMock,
                return_value=_make_sdk_response(parsed=mock_status_response),
            ),
            patch(
                "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
                new_callable=AsyncMock,
                return_value=_make_sdk_response(parsed=mock_result_response),
            ),
            patch(
                "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
                return_value=target_run_config,
            ),
            patch(
                "app.desktop.studio_server.prompt_optimization_job_api.prompt_optimization_job_from_id",
                return_value=prompt_optimization_job,
            ),
        ):
            # Call update_prompt_optimization_job_and_create_artifacts concurrently with asyncio.gather
            results = await asyncio.gather(
                update_prompt_optimization_job_and_create_artifacts(
                    prompt_optimization_job, mock_client
                ),
                update_prompt_optimization_job_and_create_artifacts(
                    prompt_optimization_job, mock_client
                ),
            )
            return results

    results = asyncio.run(concurrent_updates())

    # Both calls should succeed
    assert len(results) == 2
    assert results[0].latest_status == JobStatus.SUCCEEDED.value
    assert results[1].latest_status == JobStatus.SUCCEEDED.value

    # Should only create one prompt and one run config despite concurrent calls
    prompts = task.prompts()
    assert len(prompts) == 1

    run_configs = task.run_configs()
    assert len(run_configs) == 2  # original + optimized


@pytest.mark.parametrize(
    "previous_status,new_status,should_create_artifacts",
    [
        # Should create artifacts - transitioning TO succeeded from non-succeeded
        (JobStatus.PENDING, JobStatus.SUCCEEDED, True),
        (JobStatus.RUNNING, JobStatus.SUCCEEDED, True),
        (JobStatus.FAILED, JobStatus.SUCCEEDED, True),
        (JobStatus.CANCELLED, JobStatus.SUCCEEDED, True),
        # Should NOT create artifacts - already succeeded or not transitioning to succeeded
        (JobStatus.SUCCEEDED, JobStatus.SUCCEEDED, False),
        (JobStatus.PENDING, JobStatus.RUNNING, False),
        (JobStatus.PENDING, JobStatus.FAILED, False),
        (JobStatus.RUNNING, JobStatus.FAILED, False),
        (JobStatus.RUNNING, JobStatus.CANCELLED, False),
        (JobStatus.PENDING, JobStatus.CANCELLED, False),
    ],
)
def test_update_prompt_optimization_job_status_transitions(
    mock_api_key, tmp_path, previous_status, new_status, should_create_artifacts
):
    """Test that artifacts are only created when transitioning TO succeeded from non-succeeded status."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    # Create job with the previous_status
    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status=previous_status.value,
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    optimized_prompt = "This is the optimized prompt from Prompt Optimization"
    mock_status_response = JobStatusResponse(job_id="remote-job-123", status=new_status)
    mock_result_response = PromptOptimizationJobResultResponse(
        status=new_status,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.prompt_optimization_job_from_id",
            return_value=prompt_optimization_job,
        ),
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

    # Verify status was updated
    assert updated_job.latest_status == new_status.value

    # Verify artifacts created or not based on transition
    prompts = task.prompts()
    run_configs = task.run_configs()

    if should_create_artifacts:
        # Artifacts should be created
        assert len(prompts) == 1, (
            f"Expected 1 prompt for {previous_status.value} -> {new_status.value}"
        )
        assert prompts[0].prompt == optimized_prompt
        assert len(run_configs) == 2, (
            f"Expected 2 run configs for {previous_status.value} -> {new_status.value}"
        )
        assert updated_job.created_prompt_id is not None
        assert updated_job.created_run_config_id is not None
        assert updated_job.optimized_prompt == optimized_prompt
    else:
        # No artifacts should be created
        assert len(prompts) == 0, (
            f"Expected 0 prompts for {previous_status.value} -> {new_status.value}"
        )
        assert len(run_configs) == 1, (
            f"Expected 1 run config for {previous_status.value} -> {new_status.value}"
        )
        assert updated_job.created_prompt_id is None
        assert updated_job.created_run_config_id is None


def test_update_prompt_optimization_job_running_to_succeeded_creates_artifacts(
    mock_api_key, tmp_path
):
    """Test that transitioning from running to succeeded creates artifacts."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    target_run_config = TaskRunConfig(
        parent=task,
        name="Original Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode=StructuredOutputMode.default,
        ),
    )
    target_run_config.save_to_file()

    # Job starts as RUNNING (not pending)
    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id=target_run_config.id,
        latest_status=JobStatus.RUNNING.value,
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    optimized_prompt = "Optimized from running state"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = PromptOptimizationJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=PromptOptimizationJobOutput(optimized_prompt=optimized_prompt),
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_result_response),
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.task_run_config_from_id",
            return_value=target_run_config,
        ),
        patch(
            "app.desktop.studio_server.prompt_optimization_job_api.prompt_optimization_job_from_id",
            return_value=prompt_optimization_job,
        ),
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

    assert updated_job.latest_status == JobStatus.SUCCEEDED.value
    assert updated_job.optimized_prompt == optimized_prompt

    # Artifacts should be created even though previous status was RUNNING
    prompts = task.prompts()
    assert len(prompts) == 1
    assert prompts[0].prompt == optimized_prompt

    run_configs = task.run_configs()
    assert len(run_configs) == 2


def test_update_prompt_optimization_job_succeeded_to_succeeded_no_artifacts(
    mock_api_key, tmp_path
):
    """Test that job already succeeded does not recreate artifacts."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Job is already succeeded with artifacts
    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status=JobStatus.SUCCEEDED.value,
        optimized_prompt="Already optimized",
        created_prompt_id="id::existing-prompt",
        created_run_config_id="existing-run-config",
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

    # Should not fetch result since already succeeded
    mock_result.assert_not_called()

    # Status remains succeeded
    assert updated_job.latest_status == JobStatus.SUCCEEDED.value
    assert updated_job.optimized_prompt == "Already optimized"
    assert updated_job.created_prompt_id == "id::existing-prompt"
    assert updated_job.created_run_config_id == "existing-run-config"

    # No new artifacts should be created
    prompts = task.prompts()
    assert len(prompts) == 0

    run_configs = task.run_configs()
    assert len(run_configs) == 0


def test_update_prompt_optimization_job_pending_to_running_no_artifacts(
    mock_api_key, tmp_path
):
    """Test that transitioning from pending to running does not create artifacts."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for Prompt Optimization",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    prompt_optimization_job = PromptOptimizationJob(
        name="Test Job",
        job_id="remote-job-123",
        target_run_config_id="config-1",
        latest_status=JobStatus.PENDING.value,
        parent=task,
    )
    prompt_optimization_job.save_to_file()

    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.RUNNING
    )

    mock_client = MagicMock(spec=AuthenticatedClient)

    with (
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=_make_sdk_response(parsed=mock_status_response),
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_prompt_optimization_job_result_v1_jobs_prompt_optimization_job_job_id_result_get.asyncio_detailed",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        updated_job = asyncio.run(
            update_prompt_optimization_job_and_create_artifacts(
                prompt_optimization_job, mock_client
            )
        )

    # Should not fetch result since not succeeded
    mock_result.assert_not_called()

    # Status updated to running
    assert updated_job.latest_status == JobStatus.RUNNING.value

    # No artifacts should be created
    prompts = task.prompts()
    assert len(prompts) == 0

    run_configs = task.run_configs()
    assert len(run_configs) == 0

    assert updated_job.created_prompt_id is None
    assert updated_job.created_run_config_id is None
    assert updated_job.optimized_prompt is None
