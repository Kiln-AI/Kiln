import json
from dataclasses import dataclass
from typing import Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from app.desktop.studio_server.eval_api import (
    CreateEvalConfigRequest,
    CreateEvaluatorRequest,
    compute_score_summary,
    connect_evals_api,
    eval_config_from_id,
    get_all_run_configs,
    reusable_frozen_prompt_id,
    task_run_config_from_id,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Finetune,
    Priority,
    Project,
    RequirementRating,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskOutputRatingType,
    TaskRequirement,
    TaskRun,
)
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.datamodel_enums import (
    FineTuneStatusType,
    StructuredOutputMode,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalDataType,
    EvalInput,
    EvalOutputScore,
    EvalRun,
    EvalTemplateId,
    MultiTurnSyntheticEvalInputData,
    SingleTurnEvalInputData,
    SyntheticUserInfo,
    UserMessage,
)
from kiln_ai.datamodel.prompt import BasePrompt
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.datamodel.spec import Spec, SpecStatus
from kiln_ai.datamodel.spec_properties import DesiredBehaviourProperties, SpecType
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel.task_run import Usage


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_evals_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_task(tmp_path):
    project = Project(
        id="project1",
        name="Test Project",
        path=tmp_path / "project.kiln",
    )
    project.save_to_file()
    task = Task(
        id="task1",
        name="Test Task",
        description="Test Description",
        instruction="Test Instructions",
        path=tmp_path / "task.kiln",
        requirements=[
            TaskRequirement(
                name="score1",
                description="desc1",
                instruction="inst1",
                priority=Priority.p1,
                type=TaskOutputRatingType.five_star,
            ),
        ],
        parent=project,
    )
    task.save_to_file()
    return task


