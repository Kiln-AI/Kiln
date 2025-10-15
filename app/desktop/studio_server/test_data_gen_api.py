from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Project,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import RunConfigProperties

from app.desktop.studio_server.data_gen_api import (
    DataGenCategoriesApiInput,
    DataGenSampleApiInput,
    DataGenSaveSamplesApiInput,
    connect_data_gen_api,
    topic_path_from_string,
    topic_path_to_string,
)


@pytest.fixture
def app():
    app = FastAPI()
    connect_data_gen_api(app)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def data_source():
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "gpt-4",
            "model_provider": "openai",
            "adapter_name": "langchain_adapter",
        },
    )


@pytest.fixture
def test_task(tmp_path) -> Task:
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()

    task = Task(name="Test Task", instruction="Test Instruction", parent=project)
    task.save_to_file()
    return task


@pytest.fixture
def mock_task_run(data_source, test_task):
    return TaskRun(
        output=TaskOutput(
            output="Test Output",
            source=data_source,
        ),
        input="Test Input",
        input_source=data_source,
        parent=test_task,
    )


@pytest.fixture
def mock_langchain_adapter(mock_task_run):
    with patch("app.desktop.studio_server.data_gen_api.adapter_for_task") as mock:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock()
        mock.return_value = mock_adapter

        mock_adapter.invoke.return_value = mock_task_run

        yield mock_adapter


@pytest.fixture
def mock_task_from_id(test_task):
    with patch("app.desktop.studio_server.data_gen_api.task_from_id") as mock:
        mock.return_value = test_task
        yield mock


