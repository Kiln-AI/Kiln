from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.clarify_spec_output import (
    ClarifySpecOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.generate_batch_output import (
    GenerateBatchOutput,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models.refine_spec_api_output import (
    RefineSpecApiOutput,
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


class TestDraftInputDataGuide:
    """Tests for the input data guide copilot proxy endpoint.

    The endpoint internally:
    1. Runs the kiln_server data guide job: POST /v1/jobs/data_guide_job/start,
       poll GET /v1/jobs/data-guide-job/{job_id}/status until final, then GET
       /v1/jobs/data_guide_job/{job_id}/result → `{"output": {"draft_guide"}}`
    2. Calls the local `generate_input_preview_samples` helper to produce
       preview inputs from that draft
    3. Returns both fields together
    """

    URL = "/api/projects/proj_x/tasks/task_y/copilot/draft_input_data_guide"

    DRAFT = (
        "# Semantics\n\n## Data Patterns\nShort greetings.\n\n"
        "# Style\n\n## Input-Level Metrics\nOne short sentence.\n\n"
        "# Presentation Defaults\n\nLowercase casual register.\n"
    )

    @staticmethod
    def _payload() -> dict:
        return {
            "target_task_info": {
                "task_prompt": "Translate to French.",
                "task_input_schema": "",
                "task_output_schema": "",
            },
            "input_examples": ["hello", "frog"],
            "num_preview_samples": 2,
            "run_config_properties": {
                "type": "kiln_agent",
                "model_name": "gpt-4",
                "model_provider_name": "openai",
                "prompt_id": "simple_prompt_builder",
                "structured_output_mode": "default",
            },
        }

    @staticmethod
    def _make_task(instruction: str = "Translate the input to French.") -> Task:
        return Task(name="MockTask", instruction=instruction)

    @classmethod
    def _mock_http(
        cls,
        *,
        job_id: str = "job-123",
        start_status_code: int = 200,
        start_content: bytes = b"{}",
        start_json: dict | None = None,
        statuses: list[str] | None = None,
        status_http_code: int = 200,
        status_content: bytes = b"{}",
        result_status_code: int = 200,
        result_content: bytes = b"{}",
        draft_guide: str | None = None,
    ):
        """Build a mock httpx client modelling the start/poll/result job flow.

        `statuses` is the sequence returned by successive status polls (defaults
        to a single "succeeded").
        """
        statuses = statuses if statuses is not None else ["succeeded"]
        draft_guide = cls.DRAFT if draft_guide is None else draft_guide

        start_resp = MagicMock(status_code=start_status_code)
        start_resp.content = start_content
        start_resp.json.return_value = (
            start_json if start_json is not None else {"job_id": job_id}
        )

        result_resp = MagicMock(status_code=result_status_code)
        result_resp.content = result_content
        result_resp.json.return_value = {
            "status": "succeeded",
            "output": {"draft_guide": draft_guide},
            "output_files": [],
        }

        status_iter = iter(statuses)

        async def _get(url, *a, **kw):
            if url.endswith("/status"):
                resp = MagicMock(status_code=status_http_code)
                resp.content = status_content
                try:
                    value = next(status_iter)
                except StopIteration:
                    value = statuses[-1]
                resp.json.return_value = {"job_id": job_id, "status": value}
                return resp
            return result_resp

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=start_resp)
        mock_http.get = AsyncMock(side_effect=_get)
        mock_http.__aenter__ = AsyncMock(side_effect=lambda: mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        return mock_http

    def _post(self, client, mock_http, *, task=None, sleep_mock=None):
        """Run the request with the standard set of patches."""
        from app.desktop.studio_server.data_gen_api import GuidePreviewSample

        task = task or self._make_task()
        mock_authclient = MagicMock()
        mock_authclient.get_async_httpx_client.return_value = mock_http

        async def fake_preview(**kwargs):
            return [
                GuidePreviewSample(input="generated 1"),
                GuidePreviewSample(input="generated 2"),
            ]

        with (
            patch(
                "app.desktop.studio_server.copilot_api.get_authenticated_client",
                return_value=mock_authclient,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.generate_input_preview_samples",
                new=fake_preview,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.asyncio.sleep",
                new=sleep_mock or AsyncMock(),
            ),
        ):
            return client.post(self.URL, json=self._payload())

    def test_no_api_key(self, client):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config_shared:
            mock_config_shared.return_value.kiln_copilot_api_key = None
            response = client.post(self.URL, json=self._payload())
            assert response.status_code == 401
            assert "API key not configured" in response.json()["message"]

    def test_success(self, client, mock_api_key):
        mock_http = self._mock_http()
        response = self._post(
            client, mock_http, task=self._make_task("Translate the input to French.")
        )

        assert response.status_code == 200
        body = response.json()
        # Copilot draft emits the Mike-strict three-section shape.
        assert body["draft_guide"].startswith("# Semantics")
        assert "# Style" in body["draft_guide"]
        assert "# Presentation Defaults" in body["draft_guide"]
        assert "# Reference Inputs" not in body["draft_guide"]
        assert body["preview_samples"] == [
            {"input": "generated 1"},
            {"input": "generated 2"},
        ]
        # Start call hit the job start endpoint with the right payload shape.
        assert mock_http.post.await_args.args == ("/v1/jobs/data_guide_job/start",)
        post_kwargs = mock_http.post.await_args.kwargs
        # task_prompt comes from the server-resolved runtime prompt
        # (task.instruction here, since this task has no default run config),
        # NOT from the frontend-supplied target_task_info.task_prompt.
        assert post_kwargs["json"]["task_prompt"] == "Translate the input to French."
        assert post_kwargs["json"]["input_examples"] == ["hello", "frog"]
        # The wrapper does NOT pass task_output_schema — output is out of scope.
        assert "task_output_schema" not in post_kwargs["json"]
        # The wrapper does NOT pass task_description — the model shouldn't see
        # the user-facing task description.
        assert "task_description" not in post_kwargs["json"]
        # Status was polled at the hyphenated job-type path, result at the
        # underscore path.
        get_urls = [c.args[0] for c in mock_http.get.await_args_list]
        assert get_urls == [
            "/v1/jobs/data-guide-job/job-123/status",
            "/v1/jobs/data_guide_job/job-123/result",
        ]

    def test_polls_until_final(self, client, mock_api_key):
        sleep_mock = AsyncMock()
        mock_http = self._mock_http(statuses=["pending", "running", "succeeded"])
        response = self._post(client, mock_http, sleep_mock=sleep_mock)

        assert response.status_code == 200
        # 3 status polls + 1 result fetch.
        assert mock_http.get.await_count == 4
        # Slept between the two non-final polls (after pending, after running).
        assert sleep_mock.await_count == 2

    def test_start_error_surfaces_message_field(self, client, mock_api_key):
        mock_http = self._mock_http(
            start_status_code=402,
            start_content=b'{"message": "Your trial has expired."}',
            start_json={"message": "Your trial has expired."},
        )
        response = self._post(client, mock_http)
        assert response.status_code == 402
        assert response.json()["message"] == "Your trial has expired."

    def test_start_error_non_json_falls_back_to_default(self, client, mock_api_key):
        mock_http = self._mock_http(
            start_status_code=502, start_content=b"upstream down"
        )
        response = self._post(client, mock_http)
        assert response.status_code == 502
        assert response.json()["message"] == (
            "Failed to start the data guide job. Please try again."
        )

    def test_missing_job_id_returns_500(self, client, mock_api_key):
        mock_http = self._mock_http(job_id="")
        response = self._post(client, mock_http)
        assert response.status_code == 500
        assert "job id" in response.json()["message"].lower()

    def test_status_poll_error_surfaces(self, client, mock_api_key):
        mock_http = self._mock_http(status_http_code=500)
        response = self._post(client, mock_http)
        assert response.status_code == 500
        assert response.json()["message"] == (
            "Failed to check the data guide job status."
        )

    def test_failed_job_status_returns_502(self, client, mock_api_key):
        mock_http = self._mock_http(statuses=["failed"])
        response = self._post(client, mock_http)
        assert response.status_code == 502
        assert "did not succeed" in response.json()["message"]
        assert "failed" in response.json()["message"]

    def test_result_fetch_error_surfaces(self, client, mock_api_key):
        mock_http = self._mock_http(result_status_code=502)
        response = self._post(client, mock_http)
        assert response.status_code == 502
        assert response.json()["message"] == ("Failed to fetch the data guide result.")

    def test_empty_draft_returns_500(self, client, mock_api_key):
        mock_http = self._mock_http(draft_guide="   ")
        response = self._post(client, mock_http)
        assert response.status_code == 500
        assert "empty" in response.json()["message"].lower()