@pytest.fixture
def mock_eval(mock_task):
    eval = Eval(
        id="eval1",
        name="Test Eval",
        description="Test Description",
        template=EvalTemplateId.bias,
        output_scores=[
            EvalOutputScore(
                name="score1", instruction="desc1", type=TaskOutputRatingType.five_star
            ),
            EvalOutputScore(
                name="overall_rating",
                instruction="desc2",
                type=TaskOutputRatingType.five_star,
            ),
        ],
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    eval.save_to_file()
    return eval


@pytest.fixture
def mock_eval_config(mock_eval):
    eval_config = EvalConfig(
        id="eval_config1",
        name="Test Eval Config",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
        parent=mock_eval,
        model_name="gpt-4",
        model_provider="openai",
    )
    eval_config.save_to_file()
    return eval_config


@pytest.fixture
def mock_run_config(mock_task):
    run_config = TaskRunConfig(
        parent=mock_task,
        id="run_config1",
        name="Test Run Config",
        description="Test Description",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()
    return run_config


@pytest.fixture
def mock_task_from_id(mock_task):
    with patch("app.desktop.studio_server.eval_api.task_from_id") as mock:
        mock.return_value = mock_task
        yield mock


def test_get_evals_success(client, mock_task, mock_task_from_id, mock_eval):
    mock_task_from_id.return_value = mock_task

    response = client.get("/api/projects/project1/tasks/task1/evals")

    assert response.status_code == 200
    result = response.json()
    assert len(result) == 1
    assert result[0]["id"] == "eval1"
    assert result[0]["name"] == "Test Eval"
    mock_task_from_id.assert_called_once_with("project1", "task1")


def test_get_eval_success(client, mock_task, mock_task_from_id, mock_eval):
    mock_task_from_id.return_value = mock_task

    response = client.get("/api/projects/project1/tasks/task1/evals/eval1")

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "eval1"
    assert result["name"] == "Test Eval"
    mock_task_from_id.assert_called_once_with("project1", "task1")


def test_get_eval_not_found(client, mock_task, mock_task_from_id):
    mock_task_from_id.return_value = mock_task

    response = client.get("/api/projects/project1/tasks/task1/evals/non_existent")

    assert response.status_code == 404
    assert response.json()["message"] == "Eval not found. ID: non_existent"


@pytest.fixture
def valid_evaluator_request():
    return CreateEvaluatorRequest(
        name="Test Evaluator",
        description="Test Description",
        template=None,
        output_scores=[
            EvalOutputScore(name="score1", type=TaskOutputRatingType.five_star),
        ],
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
        template_properties={"test_property": "test_value", "numeric_property": 42},
        evaluation_data_type=EvalDataType.final_answer,
    )


@pytest.fixture
def valid_eval_config_request():
    return CreateEvalConfigRequest(
        name="Test Eval Config",
        type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
        model_name="gpt-4",
        provider=ModelProviderName.openai,
    )


@pytest.mark.asyncio
async def test_create_evaluator(
    client, mock_task_from_id, valid_evaluator_request, mock_task
):
    mock_task_from_id.return_value = mock_task

    response = client.post(
        "/api/projects/project1/tasks/task1/create_evaluator",
        json=valid_evaluator_request.model_dump(),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == valid_evaluator_request.name
    assert result["description"] == valid_evaluator_request.description
    assert result["template_properties"] == valid_evaluator_request.template_properties

    # Verify the eval was created with the correct template_properties on disk
    saved_eval = mock_task.evals()[0]
    assert saved_eval.template == valid_evaluator_request.template
    assert saved_eval.name == valid_evaluator_request.name
    assert saved_eval.description == valid_evaluator_request.description
    assert saved_eval.output_scores == valid_evaluator_request.output_scores
    assert saved_eval.eval_set_filter_id == valid_evaluator_request.eval_set_filter_id
    assert (
        saved_eval.eval_configs_filter_id
        == valid_evaluator_request.eval_configs_filter_id
    )
    assert saved_eval.template_properties == valid_evaluator_request.template_properties
    assert saved_eval.template_properties is not None
    assert saved_eval.template_properties["test_property"] == "test_value"
    assert saved_eval.template_properties["numeric_property"] == 42


@pytest.mark.asyncio
async def test_create_task_run_config_with_freezing(
    client, mock_task_from_id, mock_task
):
    mock_task_from_id.return_value = mock_task

    with (
        patch(
            "app.desktop.studio_server.eval_api.generate_memorable_name"
        ) as mock_generate_memorable_name,
    ):
        mock_generate_memorable_name.return_value = "Custom Name"

        response = client.post(
            "/api/projects/project1/tasks/task1/run_configs",
            json={
                "name": "Test Task Run Config",
                "description": "Test Description",
                "run_config_properties": {
                    "model_name": "gpt-4o",
                    "model_provider_name": "openai",
                    "prompt_id": "simple_chain_of_thought_prompt_builder",
                    "temperature": 0.5,
                    "structured_output_mode": "json_schema",
                },
                # top_p not included, should get default 1.0
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Test Task Run Config"
    assert result["description"] == "Test Description"
    assert result["run_config_properties"]["model_name"] == "gpt-4o"
    assert result["run_config_properties"]["model_provider_name"] == "openai"
    assert (
        result["run_config_properties"]["prompt_id"]
        == "task_run_config::project1::task1::" + result["id"]
    )
    # Check temperature is set to custom value 0.5
    assert result["run_config_properties"]["temperature"] == 0.5
    # Check top_p gets default value 1.0 when not specified
    assert result["run_config_properties"]["top_p"] == 1.0
    assert result["prompt"]["name"] == "Custom Name - Chain of Thought"
    assert (
        result["prompt"]["description"]
        == "Frozen copy of prompt 'simple_chain_of_thought_prompt_builder'."
    )
    # Fetch it from API
    fetch_response = client.get("/api/projects/project1/tasks/task1/run_configs")
    assert fetch_response.status_code == 200
    configs = fetch_response.json()
    assert len(configs) == 1
    assert configs[0]["id"] == result["id"]
    assert configs[0]["name"] == result["name"]
    # Verify temperature and top_p persist on disk
    assert configs[0]["run_config_properties"]["temperature"] == 0.5
    assert configs[0]["run_config_properties"]["top_p"] == 1.0
    assert configs[0]["prompt"]["name"] == "Custom Name - Chain of Thought"
    assert configs[0]["prompt"]["description"] == (
        "Frozen copy of prompt 'simple_chain_of_thought_prompt_builder'."
    )
    assert configs[0]["run_config_properties"]["prompt_id"] == (
        "task_run_config::project1::task1::" + result["id"]
    )


@pytest.mark.asyncio
async def test_create_task_run_config_without_freezing(
    client, mock_task_from_id, mock_task
):
    mock_task_from_id.return_value = mock_task

    with (
        patch(
            "app.desktop.studio_server.eval_api.generate_memorable_name"
        ) as mock_generate_memorable_name,
    ):
        mock_generate_memorable_name.return_value = "Custom Name"

        response = client.post(
            "/api/projects/project1/tasks/task1/run_configs",
            json={
                "name": "Test Task Run Config",
                "description": "Test Description",
                "run_config_properties": {
                    "model_name": "gpt-4o",
                    "model_provider_name": "openai",
                    "prompt_id": "id::prompt_123",
                    "structured_output_mode": "json_schema",
                },
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == "Test Task Run Config"
    assert result["description"] == "Test Description"
    assert result["run_config_properties"]["model_name"] == "gpt-4o"
    assert result["run_config_properties"]["model_provider_name"] == "openai"
    assert result["run_config_properties"]["prompt_id"] == "id::prompt_123"
    assert result["prompt"] is None


@pytest.mark.asyncio
async def test_create_task_run_config_reuses_existing_frozen_prompt(
    client, mock_task_from_id, mock_task
):
    mock_task_from_id.return_value = mock_task

    def create(name: str):
        return client.post(
            "/api/projects/project1/tasks/task1/run_configs",
            json={
                "name": name,
                "run_config_properties": {
                    "model_name": "gpt-4o",
                    "model_provider_name": "openai",
                    "prompt_id": "simple_chain_of_thought_prompt_builder",
                    "structured_output_mode": "json_schema",
                },
            },
        )

    first = create("First")
    assert first.status_code == 200
    first_result = first.json()
    # First config freezes a new prompt pointing at itself
    assert first_result["prompt"] is not None
    assert first_result["run_config_properties"]["prompt_id"] == (
        "task_run_config::project1::task1::" + first_result["id"]
    )

    second = create("Second")
    assert second.status_code == 200
    second_result = second.json()
    # Second config has identical content, so it reuses the first's frozen prompt
    # instead of creating a duplicate
    assert second_result["id"] != first_result["id"]
    assert second_result["prompt"] is None
    assert second_result["run_config_properties"]["prompt_id"] == (
        "task_run_config::project1::task1::" + first_result["id"]
    )

    # Only the first config contributes a frozen prompt to the task
    frozen_prompts = [rc.prompt for rc in mock_task.run_configs() if rc.prompt]
    assert len(frozen_prompts) == 1


def test_reusable_frozen_prompt_id_no_match(mock_task):
    assert (
        reusable_frozen_prompt_id(mock_task, "project1", "some prompt text", None)
        is None
    )


def test_reusable_frozen_prompt_id_picks_most_recent(mock_task):
    # Legacy case: multiple run configs with identical frozen content. The most
    # recently created one should be reused.
    older = TaskRunConfig(
        parent=mock_task,
        id="older",
        name="Older",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="task_run_config::project1::task1::older",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        prompt=BasePrompt(name="Older Frozen", prompt="shared body"),
    )
    older.save_to_file()
    newer = TaskRunConfig(
        parent=mock_task,
        id="newer",
        name="Newer",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="task_run_config::project1::task1::newer",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        prompt=BasePrompt(name="Newer Frozen", prompt="shared body"),
    )
    newer.save_to_file()

    # Force a deterministic ordering of created_at
    older.created_at = older.created_at.replace(year=2020)
    newer.created_at = newer.created_at.replace(year=2024)
    older.save_to_file()
    newer.save_to_file()

    result = reusable_frozen_prompt_id(mock_task, "project1", "shared body", None)
    assert result == "task_run_config::project1::task1::newer"

    # Content that doesn't match returns None
    assert (
        reusable_frozen_prompt_id(mock_task, "project1", "different body", None) is None
    )
    # cot mismatch is treated as a different prompt
    assert (
        reusable_frozen_prompt_id(mock_task, "project1", "shared body", "cot") is None
    )


def test_reusable_frozen_prompt_id_normalizes_empty_cot(mock_task):
    # An empty-string cot and a missing cot should be treated as equivalent.
    config = TaskRunConfig(
        parent=mock_task,
        id="rc_empty_cot",
        name="Empty CoT",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="task_run_config::project1::task1::rc_empty_cot",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        prompt=BasePrompt(
            name="Empty CoT Frozen",
            prompt="body",
            chain_of_thought_instructions="",
        ),
    )
    config.save_to_file()

    assert reusable_frozen_prompt_id(mock_task, "project1", "body", None) == (
        "task_run_config::project1::task1::rc_empty_cot"
    )
    assert reusable_frozen_prompt_id(mock_task, "project1", "body", "") == (
        "task_run_config::project1::task1::rc_empty_cot"
    )


@pytest.mark.asyncio
async def test_create_eval_config(
    client, mock_task_from_id, valid_eval_config_request, mock_eval, mock_task
):
    mock_task_from_id.return_value = mock_task

    with (
        patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id,
    ):
        mock_eval_from_id.return_value = mock_eval

        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/create_eval_config",
            json=valid_eval_config_request.model_dump(),
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == valid_eval_config_request.name
    assert result["config_type"] == valid_eval_config_request.type
    assert result["properties"] == valid_eval_config_request.properties
    assert result["model_name"] == valid_eval_config_request.model_name
    assert result["model_provider"] == valid_eval_config_request.provider

    # Fetch disk
    assert len(mock_eval.configs()) == 1
    config = mock_eval.configs()[0]
    assert config.config_type == valid_eval_config_request.type
    assert config.properties == valid_eval_config_request.properties
    assert config.model_name == valid_eval_config_request.model_name
    assert config.model_provider == valid_eval_config_request.provider
    assert config.properties["eval_steps"][0] == "step1"
    assert config.properties["eval_steps"][1] == "step2"


@pytest.mark.asyncio
async def test_create_eval_config_missing_model_for_llm_type(
    client, mock_task_from_id, mock_eval, mock_task
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/create_eval_config",
            json={
                "name": "Bad Config",
                "type": "g_eval",
                "properties": {"eval_steps": ["step1"]},
                "model_name": None,
                "provider": None,
            },
        )

    assert response.status_code == 400
    assert "model_name and provider are required" in response.json()["message"]


@pytest.mark.asyncio
async def test_create_eval_config_invalid_properties(
    client, mock_task_from_id, mock_eval, mock_task
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/create_eval_config",
            json={
                "name": "Bad Config",
                "type": "g_eval",
                "properties": {"not_a_valid_field": True},
                "model_name": "gpt-4",
                "provider": "openai",
            },
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_eval_config_invalid_v2_properties(
    client, mock_task_from_id, mock_v2_eval, mock_task
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_v2_eval

        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval_v2/create_eval_config",
            json={
                "name": "Bad V2 Config",
                "type": "v2",
                "properties": {"type": "not_a_real_type"},
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert "Invalid properties for eval config type" in body["message"]
    assert "v2" in body["message"]


def test_get_eval_config(
    client, mock_task_from_id, mock_eval, mock_task, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_config/eval_config1"
        )

    assert response.status_code == 200
    config = response.json()
    assert isinstance(config, dict)

    assert config["config_type"] == mock_eval_config.config_type
    assert config["properties"] == mock_eval_config.properties
    assert config["model_name"] == mock_eval_config.model_name
    assert config["model_provider"] == mock_eval_config.model_provider

    mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")


def test_get_eval_configs(
    client, mock_task_from_id, mock_eval, mock_task, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_configs"
        )

    assert response.status_code == 200
    configs = response.json()
    assert isinstance(configs, list)
    assert len(configs) == 1

    config = configs[0]
    assert config["config_type"] == mock_eval_config.config_type
    assert config["properties"] == mock_eval_config.properties
    assert config["model_name"] == mock_eval_config.model_name
    assert config["model_provider"] == mock_eval_config.model_provider

    mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")


@pytest.mark.asyncio
async def test_run_eval_config(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    mock_task_from_id.return_value = mock_task

    # Mock progress updates
    progress_updates = [
        Mock(complete=1, total=3, errors=0),
        Mock(complete=2, total=3, errors=0),
        Mock(complete=3, total=3, errors=0),
    ]

    # Create async generator for mock progress
    async def mock_run():
        for progress in progress_updates:
            yield progress

    with (
        patch(
            "app.desktop.studio_server.eval_api.task_run_config_from_id"
        ) as mock_run_config_from_id,
        patch("app.desktop.studio_server.eval_api.EvalRunner") as MockEvalRunner,
    ):
        mock_run_config_from_id.return_value = mock_run_config
        mock_eval_runner = Mock()
        mock_eval_runner.run.return_value = mock_run()
        MockEvalRunner.return_value = mock_eval_runner

        # Make request with specific run_config_ids
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_config/eval_config1/run_comparison",
            params={"run_config_ids": ["run_config1", "run_config2"]},
        )

        assert response.status_code == 200

        # Parse SSE messages
        messages = [msg for msg in response.iter_lines() if msg]

        # Should have 4 messages: 3 progress updates and 1 complete
        assert len(messages) == 4

        # Check progress messages
        for i, msg in enumerate(messages[:-1]):
            assert msg.startswith("data: ")
            data = json.loads(msg.split("data: ")[1])
            assert data["progress"] == i + 1
            assert data["total"] == 3
            assert data["errors"] == 0

        # Check complete message
        assert messages[-1] == "data: complete"


@pytest.mark.asyncio
async def test_run_eval_config_no_run_configs_error(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    with patch(
        "app.desktop.studio_server.eval_api.eval_config_from_id"
    ) as mock_eval_config_from_id:
        mock_eval_config_from_id.return_value = mock_eval_config

        # Make request with no run_config_ids and all_run_configs=False
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_config/eval_config1/run_comparison"
        )

        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "No run config ids provided. At least one run config id is required."
        )


@pytest.mark.asyncio
async def test_eval_config_from_id(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    eval_config = eval_config_from_id("project1", "task1", "eval1", "eval_config1")

    assert eval_config.id == "eval_config1"
    assert eval_config.name == "Test Eval Config"
    assert eval_config.config_type == EvalConfigType.g_eval
    assert eval_config.properties == {"eval_steps": ["step1", "step2"]}

    with pytest.raises(HTTPException, match=r"Eval config not found. ID: non_existent"):
        eval_config_from_id("project1", "task1", "eval1", "non_existent")


@pytest.mark.asyncio
async def test_task_run_config_from_id(
    client, mock_task_from_id, mock_task, mock_run_config
):
    mock_task_from_id.return_value = mock_task

    run_config = task_run_config_from_id("project1", "task1", "run_config1")

    assert run_config.id == "run_config1"
    assert run_config.name == "Test Run Config"
    assert run_config.description == "Test Description"

    with pytest.raises(
        HTTPException, match=r"Task run config not found. ID: non_existent"
    ):
        task_run_config_from_id("project1", "task1", "non_existent")


@pytest.mark.asyncio
async def test_task_run_config_from_id_finetune(mock_task_from_id, mock_task):
    mock_task_from_id.return_value = mock_task

    run_config_props = KilnAgentRunConfigProperties(
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_chain_of_thought_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    mock_finetune = Finetune(
        id="ft_test",
        name="Test Finetune",
        description="Test finetune description",
        provider="openai",
        base_model_id="model1",
        dataset_split_id="split1",
        system_message="System message",
        latest_status=FineTuneStatusType.completed,
        run_config=run_config_props,
        fine_tune_model_id="ft_model_123",
        parent=mock_task,
    )

    with patch(
        "app.desktop.studio_server.eval_api.finetune_from_finetune_run_config_id"
    ) as mock_finetune_from_id:
        mock_finetune_from_id.return_value = mock_finetune

        run_config = task_run_config_from_id(
            "project1", "task1", "finetune_run_config::project1::task1::ft_test"
        )

        assert run_config.id == "finetune_run_config::project1::task1::ft_test"
        assert run_config.name == "Test Finetune"
        assert run_config.description == "Test finetune description"
        assert run_config.run_config_properties == run_config_props
        assert run_config.parent == mock_task


@pytest.mark.asyncio
async def test_get_all_run_configs(mock_task_from_id, mock_task):
    """Test that get_all_run_configs returns regular run configs and completed finetune run configs."""
    mock_task_from_id.return_value = mock_task

    run_config_props = KilnAgentRunConfigProperties(
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_chain_of_thought_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    regular_run_config = TaskRunConfig(
        id="regular_run_config1",
        name="Regular Run Config",
        description="A regular run config",
        run_config_properties=run_config_props,
        parent=mock_task,
    )
    regular_run_config.save_to_file()

    completed_finetune = Finetune(
        id="ft_completed",
        name="Completed Finetune",
        provider="openai",
        base_model_id="model1",
        dataset_split_id="split1",
        system_message="System message",
        latest_status=FineTuneStatusType.completed,
        run_config=run_config_props,
        fine_tune_model_id="ft_model_123",
        parent=mock_task,
    )
    completed_finetune.save_to_file()

    incomplete_finetune = Finetune(
        id="ft_incomplete",
        name="Incomplete Finetune",
        provider="openai",
        base_model_id="model2",
        dataset_split_id="split2",
        system_message="System message",
        latest_status=FineTuneStatusType.running,
        run_config=run_config_props,
        fine_tune_model_id=None,
        parent=mock_task,
    )
    incomplete_finetune.save_to_file()

    configs = get_all_run_configs("project1", "task1")

    config_ids = [config.id for config in configs]
    assert "regular_run_config1" in config_ids
    assert "finetune_run_config::project1::task1::ft_completed" in config_ids
    assert "finetune_run_config::project1::task1::ft_incomplete" not in config_ids


def test_run_config_starred_default(mock_task):
    """Test that starred defaults to False on TaskRunConfig."""
    run_config = TaskRunConfig(
        parent=mock_task,
        name="Starred Test Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    assert run_config.starred is False


def test_run_config_starred_persists(mock_task):
    """Test that starred field persists through save and load."""
    run_config = TaskRunConfig(
        parent=mock_task,
        name="Starred Persist Config",
        starred=True,
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()
    assert run_config.starred is True

    loaded = TaskRunConfig.load_from_file(run_config.path)
    assert loaded.starred is True


def test_update_run_config_starred(client, mock_task_from_id, mock_run_config):
    """Test the PATCH endpoint to star a run config."""
    assert mock_run_config.starred is False

    response = client.patch(
        "/api/projects/project1/tasks/task1/run_configs/run_config1",
        json={"starred": True},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["starred"] is True

    loaded = TaskRunConfig.load_from_file(mock_run_config.path)
    assert loaded.starred is True


def test_update_run_config_unstar(client, mock_task_from_id, mock_run_config):
    """Test the PATCH endpoint to unstar a previously starred run config."""
    mock_run_config.starred = True
    mock_run_config.save_to_file()

    response = client.patch(
        "/api/projects/project1/tasks/task1/run_configs/run_config1",
        json={"starred": False},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["starred"] is False

    loaded = TaskRunConfig.load_from_file(mock_run_config.path)
    assert loaded.starred is False


def test_update_run_config_not_found(client, mock_task_from_id, mock_task):
    """Test the PATCH endpoint returns 404 for non-existent run config."""
    response = client.patch(
        "/api/projects/project1/tasks/task1/run_configs/non_existent",
        json={"starred": True},
    )
    assert response.status_code == 404


def test_update_run_config_no_path(client, mock_task_from_id, mock_task):
    """Test that updating a run config without a path (e.g. finetune) returns 400."""
    finetune_run_config = TaskRunConfig(
        id="finetune_run_config::project1::task1::ft1",
        name="Finetune Config",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        parent=mock_task,
    )

    with patch(
        "app.desktop.studio_server.eval_api.task_run_config_from_id"
    ) as mock_from_id:
        mock_from_id.return_value = finetune_run_config
        response = client.patch(
            "/api/projects/project1/tasks/task1/run_configs/finetune_run_config::project1::task1::ft1",
            json={"starred": True},
        )
    assert response.status_code == 400


def test_update_run_config_prompt_name(client, mock_task_from_id, mock_run_config):
    """Test the PATCH endpoint to update a frozen prompt's name."""
    mock_run_config.prompt = BasePrompt(
        name="Original Name",
        prompt="This is a frozen prompt",
    )
    mock_run_config.save_to_file()

    response = client.patch(
        "/api/projects/project1/tasks/task1/run_configs/run_config1",
        json={"prompt_name": "Updated Name"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["prompt"]["name"] == "Updated Name"

    loaded = TaskRunConfig.load_from_file(mock_run_config.path)
    assert loaded.prompt is not None
    assert loaded.prompt.name == "Updated Name"


def test_update_run_config_prompt_name_no_prompt(
    client, mock_task_from_id, mock_run_config
):
    """Test that updating prompt_name when no frozen prompt exists returns 400."""
    assert mock_run_config.prompt is None

    response = client.patch(
        "/api/projects/project1/tasks/task1/run_configs/run_config1",
        json={"prompt_name": "New Name"},
    )
    assert response.status_code == 400
    assert "no frozen prompt" in response.json()["message"].lower()


@pytest.fixture
def mock_eval_for_score_summary():
    eval = Mock(spec=Eval)
    eval.output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
        EvalOutputScore(
            name="relevance",
            instruction="Test relevance",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]
    eval.eval_set_filter_id = "tag::eval_set"
    return eval


@pytest.fixture
def mock_eval_config_for_score_summary():
    config = Mock(spec=EvalConfig)

    scores: List[Tuple[str, str, Dict[str, float]]] = [
        # Run 1 - normal
        ("run1", "dataset_id_1", {"accuracy": 0.8, "relevance": 0.9}),
        ("run1", "dataset_id_2", {"accuracy": 0.6, "relevance": 0.7}),
        # Run 2 - only 1 score, should be 0.5 complete
        ("run2", "dataset_id_1", {"accuracy": 0.9, "relevance": 0.85}),
        # Run 3 - no valid scores, 0.0 complete
        ("run3", "dataset_id_1", {"other": 0.5}),
        # Run 4 - Partial incomplete doesn't divide by zero, still 0.0 complete
        ("run4", "dataset_id_1", {"accuracy": 0.5}),
        # Run 5 - duplicate dataset_id not double counted, item not in dataset filter ignored
        ("run5", "dataset_id_1", {"accuracy": 0.8, "relevance": 0.9}),
        ("run5", "dataset_id_1", {"accuracy": 0.8, "relevance": 0.9}),
        ("run5", "dataset_id_2", {"accuracy": 0.6, "relevance": 0.7}),
        ("run5", "not_in_filter", {"accuracy": 0.1, "relevance": 0.1}),
    ]
    runs = []

    id = 0
    for run_id, dataset_id, score in scores:
        id += 1
        runs.append(
            EvalRun(
                task_run_config_id=run_id,
                scores=score,
                input="input",
                output="output",
                dataset_id=dataset_id,
            )
        )

    config.runs.return_value = runs
    return config


@pytest.mark.asyncio
async def test_get_eval_config_score_summary(
    client, mock_eval_for_score_summary, mock_eval_config_for_score_summary
):
    with (
        patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter,
        patch(
            "app.desktop.studio_server.eval_api.eval_config_from_id"
        ) as mock_eval_config_from_id,
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
    ):
        mock_eval_from_id.return_value = mock_eval_for_score_summary
        mock_eval_config_from_id.return_value = mock_eval_config_for_score_summary
        mock_dataset_ids_in_filter.return_value = {
            "dataset_id_1",
            "dataset_id_2",
        }

        mock_task = Mock(spec=Task)
        mock_task.run_configs.return_value = [
            Mock(spec=TaskRunConfig, id="run1"),
            Mock(spec=TaskRunConfig, id="run2"),
            Mock(spec=TaskRunConfig, id="run3"),
            Mock(spec=TaskRunConfig, id="run4"),
            Mock(spec=TaskRunConfig, id="run5"),
        ]
        mock_task.finetunes.return_value = []
        mock_task_from_id.return_value = mock_task

        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_config/eval_config1/score_summary"
        )

        assert response.status_code == 200
        top_level_result = response.json()

        # Verify the structure of the response
        assert "results" in top_level_result
        results = top_level_result["results"]
        assert "run_config_percent_complete" in top_level_result
        run_config_percent_complete = top_level_result["run_config_percent_complete"]
        assert "dataset_size" in top_level_result
        assert top_level_result["dataset_size"] == 2

        # Check average scores for run1
        assert results["run1"]["accuracy"]["mean_score"] == 0.7  # (0.8 + 0.6) / 2
        assert results["run1"]["accuracy"]["n_used"] == 2
        assert results["run1"]["accuracy"]["n_excluded"] == 0
        assert results["run1"]["relevance"]["mean_score"] == 0.8  # Only one valid score
        assert run_config_percent_complete["run1"] == 1.0

        # Check average scores for run2
        assert results["run2"]["accuracy"]["mean_score"] == 0.9
        assert results["run2"]["accuracy"]["n_used"] == 1
        assert results["run2"]["accuracy"]["n_excluded"] == 0
        assert results["run2"]["relevance"]["mean_score"] == 0.85
        assert run_config_percent_complete["run2"] == 0.5

        # run 3 has non valid scores
        assert results["run3"] == {}
        assert run_config_percent_complete["run3"] == 0.0

        # run 4 has no scores
        assert results["run4"]["accuracy"]["mean_score"] == 0.5
        assert results["run4"]["accuracy"]["n_used"] == 1
        assert results["run4"]["accuracy"]["n_excluded"] == 0
        assert "relevance" not in results["run4"]
        assert run_config_percent_complete["run4"] == 0.0

        # Check average scores for run5 - duplicate dataset_id not double counted
        assert results["run5"]["accuracy"]["mean_score"] == 0.7  # (0.8 + 0.6) / 2
        assert results["run5"]["accuracy"]["n_used"] == 2
        assert results["run5"]["accuracy"]["n_excluded"] == 0
        assert results["run5"]["relevance"]["mean_score"] == 0.8  # Only one valid score
        assert run_config_percent_complete["run5"] == 1.0

        # Verify the mocks were called correctly
        mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")
        mock_eval_config_from_id.assert_called_once_with(
            "project1", "task1", "eval1", "eval_config1"
        )
        mock_eval_config_for_score_summary.runs.assert_called_once_with(readonly=True)
        mock_dataset_ids_in_filter.assert_called_once_with(
            mock_task, "tag::eval_set", readonly=True
        )


def test_score_summary_n_used_n_excluded(mock_eval_for_score_summary):
    eval = mock_eval_for_score_summary
    config = Mock(spec=EvalConfig)

    runs = [
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.8, "relevance": 0.9},
            input="input",
            output="output",
            dataset_id="ds1",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={},
            input="input",
            output="output",
            dataset_id="ds2",
            skipped_reason="missing_reference_key",
            skipped_detail="key foo",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.6, "relevance": 0.7},
            input="input",
            output="output",
            dataset_id="ds3",
        ),
    ]
    config.runs.return_value = runs

    task_run_configs = [Mock(spec=TaskRunConfig, id="rc1")]
    expected_dataset_ids: set[ID_TYPE] = {"ds1", "ds2", "ds3"}

    result = compute_score_summary(eval, config, task_run_configs, expected_dataset_ids)

    assert result.dataset_size == 3
    scores = result.results["rc1"]
    assert scores["accuracy"].mean_score == pytest.approx(0.7)
    assert scores["accuracy"].n_used == 2
    assert scores["accuracy"].n_excluded == 1
    assert scores["relevance"].mean_score == pytest.approx(0.8)
    assert scores["relevance"].n_used == 2
    assert scores["relevance"].n_excluded == 1
    assert result.run_config_percent_complete["rc1"] == 1.0


def test_score_summary_all_skipped(mock_eval_for_score_summary):
    eval = mock_eval_for_score_summary
    config = Mock(spec=EvalConfig)

    runs = [
        EvalRun(
            task_run_config_id="rc1",
            scores={},
            input="input",
            output="output",
            dataset_id="ds1",
            skipped_reason="extraction_failed",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={},
            input="input",
            output="output",
            dataset_id="ds2",
            skipped_reason="missing_trace",
        ),
    ]
    config.runs.return_value = runs

    task_run_configs = [Mock(spec=TaskRunConfig, id="rc1")]
    expected_dataset_ids: set[ID_TYPE] = {"ds1", "ds2"}

    result = compute_score_summary(eval, config, task_run_configs, expected_dataset_ids)

    assert result.dataset_size == 2
    scores = result.results["rc1"]
    assert len(scores) == 2
    assert scores["accuracy"].mean_score is None
    assert scores["accuracy"].n_used == 0
    assert scores["accuracy"].n_excluded == 2
    assert scores["relevance"].mean_score is None
    assert scores["relevance"].n_used == 0
    assert scores["relevance"].n_excluded == 2
    assert result.run_config_percent_complete["rc1"] == 1.0


def test_score_summary_eval_input_keyed(mock_eval_for_score_summary):
    """EvalInput-sourced evals key their runs on eval_input_id; a run keyed by
    dataset_id (TaskRun source) never matches an EvalInput expected set."""
    eval = mock_eval_for_score_summary
    config = Mock(spec=EvalConfig)

    runs = [
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.8, "relevance": 0.9},
            input="input",
            output="output",
            eval_input_id="ei1",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.6, "relevance": 0.7},
            input="input",
            output="output",
            eval_input_id="ei2",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.0, "relevance": 0.0},
            input="input",
            output="output",
            dataset_id="ds1",
        ),
    ]
    config.runs.return_value = runs

    task_run_configs = [Mock(spec=TaskRunConfig, id="rc1")]
    expected_item_ids: set[ID_TYPE] = {"ei1", "ei2", "ei3"}

    result = compute_score_summary(eval, config, task_run_configs, expected_item_ids)

    assert result.dataset_size == 3
    scores = result.results["rc1"]
    assert scores["accuracy"].mean_score == pytest.approx(0.7)
    assert scores["accuracy"].n_used == 2
    assert scores["relevance"].mean_score == pytest.approx(0.8)
    # ei3 has no run yet; the dataset_id run must not count toward completion
    assert result.run_config_percent_complete["rc1"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_get_eval_config_score_summary_eval_input_eval(
    client, mock_task_from_id, mock_task
):
    """EvalInput-typed evals get a real score summary sized from
    eval_input_filter_id (was a 400) — the post-save spec detail page and
    compare_run_configs read this endpoint."""
    mock_task_from_id.return_value = mock_task

    eval = Eval(
        id="eval_input_eval",
        name="EvalInput Eval",
        output_scores=[
            EvalOutputScore(
                name="score1", instruction="desc1", type=TaskOutputRatingType.five_star
            ),
        ],
        eval_input_filter_id="tag::eval_slice",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    eval.save_to_file()
    eval_config = EvalConfig(
        id="eval_config1",
        name="Judge",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
        model_name="gpt-4",
        model_provider="openai",
        parent=eval,
    )
    eval_config.save_to_file()

    eval_input_ids = []
    for i in range(2):
        eval_input = EvalInput(
            data=MultiTurnSyntheticEvalInputData(
                first_message=UserMessage(text=f"seed {i}"),
                synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            ),
            tags=["eval_slice"],
            parent=mock_task,
        )
        eval_input.save_to_file()
        eval_input_ids.append(eval_input.id)

    run_config = TaskRunConfig(
        parent=mock_task,
        id="rc1",
        name="Run Config 1",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()

    EvalRun(
        task_run_config_id="rc1",
        scores={"score1": 4.0},
        input="input",
        output="output",
        eval_input_id=eval_input_ids[0],
        parent=eval_config,
    ).save_to_file()

    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval_input_eval/eval_config/eval_config1/score_summary"
    )

    assert response.status_code == 200
    result = response.json()
    assert result["dataset_size"] == 2
    assert result["results"]["rc1"]["score1"]["mean_score"] == 4.0
    assert result["results"]["rc1"]["score1"]["n_used"] == 1
    assert result["run_config_percent_complete"]["rc1"] == 0.5


@pytest.mark.asyncio
async def test_get_eval_config_score_summary_eval_input_eval_empty(
    client, mock_task_from_id, mock_task
):
    """An EvalInput-typed eval whose filter matches nothing still 400s with an
    actionable message, mirroring the TaskRun-typed empty case."""
    mock_task_from_id.return_value = mock_task

    eval = Eval(
        id="eval_input_eval",
        name="EvalInput Eval",
        output_scores=[
            EvalOutputScore(
                name="score1", instruction="desc1", type=TaskOutputRatingType.five_star
            ),
        ],
        eval_input_filter_id="tag::eval_slice",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    eval.save_to_file()
    eval_config = EvalConfig(
        id="eval_config1",
        name="Judge",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
        model_name="gpt-4",
        model_provider="openai",
        parent=eval,
    )
    eval_config.save_to_file()

    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval_input_eval/eval_config/eval_config1/score_summary"
    )

    assert response.status_code == 400
    assert "No items match" in response.json()["message"]


@pytest.mark.asyncio
async def test_get_eval_run_results(
    client,
    mock_task_from_id,
    mock_task,
    mock_eval,
    mock_eval_config,
    mock_run_config,
):
    mock_task_from_id.return_value = mock_task

    eval_run = EvalRun(
        task_run_config_id="run_config1",
        scores={"score1": 3.0, "overall_rating": 1.0},
        input="input",
        output="output",
        dataset_id="dataset_id1",
        parent=mock_eval_config,
    )
    eval_run.save_to_file()

    # Test successful retrieval
    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval1"
        "/eval_config/eval_config1/run_config/run_config1/results"
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "results" in data
    assert "eval" in data
    assert "eval_config" in data
    assert "run_config" in data

    # Verify results content
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == eval_run.id
    assert data["results"][0]["task_run_config_id"] == mock_run_config.id
    assert data["results"][0]["scores"] == {"score1": 3.0, "overall_rating": 1.0}

    # Test with invalid eval ID
    response = client.get(
        "/api/projects/project1/tasks/task1/evals/invalid_eval"
        "/eval_config/eval_config1/run_config/run_config1/results"
    )
    assert response.status_code == 404

    # Test with invalid eval config ID
    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval1"
        "/eval_config/invalid_config/run_config/run_config1/results"
    )
    assert response.status_code == 404

    # Test with invalid run config ID
    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval1"
        "/eval_config/eval_config1/run_config/invalid_run_config/results"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_eval_config_compare_summary(
    client,
    mock_task_from_id,
    mock_task,
    mock_eval,
    mock_eval_config,
    mock_run_config,
):
    mock_task_from_id.return_value = mock_task

    # structured data to make it easier to generate test cases.
    @dataclass
    class EvalConfigSummaryTestData:
        human_overall_rating: float | None
        score1_overall_rating: float | None
        eval_overall_rating: float
        eval__score1_rating: float
        eval_config_id: str
        skip_eval_run: bool = False
        skip_golden_tag: bool = False

    test_data: List[EvalConfigSummaryTestData] = [
        # Test 1: ec1
        # Normal run, with some data to check calculations on a single run
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=2.0,
            eval_overall_rating=1.0,
            eval__score1_rating=3.5,
            eval_config_id="ec1",
        ),
        # Should be ignored as it's not in the eval set filter (golden tag). Would mess up the scores of eval_config1 if included
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=5.0,
            eval_overall_rating=4.0,
            eval__score1_rating=4.0,
            eval_config_id="ec1",
            skip_golden_tag=True,
        ),
        # Test 2: ec2 - Test multiple, and correct averaging
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=5.0,
            eval_overall_rating=4.0,
            eval__score1_rating=4.0,
            eval_config_id="ec2",
        ),
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=1.0,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec2",
        ),
        # Test 3: Dataset item that has partial human rating
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=None,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec3",
        ),
        # Test 4: Dataset item that has no human rating
        EvalConfigSummaryTestData(
            human_overall_rating=None,
            score1_overall_rating=None,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec4",
        ),
        # Test 5: skipping eval run should lower the percent complete
        EvalConfigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=5.0,
            eval_overall_rating=4.0,
            eval__score1_rating=4.0,
            eval_config_id="ec5",
            skip_eval_run=True,
        ),
    ]

    # Count items that don't have skip_golden_tag set to True
    total_in_dataset = sum(1 for x in test_data if not x.skip_golden_tag)

    eval_configs_by_id: Dict[str, EvalConfig] = {}

    assert len(mock_task.requirements) == 1
    assert mock_task.requirements[0].name == "score1"
    score1_requirement_id = mock_task.requirements[0].id
    for test_case in test_data:
        # create eval config if it doesn't exist
        eval_config = eval_configs_by_id.get(test_case.eval_config_id)
        if eval_config is None:
            eval_config = EvalConfig(
                id=test_case.eval_config_id,
                name="Test Eval Config",
                config_type=EvalConfigType.g_eval,
                properties={"eval_steps": ["step1", "step2"]},
                parent=mock_eval,
                model_name="gpt-4",
                model_provider="openai",
            )
            eval_config.save_to_file()
            eval_configs_by_id[test_case.eval_config_id] = eval_config

        tags = ["golden"]
        if test_case.skip_golden_tag:
            tags = []

        ratings = {}
        if test_case.score1_overall_rating is not None:
            ratings[score1_requirement_id] = RequirementRating(
                value=test_case.score1_overall_rating,
                type=TaskOutputRatingType.five_star,
            )

        task_run = TaskRun(
            output=TaskOutput(
                output="Test Output",
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties={
                        "model_name": "gpt-4",
                        "model_provider": "openai",
                        "adapter_name": "langchain_adapter",
                    },
                ),
                rating=TaskOutputRating(
                    value=test_case.human_overall_rating,
                    requirement_ratings=ratings,
                ),
            ),
            input="Test Input",
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "langchain_adapter",
                },
            ),
            tags=tags,
            parent=mock_task,
        )
        task_run.save_to_file()

        if test_case.skip_eval_run:
            continue

        eval_run = EvalRun(
            task_run_config_id="run_config1",
            scores={
                "score1": test_case.eval__score1_rating,
                "overall_rating": test_case.eval_overall_rating,
            },
            input="input",
            output="output",
            dataset_id=task_run.id,
            parent=eval_config,
        )
        eval_run.save_to_file()

    # Test successful retrieval
    response = client.get(
        "/api/projects/project1/tasks/task1/evals/eval1/eval_configs_score_summary"
    )

    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    results = data["results"]
    assert isinstance(results, dict)

    assert "eval_config_percent_complete" in data
    eval_config_percent_complete = data["eval_config_percent_complete"]
    assert isinstance(eval_config_percent_complete, dict)

    # check the counts
    assert data["fully_rated_count"] == 4
    assert data["partially_rated_count"] == 1
    assert data["not_rated_count"] == 1
    assert data["dataset_size"] == total_in_dataset

    # Test case 1: 1 item should be included, manually calculated scores, should exclude a second item that isn't in the eval config set filter
    assert results["ec1"] == {
        "overall_rating": {
            "mean_squared_error": 16.0,  # error 4.0^2
            "mean_absolute_error": 4.0,  # error 4.0
            "mean_normalized_squared_error": 1,  # max error: 1 v 5
            "mean_normalized_absolute_error": 1,  # max error: 1 v 5
            "spearman_correlation": None,  # Not enough data
            "pearson_correlation": None,
            "kendalltau_correlation": None,
        },
        "score1": {
            "mean_squared_error": 2.25,  # error (3.5-5.0)^2
            "mean_absolute_error": 1.5,  # error 1.5
            "mean_normalized_squared_error": 0.140625,  # hand calc
            "mean_normalized_absolute_error": 0.375,  # 1.5/4
            "spearman_correlation": None,  # Not enough data
            "pearson_correlation": None,  # Not enough data
            "kendalltau_correlation": None,  # Not enough data
        },
    }
    # 1 of total_in_dataset eval configs are are in ec1 test
    assert eval_config_percent_complete["ec1"] == pytest.approx(1 / total_in_dataset)

    # Test case 2: check proper averaging
    assert results["ec2"] == {
        "overall_rating": {
            "mean_squared_error": 2.5,  # error (1^2 + 2^2) / 2
            "mean_absolute_error": 1.5,  # (1+2)/2
            "mean_normalized_squared_error": 0.15625,  # (0.25^2 + 0.5^2) / 2
            "mean_normalized_absolute_error": 0.375,  # (0.25 + 0.5) / 2
            "spearman_correlation": None,
            "pearson_correlation": None,
            "kendalltau_correlation": None,
        },
        "score1": {
            "mean_squared_error": 2.5,  # (1^2+2^2)/2
            "mean_absolute_error": 1.5,  # (1+2)/2
            "mean_normalized_squared_error": 0.15625,  # (0.25^2 + 0.5^2) / 2
            "mean_normalized_absolute_error": 0.375,  # (0.25 + 0.5) / 2
            "spearman_correlation": 0.9999999999999999,
            "pearson_correlation": 1,
            "kendalltau_correlation": 1,
        },
    }
    # 2 of total_in_dataset eval configs are are in ec2 test
    assert eval_config_percent_complete["ec2"] == pytest.approx(2 / total_in_dataset)

    # Test case 3: Check partials still calculate available scores
    assert results["ec3"] == {
        "overall_rating": {
            "mean_squared_error": 4,
            "mean_absolute_error": 2,
            "mean_normalized_squared_error": 0.25,
            "mean_normalized_absolute_error": 0.5,
            "spearman_correlation": None,
            "pearson_correlation": None,
            "kendalltau_correlation": None,
        },
    }
    # 2 of total_in_dataset eval configs are are in ec2 test
    assert eval_config_percent_complete["ec3"] == pytest.approx(1 / total_in_dataset)

    # Test case 4: Check no rating is empty results
    assert results.get("ec4", {}) == {}
    assert eval_config_percent_complete["ec4"] == pytest.approx(1 / total_in_dataset)

    # Test case 5: Check skipping eval run lowers the percent complete
    assert eval_config_percent_complete["ec5"] == pytest.approx(0 / total_in_dataset)


@pytest.mark.asyncio
async def test_get_eval_config_compare_summary_skips_custom_scores(
    client,
    mock_task_from_id,
    mock_task,
    mock_eval,
    mock_eval_config,
    mock_run_config,
):
    """A custom-typed output score whose json_key collides with a human rating
    (e.g. named "Overall Rating") must be skipped in the correlation loop:
    normalize_rating raises on custom, which 500'd the whole endpoint."""
    mock_task_from_id.return_value = mock_task

    # Human-rated item in the golden set, plus an eval run scoring it. Built
    # while the eval still has its five_star scores, so save validation passes.
    task_run = TaskRun(
        input="Test Input",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(
            output="Test Output",
            source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "langchain_adapter",
                },
            ),
            rating=TaskOutputRating(
                value=5.0,
                requirement_ratings={
                    mock_task.requirements[0].id: RequirementRating(
                        value=4.0, type=TaskOutputRatingType.five_star
                    )
                },
            ),
        ),
        tags=["golden"],
        parent=mock_task,
    )
    task_run.save_to_file()

    eval_run = EvalRun(
        task_run_config_id="run_config1",
        scores={"score1": 3.5, "overall_rating": 4.0},
        input="input",
        output="output",
        dataset_id=task_run.id,
        parent=mock_eval_config,
    )
    eval_run.save_to_file()

    # Swap the eval's "overall_rating" score to custom-typed in memory: a
    # custom-score eval can't be built with the judge config attached (the
    # EvalConfig validator rejects that pairing), so stage the collision here.
    mock_eval.output_scores[1] = EvalOutputScore(
        name="Overall Rating",
        type=TaskOutputRatingType.custom,
    )

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_configs_score_summary"
        )

    assert response.status_code == 200
    data = response.json()
    results = data["results"]
    # five_star score still correlated; the custom score is absent, not a 500
    assert "score1" in results["eval_config1"]
    assert "overall_rating" not in results["eval_config1"]
    # Custom scores are unrateable by humans, so they must not block the
    # rated tally: score1 is human-rated, so the item counts fully rated.
    assert data["fully_rated_count"] == 1
    assert data["partially_rated_count"] == 0


