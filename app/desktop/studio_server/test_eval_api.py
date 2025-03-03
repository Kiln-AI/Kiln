import json
from dataclasses import dataclass
from typing import Dict, List, Tuple
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel import (
    BasePrompt,
    DataSource,
    DataSourceType,
    Priority,
    Project,
    RequirementRating,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskRequirement,
    TaskRun,
)
from kiln_ai.datamodel.eval import (
    Eval,
    EvalConfig,
    EvalConfigType,
    EvalOutputScore,
    EvalRun,
    EvalTemplateId,
)
from kiln_ai.datamodel.task import RunConfigProperties, TaskRunConfig

from app.desktop.studio_server.eval_api import (
    CreateEvalConfigRequest,
    CreateEvaluatorRequest,
    connect_evals_api,
    eval_config_from_id,
    task_run_config_from_id,
)


@pytest.fixture
def app():
    app = FastAPI()
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
                type="five_star",
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
            EvalOutputScore(name="score1", description="desc1", type="five_star"),
            EvalOutputScore(
                name="overall_rating", description="desc2", type="five_star"
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
        prompt=BasePrompt(
            name="test",
            prompt="base prompt",
            chain_of_thought_instructions="cot prompt",
        ),
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
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name="openai",
            prompt_id="simple_chain_of_thought_prompt_builder",
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

    response = client.get("/api/projects/project1/tasks/task1/eval/eval1")

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "eval1"
    assert result["name"] == "Test Eval"
    mock_task_from_id.assert_called_once_with("project1", "task1")


def test_get_eval_not_found(client, mock_task, mock_task_from_id):
    mock_task_from_id.return_value = mock_task

    response = client.get("/api/projects/project1/tasks/task1/eval/non_existent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Eval not found. ID: non_existent"


@pytest.fixture
def valid_evaluator_request():
    return CreateEvaluatorRequest(
        name="Test Evaluator",
        description="Test Description",
        template=None,
        output_scores=[
            EvalOutputScore(name="score1", description="desc1", type="five_star"),
        ],
        eval_set_filter_id="tag::eval_set",
        eval_configs_filter_id="tag::golden",
    )


@pytest.fixture
def valid_eval_config_request():
    return CreateEvalConfigRequest(
        name="Test Eval Config",
        type=EvalConfigType.g_eval,
        properties={"eval_steps": ["step1", "step2"]},
        model_name="gpt-4",
        provider=ModelProviderName.openai,
        prompt_id="simple_chain_of_thought_prompt_builder",
    )


@pytest.mark.asyncio
async def test_create_evaluator(
    client, mock_task_from_id, valid_evaluator_request, mock_task
):
    mock_task_from_id.return_value = mock_task

    with patch.object(Eval, "save_to_file") as mock_save:
        response = client.post(
            "/api/projects/project1/tasks/task1/create_evaluator",
            json=valid_evaluator_request.model_dump(),
        )

    assert response.status_code == 200
    result = response.json()
    assert result["name"] == valid_evaluator_request.name
    assert result["description"] == valid_evaluator_request.description
    mock_save.assert_called_once()


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
            "/api/projects/project1/tasks/task1/task_run_config",
            json={
                "name": "Test Task Run Config",
                "description": "Test Description",
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "simple_chain_of_thought_prompt_builder",
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
    assert result["prompt"]["name"] == "Custom Name"
    assert (
        result["prompt"]["description"]
        == "Frozen copy of prompt 'simple_chain_of_thought_prompt_builder', created for evaluations."
    )
    # Fetch it from API
    fetch_response = client.get("/api/projects/project1/tasks/task1/task_run_configs")
    assert fetch_response.status_code == 200
    configs = fetch_response.json()
    assert len(configs) == 1
    assert configs[0]["id"] == result["id"]
    assert configs[0]["name"] == result["name"]
    assert configs[0]["prompt"]["name"] == "Custom Name"
    assert configs[0]["prompt"]["description"] == (
        "Frozen copy of prompt 'simple_chain_of_thought_prompt_builder', created for evaluations."
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
            "/api/projects/project1/tasks/task1/task_run_config",
            json={
                "name": "Test Task Run Config",
                "description": "Test Description",
                "model_name": "gpt-4o",
                "model_provider_name": "openai",
                "prompt_id": "id::prompt_123",
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
async def test_create_eval_config(
    client, mock_task_from_id, valid_eval_config_request, mock_eval, mock_task
):
    mock_task_from_id.return_value = mock_task

    with (
        patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id,
    ):
        mock_eval_from_id.return_value = mock_eval

        response = client.post(
            "/api/projects/project1/tasks/task1/eval/eval1/create_eval_config",
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


def test_get_eval_config(
    client, mock_task_from_id, mock_eval, mock_task, mock_eval_config
):
    mock_task_from_id.return_value = mock_task

    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.get(
            "/api/projects/project1/tasks/task1/eval/eval1/eval_config/eval_config1"
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
            "/api/projects/project1/tasks/task1/eval/eval1/eval_configs"
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
            "/api/projects/project1/tasks/task1/eval/eval1/eval_config/eval_config1/run_task_run_eval",
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
            "/api/projects/project1/tasks/task1/eval/eval1/eval_config/eval_config1/run_task_run_eval"
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]
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

    with pytest.raises(HTTPException, match="Eval config not found. ID: non_existent"):
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
        HTTPException, match="Task run config not found. ID: non_existent"
    ):
        task_run_config_from_id("project1", "task1", "non_existent")


@pytest.fixture
def mock_eval_for_score_summary():
    eval = Mock(spec=Eval)
    eval.output_scores = [
        EvalOutputScore(name="accuracy", description="Test accuracy", type="pass_fail"),
        EvalOutputScore(
            name="relevance", description="Test relevance", type="pass_fail"
        ),
    ]
    eval.eval_set_filter_id = "tag::eval_set"
    return eval


@pytest.fixture
def mock_eval_config_for_score_summary():
    config = Mock(spec=EvalConfig)

    scores: Tuple[str, str, Dict[str, float]] = [
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
        mock_task_from_id.return_value = mock_task

        response = client.get(
            "/api/projects/project1/tasks/task1/eval/eval1/eval_config/eval_config1/score_summary"
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
        assert results["run1"]["relevance"]["mean_score"] == 0.8  # Only one valid score
        assert run_config_percent_complete["run1"] == 1.0

        # Check average scores for run2
        assert results["run2"]["accuracy"]["mean_score"] == 0.9
        assert results["run2"]["relevance"]["mean_score"] == 0.85
        assert run_config_percent_complete["run2"] == 0.5

        # run 3 has non valid scores
        assert results["run3"] == {}
        assert run_config_percent_complete["run3"] == 0.0

        # run 4 has no scores
        assert results["run4"]["accuracy"]["mean_score"] == 0.5
        assert "relevance" not in results["run4"]
        assert run_config_percent_complete["run4"] == 0.0

        # Check average scores for run5 - duplicate dataset_id not double counted
        assert results["run5"]["accuracy"]["mean_score"] == 0.7  # (0.8 + 0.6) / 2
        assert results["run5"]["relevance"]["mean_score"] == 0.8  # Only one valid score
        assert run_config_percent_complete["run5"] == 1.0

        # Verify the mocks were called correctly
        mock_eval_from_id.assert_called_once_with("project1", "task1", "eval1")
        mock_eval_config_from_id.assert_called_once_with(
            "project1", "task1", "eval1", "eval_config1"
        )
        mock_eval_config_for_score_summary.runs.assert_called_once_with(readonly=True)
        mock_dataset_ids_in_filter.assert_called_once_with(mock_task, "tag::eval_set")


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
        "/api/projects/project1/tasks/task1/eval/eval1"
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
        "/api/projects/project1/tasks/task1/eval/invalid_eval"
        "/eval_config/eval_config1/run_config/run_config1/results"
    )
    assert response.status_code == 404

    # Test with invalid eval config ID
    response = client.get(
        "/api/projects/project1/tasks/task1/eval/eval1"
        "/eval_config/invalid_config/run_config/run_config1/results"
    )
    assert response.status_code == 404

    # Test with invalid run config ID
    response = client.get(
        "/api/projects/project1/tasks/task1/eval/eval1"
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

    # structed data to make it easier to generate test cases.
    @dataclass
    class EvalCondigSummaryTestData:
        human_overall_rating: float | None
        score1_overall_rating: float | None
        eval_overall_rating: float
        eval__score1_rating: float
        eval_config_id: str
        skip_eval_run: bool = False
        skip_golden_tag: bool = False

    test_data: List[EvalCondigSummaryTestData] = [
        # Test 1: ec1
        # Normal run, with some data to check calulations on a sinlgle run
        EvalCondigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=2.0,
            eval_overall_rating=1.0,
            eval__score1_rating=3.5,
            eval_config_id="ec1",
        ),
        # Should be ignored as it's not in the eval set filter (golden tag). Would mess up the scores of eval_config1 if included
        EvalCondigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=5.0,
            eval_overall_rating=4.0,
            eval__score1_rating=4.0,
            eval_config_id="ec1",
            skip_golden_tag=True,
        ),
        # Test 2: ec2 - Test multiple, and correct averaging
        EvalCondigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=5.0,
            eval_overall_rating=4.0,
            eval__score1_rating=4.0,
            eval_config_id="ec2",
        ),
        EvalCondigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=1.0,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec2",
        ),
        # Test 3: Dataset item that has partial human rating
        EvalCondigSummaryTestData(
            human_overall_rating=5.0,
            score1_overall_rating=None,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec3",
        ),
        # Test 4: Dataset item that has no human rating
        EvalCondigSummaryTestData(
            human_overall_rating=None,
            score1_overall_rating=None,
            eval_overall_rating=3.0,
            eval__score1_rating=3.0,
            eval_config_id="ec4",
        ),
        # Test 5: skipping eval run should lower the percent complete
        EvalCondigSummaryTestData(
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
                prompt=BasePrompt(
                    name="test",
                    prompt="base prompt",
                    chain_of_thought_instructions="cot prompt",
                ),
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
                type="five_star",
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
        "/api/projects/project1/tasks/task1/eval/eval1/eval_configs_score_summary"
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
            "/api/projects/project1/tasks/task1/eval/eval1/run_eval_config_eval"
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
    response = client.get("/api/projects/project1/tasks/task1/eval/eval1")
    assert response.status_code == 200
    eval_before = response.json()

    # The current_config_id might be None or different initially
    initial_config_id = eval_before.get("current_config_id")
    assert initial_config_id is None

    # Set the current eval config
    with patch("app.desktop.studio_server.eval_api.eval_from_id") as mock_eval_from_id:
        mock_eval_from_id.return_value = mock_eval
        response = client.post(
            "/api/projects/project1/tasks/task1/eval/eval1/set_current_eval_config/eval_config1"
        )
        assert response.status_code == 200
        updated_eval = response.json()

    # Verify the current_config_id was updated
    assert updated_eval["current_config_id"] == "eval_config1"
    assert updated_eval["id"] == "eval1"

    # Verify the change persists by fetching the eval again
    eval_from_disk = mock_task.evals()[0]
    assert eval_from_disk.current_config_id == "eval_config1"
