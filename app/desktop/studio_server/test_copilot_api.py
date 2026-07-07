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
from kiln_ai.datamodel import Project, Task, TaskRun
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalConfigType, EvalDataType, LlmJudgeProperties
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_ai.datamodel.task_output import DataSource, DataSourceType, TaskOutput
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

        # The saved judge is a V2 config: typed LlmJudgeProperties with the
        # judge prompt wrapped into a template (single-turn → I/O data blocks),
        # not the legacy llm_as_judge dict.
        configs = evals[0].configs()
        assert len(configs) == 1
        config = configs[0]
        assert config.config_type == EvalConfigType.v2
        assert isinstance(config.properties, LlmJudgeProperties)
        assert config.properties.model_name == "gpt-4"
        assert config.properties.model_provider == "openai"
        assert "Test prompt" in config.properties.prompt_template
        assert "{{ task_input }}" in config.properties.prompt_template
        assert config.model_name is None and config.model_provider is None

        specs = task.specs()
        assert len(specs) == 1
        assert specs[0].eval_id == evals[0].id


class TestClassifySpecDescription:
    """Stub endpoint. Returns 501 until kiln_server ships the real classifier."""

    def test_returns_501(self, client):
        response = client.post(
            "/api/copilot/classify_spec_description",
            json={"description": "A classification request"},
        )

        assert response.status_code == 501