@pytest.mark.asyncio
async def test_run_eval_config_eval(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    # Create a mock response for run_eval_runner_with_status
    mock_response = StreamingResponse(
        content=iter([b"data: test\n\n"]), media_type="text/event-stream"
    )

    with patch(
        "app.desktop.studio_server.eval_api.run_eval_runner_with_status"
    ) as mock_run_eval:
        # Set up the mock to return our mock response
        mock_run_eval.return_value = mock_response

        # Call the endpoint
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/run_calibration"
        )

        # Verify the response
        assert response.status_code == 200

        # Verify run_eval_runner_with_status was called with correct parameters
        mock_run_eval.assert_called_once()

        # Get the EvalRunner that was passed to run_eval_runner_with_status
        eval_runner = mock_run_eval.call_args[0][0]

        # Verify the EvalRunner was configured correctly
        assert len(eval_runner.eval_configs) == 1
        assert eval_runner.eval_configs[0].id == mock_eval_config.id
        assert eval_runner.run_configs is None
        assert eval_runner.eval_run_type == "eval_config_eval"


@pytest.mark.asyncio
async def test_set_current_eval_config(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config
):
    """Test setting the current eval config for an evaluation."""
    mock_task_from_id.return_value = mock_task

    # Get the eval before updating to verify the change
    response = client.get("/api/projects/project1/tasks/task1/evals/eval1")
    assert response.status_code == 200
    eval_before = response.json()

    # The current_config_id might be None or different initially
    initial_config_id = eval_before.get("current_config_id")
    assert initial_config_id is None

    # Set the current eval config
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/set_current_eval_config/eval_config1"
        )
        assert response.status_code == 200
        updated_eval = response.json()

    # Verify the current_config_id was updated
    assert updated_eval["current_config_id"] == "eval_config1"
    assert updated_eval["id"] == "eval1"

    # Verify the change persists by fetching the eval again
    eval_from_disk = mock_task.evals()[0]
    assert eval_from_disk.current_config_id == "eval_config1"


