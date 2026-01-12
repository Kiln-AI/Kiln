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
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


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
    with patch("app.desktop.studio_server.gepa_job_api.Config.shared") as mock_config:
        mock_config_instance = mock_config.return_value
        mock_config_instance.kiln_copilot_api_key = "test_api_key"
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
