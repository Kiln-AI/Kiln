import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_server.custom_errors import connect_custom_errors
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.utils.config import Config

from app.desktop.studio_server.repair_api import (
    RepairRunPost,
    RepairTaskApiInput,
    connect_repair_api,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_custom_errors(app)
    connect_repair_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def data_source():
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "gpt_4o",
            "model_provider": "openai",
            "adapter_name": "langchain_adapter",
            "prompt_id": "simple_prompt_builder",
        },
    )


@pytest.fixture
def project(tmp_path) -> Project:
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()
    return project


@pytest.fixture
def improvement_task(project) -> Task:
    task = Task(name="Test Task", instruction="Test Instruction", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def improvement_task_run(data_source, improvement_task):
    task_run = TaskRun(
        input="Test Input",
        input_source=data_source,
        parent=improvement_task,
        output=TaskOutput(output="Test Output", source=data_source),
    )
    task_run.save_to_file()

    return task_run


@pytest.fixture
def mock_repair_task_run(improvement_task, data_source):
    return TaskRun(
        output=TaskOutput(
            output="Test Output",
            source=data_source,
        ),
        input="The input to the improvement task",
        input_source=data_source,
    )


@pytest.fixture
def mock_repair_task_run_human_edited(improvement_task, data_source):
    return TaskRun(
        output=TaskOutput(
            output="Test Output",
            source={
                "type": "human",
                "properties": {
                    "created_by": "placeholder_user_id",
                },
            },
        ),
        input="The input to the improvement task",
        input_source=data_source,
    )


@pytest.fixture
def mock_langchain_adapter(mock_repair_task_run):
    with patch("app.desktop.studio_server.repair_api.adapter_for_task") as mock:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock()
        mock.return_value = mock_adapter

        mock_adapter.invoke.return_value = mock_repair_task_run

        yield mock_adapter


@pytest.fixture
def mock_run_and_task(improvement_task, improvement_task_run):
    with patch("app.desktop.studio_server.repair_api.task_and_run_from_id") as mock:
        mock.return_value = (improvement_task, improvement_task_run)
        yield mock


def test_repair_run_success(
    mock_run_and_task,
    mock_langchain_adapter,
    client,
    improvement_task,
    mock_repair_task_run,
):
    # Arrange
    input_data = RepairTaskApiInput(evaluator_feedback="Fix this issue")

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/generate_repair",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 200
    res = response.json()
    repaired_output = res["output"]
    assert TaskOutput.model_validate(repaired_output) == mock_repair_task_run.output
    mock_langchain_adapter.invoke.assert_awaited_once()


def test_save_repair_success(
    mock_run_and_task,
    mock_langchain_adapter,
    client,
    improvement_task,
    mock_repair_task_run,
):
    # Arrange
    input_data = RepairRunPost(
        repair_run=mock_repair_task_run.model_dump(),
        evaluator_feedback="Fix this issue",
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/save_repair",
        json=json.loads(input_data.model_dump_json()),
    )

    # Assert
    res = response.json()
    assert response.status_code == 200
    repaired_output = res["repaired_output"]
    assert TaskOutput.model_validate(repaired_output) == mock_repair_task_run.output
    assert res["repair_instructions"] == "Fix this issue"
    assert res["input"] == "Test Input"

    # Verify that the run was updated in the file system
    updated_run = improvement_task.runs()[0]
    assert updated_run.repair_instructions == "Fix this issue"
    assert updated_run.repaired_output == mock_repair_task_run.output


def test_repair_run_missing_model_info(
    mock_run_and_task,
    mock_langchain_adapter,
    client,
    improvement_task,
    mock_repair_task_run,
):
    # Arrange
    input_data = RepairTaskApiInput(evaluator_feedback="Fix this issue")
    mock_run_and_task.return_value[1].output.source.properties["model_name"] = None
    mock_run_and_task.return_value[1].output.source.properties["model_provider"] = None

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/generate_repair",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 422
    assert response.json()["message"] == "Model name and provider must be specified."


def test_repair_run_human_source(
    mock_run_and_task,
    mock_langchain_adapter,
    client,
    improvement_task,
    mock_repair_task_run_human_edited,
):
    # Arrange
    input_data = RepairRunPost(
        repair_run=mock_repair_task_run_human_edited.model_dump(),
        evaluator_feedback="Fix this issue",
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/save_repair",
        json=json.loads(input_data.model_dump_json()),
    )

    # Assert
    assert response.status_code == 200
    res = response.json()

    # source must be set and the created_by must be set to the user id
    repaired_output = res["repaired_output"]
    assert repaired_output["source"] is not None
    assert repaired_output["source"]["properties"] is not None
    assert (
        repaired_output["source"]["properties"]["created_by"] == Config.shared().user_id
    )


def test_repair_run_with_model_override(
    mock_run_and_task,
    client,
    improvement_task,
    mock_repair_task_run,
):
    """The caller can override which model generates the repair by sending model_name/provider."""
    with patch("app.desktop.studio_server.repair_api.adapter_for_task") as mock:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=mock_repair_task_run)
        mock.return_value = mock_adapter

        response = client.post(
            "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/generate_repair",
            json={
                "evaluator_feedback": "Fix this issue",
                "model_name": "llama_3_1_8b",
                "provider": "groq",
            },
        )

        assert response.status_code == 200
        # The run config that built the adapter must reflect the override, not the
        # (mock) original run's "gpt_4o" / "openai".
        run_config = mock.call_args.kwargs["run_config_properties"]
        assert run_config.model_name == "llama_3_1_8b"
        assert run_config.model_provider_name == "groq"


def test_repair_run_override_requires_both_fields(
    mock_run_and_task,
    mock_langchain_adapter,
    client,
):
    """Sending only one of model_name/provider is rejected."""
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/generate_repair",
        json={"evaluator_feedback": "Fix this issue", "model_name": "llama_3_1_8b"},
    )
    assert response.status_code == 422
    assert "must be set together" in response.json()["message"]


def test_repair_run_override_rederives_structured_output_mode(
    mock_run_and_task,
    client,
    mock_repair_task_run,
):
    """When a different model is chosen, structured_output_mode should be derived
    from the new model's defaults, not the original run's mode (which may be
    incompatible with the new model)."""
    # Original run was saved with json_schema mode.
    mock_run_and_task.return_value[1].output.source.properties[
        "structured_output_mode"
    ] = "json_schema"

    sentinel_mode = StructuredOutputMode.function_calling
    with (
        patch("app.desktop.studio_server.repair_api.adapter_for_task") as mock,
        patch(
            "app.desktop.studio_server.repair_api.default_structured_output_mode_for_model_provider",
            return_value=sentinel_mode,
        ) as mock_default_sdm,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=mock_repair_task_run)
        mock.return_value = mock_adapter

        response = client.post(
            "/api/projects/proj-ID/tasks/task-ID/runs/run-ID/generate_repair",
            json={
                "evaluator_feedback": "Fix",
                "model_name": "llama_3_1_8b",
                "provider": "groq",
            },
        )
        assert response.status_code == 200
        # The lookup must be called with the override model/provider (not the
        # original run's gpt_4o/openai), and its result must be the mode used —
        # proving we didn't blindly forward the original "json_schema".
        mock_default_sdm.assert_called_once_with("llama_3_1_8b", ModelProviderName.groq)
        run_config = mock.call_args.kwargs["run_config_properties"]
        assert run_config.structured_output_mode == sentinel_mode