def test_delete_eval_success(client, mock_task_from_id, mock_eval, mock_task):
    assert len(mock_task.evals()) == 1
    # Set up the mock eval to be returned by eval_from_id
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        # Make the delete request
        response = client.delete("/api/projects/project1/tasks/task1/evals/eval1")

    # Verify the response
    assert response.status_code == 200

    # Verify that eval_from_id was called with the correct parameters
    mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")

    # Verify that the eval was deleted
    assert len(mock_task.evals()) == 0


def test_delete_eval_not_found(client):
    # Set up the patch for eval_from_id to raise an HTTPException
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.side_effect = HTTPException(
            status_code=404, detail="Eval not found. ID: nonexistent_eval"
        )

        # Make the delete request
        response = client.delete(
            "/api/projects/project1/tasks/task1/evals/nonexistent_eval"
        )

    # Verify the response
    assert response.status_code == 404
    assert response.json()["message"] == "Eval not found. ID: nonexistent_eval"


async def test_create_eval_then_delete_on_spec_failure(
    client, mock_task_from_id, mock_task
):
    create_request = {
        "name": "Test Eval for Spec",
        "description": "Test eval that will be cleaned up",
        "template": None,
        "output_scores": [
            {
                "name": "tone",
                "type": "pass_fail",
                "instruction": "Evaluate tone",
            }
        ],
        "eval_set_filter_id": "tag::test_tag",
        "eval_configs_filter_id": "tag::test_tag_golden",
        "template_properties": None,
        "evaluation_data_type": "final_answer",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/create_evaluator", json=create_request
    )

    assert response.status_code == 200
    eval_data = response.json()
    eval_id = eval_data["id"]

    assert len(mock_task.evals()) == 1

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        created_eval = mock_task.evals()[0]
        mock_eval_from_id.return_value = created_eval

        delete_response = client.delete(
            f"/api/projects/project1/tasks/task1/evals/{eval_id}"
        )

    assert delete_response.status_code == 200
    assert len(mock_task.evals()) == 0


def test_update_eval_name_and_description(
    client, mock_task_from_id, mock_eval, mock_task
):
    """Test that update_eval successfully updates name and description."""
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        update_request = {
            "name": "Updated Eval Name",
            "description": "Updated description",
        }

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/eval1",
            json=update_request,
        )

    assert response.status_code == 200
    updated_eval = response.json()
    assert updated_eval["name"] == "Updated Eval Name"
    assert updated_eval["description"] == "Updated description"

    # Verify the eval was saved
    eval_from_disk = mock_task.evals()[0]
    assert eval_from_disk.name == "Updated Eval Name"
    assert eval_from_disk.description == "Updated description"


def test_update_eval_train_set_filter_id_when_none(
    client, mock_task_from_id, mock_eval, mock_task
):
    """Test that update_eval successfully sets train_set_filter_id when it's None."""
    # Ensure train_set_filter_id is None
    mock_eval.train_set_filter_id = None

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        update_request = {
            "train_set_filter_id": "tag::train_my_eval",
        }

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/eval1",
            json=update_request,
        )

    assert response.status_code == 200
    updated_eval = response.json()
    assert updated_eval["train_set_filter_id"] == "tag::train_my_eval"

    # Verify the eval was saved
    eval_from_disk = mock_task.evals()[0]
    assert eval_from_disk.train_set_filter_id == "tag::train_my_eval"


def test_update_eval_train_set_filter_id_when_already_set(
    client, mock_task_from_id, mock_eval
):
    """Test that update_eval raises error when trying to change existing train_set_filter_id."""
    # Set an existing train_set_filter_id
    mock_eval.train_set_filter_id = "tag::existing_train_set"

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        update_request = {
            "train_set_filter_id": "tag::new_train_set",
        }

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/eval1",
            json=update_request,
        )

    assert response.status_code == 400
    assert (
        "Train set filter is already set and cannot be changed"
        in response.json()["message"]
    )


def test_update_eval_partial_update(client, mock_task_from_id, mock_eval, mock_task):
    """Test that update_eval only updates provided fields."""
    original_name = mock_eval.name
    original_description = mock_eval.description
    mock_eval.train_set_filter_id = None

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        # Only update train_set_filter_id
        update_request = {
            "train_set_filter_id": "tag::train_set",
        }

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/eval1",
            json=update_request,
        )

    assert response.status_code == 200
    updated_eval = response.json()

    # Name and description should remain unchanged
    assert updated_eval["name"] == original_name
    assert updated_eval["description"] == original_description
    # train_set_filter_id should be updated
    assert updated_eval["train_set_filter_id"] == "tag::train_set"


def test_update_eval_not_found(client):
    """Test that update_eval returns 404 when eval is not found."""
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.side_effect = HTTPException(
            status_code=404, detail="Eval not found. ID: nonexistent_eval"
        )

        update_request = {
            "name": "Updated Name",
        }

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/nonexistent_eval",
            json=update_request,
        )

    assert response.status_code == 404
    assert "Eval not found" in response.json()["message"]


def test_update_eval_empty_request(client, mock_task_from_id, mock_eval, mock_task):
    """Test that update_eval succeeds with empty request (no fields to update)."""
    original_name = mock_eval.name
    original_description = mock_eval.description
    original_train_set_filter_id = mock_eval.train_set_filter_id

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval

        # Empty update request
        update_request = {}

        response = client.patch(
            "/api/projects/project1/tasks/task1/evals/eval1",
            json=update_request,
        )

    assert response.status_code == 200
    updated_eval = response.json()

    # All fields should remain unchanged
    assert updated_eval["name"] == original_name
    assert updated_eval["description"] == original_description
    assert updated_eval["train_set_filter_id"] == original_train_set_filter_id


def test_runs_in_filter():
    # Create a mock task with runs
    mock_task = Mock(spec=Task)

    # Create task runs with different tags
    run1 = Mock(spec=TaskRun, id="run1")
    run2 = Mock(spec=TaskRun, id="run2")
    run3 = Mock(spec=TaskRun, id="run3")

    mock_task.runs.return_value = [run1, run2, run3]

    # Mock the dataset filter
    mock_filter = Mock()

    # Configure the filter to include only run1 and run3
    mock_filter.side_effect = lambda run: run.id in ["run1", "run3"]

    # Mock the dataset_filter_from_id function
    with patch(
        "app.desktop.studio_server.eval_api.dataset_filter_from_id"
    ) as mock_dataset_filter_from_id:
        mock_dataset_filter_from_id.return_value = mock_filter

        # Call the function under test
        from app.desktop.studio_server.eval_api import runs_in_filter

        result = runs_in_filter(mock_task, "tag::some_filter", readonly=True)

        # Verify the results
        assert len(result) == 2
        assert result[0].id == "run1"
        assert result[1].id == "run3"

        # Verify the filter was called for each run
        assert mock_filter.call_count == 3
        mock_dataset_filter_from_id.assert_called_once_with("tag::some_filter")


def test_build_score_key_to_task_requirement_id():
    # Create a mock task with requirements
    mock_task = Mock(spec=Task)

    # Create task requirements with different names
    req1 = Mock(spec=TaskRequirement)
    req1.id = "req_id_1"
    req1.name = "First Requirement"

    req2 = Mock(spec=TaskRequirement)
    req2.id = "req_id_2"
    req2.name = "Second Requirement"

    req3 = Mock(spec=TaskRequirement)
    req3.id = "req_id_3"
    req3.name = "Third-With-Hyphens"

    mock_task.requirements = [req1, req2, req3]

    # Mock the string_to_json_key function
    with patch(
        "app.desktop.studio_server.eval_api.string_to_json_key"
    ) as mock_string_to_json_key:
        # Configure the mock to convert spaces to underscores and lowercase
        mock_string_to_json_key.side_effect = lambda name: (
            name.lower().replace(" ", "_").replace("-", "_")
        )

        # Call the function under test
        from app.desktop.studio_server.eval_api import (
            build_score_key_to_task_requirement_id,
        )

        result = build_score_key_to_task_requirement_id(mock_task)

        # Verify the results
        assert len(result) == 3
        assert result["first_requirement"] == "req_id_1"
        assert result["second_requirement"] == "req_id_2"
        assert result["third_with_hyphens"] == "req_id_3"

        # Verify string_to_json_key was called for each requirement
        assert mock_string_to_json_key.call_count == 3
        mock_string_to_json_key.assert_any_call("First Requirement")
        mock_string_to_json_key.assert_any_call("Second Requirement")
        mock_string_to_json_key.assert_any_call("Third-With-Hyphens")


@pytest.mark.asyncio
async def test_get_eval_progress(client, mock_task_from_id, mock_task, mock_eval):
    mock_task_from_id.return_value = mock_task

    # Create runs for testing
    run1 = TaskRun(
        input="input1",
        output=TaskOutput(
            output="output1",
            rating=TaskOutputRating(
                value=4.0,  # Has overall rating
                requirement_ratings={
                    "req_id": RequirementRating(
                        value=3.0, type=TaskOutputRatingType.five_star
                    )
                },  # Has requirement rating
            ),
        ),
        tags=["golden"],
        parent=mock_task,
    )

    run2 = TaskRun(
        input="input2",
        output=TaskOutput(
            output="output2",
            rating=TaskOutputRating(
                value=5.0,  # Has overall rating
                requirement_ratings={},  # Missing requirement rating
            ),
        ),
        tags=["golden"],
        parent=mock_task,
    )

    run3 = TaskRun(
        input="input3",
        output=TaskOutput(
            output="output3",
            rating=None,  # No ratings at all
        ),
        tags=["golden"],
        parent=mock_task,
    )

    # Mock the necessary functions
    with (
        patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter,
        patch(
            "app.desktop.studio_server.eval_api.runs_in_filter"
        ) as mock_runs_in_filter,
        patch(
            "app.desktop.studio_server.eval_api.build_score_key_to_task_requirement_id"
        ) as mock_build_score_key,
        patch(
            "app.desktop.studio_server.eval_api.count_human_evals"
        ) as mock_count_human_evals,
    ):
        mock_eval_from_id.return_value = mock_eval
        mock_dataset_ids_in_filter.return_value = {"run1", "run2", "run3", "run4"}
        mock_runs_in_filter.return_value = [run1, run2, run3]
        mock_build_score_key.return_value = {"score1": "req_id"}
        mock_count_human_evals.return_value = (
            1,
            1,
            1,
        )  # fully_rated, partially_rated, not_rated

        # Call the endpoint
        response = client.get("/api/projects/project1/tasks/task1/evals/eval1/progress")

        # Verify the response
        assert response.status_code == 200
        result = response.json()

        assert result["dataset_size"] == 4
        assert result["golden_dataset_size"] == 3
        assert result["golden_dataset_fully_rated_count"] == 1
        assert result["golden_dataset_partially_rated_count"] == 1
        assert result["golden_dataset_not_rated_count"] == 1
        assert result["current_eval_method"] is None

        # Verify the function calls
        mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")
        mock_dataset_ids_in_filter.assert_called_once_with(
            mock_task, mock_eval.eval_set_filter_id, readonly=True
        )
        mock_runs_in_filter.assert_called_once_with(
            mock_task, mock_eval.eval_configs_filter_id, readonly=True
        )
        mock_build_score_key.assert_called_once_with(mock_task)
        mock_count_human_evals.assert_called_once_with(
            [run1, run2, run3], mock_eval, {"score1": "req_id"}
        )


@pytest.mark.asyncio
async def test_get_eval_progress_eval_input_slice(client, mock_task_from_id, mock_task):
    """An EvalInput-typed eval reports its slice size from the matching
    EvalInput items — the spec page relies on this instead of a 400."""
    mock_task_from_id.return_value = mock_task

    eval = Eval(
        id="eval_input_eval",
        name="EvalInput Eval",
        output_scores=[
            EvalOutputScore(
                name="score1", instruction="desc1", type=TaskOutputRatingType.five_star
            ),
        ],
        eval_input_filter_id="tag::eval_slice",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    eval.save_to_file()
    for i in range(3):
        EvalInput(
            data=MultiTurnSyntheticEvalInputData(
                first_message=UserMessage(text=f"seed {i}"),
                synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            ),
            tags=["eval_slice"],
            parent=mock_task,
        ).save_to_file()
    # An input outside the slice tag is not counted.
    EvalInput(
        data=SingleTurnEvalInputData(user_message=UserMessage(text="other")),
        tags=["other"],
        parent=mock_task,
    ).save_to_file()

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = eval
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval_input_eval/progress"
        )

    assert response.status_code == 200
    result = response.json()
    assert result["dataset_size"] == 3
    assert result["golden_dataset_size"] == 0


@pytest.mark.asyncio
async def test_get_eval_progress_not_found(client, mock_task_from_id, mock_task):
    mock_task_from_id.return_value = mock_task

    # Mock eval_from_id to raise HTTPException
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.side_effect = HTTPException(
            status_code=404,
            detail="Eval not found. ID: non_existent",
        )

        # Call the endpoint with non-existent eval ID
        response = client.get(
            "/api/projects/project1/tasks/task1/evals/non_existent/progress"
        )

        # Verify the response
        assert response.status_code == 404
        assert response.json()["message"] == "Eval not found. ID: non_existent"
        mock_eval_from_id.assert_called_once_with("project1", "task1", "non_existent")


@pytest.mark.asyncio
async def test_set_current_eval_config_none(
    client, mock_task_from_id, mock_task, mock_eval
):
    """Test clearing the current eval config for an evaluation by setting it to 'None'."""
    mock_task_from_id.return_value = mock_task

    # First set a non-null value to verify it can be cleared
    mock_eval.current_config_id = "some_existing_config_id"
    mock_eval.save_to_file()

    # Verify the current_config_id is set
    assert mock_task.evals()[0].current_config_id == "some_existing_config_id"

    # Clear the current eval config by setting it to "None"
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/set_current_eval_config/None"
        )
        assert response.status_code == 200
        updated_eval = response.json()

    # Verify the current_config_id was cleared (set to None)
    assert updated_eval["current_config_id"] is None
    assert updated_eval["id"] == "eval1"

    # Verify the change persists by fetching the eval again
    eval_from_disk = mock_task.evals()[0]
    assert eval_from_disk.current_config_id is None


@pytest.mark.asyncio
async def test_set_current_eval_config_not_found(
    client, mock_task_from_id, mock_task, mock_eval
):
    """Test 400 error when setting a non-existent eval config as default."""
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.post(
            "/api/projects/project1/tasks/task1/evals/eval1/set_current_eval_config/non_existent_eval_config"
        )

    # Verify the response
    assert response.status_code == 400
    assert response.json()["message"] == "Eval config not found."


@pytest.mark.parametrize(
    "score_name,expected_score,has_overall_rating,has_requirement_rating,has_named_rating",
    [
        # Test overall rating
        ("overall_rating", 5.0, True, False, False),
        ("overall_rating", None, False, False, False),
        # Test task requirement rating
        ("score1", 3.0, False, True, False),
        ("score1", None, False, False, False),
        # Test named rating
        ("Named Score", 4.0, False, False, True),
        ("Named Score", None, False, False, False),
    ],
)
def test_human_score_from_task_run(
    score_name,
    expected_score,
    has_overall_rating,
    has_requirement_rating,
    has_named_rating,
):
    # Create a mock task run with the specified ratings
    task_run = Mock(spec=TaskRun)
    task_run.output = Mock(spec=TaskOutput)

    # Set up the rating object
    rating = Mock(spec=TaskOutputRating)
    rating.value = 5.0 if has_overall_rating else None

    # Set up requirement ratings
    requirement_ratings = {}
    if has_requirement_rating:
        requirement_ratings["req_id"] = RequirementRating(
            value=3.0, type=TaskOutputRatingType.five_star
        )
    if has_named_rating:
        requirement_ratings["named::Named Score"] = RequirementRating(
            value=4.0, type=TaskOutputRatingType.five_star
        )
    rating.requirement_ratings = requirement_ratings

    task_run.output.rating = (
        rating
        if (has_overall_rating or has_requirement_rating or has_named_rating)
        else None
    )

    # Create the score object
    score = EvalOutputScore(
        name=score_name, instruction="Test score", type=TaskOutputRatingType.five_star
    )

    # Create the score key to requirement ID mapping
    score_key_to_task_requirement_id: Dict[str, ID_TYPE] = {"score1": "req_id"}

    # Call the function
    from app.desktop.studio_server.eval_api import human_score_from_task_run

    result = human_score_from_task_run(
        task_run, score, score_key_to_task_requirement_id
    )

    # Verify the result
    assert result == expected_score


