from unittest.mock import AsyncMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.gepa_job_output import (
    GEPAJobOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.gepa_job_result_response import (
    GEPAJobResultResponse,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.http_validation_error import (
    HTTPValidationError,
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
from app.desktop.studio_server.gepa_job_api import (
    PublicGEPAJobResultResponse,
    PublicGEPAJobStatusResponse,
    connect_gepa_job_api,
    is_job_status_final,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import GepaJob, Project, Task


@pytest.fixture
def app():
    app = FastAPI()
    connect_gepa_job_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with (
        patch("app.desktop.studio_server.gepa_job_api.Config.shared") as mock_config,
        patch("kiln_ai.datamodel.basemodel.Config.shared") as mock_basemodel_config,
    ):
        mock_config_instance = mock_config.return_value
        mock_config_instance.kiln_copilot_api_key = "test_api_key"
        mock_config_instance.user_id = "test_user"

        mock_basemodel_config_instance = mock_basemodel_config.return_value
        mock_basemodel_config_instance.user_id = "test_user"

        yield mock_config_instance


def test_get_gepa_job_result_success(client, mock_api_key):
    """Test successfully getting a GEPA job result."""
    job_id = "test-job-123"
    expected_prompt = "This is the optimized prompt"

    mock_output = GEPAJobOutput(optimized_prompt=expected_prompt)
    mock_response = GEPAJobResultResponse(
        status=JobStatus.SUCCEEDED, output=mock_output
    )

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 200
        assert response.json() == {"optimized_prompt": expected_prompt}

        result = PublicGEPAJobResultResponse(**response.json())
        assert result.optimized_prompt == expected_prompt


def test_get_gepa_job_result_not_found(client, mock_api_key):
    """Test getting a GEPA job result that doesn't exist."""
    job_id = "nonexistent-job"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 404
        assert f"GEPA job {job_id} result not found" in response.json()["detail"]


def test_get_gepa_job_result_no_output(client, mock_api_key):
    """Test getting a GEPA job result that has no output."""
    job_id = "test-job-no-output"

    mock_response = GEPAJobResultResponse(status=JobStatus.RUNNING, output=None)

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 500
        assert "has no output" in response.json()["detail"]


def test_get_gepa_job_result_api_error(client, mock_api_key):
    """Test handling of API errors when getting GEPA job result."""
    job_id = "test-job-error"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
        new_callable=AsyncMock,
        side_effect=Exception("API connection failed"),
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 500
        assert "Failed to get GEPA job result" in response.json()["detail"]


def test_get_gepa_job_status_success(client, mock_api_key):
    """Test successfully getting GEPA job status."""
    job_id = "test-job-123"

    mock_response = JobStatusResponse(job_id=job_id, status=JobStatus.RUNNING)

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/status")

        assert response.status_code == 200
        assert response.json() == {"job_id": job_id, "status": "running"}

        result = PublicGEPAJobStatusResponse(**response.json())
        assert result.job_id == job_id
        assert result.status == JobStatus.RUNNING


def test_get_gepa_job_status_not_found(client, mock_api_key):
    """Test getting status for a job that doesn't exist."""
    job_id = "nonexistent-job"

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
        new_callable=AsyncMock,
        return_value=None,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/status")

        assert response.status_code == 404
        assert f"GEPA job {job_id} not found" in response.json()["detail"]


def test_get_gepa_job_result_no_api_key(client):
    """Test getting GEPA job result without API key configured."""
    job_id = "test-job-123"

    with patch("app.desktop.studio_server.gepa_job_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.kiln_copilot_api_key = None

        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 401
        assert "API key not configured" in response.json()["detail"]


def test_get_gepa_job_result_validation_error(client, mock_api_key):
    """Test getting GEPA job result with validation error from server."""
    job_id = "test-job-123"

    mock_error = HTTPValidationError(detail=[])

    with patch(
        "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
        new_callable=AsyncMock,
        return_value=mock_error,
    ):
        response = client.get(f"/api/gepa_jobs/{job_id}/result")

        assert response.status_code == 404


def test_public_gepa_job_result_response_model():
    """Test the PublicGEPAJobResultResponse Pydantic model."""
    prompt = "Test optimized prompt"
    model = PublicGEPAJobResultResponse(optimized_prompt=prompt)

    assert model.optimized_prompt == prompt
    assert model.model_dump() == {"optimized_prompt": prompt}

    json_str = model.model_dump_json()
    assert prompt in json_str

    parsed = PublicGEPAJobResultResponse.model_validate_json(json_str)
    assert parsed.optimized_prompt == prompt


def test_public_gepa_job_status_response_model():
    """Test the PublicGEPAJobStatusResponse Pydantic model."""
    job_id = "test-job-123"
    status = JobStatus.RUNNING
    model = PublicGEPAJobStatusResponse(job_id=job_id, status=status)

    assert model.job_id == job_id
    assert model.status == JobStatus.RUNNING
    assert model.model_dump() == {"job_id": job_id, "status": status}

    json_str = model.model_dump_json()
    assert job_id in json_str
    assert "running" in json_str

    parsed = PublicGEPAJobStatusResponse.model_validate_json(json_str)
    assert parsed.job_id == job_id
    assert parsed.status == JobStatus.RUNNING


def test_start_gepa_job_creates_datamodel(client, mock_api_key, tmp_path):
    """Test that starting a GEPA job creates and saves a GepaJob datamodel."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    project_id = project.id
    task_id = task.id

    mock_start_response = JobStartResponse(job_id="remote-job-123")

    with (
        patch(
            "app.desktop.studio_server.gepa_job_api.task_from_id",
            return_value=task,
        ),
        patch(
            "app.desktop.studio_server.gepa_job_api.zip_project",
            return_value=b"fake zip data",
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.start_gepa_job_v1_jobs_gepa_job_start_post.asyncio",
            new_callable=AsyncMock,
            return_value=mock_start_response,
        ),
    ):
        response = client.post(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/start",
            json={
                "token_budget": "medium",
                "target_run_config_id": "test-run-config-id",
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert result["job_id"] == "remote-job-123"
        assert result["token_budget"] == "medium"
        assert result["target_run_config_id"] == "test-run-config-id"
        assert result["latest_status"] == "pending"
        assert "id" in result
        assert "name" in result

        gepa_jobs = task.gepa_jobs()
        assert len(gepa_jobs) == 1
        assert gepa_jobs[0].job_id == "remote-job-123"


def test_list_gepa_jobs(client, mock_api_key, tmp_path):
    """Test listing all GEPA jobs for a task."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job_1 = GepaJob(
        name="Job 1",
        job_id="remote-job-1",
        token_budget="light",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    gepa_job_1.save_to_file()

    gepa_job_2 = GepaJob(
        name="Job 2",
        job_id="remote-job-2",
        token_budget="heavy",
        target_run_config_id="config-2",
        latest_status="succeeded",
        parent=task,
    )
    gepa_job_2.save_to_file()

    project_id = project.id
    task_id = task.id

    with patch(
        "app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs",
            params={"update_status": False},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 2
        job_names = {job["name"] for job in result}
        assert job_names == {"Job 1", "Job 2"}
        job_ids = {job["job_id"] for job in result}
        assert job_ids == {"remote-job-1", "remote-job-2"}


def test_get_gepa_job_detail(client, mock_api_key, tmp_path):
    """Test getting GEPA job detail."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.RUNNING
    )

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=mock_status_response,
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Test Job"
        assert result["job_id"] == "remote-job-123"
        assert result["latest_status"] == "running"


def test_gepa_job_creates_prompt_on_success(client, mock_api_key, tmp_path):
    """Test that a prompt is created when a GEPA job succeeds."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    optimized_prompt = "This is the optimized prompt from GEPA"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = GEPAJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=GEPAJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=mock_status_response,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
            new_callable=AsyncMock,
            return_value=mock_result_response,
        ),
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"
        assert result["optimized_prompt"] == optimized_prompt
        assert result["created_prompt_id"] is not None

        prompts = task.prompts()
        assert len(prompts) == 1
        assert prompts[0].prompt == optimized_prompt
        assert prompts[0].name == f"GEPA - {gepa_job.name}"
        assert prompts[0].generator_id == "gepa"


def test_gepa_job_only_creates_prompt_once(client, mock_api_key, tmp_path):
    """Test that a prompt is only created once even if status is checked multiple times."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="pending",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    optimized_prompt = "This is the optimized prompt from GEPA"
    mock_status_response = JobStatusResponse(
        job_id="remote-job-123", status=JobStatus.SUCCEEDED
    )
    mock_result_response = GEPAJobResultResponse(
        status=JobStatus.SUCCEEDED,
        output=GEPAJobOutput(optimized_prompt=optimized_prompt),
    )

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
            return_value=mock_status_response,
        ),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
            new_callable=AsyncMock,
            return_value=mock_result_response,
        ),
    ):
        response_1 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )
        assert response_1.status_code == 200

        response_2 = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )
        assert response_2.status_code == 200

        prompts = task.prompts()
        assert len(prompts) == 1


def test_get_gepa_job_skips_update_when_succeeded(client, mock_api_key, tmp_path):
    """Test that getting a job that's already succeeded skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="succeeded",
        optimized_prompt="Already optimized",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "succeeded"
        assert result["optimized_prompt"] == "Already optimized"

        mock_status.assert_not_called()
        mock_result.assert_not_called()


def test_get_gepa_job_skips_update_when_failed(client, mock_api_key, tmp_path):
    """Test that getting a job that's already failed skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="failed",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["latest_status"] == "failed"

        mock_status.assert_not_called()
        mock_result.assert_not_called()


def test_get_gepa_job_skips_update_when_cancelled(client, mock_api_key, tmp_path):
    """Test that getting a job that's already cancelled skips the API status update."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    gepa_job = GepaJob(
        name="Test Job",
        job_id="remote-job-123",
        token_budget="medium",
        target_run_config_id="config-1",
        latest_status="cancelled",
        parent=task,
    )
    gepa_job.save_to_file()

    project_id = project.id
    task_id = task.id
    gepa_job_id = gepa_job.id

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_status,
        patch(
            "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs.get_gepa_job_result_v1_jobs_gepa_job_job_id_result_get.asyncio",
            new_callable=AsyncMock,
        ) as mock_result,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs/{gepa_job_id}"
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


def test_list_gepa_jobs_updates_statuses_in_parallel_batches(
    client, mock_api_key, tmp_path
):
    """Test that list_gepa_jobs updates statuses in parallel batches of 5."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create 12 jobs with non-final statuses and 3 with final statuses
    for i in range(12):
        GepaJob(
            name=f"Job {i}",
            job_id=f"remote-job-{i}",
            token_budget="light",
            target_run_config_id="config-1",
            latest_status=JobStatus.PENDING.value
            if i % 2 == 0
            else JobStatus.RUNNING.value,
            parent=task,
        ).save_to_file()

    for i in range(12, 15):
        GepaJob(
            name=f"Job {i}",
            job_id=f"remote-job-{i}",
            token_budget="light",
            target_run_config_id="config-1",
            latest_status=JobStatus.SUCCEEDED.value,
            parent=task,
        ).save_to_file()

    project_id = project.id
    task_id = task.id

    # Track calls to the update function
    update_calls = []

    async def mock_update(gepa_job, client):
        update_calls.append(gepa_job.job_id)
        return gepa_job

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.gepa_job_api.update_gepa_job_status_and_create_prompt",
            new_callable=AsyncMock,
            side_effect=mock_update,
        ) as mock_update_fn,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs",
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


def test_list_gepa_jobs_skips_final_status_updates(client, mock_api_key, tmp_path):
    """Test that list_gepa_jobs skips updating jobs with final statuses."""
    project = Project(name="Test Project", path=tmp_path / "project.kiln")
    project.save_to_file()

    task = Task(
        name="Test Task",
        description="Test task for GEPA",
        instruction="Test instruction",
        parent=project,
    )
    task.save_to_file()

    # Create jobs with final statuses
    GepaJob(
        name="Succeeded Job",
        job_id="remote-job-succeeded",
        token_budget="light",
        target_run_config_id="config-1",
        latest_status=JobStatus.SUCCEEDED.value,
        parent=task,
    ).save_to_file()

    GepaJob(
        name="Failed Job",
        job_id="remote-job-failed",
        token_budget="light",
        target_run_config_id="config-1",
        latest_status=JobStatus.FAILED.value,
        parent=task,
    ).save_to_file()

    GepaJob(
        name="Cancelled Job",
        job_id="remote-job-cancelled",
        token_budget="light",
        target_run_config_id="config-1",
        latest_status=JobStatus.CANCELLED.value,
        parent=task,
    ).save_to_file()

    project_id = project.id
    task_id = task.id

    with (
        patch("app.desktop.studio_server.gepa_job_api.task_from_id", return_value=task),
        patch(
            "app.desktop.studio_server.gepa_job_api.update_gepa_job_status_and_create_prompt",
            new_callable=AsyncMock,
        ) as mock_update,
    ):
        response = client.get(
            f"/api/projects/{project_id}/tasks/{task_id}/gepa_jobs",
            params={"update_status": True},
        )

        assert response.status_code == 200
        result = response.json()
        assert len(result) == 3

        # Should not call update for any of the jobs since they're all final
        mock_update.assert_not_called()