class TestCreateSpecWithCopilotMultiTurn:
    """Multi-turn save path: tag existing chain leaves instead of synthesising
    new examples. See specs/projects/eval_builder_v2/design.md for context.
    """

    BATCH_TAG = "abc123def456"

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
    def synthetic_chain_leaves(self, project_and_task):
        """Persist three single-run "chains" tagged like the multi-turn runner
        leaves them. Single TaskRuns (no actual multi-turn parents) are
        sufficient: the endpoint only cares about the leaf tag.
        """
        _, task = project_and_task
        source = DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "haiku",
                "model_provider": "openrouter",
                "adapter_name": "kiln_synthetic_user_runner",
            },
        )
        leaves = []
        for i in range(3):
            run = TaskRun(
                parent=task,
                input=f"input {i}",
                input_source=source,
                output=TaskOutput(output=f"output {i}", source=source),
                tags=[
                    "synthetic_user_case",
                    f"synthetic_user_batch:{TestCreateSpecWithCopilotMultiTurn.BATCH_TAG}",
                ],
            )
            run.save_to_file()
            leaves.append(run)
        return leaves

    @pytest.fixture
    def multi_turn_request_data(self):
        step_config = {
            "task_metadata": {
                "model_name": "gpt-4",
                "model_provider_name": "openai",
            },
            "prompt": "Test prompt",
        }
        return {
            "name": "Multi Turn Spec",
            "definition": "The agent should not fabricate policies",
            "properties": {
                "spec_type": SpecType.issue.value,
                "issue_description": "Don't make stuff up",
            },
            "evaluate_full_trace": True,
            "judge_info": step_config,
            "multi_turn": {"batch_tag": TestCreateSpecWithCopilotMultiTurn.BATCH_TAG},
            "task_description": "Test task",
            "task_prompt_with_example": "Test prompt",
        }

    @staticmethod
    def _reviewed_chain(leaf_run_id: str, meets_spec: bool) -> dict:
        return {
            "leaf_run_id": leaf_run_id,
            "user_says_meets_spec": meets_spec,
            "feedback": "" if meets_spec else "Fabricated a return window.",
            "claim_review": {
                "judge_score": "PASS" if meets_spec else "FAIL",
                "judge_reasoning": "Judge reasoning here.",
                "claims": [
                    {
                        "claim": "The agent stated a return window.",
                        "evidence": "Gives 30 days [1].",
                        "expected_result": "fail",
                        "human_grade": "agree",
                        "human_feedback": None,
                    }
                ],
                "final_judgement": {
                    "claim": "Overall verdict.",
                    "evidence": "Decisive fact [1].",
                    "expected_result": "pass" if meets_spec else "fail",
                    "human_grade": "agree",
                    "human_feedback": None,
                },
            },
        }

    def test_multi_turn_save_success_tags_chains_and_creates_eval(
        self,
        client,
        project_and_task,
        synthetic_chain_leaves,
        multi_turn_request_data,
    ):
        project, task = project_and_task
        # Two of the three chains were reviewed: one pass, one fail.
        multi_turn_request_data["multi_turn"]["reviewed_chains"] = [
            self._reviewed_chain(synthetic_chain_leaves[0].id, meets_spec=False),
            self._reviewed_chain(synthetic_chain_leaves[1].id, meets_spec=True),
        ]

        with (
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.generate_memorable_name",
                return_value="multi-turn-judge",
            ),
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 200, response.text
        res = response.json()
        assert res["name"] == "Multi Turn Spec"
        assert res["eval_id"] is not None
        # Multi-turn doesn't snapshot a generation config on the spec —
        # the operational state lives on the Eval.
        assert res["synthetic_data_generation_session_config"] is None

        # Eval: full_trace data type + judge config attached.
        # Note: train_set_filter_id is saved as None on disk but a
        # backward-compat migration in Eval (libs/core/.../eval.py
        # migrate_train_set_filter_id) auto-populates it to
        # tag::train_<name> on read for legacy evals. The functional
        # invariant for multi-turn is "no runs tagged with train_*",
        # checked below — the field value itself is incidental.
        evals = task.evals()
        assert len(evals) == 1
        eval_obj = evals[0]
        assert eval_obj.evaluation_data_type == EvalDataType.full_trace
        assert eval_obj.eval_set_filter_id == "tag::eval_multi_turn_spec"
        assert eval_obj.current_config_id is not None

        # The saved judge is a V2 config with a multi-turn (trace) template.
        configs = eval_obj.configs()
        assert len(configs) == 1
        assert configs[0].config_type == EvalConfigType.v2
        assert isinstance(configs[0].properties, LlmJudgeProperties)
        assert "{{ trace | tojson }}" in configs[0].properties.prompt_template

        # Leaves got the eval + golden tags applied on top of their existing
        # synthetic_user_* tags. No train tag (multi-turn has no train set).
        expected_eval_tag = "eval_multi_turn_spec"
        expected_golden_tag = "eval_golden_multi_turn_spec"
        train_tag = "train_multi_turn_spec"
        for leaf in task.runs():
            assert expected_eval_tag in leaf.tags
            assert expected_golden_tag in leaf.tags
            assert train_tag not in leaf.tags
            assert "synthetic_user_case" in leaf.tags

        # Reviewed leaves carry golden ratings matching the review clicks,
        # plus feedback + per-claim grades; the unreviewed leaf stays unrated.
        runs_by_id = {run.id: run for run in task.runs()}
        rating_key = "named::Multi Turn Spec"
        failed = runs_by_id[synthetic_chain_leaves[0].id]
        assert failed.output.rating.requirement_ratings[rating_key].value == 0.0
        assert (
            failed.output.rating.requirement_ratings[rating_key].type
            == TaskOutputRatingType.pass_fail
        )
        assert len(failed.feedback()) == 1
        assert failed.feedback()[0].feedback == "Fabricated a return window."
        assert len(failed.claim_reviews()) == 1
        assert failed.claim_reviews()[0].judge_score == "FAIL"
        assert failed.claim_reviews()[0].final_judgement.expected_result == "fail"

        passed = runs_by_id[synthetic_chain_leaves[1].id]
        assert passed.output.rating.requirement_ratings[rating_key].value == 1.0
        assert passed.feedback() == []
        assert len(passed.claim_reviews()) == 1

        unreviewed = runs_by_id[synthetic_chain_leaves[2].id]
        assert unreviewed.output.rating is None
        assert unreviewed.claim_reviews() == []

    def test_multi_turn_save_unknown_leaf_fails_before_any_save(
        self,
        client,
        project_and_task,
        synthetic_chain_leaves,
        multi_turn_request_data,
    ):
        # A reviewed chain referencing a leaf outside the batch is rejected up
        # front — nothing is created and no leaf is mutated.
        project, task = project_and_task
        multi_turn_request_data["multi_turn"]["reviewed_chains"] = [
            self._reviewed_chain(synthetic_chain_leaves[0].id, meets_spec=False),
            self._reviewed_chain("not_a_real_leaf", meets_spec=True),
        ]

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 404
        assert "not_a_real_leaf" in response.json()["message"]
        assert len(task.evals()) == 0
        assert len(task.specs()) == 0
        for leaf in task.runs():
            assert leaf.output.rating is None
            assert leaf.feedback() == []
            assert leaf.claim_reviews() == []
            assert "eval_multi_turn_spec" not in leaf.tags
            assert "eval_golden_multi_turn_spec" not in leaf.tags

    def test_multi_turn_save_rejects_duplicate_reviewed_leaves(
        self,
        client,
        project_and_task,
        synthetic_chain_leaves,
        multi_turn_request_data,
    ):
        # The same leaf reviewed twice is a malformed request — rejected up
        # front (422) with nothing created or mutated.
        project, task = project_and_task
        multi_turn_request_data["multi_turn"]["reviewed_chains"] = [
            self._reviewed_chain(synthetic_chain_leaves[0].id, meets_spec=False),
            self._reviewed_chain(synthetic_chain_leaves[0].id, meets_spec=True),
        ]

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 422
        assert "at most once" in response.json()["message"]
        assert len(task.evals()) == 0
        assert len(task.specs()) == 0
        for leaf in task.runs():
            assert leaf.output.rating is None

    def test_multi_turn_save_failure_mid_rating_rolls_back(
        self,
        client,
        project_and_task,
        synthetic_chain_leaves,
        multi_turn_request_data,
    ):
        # A failure AFTER tagging/rating started reverses everything: leaf
        # tags and ratings revert, created models are deleted.
        project, task = project_and_task
        multi_turn_request_data["multi_turn"]["reviewed_chains"] = [
            self._reviewed_chain(synthetic_chain_leaves[0].id, meets_spec=False),
        ]

        from app.desktop.studio_server.utils import copilot_utils

        def rate_then_boom(*args, **kwargs):
            copilot_utils.rate_multi_turn_chain_leaves(*args, **kwargs)
            raise RuntimeError("disk full")

        with (
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=task,
            ),
            patch(
                "app.desktop.studio_server.copilot_api.rate_multi_turn_chain_leaves",
                side_effect=rate_then_boom,
            ),
            # The endpoint re-raises after rollback; TestClient propagates it.
            pytest.raises(RuntimeError, match="disk full"),
        ):
            client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert len(task.evals()) == 0
        assert len(task.specs()) == 0
        for leaf in task.runs():
            assert leaf.output.rating is None
            assert leaf.feedback() == []
            assert leaf.claim_reviews() == []
            assert "eval_multi_turn_spec" not in leaf.tags
            assert "eval_golden_multi_turn_spec" not in leaf.tags

    def test_multi_turn_save_404_when_batch_tag_matches_nothing(
        self, client, project_and_task, multi_turn_request_data
    ):
        project, task = project_and_task

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 404
        assert "batch_tag" in response.json()["message"]
        # No models created when the lookup fails up front.
        assert len(task.evals()) == 0
        assert len(task.specs()) == 0

    def test_validator_rejects_both_multi_turn_and_sdg_config(
        self, client, project_and_task, multi_turn_request_data
    ):
        project, task = project_and_task
        step_config = {
            "task_metadata": {
                "model_name": "gpt-4",
                "model_provider_name": "openai",
            },
            "prompt": "Test prompt",
        }
        multi_turn_request_data["sdg_session_config"] = {
            "topic_generation_config": step_config,
            "input_generation_config": step_config,
            "output_generation_config": step_config,
        }

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 422
        body = response.json()
        # Pydantic surfaces the validator message somewhere in the response.
        assert "multi_turn" in str(body) and "sdg_session_config" in str(body)

    def test_validator_rejects_neither_multi_turn_nor_sdg_config(
        self, client, project_and_task, multi_turn_request_data
    ):
        project, task = project_and_task
        del multi_turn_request_data["multi_turn"]

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 422
        assert "multi_turn" in str(response.json())

    def test_validator_rejects_multi_turn_without_evaluate_full_trace(
        self, client, project_and_task, multi_turn_request_data
    ):
        project, task = project_and_task
        multi_turn_request_data["evaluate_full_trace"] = False

        with patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        ):
            response = client.post(
                f"/api/projects/{project.id}/tasks/{task.id}/spec_with_copilot",
                json=multi_turn_request_data,
            )

        assert response.status_code == 422
        assert "evaluate_full_trace" in str(response.json())


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
        # Plaintext task → no input schema derived.
        assert not body.task_input_schema
        # The body model has no output schema or task description fields — output
        # policy must never reach the guide LLM.
        body_dict = body.to_dict()
        assert "task_output_schema" not in body_dict
        assert "task_description" not in body_dict

    def test_start_derives_input_schema_from_task(self, client, mock_api_key):
        """The input schema is read off the task server-side, not sent by the
        client (the payload has no schema field)."""
        schema = '{"type": "object", "properties": {"q": {"type": "string"}}}'
        structured_task = Task(
            name="MockTask",
            instruction="Answer the question.",
            input_json_schema=schema,
        )
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(parsed=JobStartResponse(job_id="job-123"))
        )
        p1, p2, p3 = self._patches(_START_FN, sdk_mock, task=structured_task)
        with p1, p2, p3:
            response = client.post(
                self.START_URL,
                json={"input_examples": ['{"q": "hello"}', '{"q": "frog"}']},
            )
        assert response.status_code == 200
        body = sdk_mock.await_args.kwargs["body"]
        assert body.task_input_schema == schema

    # --- structured-input validation ----------------------------------------

    STRUCTURED_SCHEMA = (
        '{"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}'
    )

    def _structured_task(self) -> Task:
        return Task(
            name="MockTask",
            instruction="Answer the question.",
            input_json_schema=self.STRUCTURED_SCHEMA,
        )

    def test_start_accepts_valid_structured_examples(self, client, mock_api_key):
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(parsed=JobStartResponse(job_id="job-123"))
        )
        p1, p2, p3 = self._patches(_START_FN, sdk_mock, task=self._structured_task())
        with p1, p2, p3:
            response = client.post(
                self.START_URL,
                json={"input_examples": ['{"q": "hello"}', '{"q": "frog"}']},
            )
        assert response.status_code == 200
        sdk_mock.assert_awaited_once()

    def test_start_rejects_structured_example_not_matching_schema(
        self, client, mock_api_key
    ):
        sdk_mock = AsyncMock()
        p1, p2, p3 = self._patches(_START_FN, sdk_mock, task=self._structured_task())
        with p1, p2, p3:
            response = client.post(
                self.START_URL,
                # second example is missing the required "q" field
                json={"input_examples": ['{"q": "ok"}', "{}"]},
            )
        assert response.status_code == 422
        assert "Example 2" in response.json()["message"]
        # validation must fail before the draft job is started
        sdk_mock.assert_not_awaited()

    def test_start_rejects_non_json_structured_example(self, client, mock_api_key):
        sdk_mock = AsyncMock()
        p1, p2, p3 = self._patches(_START_FN, sdk_mock, task=self._structured_task())
        with p1, p2, p3:
            response = client.post(
                self.START_URL,
                json={"input_examples": ["not valid json"]},
            )
        assert response.status_code == 422
        assert "not valid JSON" in response.json()["message"]
        sdk_mock.assert_not_awaited()

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

    def test_status_succeeded_held_until_result_ready(self, client, mock_api_key):
        """Status reads succeeded but the result endpoint still reports the job
        in-progress → hold at running so the UI stays in-progress instead of
        fetching an unfinished result."""
        status_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=JobStatusResponse(job_id="job-123", status=JobStatus.SUCCEEDED)
            )
        )
        result_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(status=JobStatus.RUNNING, output=None)
            )
        )
        with (
            patch(_STATUS_FN, status_mock),
            patch(_RESULT_FN, result_mock),
            patch(
                "app.desktop.studio_server.copilot_api.get_authenticated_client",
                return_value=MagicMock(),
            ),
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=self._make_task(),
            ),
        ):
            response = client.get(self.STATUS_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "running"}

    def test_status_succeeded_when_result_ready(self, client, mock_api_key):
        """When both status and result report succeeded, report succeeded."""
        status_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=JobStatusResponse(job_id="job-123", status=JobStatus.SUCCEEDED)
            )
        )
        result_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(
                    status=JobStatus.SUCCEEDED,
                    output=DataGuideJobOutput(draft_guide="# Semantics"),
                )
            )
        )
        with (
            patch(_STATUS_FN, status_mock),
            patch(_RESULT_FN, result_mock),
            patch(
                "app.desktop.studio_server.copilot_api.get_authenticated_client",
                return_value=MagicMock(),
            ),
            patch(
                "app.desktop.studio_server.copilot_api.task_from_id",
                return_value=self._make_task(),
            ),
        ):
            response = client.get(self.STATUS_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "succeeded"}

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

    def test_result_not_ready_returns_425(self, client, mock_api_key):
        """If the result endpoint returns before the job is actually succeeded
        (output not yet committed), surface a distinct "still generating" 425
        rather than mislabeling it as an empty draft."""
        sdk_mock = AsyncMock(
            return_value=_make_sdk_response(
                parsed=DataGuideJobResultResponse(status=JobStatus.RUNNING, output=None)
            )
        )
        p1, p2, p3 = self._patches(_RESULT_FN, sdk_mock)
        with p1, p2, p3:
            response = client.get(self.RESULT_URL)
        assert response.status_code == 425
        assert "still being generated" in response.json()["message"].lower()