def test_human_score_named_rating_survives_requirement_name_collision():
    """A task requirement whose name maps to the same json_key as the score
    must not hide a named rating: spec-created evals store the human verdict
    under named::{score.name}, and the like-named requirement may be unrated."""
    task_run = Mock(spec=TaskRun)
    task_run.output = Mock(spec=TaskOutput)
    rating = Mock(spec=TaskOutputRating)
    rating.value = None
    rating.requirement_ratings = {
        # No rating under the colliding requirement's id ("req_id"); the
        # human verdict lives under the named key.
        "named::My Spec": RequirementRating(
            value=1.0, type=TaskOutputRatingType.pass_fail
        ),
    }
    task_run.output.rating = rating

    score = EvalOutputScore(
        name="My Spec", instruction="Test score", type=TaskOutputRatingType.pass_fail
    )
    # A requirement named like the score maps to the same json_key.
    score_key_to_task_requirement_id: Dict[str, ID_TYPE] = {"my_spec": "req_id"}

    from app.desktop.studio_server.eval_api import human_score_from_task_run

    result = human_score_from_task_run(
        task_run, score, score_key_to_task_requirement_id
    )

    assert result == 1.0

    # When the colliding requirement IS rated, its rating still wins.
    rating.requirement_ratings["req_id"] = RequirementRating(
        value=0.0, type=TaskOutputRatingType.pass_fail
    )
    assert (
        human_score_from_task_run(task_run, score, score_key_to_task_requirement_id)
        == 0.0
    )


@pytest.mark.asyncio
async def test_create_task_run_config_invalid_temperature_values(
    client, mock_task_from_id, mock_task
):
    """Test that invalid temperature values return 422 errors."""
    mock_task_from_id.return_value = mock_task

    # Test temperature below 0
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "temperature": -0.1,
                "structured_output_mode": "json_schema",
            },
        },
    )
    assert response.status_code == 422
    error_detail = response.json()["message"]
    assert "temperature must be between 0 and 2" in str(error_detail)

    # Test temperature above 2
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "temperature": 2.1,
                "structured_output_mode": "json_schema",
            },
        },
    )
    assert response.status_code == 422
    error_detail = response.json()["message"]
    assert "temperature must be between 0 and 2" in str(error_detail)


@pytest.mark.asyncio
async def test_create_task_run_config_invalid_top_p_values(
    client, mock_task_from_id, mock_task
):
    """Test that invalid top_p values return 422 errors."""
    mock_task_from_id.return_value = mock_task

    # Test top_p below 0
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "top_p": -0.1,
                "structured_output_mode": "json_schema",
            },
        },
    )
    assert response.status_code == 422
    error_detail = response.json()["message"]
    assert "top_p must be between 0 and 1" in str(error_detail)

    # Test top_p above 1
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "top_p": 1.1,
                "structured_output_mode": "json_schema",
            },
        },
    )
    assert response.status_code == 422
    error_detail = response.json()["message"]
    assert "top_p must be between 0 and 1" in str(error_detail)


@pytest.mark.asyncio
async def test_create_task_run_config_valid_boundary_values(
    client, mock_task_from_id, mock_task
):
    """Test that valid boundary values for temperature and top_p work correctly."""
    mock_task_from_id.return_value = mock_task

    # Test valid boundary values - temperature = 0, top_p = 0
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config Min",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "temperature": 0.0,
                "top_p": 0.0,
                "structured_output_mode": "json_schema",
            },
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["run_config_properties"]["temperature"] == 0.0
    assert result["run_config_properties"]["top_p"] == 0.0

    # Test valid boundary values - temperature = 2, top_p = 1
    response = client.post(
        "/api/projects/project1/tasks/task1/run_configs",
        json={
            "name": "Test Task Run Config Max",
            "run_config_properties": {
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
                "temperature": 2.0,
                "top_p": 1.0,
                "structured_output_mode": "json_schema",
            },
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["run_config_properties"]["temperature"] == 2.0
    assert result["run_config_properties"]["top_p"] == 1.0


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_with_usage(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """Test that get_run_config_eval_scores correctly calculates mean usage statistics"""
    mock_task_from_id.return_value = mock_task

    # Create TaskRuns with usage data
    task_run_1 = TaskRun(
        input="test input 1",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 1"),
        usage=Usage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.005,
            total_llm_latency_ms=500,
        ),
        parent=mock_task,
    )
    task_run_1.save_to_file()

    task_run_2 = TaskRun(
        input="test input 2",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 2"),
        usage=Usage(
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            cost=0.010,
            total_llm_latency_ms=1000,
        ),
        parent=mock_task,
    )
    task_run_2.save_to_file()

    # Create a TaskRun without usage data
    task_run_3 = TaskRun(
        input="test input 3",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 3"),
        # No usage data
        parent=mock_task,
    )
    task_run_3.save_to_file()

    # Create EvalRuns for these TaskRuns
    eval_run_1 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 4.0, "overall_rating": 4.0},
        input="test input 1",
        output="test output 1",
        dataset_id=task_run_1.id,
        task_run_usage=task_run_1.usage,  # Copy usage from TaskRun
        parent=mock_eval_config,
    )
    eval_run_1.save_to_file()

    eval_run_2 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 4.5, "overall_rating": 4.5},
        input="test input 2",
        output="test output 2",
        dataset_id=task_run_2.id,
        task_run_usage=task_run_2.usage,  # Copy usage from TaskRun
        parent=mock_eval_config,
    )
    eval_run_2.save_to_file()

    eval_run_3 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 3.5, "overall_rating": 3.5},
        input="test input 3",
        output="test output 3",
        dataset_id=task_run_3.id,
        task_run_usage=task_run_3.usage,  # Copy usage from TaskRun (this will be None)
        parent=mock_eval_config,
    )
    eval_run_3.save_to_file()

    # Create mock objects instead of patching Pydantic models
    mock_task_for_api = MagicMock()
    mock_task_for_api.runs.return_value = [task_run_1, task_run_2, task_run_3]
    mock_task_for_api.evals.return_value = [mock_eval]

    mock_eval_config_for_api = MagicMock()
    mock_eval_config_for_api.runs.return_value = [eval_run_1, eval_run_2, eval_run_3]
    mock_eval_config_for_api.id = mock_eval_config.id

    mock_eval_for_api = MagicMock()
    mock_eval_for_api.configs.return_value = [mock_eval_config_for_api]
    mock_eval_for_api.id = mock_eval.id
    mock_eval_for_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_for_api.output_scores = mock_eval.output_scores

    mock_eval.current_config_id = mock_eval_config.id

    # Patch the task_from_id to return our mock
    with (
        patch(
            "app.desktop.studio_server.eval_api.task_from_id"
        ) as mock_task_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.eval_from_id"
        ) as mock_eval_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.task_run_config_from_id"
        ) as mock_task_run_config_from_id_patch,
    ):
        mock_task_from_id_patch.return_value = mock_task_for_api
        mock_eval_from_id_patch.return_value = mock_eval_for_api
        mock_task_run_config_from_id_patch.return_value = mock_run_config

        with patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter:
            mock_dataset_ids_in_filter.return_value = {
                task_run_1.id,
                task_run_2.id,
                task_run_3.id,
            }

            response = client.get(
                f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
            )

    assert response.status_code == 200
    data = response.json()

    # Verify the structure
    assert "eval_results" in data
    eval_results = data["eval_results"]
    assert len(eval_results) == 1

    eval_result = eval_results[0]
    assert "eval_config_result" in eval_result
    eval_config_result = eval_result["eval_config_result"]
    assert eval_config_result is not None
    assert eval_config_result["results"]["score1"]["mean_score"] == 4.0
    assert eval_config_result["results"]["overall_rating"]["mean_score"] == 4.0

    # Check that mean_usage is at the top level of the response
    assert "mean_usage" in data
    mean_usage = data["mean_usage"]
    assert mean_usage is not None

    # With 3 eval runs and 2 having usage data (2/3 = 66.7% > 50%),
    # all usage metrics should be included
    # Expected means: input_tokens=(100+200)/2=150, output_tokens=(50+100)/2=75,
    # total_tokens=(150+300)/2=225, cost=(0.005+0.010)/2=0.0075
    assert mean_usage["mean_input_tokens"] == 150.0
    assert mean_usage["mean_output_tokens"] == 75.0
    assert mean_usage["mean_total_tokens"] == 225.0
    assert mean_usage["mean_cost"] == 0.0075
    # Expected mean latency: (500+1000)/2 = 750.0 (2 of 3 runs have latency, 66.7% > 50%)
    assert mean_usage["mean_total_llm_latency_ms"] == 750.0


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_latency_below_threshold(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """Test that mean_total_llm_latency_ms is None when fewer than 50% of runs have latency data"""
    mock_task_from_id.return_value = mock_task

    # Create 3 TaskRuns, only 1 with latency data (1/3 = 33% < 50% threshold)
    task_run_1 = TaskRun(
        input="test input 1",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 1"),
        usage=Usage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.005,
            total_llm_latency_ms=500,
        ),
        parent=mock_task,
    )
    task_run_1.save_to_file()

    task_run_2 = TaskRun(
        input="test input 2",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 2"),
        usage=Usage(
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            cost=0.010,
        ),
        parent=mock_task,
    )
    task_run_2.save_to_file()

    task_run_3 = TaskRun(
        input="test input 3",
        input_source=DataSource(
            type=DataSourceType.synthetic,
            properties={
                "model_name": "gpt-4",
                "model_provider": "openai",
                "adapter_name": "langchain_adapter",
            },
        ),
        output=TaskOutput(output="test output 3"),
        usage=Usage(
            input_tokens=150,
            output_tokens=75,
            total_tokens=225,
            cost=0.008,
        ),
        parent=mock_task,
    )
    task_run_3.save_to_file()

    eval_run_1 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 4.0, "overall_rating": 4.0},
        input="test input 1",
        output="test output 1",
        dataset_id=task_run_1.id,
        task_run_usage=task_run_1.usage,
        parent=mock_eval_config,
    )
    eval_run_1.save_to_file()

    eval_run_2 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 4.5, "overall_rating": 4.5},
        input="test input 2",
        output="test output 2",
        dataset_id=task_run_2.id,
        task_run_usage=task_run_2.usage,
        parent=mock_eval_config,
    )
    eval_run_2.save_to_file()

    eval_run_3 = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 3.5, "overall_rating": 3.5},
        input="test input 3",
        output="test output 3",
        dataset_id=task_run_3.id,
        task_run_usage=task_run_3.usage,
        parent=mock_eval_config,
    )
    eval_run_3.save_to_file()

    mock_task_for_api = MagicMock()
    mock_task_for_api.runs.return_value = [task_run_1, task_run_2, task_run_3]
    mock_task_for_api.evals.return_value = [mock_eval]

    mock_eval_config_for_api = MagicMock()
    mock_eval_config_for_api.runs.return_value = [eval_run_1, eval_run_2, eval_run_3]
    mock_eval_config_for_api.id = mock_eval_config.id

    mock_eval_for_api = MagicMock()
    mock_eval_for_api.configs.return_value = [mock_eval_config_for_api]
    mock_eval_for_api.id = mock_eval.id
    mock_eval_for_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_for_api.output_scores = mock_eval.output_scores

    mock_eval.current_config_id = mock_eval_config.id

    with (
        patch(
            "app.desktop.studio_server.eval_api.task_from_id"
        ) as mock_task_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.eval_from_id"
        ) as mock_eval_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.task_run_config_from_id"
        ) as mock_task_run_config_from_id_patch,
    ):
        mock_task_from_id_patch.return_value = mock_task_for_api
        mock_eval_from_id_patch.return_value = mock_eval_for_api
        mock_task_run_config_from_id_patch.return_value = mock_run_config

        with patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter:
            mock_dataset_ids_in_filter.return_value = {
                task_run_1.id,
                task_run_2.id,
                task_run_3.id,
            }

            response = client.get(
                f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
            )

    assert response.status_code == 200
    data = response.json()
    mean_usage = data["mean_usage"]
    assert mean_usage is not None

    # Cost/tokens should be present (3/3 = 100% > 50%)
    assert mean_usage["mean_cost"] is not None
    # Latency should be None (only 1/3 = 33% < 50% threshold)
    assert mean_usage["mean_total_llm_latency_ms"] is None


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_inline_aggregation(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """Verify the inline aggregation path returns correct n_used, n_excluded, and percent_complete."""
    mock_task_from_id.return_value = mock_task

    task_runs = []
    for i in range(3):
        tr = TaskRun(
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "test",
                },
            ),
            output=TaskOutput(output=f"output {i}"),
            parent=mock_task,
        )
        tr.save_to_file()
        task_runs.append(tr)

    scored_run = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={"score1": 3.0, "overall_rating": 4.0},
        input="input 0",
        output="output 0",
        dataset_id=task_runs[0].id,
        parent=mock_eval_config,
    )
    scored_run.save_to_file()

    skipped_run = EvalRun(
        task_run_config_id=mock_run_config.id,
        scores={},
        input="input 1",
        output="output 1",
        dataset_id=task_runs[1].id,
        skipped_reason="extraction_failed",
        parent=mock_eval_config,
    )
    skipped_run.save_to_file()

    mock_task_api = MagicMock()
    mock_task_api.runs.return_value = task_runs
    mock_task_api.evals.return_value = [mock_eval]
    mock_task_api.specs.return_value = []

    mock_ec_api = MagicMock()
    mock_ec_api.runs.return_value = [scored_run, skipped_run]
    mock_ec_api.id = mock_eval_config.id

    mock_eval_api = MagicMock()
    mock_eval_api.configs.return_value = [mock_ec_api]
    mock_eval_api.id = mock_eval.id
    mock_eval_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_api.output_scores = mock_eval.output_scores
    mock_eval_api.name = mock_eval.name

    mock_eval.current_config_id = mock_eval_config.id

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as p_task,
        patch("app.desktop.studio_server.eval_api.eval_from_id") as p_eval,
        patch("app.desktop.studio_server.eval_api.task_run_config_from_id") as p_rc,
        patch("app.desktop.studio_server.eval_api.dataset_ids_in_filter") as p_ds,
    ):
        p_task.return_value = mock_task_api
        p_eval.return_value = mock_eval_api
        p_rc.return_value = mock_run_config
        p_ds.return_value = {tr.id for tr in task_runs}

        response = client.get(
            f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
        )

    assert response.status_code == 200
    data = response.json()
    er = data["eval_results"][0]
    ecr = er["eval_config_result"]

    assert ecr["n_excluded"] == 1
    assert ecr["results"]["score1"]["n_used"] == 1
    assert ecr["results"]["score1"]["n_excluded"] == 1
    assert ecr["results"]["score1"]["mean_score"] == 3.0
    assert ecr["results"]["overall_rating"]["n_used"] == 1
    assert ecr["results"]["overall_rating"]["n_excluded"] == 1
    assert ecr["results"]["overall_rating"]["mean_score"] == 4.0
    assert ecr["percent_complete"] == pytest.approx(2.0 / 3.0)


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_all_skipped(
    client, mock_task_from_id, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """When every EvalRun is skipped, mean_score should be None and n_used == 0."""
    mock_task_from_id.return_value = mock_task

    task_runs = []
    for i in range(2):
        tr = TaskRun(
            input=f"input {i}",
            input_source=DataSource(
                type=DataSourceType.synthetic,
                properties={
                    "model_name": "gpt-4",
                    "model_provider": "openai",
                    "adapter_name": "test",
                },
            ),
            output=TaskOutput(output=f"output {i}"),
            parent=mock_task,
        )
        tr.save_to_file()
        task_runs.append(tr)

    skipped_runs = [
        EvalRun(
            task_run_config_id=mock_run_config.id,
            scores={},
            input=f"input {i}",
            output=f"output {i}",
            dataset_id=task_runs[i].id,
            skipped_reason="incompatible_input_shape",
            parent=mock_eval_config,
        )
        for i in range(2)
    ]
    for sr in skipped_runs:
        sr.save_to_file()

    mock_task_api = MagicMock()
    mock_task_api.runs.return_value = task_runs
    mock_task_api.evals.return_value = [mock_eval]
    mock_task_api.specs.return_value = []

    mock_ec_api = MagicMock()
    mock_ec_api.runs.return_value = skipped_runs
    mock_ec_api.id = mock_eval_config.id

    mock_eval_api = MagicMock()
    mock_eval_api.configs.return_value = [mock_ec_api]
    mock_eval_api.id = mock_eval.id
    mock_eval_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_api.output_scores = mock_eval.output_scores
    mock_eval_api.name = mock_eval.name

    mock_eval.current_config_id = mock_eval_config.id

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as p_task,
        patch("app.desktop.studio_server.eval_api.eval_from_id") as p_eval,
        patch("app.desktop.studio_server.eval_api.task_run_config_from_id") as p_rc,
        patch("app.desktop.studio_server.eval_api.dataset_ids_in_filter") as p_ds,
    ):
        p_task.return_value = mock_task_api
        p_eval.return_value = mock_eval_api
        p_rc.return_value = mock_run_config
        p_ds.return_value = {tr.id for tr in task_runs}

        response = client.get(
            f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
        )

    assert response.status_code == 200
    data = response.json()
    er = data["eval_results"][0]
    ecr = er["eval_config_result"]

    assert ecr["n_excluded"] == 2
    assert ecr["results"]["score1"]["n_used"] == 0
    assert ecr["results"]["score1"]["n_excluded"] == 2
    assert ecr["results"]["score1"]["mean_score"] is None
    assert ecr["results"]["overall_rating"]["n_used"] == 0
    assert ecr["results"]["overall_rating"]["n_excluded"] == 2
    assert ecr["results"]["overall_rating"]["mean_score"] is None
    assert ecr["percent_complete"] == 1.0


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_includes_eval_input_evals(
    client, mock_task_from_id, mock_task
):
    """EvalInput-typed evals appear in a run config's eval scores with real
    sizing and completion instead of being silently omitted."""
    mock_task_from_id.return_value = mock_task

    eval = Eval(
        id="eval_input_eval",
        name="EvalInput Eval",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                instruction="Test accuracy",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        eval_input_filter_id="tag::eval_slice",
        eval_configs_filter_id="tag::golden",
        current_config_id="ec1",
        parent=mock_task,
    )
    eval.save_to_file()
    eval_config = EvalConfig(
        id="ec1",
        name="Judge",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
        model_name="gpt-4",
        model_provider="openai",
        parent=eval,
    )
    eval_config.save_to_file()

    eval_input_ids = []
    for i in range(2):
        eval_input = EvalInput(
            data=MultiTurnSyntheticEvalInputData(
                first_message=UserMessage(text=f"seed {i}"),
                synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            ),
            tags=["eval_slice"],
            parent=mock_task,
        )
        eval_input.save_to_file()
        eval_input_ids.append(eval_input.id)

    run_config = TaskRunConfig(
        parent=mock_task,
        id="rc1",
        name="Run Config 1",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()

    for eval_input_id, score in zip(eval_input_ids, [1.0, 0.0]):
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": score},
            input="input",
            output="output",
            eval_input_id=eval_input_id,
            parent=eval_config,
        ).save_to_file()

    response = client.get(
        "/api/projects/project1/tasks/task1/run_configs/rc1/eval_scores"
    )

    assert response.status_code == 200
    data = response.json()
    eval_result = next(
        (er for er in data["eval_results"] if er["eval_id"] == "eval_input_eval"),
        None,
    )
    assert eval_result is not None, "EvalInput eval missing from eval_scores"
    assert eval_result["dataset_size"] == 2
    ecr = eval_result["eval_config_result"]
    assert ecr["results"]["accuracy"]["mean_score"] == pytest.approx(0.5)
    assert ecr["results"]["accuracy"]["n_used"] == 2
    assert ecr["percent_complete"] == 1.0