def test_generate_categories_success(
    mock_task_from_id,
    mock_langchain_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenCategoriesApiInput(
        node_path=["parent", "child"],
        num_subtopics=4,
        guidance="Generate tech categories",
        gen_type="eval",
        model_name="gpt-4",
        provider="openai",
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_categories",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 200
    res = response.json()
    assert TaskOutput.model_validate(res["output"]) == mock_task_run.output
    mock_langchain_adapter.invoke.assert_awaited_once()


def test_generate_samples_success(
    mock_task_from_id,
    mock_langchain_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenSampleApiInput(
        topic=["technology", "AI"],
        gen_type="training",
        guidance="Make long samples",
        model_name="gpt-4",
        provider="openai",
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_inputs",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 200
    res = response.json()
    assert TaskOutput.model_validate(res["output"]) == mock_task_run.output
    mock_langchain_adapter.invoke.assert_awaited_once()


@pytest.mark.paid
def test_save_sample_success_paid_run(
    mock_task_from_id,
    client,
    test_task,
):
    # Arrange
    input_data = DataGenSaveSamplesApiInput(
        input="Test sample input",
        input_model_name="gpt_4o",
        input_provider="openai",
        output_run_config_properties=RunConfigProperties(
            model_name="gpt_4o_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        topic_path=[],  # No topic path
        tags=["test_tag"],
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/save_sample",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 200
    # Verify TaskRun was created with correct properties
    mock_task_from_id.assert_called_once_with("proj-ID", "task-ID")
    saved_runs = test_task.runs()
    assert len(saved_runs) == 1
    saved_run = saved_runs[0]

    assert saved_run.input == "Test sample input"
    assert saved_run.input_source.type == DataSourceType.synthetic
    properties = saved_run.input_source.properties
    assert properties == {
        "model_name": "gpt_4o",
        "model_provider": "openai",
        "adapter_name": "kiln_data_gen",
    }
    assert "topic_path" not in properties

    assert saved_run.output.source.type == DataSourceType.synthetic
    assert saved_run.output.source.properties["model_name"] == "gpt_4o_mini"
    assert saved_run.output.source.properties["model_provider"] == "openai"
    assert "test_tag" in saved_run.tags

    # Confirm the response contains same run
    assert response.json()["id"] == saved_run.id

    return


def test_generate_sample_success_with_mock_invoke(
    mock_task_from_id,
    mock_langchain_adapter,
    client,
    mock_task_run,
    test_task,
):
    # Arrange
    input_data = DataGenSaveSamplesApiInput(
        input="Test sample input",
        input_model_name="gpt_4o",
        input_provider="openai",
        output_run_config_properties=RunConfigProperties(
            model_name="gpt_4o_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
        topic_path=["AI", "Machine Learning", "Deep Learning"],
        tags=["test_tag"],
    )

    # Act

    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_sample?session_id=1234",
        json=input_data.model_dump(),
    )

    mock_langchain_adapter.invoke.assert_awaited_once()
    invoke_args = mock_langchain_adapter.invoke.await_args[1]
    assert invoke_args["input"] == "Test sample input"
    assert invoke_args["input_source"].type == DataSourceType.synthetic
    properties = invoke_args["input_source"].properties
    assert properties == {
        "model_name": "gpt_4o",
        "model_provider": "openai",
        "adapter_name": "kiln_data_gen",
        "topic_path": "AI>>>>>Machine Learning>>>>>Deep Learning",
    }

    # Assert
    assert response.status_code == 200
    # Verify TaskRun was created with correct properties
    mock_task_from_id.assert_called_once_with("proj-ID", "task-ID")

    # Check none are saved before calling save
    saved_runs = test_task.runs()
    assert len(saved_runs) == 0

    # Call save
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/save_sample",
        json=response.json(),
    )
    assert response.status_code == 200

    # Check one is saved after calling save
    saved_runs = test_task.runs()
    assert len(saved_runs) == 1
    saved_run = saved_runs[0]
    assert saved_run.input_source.type == DataSourceType.synthetic
    # Not checking values since we mock them. We check it's called with correct properties above
    assert saved_run.output == mock_task_run.output
    assert saved_run.output.source.type == DataSourceType.synthetic
    assert "test_tag" in saved_run.tags
    assert "synthetic" in saved_run.tags
    assert "synthetic_session_1234" in saved_run.tags

    assert saved_run.output.source.properties == mock_task_run.input_source.properties

    # Confirm the response contains same run
    assert response.json()["id"] == saved_run.id


def test_generate_sample_success_with_topic_path(
    mock_task_from_id,
    mock_langchain_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenSaveSamplesApiInput(
        input="Test sample input",
        topic_path=["AI", "Machine Learning", "Deep Learning"],
        input_model_name="gpt_4o",
        input_provider="openai",
        output_run_config_properties=RunConfigProperties(
            model_name="gpt_4o_mini",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    )

    # Act
    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_sample",
        json=input_data.model_dump(),
    )

    # Assert
    assert response.status_code == 200
    invoke_args = mock_langchain_adapter.invoke.await_args[1]
    assert (
        invoke_args["input_source"].properties["topic_path"]
        == "AI>>>>>Machine Learning>>>>>Deep Learning"
    )
    parsed_path = topic_path_from_string(
        invoke_args["input_source"].properties["topic_path"]
    )
    assert parsed_path == ["AI", "Machine Learning", "Deep Learning"]


def test_topic_path_conversions():
    # Test empty path
    assert topic_path_to_string([]) is None
    assert topic_path_from_string(None) == []
    assert topic_path_from_string("") == []

    # Test non-empty path
    test_path = ["AI", "Machine Learning", "Deep Learning"]
    path_string = topic_path_to_string(test_path)
    assert path_string == "AI>>>>>Machine Learning>>>>>Deep Learning"
    assert topic_path_from_string(path_string) == test_path

    # Test single item path
    assert topic_path_to_string(["AI"]) == "AI"
    assert topic_path_from_string("AI") == ["AI"]


@pytest.mark.parametrize(
    "guidance,topic_path,initial_instruction,expected_wrapped_call,expected_final_instruction,should_call_wrap",
    [
        # Test 1: Only guidance provided (no topic path)
        (
            "Custom guidance for generation",
            [],
            "Test Instruction",
            "Custom guidance for generation",
            "wrapped_instruction",
            True,
        ),
        # Test 2: Only topic path provided (no guidance)
        (
            None,
            ["AI", "Machine Learning"],
            "Original instruction",
            """
## Topic Path
The topic path for this sample is:
["AI", "Machine Learning"]
""",
            "wrapped_instruction_with_topic",
            True,
        ),
        # Test 3: Both guidance and topic path provided
        (
            "Focus on technical accuracy",
            ["Technology", "AI"],
            "Original instruction",
            """Focus on technical accuracy
## Topic Path
The topic path for this sample is:
["Technology", "AI"]
""",
            "wrapped_instruction_combined",
            True,
        ),
        # Test 4: Neither guidance nor topic path provided
        (
            None,
            [],
            "Original instruction",
            None,  # Won't be called
            "Original instruction",  # Should remain unchanged
            False,
        ),
        # Test 5: Empty guidance string (should be treated as no guidance)
        (
            "",
            [],
            "Original instruction",
            None,  # Won't be called
            "Original instruction",  # Should remain unchanged
            False,
        ),
    ],
    ids=[
        "only_guidance",
        "only_topic_path",
        "both_guidance_and_topic_path",
        "neither_guidance_nor_topic_path",
        "empty_guidance",
    ],
)
def test_generate_sample_guidance_generation(
    mock_task_from_id,
    mock_langchain_adapter,
    client,
    mock_task_run,
    test_task,
    guidance,
    topic_path,
    initial_instruction,
    expected_wrapped_call,
    expected_final_instruction,
    should_call_wrap,
):
    """Test that guidance is properly generated and applied in save_sample function"""
    from unittest.mock import patch

    with patch(
        "app.desktop.studio_server.data_gen_api.wrap_task_with_guidance"
    ) as mock_wrap:
        # Set up the mock return value and initial task instruction
        mock_wrap.return_value = expected_final_instruction
        test_task.instruction = initial_instruction

        input_data = DataGenSaveSamplesApiInput(
            input="Test input",
            input_model_name="gpt-4",
            input_provider="openai",
            output_run_config_properties=RunConfigProperties(
                model_name="gpt-4",
                model_provider_name=ModelProviderName.openai,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            topic_path=topic_path,
            guidance=guidance,
        )

        response = client.post(
            "/api/projects/proj-ID/tasks/task-ID/generate_sample",
            json=input_data.model_dump(),
        )

        assert response.status_code == 200

        if should_call_wrap:
            # Verify wrap_task_with_guidance was called with expected parameters
            mock_wrap.assert_called_once_with(
                initial_instruction, expected_wrapped_call
            )
        else:
            # Verify wrap_task_with_guidance was NOT called
            mock_wrap.assert_not_called()

        # Verify task instruction final state
        assert test_task.instruction == expected_final_instruction
