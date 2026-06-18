from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.clarify_spec_output import (
    ClarifySpecOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.data_guide_job_output import (
    DataGuideJobOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.data_guide_job_result_response import (
    DataGuideJobResultResponse,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.generate_batch_output import (
    GenerateBatchOutput,
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
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.job_type import (
    JobType,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.refine_spec_api_output import (
    RefineSpecApiOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import (
    Response as SdkResponse,
)
from app.desktop.studio_server.copilot_api import connect_copilot_api
from app.desktop.studio_server.utils.copilot_utils import DatasetTaskRuns
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import Project, Task
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_server.custom_errors import connect_custom_errors


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_copilot_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_api_key():
    with patch(
        "app.desktop.studio_server.utils.copilot_utils.Config.shared"
    ) as mock_config_shared:
        mock_config = mock_config_shared.return_value
        mock_config.kiln_copilot_api_key = "test_api_key"
        yield mock_config


@pytest.fixture
def clarify_spec_input():
    return {
        "target_task_info": {
            "task_prompt": "Test task prompt",
            "task_input_schema": '{"type": "string"}',
            "task_output_schema": '{"type": "string"}',
        },
        "target_specification": "Test template",
        "num_samples_per_topic": 5,
        "num_topics": 3,
        "providers": ["openai"],
        "num_exemplars": 10,
    }


@pytest.fixture
def refine_spec_input():
    return {
        "target_task_info": {
            "task_prompt": "Test task prompt",
            "task_input_schema": '{"type": "string"}',
            "task_output_schema": '{"type": "string"}',
        },
        "target_specification": {
            "spec_fields": {},
            "spec_field_current_values": {},
        },
        "examples_with_feedback": [
            {
                "user_agrees_with_judge": True,
                "input": "test input",
                "output": "test output",
                "fails_specification": False,
            }
        ],
    }


@pytest.fixture
def generate_batch_input():
    return {
        "target_task_info": {
            "task_prompt": "Test task prompt",
            "task_input_schema": '{"type": "string"}',
            "task_output_schema": '{"type": "string"}',
        },
        "sdg_session_config": {
            "topic_generation_config": {
                "task_metadata": {
                    "model_name": "gpt-4",
                    "model_provider_name": "openai",
                },
                "prompt": "Test topic generation prompt",
            },
            "input_generation_config": {
                "task_metadata": {
                    "model_name": "gpt-4",
                    "model_provider_name": "openai",
                },
                "prompt": "Test input generation prompt",
            },
            "output_generation_config": {
                "task_metadata": {
                    "model_name": "gpt-4",
                    "model_provider_name": "openai",
                },
                "prompt": "Test output generation prompt",
            },
        },
        "target_specification": "Test template",
        "num_samples_per_topic": 5,
        "num_topics": 3,
    }


class TestClarifySpec:
    def test_clarify_spec_no_api_key(self, client, clarify_spec_input):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None

            response = client.post("/api/copilot/clarify_spec", json=clarify_spec_input)
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_clarify_spec_success(self, client, clarify_spec_input, mock_api_key):
        mock_output = MagicMock(spec=ClarifySpecOutput)
        mock_output.to_dict.return_value = {
            "examples_for_feedback": [
                {
                    "input": "test input",
                    "output": "test output",
                    "fails_specification": False,
                }
            ],
            "judge_result": {
                "task_metadata": {
                    "model_name": "gpt-4",
                    "model_provider_name": "openai",
                },
                "prompt": "Test judge prompt",
            },
            "sdg_session_config": {
                "topic_generation_config": {
                    "task_metadata": {
                        "model_name": "gpt-4",
                        "model_provider_name": "openai",
                    },
                    "prompt": "Test topic generation prompt",
                },
                "input_generation_config": {
                    "task_metadata": {
                        "model_name": "gpt-4",
                        "model_provider_name": "openai",
                    },
                    "prompt": "Test input generation prompt",
                },
                "output_generation_config": {
                    "task_metadata": {
                        "model_name": "gpt-4",
                        "model_provider_name": "openai",
                    },
                    "prompt": "Test output generation prompt",
                },
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = mock_output

        with patch(
            "app.desktop.studio_server.copilot_api.clarify_spec_v1_copilot_clarify_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/clarify_spec", json=clarify_spec_input)
            assert response.status_code == 200
            result = response.json()
            assert "examples_for_feedback" in result
            assert result["judge_result"]["task_metadata"]["model_name"] == "gpt-4"

    def test_clarify_spec_no_response(self, client, clarify_spec_input, mock_api_key):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.copilot_api.clarify_spec_v1_copilot_clarify_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/clarify_spec", json=clarify_spec_input)
            assert response.status_code == 500
            assert "Failed to analyze spec" in response.json()["message"]

    def test_clarify_spec_validation_error(
        self, client, clarify_spec_input, mock_api_key
    ):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.content = b'{"message": "Validation error from server"}'

        with patch(
            "app.desktop.studio_server.copilot_api.clarify_spec_v1_copilot_clarify_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/clarify_spec", json=clarify_spec_input)
            assert response.status_code == 422
            assert "Validation error from server" in response.json()["message"]


class TestRefineSpec:
    def test_refine_spec_no_api_key(self, client, refine_spec_input):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None

            response = client.post("/api/copilot/refine_spec", json=refine_spec_input)
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_refine_spec_success(self, client, refine_spec_input, mock_api_key):
        mock_output = MagicMock(spec=RefineSpecApiOutput)
        mock_output.to_dict.return_value = {
            "new_proposed_spec_edits": [],
            "not_incorporated_feedback": None,
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = mock_output

        with patch(
            "app.desktop.studio_server.copilot_api.refine_spec_v1_copilot_refine_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/refine_spec", json=refine_spec_input)
            assert response.status_code == 200
            result = response.json()
            assert "new_proposed_spec_edits" in result
            assert "not_incorporated_feedback" in result

    def test_refine_spec_no_response(self, client, refine_spec_input, mock_api_key):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.copilot_api.refine_spec_v1_copilot_refine_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/refine_spec", json=refine_spec_input)
            assert response.status_code == 500
            assert "Failed to refine spec" in response.json()["message"]

    def test_refine_spec_validation_error(
        self, client, refine_spec_input, mock_api_key
    ):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.content = b'{"message": "Validation error from server"}'

        with patch(
            "app.desktop.studio_server.copilot_api.refine_spec_v1_copilot_refine_spec_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post("/api/copilot/refine_spec", json=refine_spec_input)
            assert response.status_code == 422
            assert "Validation error from server" in response.json()["message"]


class TestGenerateBatch:
    def test_generate_batch_no_api_key(self, client, generate_batch_input):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config = mock_config_shared.return_value
            mock_config.kiln_copilot_api_key = None

            response = client.post(
                "/api/copilot/generate_batch", json=generate_batch_input
            )
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_generate_batch_success(self, client, generate_batch_input, mock_api_key):
        mock_output = MagicMock(spec=GenerateBatchOutput)
        mock_output.to_dict.return_value = {"data_by_topic": {}}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = mock_output

        with patch(
            "app.desktop.studio_server.copilot_api.generate_batch_v1_copilot_generate_batch_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(
                "/api/copilot/generate_batch", json=generate_batch_input
            )
            assert response.status_code == 200
            result = response.json()
            assert "data_by_topic" in result

    def test_generate_batch_no_response(
        self, client, generate_batch_input, mock_api_key
    ):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.parsed = None

        with patch(
            "app.desktop.studio_server.copilot_api.generate_batch_v1_copilot_generate_batch_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(
                "/api/copilot/generate_batch", json=generate_batch_input
            )
            assert response.status_code == 500
            assert "Failed to generate synthetic data" in response.json()["message"]

    def test_generate_batch_validation_error(
        self, client, generate_batch_input, mock_api_key
    ):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.content = b'{"message": "Validation error from server"}'

        with patch(
            "app.desktop.studio_server.copilot_api.generate_batch_v1_copilot_generate_batch_post.asyncio_detailed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            response = client.post(
                "/api/copilot/generate_batch", json=generate_batch_input
            )
            assert response.status_code == 422
            assert "Validation error from server" in response.json()["message"]


class TestCreateSpecWithCopilot:
    @pytest.fixture
    def project_and_task(self, tmp_path):
        project_path = tmp_path / "test_project" / "project.kiln"
        project_path.parent.mkdir()
        project = Project(name="Test Project", path=project_path)
        project.save_to_file()
        task = Task(
            name="Test Task",
            instruction="Test instruction",
            description="Test task",
            parent=project,
        )
        task.save_to_file()
        return project, task

    @pytest.fixture
    def copilot_request_data(self):
        step_config = {
            "task_metadata": {
                "model_name": "gpt-4",
                "model_provider_name": "openai",
            },
            "prompt": "Test prompt",
        }
        return {
            "name": "Test Spec",
            "definition": "The system should respond politely",
            "properties": {
                "spec_type": SpecType.tone.value,
                "core_requirement": "Be polite",
                "tone_description": "Professional and friendly",
            },
            "judge_info": step_config,
            "sdg_session_config": {
                "topic_generation_config": step_config,
                "input_generation_config": step_config,
                "output_generation_config": step_config,
            },
            "task_description": "Test task",
            "task_prompt_with_example": "Test prompt",
        }

    def test_create_spec_with_copilot_success(
        self, client, project_and_task, copilot_request_data
    ):
        project, task = project_and_task

        with (
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.get_copilot_api_key",
                return_value="test_key",
            ),
            patch(
                "app.desktop.studio_server.copilot_api.generate_copilot_examples",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.desktop.studio_server.copilot_api.create_dataset_task_runs",
                return_value=DatasetTaskRuns(),
            ),
            patch(
                "app.desktop.studio_server.copilot_api.generate_memorable_name",
                return_value="test-config-name",
            ),
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=copilot_request_data,
            )

        assert response.status_code == 200
        res = response.json()
        assert res["name"] == "Test Spec"
        assert res["definition"] == "The system should respond politely"
        assert res["eval_id"] is not None

        # Verify models were saved
        evals = task.evals()
        assert len(evals) == 1
        assert evals[0].name == "Test Spec"
        assert evals[0].current_config_id is not None

        specs = task.specs()
        assert len(specs) == 1
        assert specs[0].eval_id == evals[0].id


_JOBS_API = "app.desktop.studio_server.api_client.kiln_ai_server_client.api.jobs"
_START_FN = f"{_JOBS_API}.start_data_guide_job_v1_jobs_data_guide_job_start_post.asyncio_detailed"
_STATUS_FN = (
    f"{_JOBS_API}.get_job_status_v1_jobs_job_type_job_id_status_get.asyncio_detailed"
)
_RESULT_FN = f"{_JOBS_API}.get_data_guide_job_result_v1_jobs_data_guide_job_job_id_result_get.asyncio_detailed"


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


class TestDataGuideJob:
    """Tests for the data guide draft job proxy endpoints.

    The draft runs as a kiln_server background job. The studio server proxies
    its lifecycle (via the generated kiln_ai_server_client) so the web UI owns
    polling:
      - POST .../copilot/data_guide_job/start → start_data_guide_job
      - GET  .../copilot/data_guide_job/{id}/status → get_job_status (DATA_GUIDE_JOB)
      - GET  .../copilot/data_guide_job/{id}/result → get_data_guide_job_result
    """

    START_URL = "/api/projects/proj_x/tasks/task_y/copilot/data_guide_job/start"
    STATUS_URL = (
        "/api/projects/proj_x/tasks/task_y/copilot/data_guide_job/job-123/status"
    )
    RESULT_URL = (
        "/api/projects/proj_x/tasks/task_y/copilot/data_guide_job/job-123/result"
    )

    DRAFT = (
        "# Semantics\n\n## Data Patterns\nShort greetings.\n\n"
        "# Style\n\n## Input-Level Metrics\nOne short sentence.\n\n"
        "# Presentation Defaults\n\nLowercase casual register.\n"
    )

    @staticmethod
    def _start_payload() -> dict:
        return {
            "task_input_schema": "",
            "input_examples": ["hello", "frog"],
        }

    @staticmethod
    def _make_task(instruction: str = "Translate the input to French.") -> Task:
        return Task(name="MockTask", instruction=instruction)

    def _patches(self, fn_path: str, sdk_mock: AsyncMock, *, task=None):
        """Patch the typed SDK endpoint plus the auth client and (for start)
        task lookup. The mocked endpoint never touches the auth client, so a
        bare MagicMock suffices."""
        return (
            patch(fn_path, sdk_mock),
            patch(
                "app.desktop.studio_server.copilot_api.get_authenticated_client",
                return_value=MagicMock(),
            ),
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=task or self._make_task(),
            ),
        )

    # --- start --------------------------------------------------------------

    def test_start_no_api_key(self, client):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config_shared.return_value.kiln_copilot_api_key = None
            response = client.post(self.START_URL, json=self._start_payload())
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_start_success(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(parsed=JobStartResponse(job_id="job-123"))
        )
        p1, p2, p3 = self._patches(
            _START_FN, sdk_mock, task=self._make_task("Translate the input to French.")
        )
        with p1, p2, p3:
            response = client.post(self.START_URL, json=self._start_payload())

        assert response.status_code == 200
        assert response.json() == {"job_id": "job-123"}
        # The typed request body carries the server-resolved runtime prompt
        # (task.instruction here, since this task has no default run config),
        # never a client-supplied prompt.
        body = sdk_mock.await_args.kwargs["body"]
        assert body.task_prompt == "Translate the input to French."
        assert body.input_examples == ["hello", "frog"]
        # The body model has no output schema or task description fields — output
        # policy must never reach the guide LLM.
        body_dict = body.to_dict()
        assert "task_output_schema" not in body_dict
        assert "task_description" not in body_dict

    def test_start_error_surfaces_message_field(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                status_code=HTTPStatus.PAYMENT_REQUIRED,
                content=b'{"message": "Your trial has expired."}',
            )
        )
        p1, p2, p3 = self._patches(_START_FN, sdk_mock)
        with p1, p2, p3:
            response = client.post(self.START_URL, json=self._start_payload())
        assert response.status_code == 402
        assert response.json()["message"] == "Your trial has expired."

    def test_start_error_non_json_falls_back_to_default(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                status_code=HTTPStatus.BAD_GATEWAY,
                content=b"upstream down",
            )
        )
        p1, p2, p3 = self._patches(_START_FN, sdk_mock)
        with p1, p2, p3:
            response = client.post(self.START_URL, json=self._start_payload())
        assert response.status_code == 502
        assert response.json()["message"] == (
            "Failed to start the data guide job. Please try again."
        )

    def test_start_missing_job_id_returns_500(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(parsed=JobStartResponse(job_id=""))
        )
        p1, p2, p3 = self._patches(_START_FN, sdk_mock)
        with p1, p2, p3:
            response = client.post(self.START_URL, json=self._start_payload())
        assert response.status_code == 500
        assert "job id" in response.json()["message"].lower()

    # --- status -------------------------------------------------------------

    def test_status_success(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=JobStatusResponse(job_id="job-123", status=JobStatus.RUNNING)
            )
        )
        p1, p2, p3 = self._patches(_STATUS_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.STATUS_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "running"}
        # Status routes through the shared status endpoint keyed by job type.
        assert sdk_mock.await_args.kwargs["job_type"] == JobType.DATA_GUIDE_JOB
        assert sdk_mock.await_args.kwargs["job_id"] == "job-123"

    def test_status_error_surfaces(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR
            )
        )
        p1, p2, p3 = self._patches(_STATUS_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.STATUS_URL)
        assert response.status_code == 500
        assert response.json()["message"] == (
            "Failed to check the data guide job status."
        )

    # --- result -------------------------------------------------------------

    def test_result_success(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(
                    status=JobStatus.SUCCEEDED,
                    output=DataGuideJobOutput(draft_guide=self.DRAFT),
                )
            )
        )
        p1, p2, p3 = self._patches(_RESULT_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.RESULT_URL)
        assert response.status_code == 200
        draft = response.json()["draft_guide"]
        # Copilot draft emits the Mike-strict three-section shape.
        assert draft.startswith("# Semantics")
        assert "# Style" in draft
        assert "# Presentation Defaults" in draft
        assert "# Reference Inputs" not in draft
        assert sdk_mock.await_args.kwargs["job_id"] == "job-123"

    def test_result_empty_output_returns_500(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(
                    status=JobStatus.SUCCEEDED, output=None
                )
            )
        )
        p1, p2, p3 = self._patches(_RESULT_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.RESULT_URL)
        assert response.status_code == 500
        assert "empty draft guide" in response.json()["message"].lower()

    def test_result_fetch_error_surfaces(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(status_code=HTTPStatus.BAD_GATEWAY)
        )
        p1, p2, p3 = self._patches(_RESULT_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.RESULT_URL)
        assert response.status_code == 502
        assert response.json()["message"] == ("Failed to fetch the data guide result.")

    def test_result_empty_draft_returns_500(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(
                    status=JobStatus.SUCCEEDED,
                    output=DataGuideJobOutput(draft_guide="   "),
                )
            )
        )
        p1, p2, p3 = self._patches(_RESULT_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.RESULT_URL)
        assert response.status_code == 500
        assert "empty" in response.json()["message"].lower()