def test_get_eval_configs_score_summary_no_filter_id(
    client, mock_task, mock_task_from_id
):
    """Test that get_eval_configs_score_summary returns 400 when eval_configs_filter_id is None"""
    mock_task_from_id.return_value = mock_task

    # Create an eval with eval_configs_filter_id set to None
    # Only RAG template allows eval_configs_filter_id to be None
    eval_without_filter = Eval(
        id="eval1",
        name="Test Eval",
        description="Test Description",
        template=EvalTemplateId.rag,
        output_scores=[
            EvalOutputScore(
                name="score1", instruction="desc1", type=TaskOutputRatingType.five_star
            ),
        ],
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id=None,
        parent=mock_task,
    )
    eval_without_filter.save_to_file()

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = eval_without_filter

        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1/eval_configs_score_summary"
        )

        assert response.status_code == 400
        assert (
            response.json()["message"]
            == "No eval configs filter id set, cannot get eval configs score summary."
        )
        mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_includes_spec_id(
    client, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """Test that get_run_config_eval_scores includes spec_id for spec-associated evals and None for legacy evals"""

    # Create a spec that references the eval
    spec = Spec(
        id="spec1",
        name="Test Spec",
        definition="Test spec definition",
        properties=DesiredBehaviourProperties(
            spec_type=SpecType.desired_behaviour,
            core_requirement="test instruction",
            desired_behaviour_description="test desired behaviour",
        ),
        eval_id=mock_eval.id,  # Associate this spec with the eval
        parent=mock_task,
    )
    spec.save_to_file()

    # Create a second eval that is NOT associated with any spec (legacy eval)
    legacy_eval = Eval(
        id="legacy_eval1",
        name="Legacy Eval",
        description="Legacy eval without spec",
        template=None,
        eval_set_filter_id="tag::legacy_eval_set",
        eval_configs_filter_id="tag::legacy_golden",
        output_scores=[
            EvalOutputScore(
                name="score1",
                instruction="desc1",
                type=TaskOutputRatingType.five_star,
            ),
        ],
        parent=mock_task,
    )
    legacy_eval.save_to_file()

    # Create an eval config for the legacy eval
    legacy_eval_config = EvalConfig(
        id="legacy_eval_config1",
        name="Legacy Eval Config",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
        parent=legacy_eval,
        model_name="gpt-4",
        model_provider="openai",
    )
    legacy_eval_config.save_to_file()
    legacy_eval.current_config_id = legacy_eval_config.id
    legacy_eval.save_to_file()

    # Create mock objects for the API
    mock_task_for_api = MagicMock()
    mock_task_for_api.evals.return_value = [mock_eval, legacy_eval]
    mock_task_for_api.specs.return_value = [spec]

    mock_eval_config_for_api = MagicMock()
    mock_eval_config_for_api.runs.return_value = []
    mock_eval_config_for_api.id = mock_eval_config.id

    mock_eval_for_api = MagicMock()
    mock_eval_for_api.configs.return_value = [mock_eval_config_for_api]
    mock_eval_for_api.id = mock_eval.id
    mock_eval_for_api.name = mock_eval.name
    mock_eval_for_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_for_api.output_scores = mock_eval.output_scores
    mock_eval_for_api.current_config_id = mock_eval_config.id

    legacy_eval_config_for_api = MagicMock()
    legacy_eval_config_for_api.runs.return_value = []
    legacy_eval_config_for_api.id = legacy_eval_config.id

    legacy_eval_for_api = MagicMock()
    legacy_eval_for_api.configs.return_value = [legacy_eval_config_for_api]
    legacy_eval_for_api.id = legacy_eval.id
    legacy_eval_for_api.name = legacy_eval.name
    legacy_eval_for_api.eval_set_filter_id = legacy_eval.eval_set_filter_id
    legacy_eval_for_api.output_scores = legacy_eval.output_scores
    legacy_eval_for_api.current_config_id = legacy_eval_config.id

    # Patch the API dependencies
    with (
        patch(
            "app.desktop.studio_server.eval_api.task_from_id"
        ) as mock_task_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.task_run_config_from_id"
        ) as mock_task_run_config_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter,
    ):
        mock_task_from_id_patch.return_value = mock_task_for_api
        mock_task_run_config_from_id_patch.return_value = mock_run_config
        mock_dataset_ids_in_filter.return_value = set()

        response = client.get(
            f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
        )

    assert response.status_code == 200
    data = response.json()

    # Verify the structure
    assert "eval_results" in data
    assert len(data["eval_results"]) == 2

    # Find the results by eval name
    spec_eval_result = next(
        (r for r in data["eval_results"] if r["eval_name"] == "Test Eval"), None
    )
    legacy_eval_result = next(
        (r for r in data["eval_results"] if r["eval_name"] == "Legacy Eval"), None
    )

    assert spec_eval_result is not None
    assert legacy_eval_result is not None

    # Verify spec_id is populated for spec-associated eval
    assert spec_eval_result["spec_id"] == "spec1"

    # Verify spec_id is None for legacy eval
    assert legacy_eval_result["spec_id"] is None


@pytest.mark.asyncio
async def test_get_run_config_eval_scores_excludes_archived_specs(
    client, mock_task, mock_eval, mock_eval_config, mock_run_config
):
    """Test that get_run_config_eval_scores excludes evals associated with archived specs"""

    # Create an active spec
    active_spec = Spec(
        id="active_spec1",
        name="Active Spec",
        definition="Active spec definition",
        properties=DesiredBehaviourProperties(
            spec_type=SpecType.desired_behaviour,
            core_requirement="test instruction",
            desired_behaviour_description="test desired behaviour",
        ),
        eval_id=mock_eval.id,
        status=SpecStatus.active,
        parent=mock_task,
    )
    active_spec.save_to_file()

    # Create an archived spec with its own eval
    archived_eval = Eval(
        id="archived_eval1",
        name="Archived Eval",
        description="Eval for archived spec",
        template=None,
        eval_set_filter_id="tag::archived_eval_set",
        eval_configs_filter_id="tag::archived_golden",
        output_scores=[
            EvalOutputScore(
                name="score1",
                instruction="desc1",
                type=TaskOutputRatingType.five_star,
            ),
        ],
        parent=mock_task,
    )
    archived_eval.save_to_file()

    archived_eval_config = EvalConfig(
        id="archived_eval_config1",
        name="Archived Eval Config",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
        parent=archived_eval,
        model_name="gpt-4",
        model_provider="openai",
    )
    archived_eval_config.save_to_file()
    archived_eval.current_config_id = archived_eval_config.id
    archived_eval.save_to_file()

    archived_spec = Spec(
        id="archived_spec1",
        name="Archived Spec",
        definition="Archived spec definition",
        properties=DesiredBehaviourProperties(
            spec_type=SpecType.desired_behaviour,
            core_requirement="test instruction",
            desired_behaviour_description="test desired behaviour",
        ),
        eval_id=archived_eval.id,
        status=SpecStatus.archived,
        parent=mock_task,
    )
    archived_spec.save_to_file()

    # Build mock eval objects with explicit attributes
    mock_eval_config_for_api = MagicMock()
    mock_eval_config_for_api.id = mock_eval_config.id
    mock_eval_config_for_api.runs.return_value = []

    mock_eval_for_api = MagicMock()
    mock_eval_for_api.id = mock_eval.id
    mock_eval_for_api.name = mock_eval.name
    mock_eval_for_api.eval_set_filter_id = mock_eval.eval_set_filter_id
    mock_eval_for_api.output_scores = mock_eval.output_scores
    mock_eval_for_api.current_config_id = mock_eval_config.id
    mock_eval_for_api.configs.return_value = [mock_eval_config_for_api]

    archived_eval_config_for_api = MagicMock()
    archived_eval_config_for_api.id = archived_eval_config.id
    archived_eval_config_for_api.runs.return_value = []

    archived_eval_for_api = MagicMock()
    archived_eval_for_api.id = archived_eval.id
    archived_eval_for_api.name = archived_eval.name
    archived_eval_for_api.eval_set_filter_id = archived_eval.eval_set_filter_id
    archived_eval_for_api.output_scores = archived_eval.output_scores
    archived_eval_for_api.current_config_id = archived_eval_config.id
    archived_eval_for_api.configs.return_value = [archived_eval_config_for_api]

    mock_task_for_api = MagicMock()
    mock_task_for_api.evals.return_value = [mock_eval_for_api, archived_eval_for_api]
    mock_task_for_api.specs.return_value = [active_spec, archived_spec]

    with (
        patch(
            "app.desktop.studio_server.eval_api.task_from_id"
        ) as mock_task_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.task_run_config_from_id"
        ) as mock_task_run_config_from_id_patch,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_dataset_ids_in_filter,
    ):
        mock_task_from_id_patch.return_value = mock_task_for_api
        mock_task_run_config_from_id_patch.return_value = mock_run_config
        mock_dataset_ids_in_filter.return_value = set()

        response = client.get(
            f"/api/projects/project1/tasks/task1/run_configs/{mock_run_config.id}/eval_scores"
        )

    assert response.status_code == 200
    data = response.json()

    # Only the active spec's eval should be present, not the archived one
    assert len(data["eval_results"]) == 1
    assert data["eval_results"][0]["eval_name"] == "Test Eval"
    assert data["eval_results"][0]["spec_id"] == "active_spec1"


@pytest.mark.asyncio
async def test_get_run_configs_includes_finetunes_with_run_config(
    client, mock_task_from_id, mock_task
):
    """Test that finetunes are included in run configs only if they have a run_config set."""
    mock_task_from_id.return_value = mock_task

    run_config_props = KilnAgentRunConfigProperties(
        model_name="gpt-4",
        model_provider_name=ModelProviderName.openai,
        prompt_id="simple_chain_of_thought_prompt_builder",
        structured_output_mode=StructuredOutputMode.json_schema,
    )

    finetunes = [
        Finetune(
            id="ft_completed",
            name="Completed Finetune",
            provider="openai",
            base_model_id="model1",
            dataset_split_id="split1",
            system_message="System message",
            latest_status=FineTuneStatusType.completed,
            run_config=run_config_props,
            fine_tune_model_id="ft_model_123",
            parent=mock_task,
        ),
        Finetune(
            id="ft_running",
            name="Running Finetune",
            provider="openai",
            base_model_id="model2",
            dataset_split_id="split2",
            system_message="System message",
            latest_status=FineTuneStatusType.running,
            run_config=run_config_props,
            fine_tune_model_id=None,
            parent=mock_task,
        ),
        Finetune(
            id="ft_unknown",
            name="Unknown Finetune",
            provider="openai",
            base_model_id="model3",
            dataset_split_id="split3",
            system_message="System message",
            latest_status=FineTuneStatusType.unknown,
            run_config=run_config_props,
            fine_tune_model_id=None,
            parent=mock_task,
        ),
        Finetune(
            id="ft_failed",
            name="Failed Finetune",
            provider="openai",
            base_model_id="model4",
            dataset_split_id="split4",
            system_message="System message",
            latest_status=FineTuneStatusType.failed,
            run_config=run_config_props,
            fine_tune_model_id=None,
            parent=mock_task,
        ),
        Finetune(
            id="ft_no_run_config",
            name="No Run Config Finetune",
            provider="openai",
            base_model_id="model5",
            dataset_split_id="split5",
            system_message="System message",
            latest_status=FineTuneStatusType.completed,
            run_config=None,
            parent=mock_task,
        ),
    ]

    for finetune in finetunes:
        finetune.save_to_file()

    response = client.get("/api/projects/project1/tasks/task1/run_configs")

    assert response.status_code == 200
    configs = response.json()

    config_ids = [config["id"] for config in configs]

    assert "finetune_run_config::project1::task1::ft_completed" in config_ids
    assert "finetune_run_config::project1::task1::ft_running" not in config_ids
    assert "finetune_run_config::project1::task1::ft_failed" not in config_ids
    assert "finetune_run_config::project1::task1::ft_unknown" not in config_ids
    assert "finetune_run_config::project1::task1::ft_no_run_config" not in config_ids


# --- SSE endpoints must carry @no_write_lock ---


def _find_endpoint_by_path(app, path_suffix: str):
    """Locate the endpoint function for a route ending with path_suffix."""
    for route in app.routes:
        if getattr(route, "path", "").endswith(path_suffix):
            return route.endpoint  # type: ignore[attr-defined]
    raise AssertionError(f"Route ending in {path_suffix} not found")


def test_run_comparison_has_no_write_lock(app):
    endpoint = _find_endpoint_by_path(
        app, "/eval_config/{eval_config_id}/run_comparison"
    )
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True


def test_run_calibration_has_no_write_lock(app):
    endpoint = _find_endpoint_by_path(app, "/evals/{eval_id}/run_calibration")
    assert getattr(endpoint, "_git_sync_no_write_lock", False) is True


# --- eval_results_summary tests ---


def _build_mock_eval(
    eval_id: str,
    name: str,
    current_config_id: str | None,
    eval_set_filter_id: str,
    output_scores: list[EvalOutputScore],
    configs: list,
) -> Mock:
    mock = Mock(spec=Eval)
    mock.id = eval_id
    mock.name = name
    mock.current_config_id = current_config_id
    mock.eval_set_filter_id = eval_set_filter_id
    mock.output_scores = output_scores
    mock.configs.return_value = configs
    return mock


def _build_mock_eval_config(
    config_id: str,
    name: str,
    eval_runs: list[EvalRun],
) -> Mock:
    mock = Mock(spec=EvalConfig)
    mock.id = config_id
    mock.name = name
    mock.runs.return_value = eval_runs
    return mock