class TestParseImportFile:
    """Tests for the server-side bulk-import file parser.

    Plaintext tasks → single-column CSV (stdlib csv reader, single-column
    enforced). Structured tasks → one JSON object per line, schema-validated.
    """

    URL = "/api/projects/proj_x/tasks/task_y/copilot/parse_import_file"

    STRUCTURED_SCHEMA = (
        '{"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}'
    )

    def _post(self, client, content: bytes, name: str = "examples.csv"):
        return client.post(self.URL, files={"file": (name, content, "text/plain")})

    def _patch_task(self, task: Task):
        return patch(
            "app.desktop.studio_server.copilot_api.task_from_id",
            return_value=task,
        )

    def _plaintext_task(self) -> Task:
        return Task(name="MockTask", instruction="Echo the input.")

    def _structured_task(self) -> Task:
        return Task(
            name="MockTask",
            instruction="Answer.",
            input_json_schema=self.STRUCTURED_SCHEMA,
        )

    # --- plaintext ----------------------------------------------------------

    def test_plaintext_single_column(self, client):
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b"hello\nworld\n")
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == ["hello", "world"]
        assert body["error"] is None

    def test_plaintext_quoted_comma_and_newline_preserved(self, client):
        # A quoted field carries commas and newlines as a single value.
        content = b'"a, b\nc"\n"second"\n'
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, content)
        assert response.status_code == 200
        assert response.json()["rows"] == ["a, b\nc", "second"]

    def test_plaintext_unescaped_comma_is_rejected(self, client):
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b"fine\nhas, an unescaped comma\n")
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == []
        assert body["error"] == "Invalid CSV format. Expected only one column."

    def test_plaintext_optional_input_header_dropped(self, client):
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b"input\nhello\nworld\n")
        assert response.status_code == 200
        assert response.json()["rows"] == ["hello", "world"]

    def test_plaintext_lone_quote_does_not_swallow_rows(self, client):
        # The stdlib parser keeps a mid-field quote literal — it must not merge
        # the following row (the bug the old hand-rolled parser had).
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b'5" nail\nnext row\n')
        assert response.status_code == 200
        assert response.json()["rows"] == ['5" nail', "next row"]

    def test_plaintext_empty_file(self, client):
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b"\n  \n")
        assert response.status_code == 200
        assert response.json()["error"] == "No examples found in the file."

    # --- structured (one JSON object per CSV cell) --------------------------

    MULTI_FIELD_SCHEMA = (
        '{"type": "object", "properties": {"q": {"type": "string"}, '
        '"n": {"type": "integer"}}, "required": ["q"]}'
    )

    def test_structured_single_field_cells(self, client):
        # A single-property JSON object has no comma, so it's a clean one-column
        # CSV without needing quotes.
        content = b'{"q": "hello"}\n{"q": "world"}\n'
        with self._patch_task(self._structured_task()):
            response = self._post(client, content, name="examples.csv")
        assert response.status_code == 200
        body = response.json()
        assert body["rows"] == ['{"q": "hello"}', '{"q": "world"}']
        assert body["error"] is None

    def test_structured_quoted_multi_field_cells(self, client):
        # Spreadsheet-export form: each JSON object is a quoted CSV cell with its
        # inner quotes doubled, so the JSON's commas don't split the columns.
        content = b'"{""q"": ""a"", ""n"": 1}"\n"{""q"": ""b"", ""n"": 2}"\n'
        task = Task(
            name="MockTask",
            instruction="Answer.",
            input_json_schema=self.MULTI_FIELD_SCHEMA,
        )
        with self._patch_task(task):
            response = self._post(client, content, name="examples.csv")
        assert response.status_code == 200
        assert response.json()["rows"] == ['{"q": "a", "n": 1}', '{"q": "b", "n": 2}']

    def test_structured_unquoted_multi_field_json_rejected(self, client):
        # Raw (unquoted) multi-field JSON: the comma splits it into columns, so
        # the single-column check rejects it and points the user at quoting.
        task = Task(
            name="MockTask",
            instruction="Answer.",
            input_json_schema=self.MULTI_FIELD_SCHEMA,
        )
        with self._patch_task(task):
            response = self._post(client, b'{"q": "a", "n": 1}\n', name="x.csv")
        assert response.status_code == 200
        assert (
            response.json()["error"] == "Invalid CSV format. Expected only one column."
        )

    def test_structured_non_json_cell(self, client):
        with self._patch_task(self._structured_task()):
            response = self._post(client, b'{"q": "ok"}\nnope\n', name="x.csv")
        assert response.status_code == 200
        assert response.json()["error"] == "Row 2 is not valid JSON."

    def test_structured_schema_mismatch(self, client):
        # Missing the required "q" field.
        with self._patch_task(self._structured_task()):
            response = self._post(client, b'{"q": "ok"}\n{}\n', name="x.csv")
        assert response.status_code == 200
        assert "Row 2 does not match the task input schema" in response.json()["error"]

    # --- encoding -----------------------------------------------------------

    def test_non_utf8_file_rejected(self, client):
        with self._patch_task(self._plaintext_task()):
            response = self._post(client, b"\xff\xfe invalid bytes")
        assert response.status_code == 422
        assert "UTF-8" in response.json()["message"]