@pytest.mark.asyncio
async def test_eval_results_summary_happy_path(client):
    output_scores_1 = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]
    output_scores_2 = [
        EvalOutputScore(
            name="relevance",
            instruction="Test relevance",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]

    # Eval 1 default config (ec1): rc1 has 2 runs, rc2 has 1 run
    eval1_runs_default = [
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.8},
            input="i",
            output="o",
            dataset_id="ds1",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.6},
            input="i",
            output="o",
            dataset_id="ds2",
        ),
        EvalRun(
            task_run_config_id="rc2",
            scores={"accuracy": 0.9},
            input="i",
            output="o",
            dataset_id="ds1",
        ),
    ]

    # Eval 2 default config (ec4): rc2 has 1 run
    eval2_runs_default = [
        EvalRun(
            task_run_config_id="rc2",
            scores={"relevance": 0.3},
            input="i",
            output="o",
            dataset_id="ds3",
        ),
    ]

    e1c1 = _build_mock_eval_config("ec1", "Judge A", eval1_runs_default)
    e1c2 = _build_mock_eval_config("ec2", "Judge B", [])

    e2c1 = _build_mock_eval_config("ec3", "Judge C", [])
    e2c2 = _build_mock_eval_config("ec4", "Judge D", eval2_runs_default)

    eval1 = _build_mock_eval(
        eval_id="eval1",
        name="Eval One",
        current_config_id="ec1",
        eval_set_filter_id="tag::eval_set_1",
        output_scores=output_scores_1,
        configs=[e1c1, e1c2],
    )
    eval2 = _build_mock_eval(
        eval_id="eval2",
        name="Eval Two",
        current_config_id="ec4",
        eval_set_filter_id="tag::eval_set_2",
        output_scores=output_scores_2,
        configs=[e2c1, e2c2],
    )

    rc1_mock = Mock(spec=TaskRunConfig, id="rc1")
    rc1_mock.name = "Run Config 1"
    rc2_mock = Mock(spec=TaskRunConfig, id="rc2")
    rc2_mock.name = "Run Config 2"
    rc3_mock = Mock(spec=TaskRunConfig, id="rc3")
    rc3_mock.name = "Run Config 3"

    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = [rc1_mock, rc2_mock, rc3_mock]
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = [eval1, eval2]

    def ds_filter_side_effect(task, filter_id, readonly):
        if filter_id == "tag::eval_set_1":
            return {"ds1", "ds2"}
        elif filter_id == "tag::eval_set_2":
            return {"ds3"}
        return set()

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter",
            side_effect=ds_filter_side_effect,
        ),
    ):
        mock_task_from_id.return_value = mock_task

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    data = response.json()

    # --- evals_by_id dict ---
    assert "eval1" in data["evals_by_id"]
    assert "eval2" in data["evals_by_id"]
    assert data["evals_by_id"]["eval1"]["name"] == "Eval One"
    assert data["evals_by_id"]["eval1"]["default_judge_config_id"] == "ec1"
    assert data["evals_by_id"]["eval1"]["dataset_size"] == 2
    assert data["evals_by_id"]["eval1"]["output_score_keys"] == ["accuracy"]
    assert data["evals_by_id"]["eval2"]["name"] == "Eval Two"
    assert data["evals_by_id"]["eval2"]["default_judge_config_id"] == "ec4"
    assert data["evals_by_id"]["eval2"]["dataset_size"] == 1
    assert data["evals_by_id"]["eval2"]["output_score_keys"] == ["relevance"]

    # --- run_configs_by_id dict ---
    assert data["run_configs_by_id"]["rc1"]["name"] == "Run Config 1"
    assert data["run_configs_by_id"]["rc2"]["name"] == "Run Config 2"
    assert data["run_configs_by_id"]["rc3"]["name"] == "Run Config 3"

    # --- scores_by_run_config_by_eval dict (run_config outer, eval inner) ---
    # Eval 1 default judge (ec1): rc1 mean=0.7, rc2 mean=0.9
    assert data["scores_by_run_config_by_eval"]["rc1"]["eval1"]["mean_scores"][
        "accuracy"
    ] == pytest.approx(0.7)
    assert (
        data["scores_by_run_config_by_eval"]["rc1"]["eval1"]["percent_complete"] == 1.0
    )
    assert data["scores_by_run_config_by_eval"]["rc2"]["eval1"]["mean_scores"][
        "accuracy"
    ] == pytest.approx(0.9)
    assert (
        data["scores_by_run_config_by_eval"]["rc2"]["eval1"]["percent_complete"] == 0.5
    )

    # Eval 2 default judge (ec4): rc2 mean=0.3
    assert data["scores_by_run_config_by_eval"]["rc2"]["eval2"]["mean_scores"][
        "relevance"
    ] == pytest.approx(0.3)
    assert (
        data["scores_by_run_config_by_eval"]["rc2"]["eval2"]["percent_complete"] == 1.0
    )


@pytest.mark.asyncio
async def test_eval_results_summary_includes_eval_input_evals(
    client, mock_task_from_id, mock_task
):
    """EvalInput-typed evals appear in the cross-eval summary with real sizing
    and scores instead of being silently omitted. Both evals here filter on the
    SAME tag string, so this also proves the expected-ids cache doesn't collide
    across the TaskRun and EvalInput stores."""
    mock_task_from_id.return_value = mock_task

    shared_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]
    eval_input_eval = Eval(
        id="eval_input_eval",
        name="EvalInput Eval",
        output_scores=shared_scores,
        eval_input_filter_id="tag::shared",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    eval_input_eval.save_to_file()
    dataset_eval = Eval(
        id="dataset_eval",
        name="Dataset Eval",
        output_scores=shared_scores,
        eval_set_filter_id="tag::shared",
        eval_configs_filter_id="tag::golden",
        parent=mock_task,
    )
    dataset_eval.save_to_file()

    eval_input_ids = []
    for i in range(3):
        eval_input = EvalInput(
            data=MultiTurnSyntheticEvalInputData(
                first_message=UserMessage(text=f"seed {i}"),
                synthetic_user_info=SyntheticUserInfo(persona="p", goal="g"),
            ),
            tags=["shared"],
            parent=mock_task,
        )
        eval_input.save_to_file()
        eval_input_ids.append(eval_input.id)

    eval_config = EvalConfig(
        id="ec1",
        name="Judge",
        config_type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1"]},
        model_name="gpt-4",
        model_provider="openai",
        parent=eval_input_eval,
    )
    eval_config.save_to_file()
    eval_input_eval.current_config_id = "ec1"
    eval_input_eval.save_to_file()
    EvalRun(
        task_run_config_id="rc1",
        scores={"accuracy": 1.0},
        input="input",
        output="output",
        eval_input_id=eval_input_ids[0],
        parent=eval_config,
    ).save_to_file()

    run_config = TaskRunConfig(
        parent=mock_task,
        id="rc1",
        name="Run Config 1",
        run_config_properties=KilnAgentRunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id="simple_chain_of_thought_prompt_builder",
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )
    run_config.save_to_file()

    # The TaskRun store has TWO items tagged "shared" (vs three EvalInputs)
    with patch(
        "app.desktop.studio_server.eval_api.dataset_ids_in_filter",
        return_value={"ds1", "ds2"},
    ):
        response = client.get("/api/projects/project1/tasks/task1/eval_results_summary")

    assert response.status_code == 200
    data = response.json()

    assert data["evals_by_id"]["eval_input_eval"]["dataset_size"] == 3
    assert data["evals_by_id"]["dataset_eval"]["dataset_size"] == 2

    cell = data["scores_by_run_config_by_eval"]["rc1"]["eval_input_eval"]
    assert cell["mean_scores"]["accuracy"] == 1.0
    assert cell["percent_complete"] == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_eval_results_summary_behavioral_equivalence(client):
    """For the default judge of an eval, results in eval_results_summary match /score_summary."""
    output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
        EvalOutputScore(
            name="relevance",
            instruction="Test relevance",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]

    eval_runs = [
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.8, "relevance": 0.9},
            input="i",
            output="o",
            dataset_id="ds1",
        ),
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.6, "relevance": 0.7},
            input="i",
            output="o",
            dataset_id="ds2",
        ),
    ]

    ec1 = _build_mock_eval_config("ec1", "Judge A", eval_runs)

    eval1 = _build_mock_eval(
        eval_id="eval1",
        name="Eval One",
        current_config_id="ec1",
        eval_set_filter_id="tag::eval_set",
        output_scores=output_scores,
        configs=[ec1],
    )

    rc1_mock = Mock(spec=TaskRunConfig, id="rc1")
    rc1_mock.name = "Run Config 1"

    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = [rc1_mock]
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = [eval1]

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_ds_filter,
        patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id,
        patch(
            "app.desktop.studio_server.eval_api.eval_config_from_id"
        ) as mock_eval_config_from_id,
    ):
        mock_task_from_id.return_value = mock_task
        mock_ds_filter.return_value = {"ds1", "ds2"}
        mock_eval_from_id.return_value = eval1
        mock_eval_config_from_id.return_value = ec1

        summary_response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")
        score_response = client.get(
            "/api/projects/p1/tasks/t1/evals/eval1/eval_config/ec1/score_summary"
        )

    assert summary_response.status_code == 200
    assert score_response.status_code == 200

    summary_data = summary_response.json()
    score_data = score_response.json()

    # Compare per run_config cell: mean_scores should match score_summary results
    for rc_id, evals_dict in summary_data["scores_by_run_config_by_eval"].items():
        cell = evals_dict["eval1"]
        for score_key, mean_val in cell["mean_scores"].items():
            assert mean_val == pytest.approx(
                score_data["results"][rc_id][score_key]["mean_score"]
            )
        assert cell["percent_complete"] == pytest.approx(
            score_data["run_config_percent_complete"][rc_id]
        )


@pytest.mark.asyncio
async def test_eval_results_summary_empty_filter(client):
    """Empty dataset filter: eval appears in evals but not in results."""
    output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]
    ec1 = _build_mock_eval_config("ec1", "Judge A", [])
    eval1 = _build_mock_eval(
        eval_id="eval1",
        name="Eval One",
        current_config_id="ec1",
        eval_set_filter_id="tag::empty",
        output_scores=output_scores,
        configs=[ec1],
    )

    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = []
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = [eval1]

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_ds_filter,
    ):
        mock_task_from_id.return_value = mock_task
        mock_ds_filter.return_value = set()

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    data = response.json()
    assert "eval1" in data["evals_by_id"]
    assert data["evals_by_id"]["eval1"]["dataset_size"] == 0
    # No run_config should have an eval1 entry
    for rc_evals in data["scores_by_run_config_by_eval"].values():
        assert "eval1" not in rc_evals


@pytest.mark.asyncio
async def test_eval_results_summary_no_default_judge(client):
    """Eval with no current_config_id appears in evals but not in results."""
    output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]
    ec1 = _build_mock_eval_config("ec1", "Judge A", [])
    eval1 = _build_mock_eval(
        eval_id="eval1",
        name="Eval One",
        current_config_id=None,
        eval_set_filter_id="tag::test",
        output_scores=output_scores,
        configs=[ec1],
    )

    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = []
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = [eval1]

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
        ) as mock_ds_filter,
    ):
        mock_task_from_id.return_value = mock_task
        mock_ds_filter.return_value = {"ds1"}

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    data = response.json()
    assert "eval1" in data["evals_by_id"]
    assert data["evals_by_id"]["eval1"]["default_judge_config_id"] is None
    # No run_config should have an eval1 entry
    for rc_evals in data["scores_by_run_config_by_eval"].values():
        assert "eval1" not in rc_evals


@pytest.mark.asyncio
async def test_eval_results_summary_no_evals(client):
    """Task with no evals returns empty dicts."""
    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = []
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = []

    with patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id:
        mock_task_from_id.return_value = mock_task

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    assert response.json() == {
        "evals_by_id": {},
        "run_configs_by_id": {},
        "scores_by_run_config_by_eval": {},
    }


@pytest.mark.asyncio
async def test_eval_results_summary_dataset_ids_cached_per_filter(client):
    """dataset_ids_in_filter is called once per unique filter_id, not per eval."""
    output_scores = [
        EvalOutputScore(
            name="accuracy",
            instruction="Test accuracy",
            type=TaskOutputRatingType.pass_fail,
        ),
    ]

    eval_runs = [
        EvalRun(
            task_run_config_id="rc1",
            scores={"accuracy": 0.8},
            input="i",
            output="o",
            dataset_id="ds1",
        ),
    ]

    ec1a = _build_mock_eval_config("ec1a", "Judge A1", eval_runs)
    ec2a = _build_mock_eval_config("ec2a", "Judge B1", eval_runs)

    eval1 = _build_mock_eval(
        eval_id="eval1",
        name="Eval One",
        current_config_id="ec1a",
        eval_set_filter_id="tag::set1",
        output_scores=output_scores,
        configs=[ec1a],
    )
    eval2 = _build_mock_eval(
        eval_id="eval2",
        name="Eval Two",
        current_config_id="ec2a",
        eval_set_filter_id="tag::set2",
        output_scores=output_scores,
        configs=[ec2a],
    )

    rc1_mock = Mock(spec=TaskRunConfig, id="rc1")
    rc1_mock.name = "RC1"

    mock_task = Mock(spec=Task)
    mock_task.run_configs.return_value = [rc1_mock]
    mock_task.finetunes.return_value = []
    mock_task.evals.return_value = [eval1, eval2]

    runs_call_count = 0

    def counting_dataset_ids_in_filter(task, filter_id, readonly):
        nonlocal runs_call_count
        runs_call_count += 1
        return {"ds1"}

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter",
            side_effect=counting_dataset_ids_in_filter,
        ),
    ):
        mock_task_from_id.return_value = mock_task

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    assert runs_call_count == 2

    # If they shared the same filter_id, it would be called once
    eval2.eval_set_filter_id = "tag::set1"
    runs_call_count = 0

    with (
        patch("app.desktop.studio_server.eval_api.task_from_id") as mock_task_from_id,
        patch(
            "app.desktop.studio_server.eval_api.dataset_ids_in_filter",
            side_effect=counting_dataset_ids_in_filter,
        ),
    ):
        mock_task_from_id.return_value = mock_task

        response = client.get("/api/projects/p1/tasks/t1/eval_results_summary")

    assert response.status_code == 200
    assert runs_call_count == 1


class TestCodeEvalTrustEndpoints:
    @pytest.fixture(autouse=True)
    def _clear_trust(self):
        from kiln_ai.adapters.eval.v2_eval_code_eval import _trusted_projects

        _trusted_projects.clear()
        yield
        _trusted_projects.clear()

    def test_grant_trust(self, client):
        with patch("app.desktop.studio_server.eval_api.project_from_id") as mock_proj:
            mock_proj.return_value = Mock()
            response = client.post("/api/projects/proj-1/grant_code_eval_trust")

        assert response.status_code == 200
        assert response.json() == {"trusted": True}

    def test_grant_trust_invalid_project(self, client):
        with patch("app.desktop.studio_server.eval_api.project_from_id") as mock_proj:
            mock_proj.side_effect = HTTPException(status_code=404, detail="Not found")
            response = client.post("/api/projects/bad-id/grant_code_eval_trust")

        assert response.status_code == 404

    def test_check_trust_untrusted(self, client):
        with patch("app.desktop.studio_server.eval_api.project_from_id") as mock_proj:
            mock_proj.return_value = Mock()
            response = client.get("/api/projects/proj-1/code_eval_trust")
        assert response.status_code == 200
        assert response.json() == {"trusted": False}

    def test_check_trust_after_grant(self, client):
        mock_project = Mock()
        with patch("app.desktop.studio_server.eval_api.project_from_id") as mock_proj:
            mock_proj.return_value = mock_project
            client.post("/api/projects/proj-1/grant_code_eval_trust")
            response = client.get("/api/projects/proj-1/code_eval_trust")
        assert response.status_code == 200
        assert response.json() == {"trusted": True}


@pytest.fixture
def mock_v2_eval(mock_task):
    eval = Eval(
        id="eval_v2",
        name="V2 Test Eval",
        description="V2 eval for testing",
        output_scores=[
            EvalOutputScore(
                name="accuracy",
                instruction="Is the answer accurate?",
                type=TaskOutputRatingType.pass_fail,
            ),
        ],
        eval_input_filter_id="tag::v2_eval_set",
        evaluation_data_type=None,
        parent=mock_task,
    )
    eval.save_to_file()
    return eval


class TestTestV2Eval:
    def _url(self, eval_id: str = "eval_v2") -> str:
        return f"/api/projects/project1/tasks/task1/evals/{eval_id}/test_v2_eval"

    def _exact_match_payload(self) -> dict:
        return {
            "properties": {
                "type": "exact_match",
                "expected_value": "hello",
            },
            "eval_input": {
                "final_message": "hello",
            },
        }

    def test_exact_match_pass(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json=self._exact_match_payload(),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["scores"]["accuracy"] == 1.0
        assert body["skipped_reason"] is None
        assert body["skipped_detail"] is None

    def test_exact_match_fail(self, client, mock_v2_eval):
        payload = self._exact_match_payload()
        payload["eval_input"]["final_message"] = "world"
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["scores"]["accuracy"] == 0.0
        assert body["skipped_reason"] is None

    def test_code_eval_untrusted_skip(self, client, mock_v2_eval):
        payload = {
            "properties": {
                "type": "code_eval",
                "code": "def score(output, **kwargs):\n    return {'accuracy': 1.0}\n",
            },
            "eval_input": {
                "final_message": "test",
            },
        }
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["scores"] == {}
        assert body["skipped_reason"] == "code_eval_not_trusted"
        assert body["skipped_detail"] == "Project not trusted for code eval execution."

    def test_code_eval_trusted_execution(self, client, mock_v2_eval):
        payload = {
            "properties": {
                "type": "code_eval",
                "code": "def score(output, **kwargs):\n    return {'accuracy': 1.0}\n",
            },
            "eval_input": {
                "final_message": "test",
            },
        }
        with (
            patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid,
            patch(
                "kiln_ai.adapters.eval.v2_eval_code_eval.is_code_eval_trusted",
                return_value=True,
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer",
                return_value={"ok": {"accuracy": 0.75}},
            ),
        ):
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["scores"]["accuracy"] == 0.75
        assert body["skipped_reason"] is None

    def test_llm_judge_with_mocked_model(self, client, mock_v2_eval):
        payload = {
            "properties": {
                "type": "llm_judge",
                "model_name": "gpt-4o",
                "model_provider": "openai",
                "prompt_template": "Is this correct? Output: {{ final_message }}",
            },
            "eval_input": {
                "final_message": "test output",
            },
        }
        mock_run_output = RunOutput(
            output={"accuracy": 5},
            intermediate_outputs=None,
        )
        mock_adapter = MagicMock()
        mock_adapter.invoke_returning_run_output = AsyncMock(
            return_value=(None, mock_run_output)
        )
        with (
            patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid,
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task",
                return_value=mock_adapter,
            ),
        ):
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert "accuracy" in body["scores"]
        assert body["skipped_reason"] is None

    def test_nothing_persisted(self, client, mock_v2_eval):
        eval_dir = mock_v2_eval.path.parent
        files_before = set(str(f) for f in eval_dir.rglob("*"))

        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            client.post(self._url(), json=self._exact_match_payload())

        files_after = set(str(f) for f in eval_dir.rglob("*"))
        new_files = files_after - files_before
        assert len(new_files) == 0, f"Unexpected new files created: {new_files}"

    def test_eval_not_found(self, client):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.side_effect = HTTPException(
                status_code=404, detail="Eval not found. ID: bad_id"
            )
            response = client.post(
                self._url("bad_id"),
                json=self._exact_match_payload(),
            )
        assert response.status_code == 404

    def test_llm_judge_builder_input(self, client, mock_v2_eval):
        payload = {
            "llm_judge_builder_input": {
                "model_name": "gpt-4o",
                "provider": "openai",
                "g_eval": False,
            },
            "eval_input": {
                "final_message": "test output",
            },
        }
        mock_run_output = RunOutput(
            output={"accuracy": 5},
            intermediate_outputs=None,
        )
        mock_adapter = MagicMock()
        mock_adapter.invoke_returning_run_output = AsyncMock(
            return_value=(None, mock_run_output)
        )
        with (
            patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid,
            patch(
                "app.desktop.studio_server.eval_api.materialize_llm_judge_properties"
            ) as mock_materialize,
            patch(
                "kiln_ai.adapters.eval.v2_eval_llm_judge.adapter_for_task",
                return_value=mock_adapter,
            ),
        ):
            mock_materialize.return_value = {
                "type": "llm_judge",
                "model_name": "gpt-4o",
                "model_provider": "openai",
                "g_eval": False,
                "prompt_template": "test template {{ final_message }}",
            }
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        mock_materialize.assert_called_once_with(
            eval=mock_v2_eval,
            model_name="gpt-4o",
            model_provider="openai",
            g_eval=False,
            judge_prompt=None,
            system_prompt=None,
        )
        body = response.json()
        assert "accuracy" in body["scores"]
        assert body["skipped_reason"] is None

    def test_400_when_no_properties_or_builder_input(self, client, mock_v2_eval):
        payload = {
            "eval_input": {
                "final_message": "test output",
            },
        }
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 400
        body = response.json()
        msg = (body.get("message") or body.get("detail") or "").lower()
        assert "properties" in msg or "llm_judge" in msg

    def test_score_range_errors_none_for_in_range(self, client, mock_v2_eval):
        """In-range scores should NOT produce score_range_errors."""
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json=self._exact_match_payload(),
            )
        assert response.status_code == 200
        body = response.json()
        assert body["scores"]["accuracy"] == 1.0
        assert body["score_range_errors"] is None

    def test_score_range_errors_populated_for_out_of_range(self, client, mock_v2_eval):
        """Out-of-range scores should populate score_range_errors."""
        payload = {
            "properties": {
                "type": "code_eval",
                "code": "def score(output, **kwargs):\n    return {'accuracy': 5.0}\n",
            },
            "eval_input": {
                "final_message": "test",
            },
        }
        with (
            patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid,
            patch(
                "kiln_ai.adapters.eval.v2_eval_code_eval.is_code_eval_trusted",
                return_value=True,
            ),
            patch(
                "kiln_ai.adapters.eval.v2_eval_code_eval.run_scorer",
                return_value={"ok": {"accuracy": 5.0}},
            ),
        ):
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["scores"]["accuracy"] == 5.0
        assert body["score_range_errors"] is not None
        assert len(body["score_range_errors"]) == 1
        assert "pass_fail" in body["score_range_errors"][0]

    def test_score_range_errors_none_when_skipped(self, client, mock_v2_eval):
        """Skipped results should not have score_range_errors."""
        payload = {
            "properties": {
                "type": "code_eval",
                "code": "def score(output, **kwargs):\n    return {'accuracy': 1.0}\n",
            },
            "eval_input": {
                "final_message": "test",
            },
        }
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(self._url(), json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["skipped_reason"] == "code_eval_not_trusted"
        assert body["score_range_errors"] is None


class TestCreateLlmJudgeConfig:
    def _url(self, eval_id: str = "eval_v2") -> str:
        return f"/api/projects/project1/tasks/task1/evals/{eval_id}/create_llm_judge_config"

    def test_success(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["config_type"] == "v2"
        props = body["properties"]
        assert props["type"] == "llm_judge"
        assert props["model_name"] == "gpt-4o"
        assert props["model_provider"] == "openai"
        assert props["g_eval"] is False
        assert "{{ task_input }}" in props["prompt_template"]
        assert "{{ final_message }}" in props["prompt_template"]
        assert props["system_prompt"] is not None
        assert props["thinking_instruction"] is not None
        assert props["reference_keys"] == []

    def test_g_eval_true(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": True,
                },
            )
        assert response.status_code == 200
        assert response.json()["properties"]["g_eval"] is True

    def test_persisted_to_disk(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                },
            )
        configs = mock_v2_eval.configs()
        assert len(configs) == 1
        cfg = configs[0]
        assert cfg.config_type.value == "v2"
        assert cfg.properties.type.value == "llm_judge"

    def test_eval_not_found(self, client):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.side_effect = HTTPException(
                status_code=404, detail="Eval not found. ID: bad_id"
            )
            response = client.post(
                self._url("bad_id"),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                },
            )
        assert response.status_code == 404

    def test_missing_model(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "g_eval": False,
                },
            )
        assert response.status_code == 422

    def test_with_custom_name(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "name": "My Custom Judge",
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                },
            )
        assert response.status_code == 200
        assert response.json()["name"] == "My Custom Judge"


class TestV1CoexistenceAPI:
    """V1 coexistence regression guards at the API layer.

    Ensures that V1 g_eval / llm_as_judge configs and their runs continue to
    work through score-summary and eval-results endpoints after V2 additions.
    """

    def test_v1_g_eval_score_summary(
        self,
        client,
        mock_task_from_id,
        mock_task,
        mock_eval,
        mock_eval_config,
        mock_run_config,
    ):
        mock_task_from_id.return_value = mock_task

        run = EvalRun(
            parent=mock_eval_config,
            dataset_id="dataset_id1",
            task_run_config_id="run_config1",
            input="test input",
            output="test output",
            scores={"score1": 4.0, "overall_rating": 3.0},
        )
        run.save_to_file()

        run2 = EvalRun(
            parent=mock_eval_config,
            dataset_id="dataset_id2",
            task_run_config_id="run_config1",
            input="test input 2",
            output="test output 2",
            scores={"score1": 2.0, "overall_rating": 5.0},
        )
        run2.save_to_file()

        with (
            patch(
                "app.desktop.studio_server.eval_api.dataset_ids_in_filter"
            ) as mock_ds_filter,
        ):
            mock_ds_filter.return_value = {"dataset_id1", "dataset_id2"}

            response = client.get(
                "/api/projects/project1/tasks/task1/evals/eval1"
                "/eval_config/eval_config1/score_summary"
            )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert "dataset_size" in body
        assert body["dataset_size"] == 2

        scores = body["results"]["run_config1"]
        assert scores["score1"]["mean_score"] == pytest.approx(3.0)
        assert scores["score1"]["n_used"] == 2
        assert scores["score1"]["n_excluded"] == 0
        assert scores["overall_rating"]["mean_score"] == pytest.approx(4.0)

        assert body["run_config_percent_complete"]["run_config1"] == 1.0

    def test_v1_g_eval_run_results(
        self,
        client,
        mock_task_from_id,
        mock_task,
        mock_eval,
        mock_eval_config,
        mock_run_config,
    ):
        mock_task_from_id.return_value = mock_task

        run = EvalRun(
            parent=mock_eval_config,
            task_run_config_id="run_config1",
            scores={"score1": 3.5, "overall_rating": 4.0},
            input="hello",
            output="world",
            dataset_id="ds1",
        )
        run.save_to_file()

        response = client.get(
            "/api/projects/project1/tasks/task1/evals/eval1"
            "/eval_config/eval_config1/run_config/run_config1/results"
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "eval" in data
        assert "eval_config" in data
        assert "run_config" in data

        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["scores"] == {"score1": 3.5, "overall_rating": 4.0}
        assert result["dataset_id"] == "ds1"
        assert result["task_run_config_id"] == "run_config1"
        assert result["input"] == "hello"
        assert result["output"] == "world"

        for v2_field in (
            "eval_input_id",
            "reference_data",
            "skipped_reason",
            "skipped_detail",
        ):
            assert v2_field in result
            assert result[v2_field] is None

    def test_v1_llm_as_judge_config_accepted(
        self,
        mock_eval,
    ):
        config = EvalConfig(
            name="LLM Judge V1",
            config_type=EvalConfigType.llm_as_judge,
            model_name="gpt-4",
            model_provider="openai",
            properties={"eval_steps": ["judge step"]},
            parent=mock_eval,
        )
        config.save_to_file()

        loaded = EvalConfig.load_from_file(str(config.path))
        assert loaded.config_type == EvalConfigType.llm_as_judge
        assert isinstance(loaded.properties, dict)
        assert loaded.properties["eval_steps"] == ["judge step"]
        assert loaded.model_name == "gpt-4"
        assert loaded.model_provider == "openai"

    def test_v1_score_summary_with_v2_optional_fields_on_runs(
        self,
        mock_eval_for_score_summary,
    ):
        config = Mock(spec=EvalConfig)

        runs = [
            EvalRun(
                task_run_config_id="rc1",
                scores={"accuracy": 0.9, "relevance": 0.8},
                input="input1",
                output="output1",
                dataset_id="ds1",
            ),
            EvalRun(
                task_run_config_id="rc1",
                scores={"accuracy": 0.7, "relevance": 0.6},
                input="input2",
                output="output2",
                dataset_id="ds2",
            ),
        ]
        for r in runs:
            assert r.eval_input_id is None
            assert r.reference_data is None
            assert r.skipped_reason is None

        config.runs.return_value = runs

        task_run_configs = [Mock(spec=TaskRunConfig, id="rc1")]
        expected_dataset_ids: set[ID_TYPE] = {"ds1", "ds2"}

        result = compute_score_summary(
            mock_eval_for_score_summary, config, task_run_configs, expected_dataset_ids
        )

        assert result.dataset_size == 2
        scores = result.results["rc1"]
        assert scores["accuracy"].mean_score == pytest.approx(0.8)
        assert scores["accuracy"].n_used == 2
        assert scores["accuracy"].n_excluded == 0
        assert scores["relevance"].mean_score == pytest.approx(0.7)
        assert scores["relevance"].n_used == 2
        assert scores["relevance"].n_excluded == 0


class TestDefaultLlmJudgePrompt:
    def _url(self, eval_id: str = "eval_v2") -> str:
        return f"/api/projects/project1/tasks/task1/evals/{eval_id}/default_llm_judge_prompt"

    def test_returns_rich_prompt(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.get(self._url())
        assert response.status_code == 200
        body = response.json()
        assert "judge_prompt" in body
        assert "system_prompt" in body
        assert body["system_prompt"] == "You are an evaluator."
        assert "{{ task_input }}" in body["judge_prompt"]
        assert "{{ final_message }}" in body["judge_prompt"]
        assert "Is the answer accurate?" in body["judge_prompt"]

    def test_eval_not_found(self, client):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.side_effect = HTTPException(
                status_code=404, detail="Eval not found. ID: bad_id"
            )
            response = client.get(self._url("bad_id"))
        assert response.status_code == 404


class TestCreateLlmJudgeConfigOverrides:
    def _url(self, eval_id: str = "eval_v2") -> str:
        return f"/api/projects/project1/tasks/task1/evals/{eval_id}/create_llm_judge_config"

    def test_with_judge_prompt_override(self, client, mock_v2_eval):
        custom_prompt = "Custom {{ task_input }} {{ final_message }}"
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                    "judge_prompt": custom_prompt,
                },
            )
        assert response.status_code == 200
        props = response.json()["properties"]
        assert props["prompt_template"] == custom_prompt

    def test_with_system_prompt_override(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                    "system_prompt": "Be very strict.",
                },
            )
        assert response.status_code == 200
        assert response.json()["properties"]["system_prompt"] == "Be very strict."

    def test_empty_judge_prompt_uses_default(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                    "judge_prompt": "   ",
                },
            )
        assert response.status_code == 200
        props = response.json()["properties"]
        assert "<steps>" in props["prompt_template"]

    def test_invalid_jinja_returns_400(self, client, mock_v2_eval):
        with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid:
            mock_eid.return_value = mock_v2_eval
            response = client.post(
                self._url(),
                json={
                    "model_name": "gpt-4o",
                    "provider": "openai",
                    "g_eval": False,
                    "judge_prompt": "{% invalid %}",
                },
            )
        assert response.status_code == 400


class TestTestV2EvalOverrides:
    def _url(self, eval_id: str = "eval_v2") -> str:
        return f"/api/projects/project1/tasks/task1/evals/{eval_id}/test_v2_eval"

    def test_llm_judge_builder_passes_overrides(self, client, mock_v2_eval):
        with (
            patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eid,
            patch(
                "app.desktop.studio_server.eval_api.materialize_llm_judge_properties"
            ) as mock_mat,
            patch(
                "app.desktop.studio_server.eval_api.v2_eval_adapter_from_config"
            ) as mock_adapter_factory,
        ):
            mock_eid.return_value = mock_v2_eval

            from kiln_ai.datamodel.eval import LlmJudgeProperties

            mock_mat.return_value = LlmJudgeProperties(
                model_name="gpt-4o",
                model_provider="openai",
                prompt_template="Custom {{ task_input }} {{ final_message }}",
                system_prompt="Be strict.",
                thinking_instruction="Think.",
                g_eval=False,
            )

            from kiln_ai.datamodel.eval import V2EvalResult

            mock_adapter = MagicMock()
            mock_adapter.evaluate = AsyncMock(
                return_value=V2EvalResult(scores={"accuracy": 1.0})
            )
            mock_adapter_factory.return_value = mock_adapter

            response = client.post(
                self._url(),
                json={
                    "eval_input": {
                        "final_message": "test output",
                        "task_input": "test input",
                    },
                    "llm_judge_builder_input": {
                        "model_name": "gpt-4o",
                        "provider": "openai",
                        "g_eval": False,
                        "judge_prompt": "Custom {{ task_input }} {{ final_message }}",
                        "system_prompt": "Be strict.",
                    },
                },
            )
        assert response.status_code == 200
        mock_mat.assert_called_once()
        call_kwargs = mock_mat.call_args
        assert (
            call_kwargs.kwargs["judge_prompt"]
            == "Custom {{ task_input }} {{ final_message }}"
        )
        assert call_kwargs.kwargs["system_prompt"] == "Be strict."
