from unittest.mock import AsyncMock, MagicMock, patch

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
from kiln_ai.datamodel.extraction import Document
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import RunConfigProperties

from app.desktop.studio_server.data_gen_api import (
    DataGenCategoriesApiInput,
    DataGenQnaApiInput,
    DataGenSampleApiInput,
    DataGenSaveSamplesApiInput,
    SaveQnaPairInput,
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
def mock_task_adapter(mock_task_run):
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
    mock_task_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenCategoriesApiInput(
        node_path=["parent", "child"],
        num_subtopics=4,
        guidance="Generate tech categories",
        gen_type="eval",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
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
    mock_task_adapter.invoke.assert_awaited_once()


def test_generate_samples_success(
    mock_task_from_id,
    mock_task_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenSampleApiInput(
        topic=["technology", "AI"],
        gen_type="training",
        guidance="Make long samples",
        run_config_properties=RunConfigProperties(
            model_name="gpt-4",
            model_provider_name=ModelProviderName.openai,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
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
    mock_task_adapter.invoke.assert_awaited_once()


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
        run_config_properties=RunConfigProperties(
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
    mock_task_adapter,
    client,
    mock_task_run,
    test_task,
):
    # Arrange
    input_data = DataGenSaveSamplesApiInput(
        input="Test sample input",
        input_model_name="gpt_4o",
        input_provider="openai",
        run_config_properties=RunConfigProperties(
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

    mock_task_adapter.invoke.assert_awaited_once()
    invoke_args = mock_task_adapter.invoke.await_args[1]
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
    mock_task_adapter,
    client,
    mock_task_run,
):
    # Arrange
    input_data = DataGenSaveSamplesApiInput(
        input="Test sample input",
        topic_path=["AI", "Machine Learning", "Deep Learning"],
        input_model_name="gpt_4o",
        input_provider="openai",
        run_config_properties=RunConfigProperties(
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
    invoke_args = mock_task_adapter.invoke.await_args[1]
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
    mock_task_adapter,
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
            run_config_properties=RunConfigProperties(
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


def test_generate_qna_success_with_session_and_tags(
    mock_task_from_id,
    mock_task_adapter,
    client,
    mock_task_run,
    test_task,
):
    with (
        patch(
            "kiln_ai.datamodel.extraction.Document.from_id_and_parent_path"
        ) as mock_document,
        patch(
            "app.desktop.studio_server.data_gen_api.project_from_id"
        ) as mock_project_from_id,
    ):
        mock_document.return_value = MagicMock(friendly_name="doc1", spec=Document)
        mock_project_from_id.return_value = test_task.parent

        input_data = DataGenQnaApiInput(
            document_id="doc1",
            part_text=["section a", "section b"],
            num_samples=3,
            run_config_properties=RunConfigProperties(
                model_name="gpt_4o_mini",
                model_provider_name=ModelProviderName.openai,
                prompt_id=PromptGenerators.SIMPLE,
                structured_output_mode=StructuredOutputMode.json_schema,
            ),
            guidance="Make concise QnA",
            tags=["custom_tag"],
        )

        response = client.post(
            "/api/projects/proj-ID/tasks/task-ID/generate_qna?session_id=abcd",
            json=input_data.model_dump(),
        )

        assert response.status_code == 200
        res = response.json()
        assert set(
            ["synthetic", "qna", "synthetic_qna_session_abcd", "custom_tag"]
        ).issubset(set(res.get("tags", [])))

        # Verify adapter was invoked with the expected positional dict payload
        called_args, called_kwargs = mock_task_adapter.invoke.await_args
        assert called_kwargs == {}
        payload = called_args[0]
        assert payload["kiln_data_gen_document_name"] == "doc1"
        assert payload["kiln_data_gen_part_text"] == ["section a", "section b"]
        assert payload["kiln_data_gen_num_samples"] == 3


def test_save_qna_pair_persists_task_run(
    mock_task_from_id,
    client,
    test_task,
):
    input_data = SaveQnaPairInput(
        query="What is Kiln?",
        answer="Kiln is an app for building AI systems.",
        model_name="gpt-4",
        model_provider="openai",
        tags=["my_tag"],
    )

    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/save_qna_pair?session_id=9876",
        json=input_data.model_dump(),
    )

    assert response.status_code == 200
    mock_task_from_id.assert_called_once_with("proj-ID", "task-ID")

    saved_runs = test_task.runs()
    assert len(saved_runs) == 1
    run = saved_runs[0]

    assert run.input == "What is Kiln?"
    assert run.output.output == "Kiln is an app for building AI systems."

    assert run.input_source.type == DataSourceType.synthetic
    assert run.input_source.properties == {
        "model_name": "gpt-4",
        "model_provider": "openai",
        "adapter_name": "kiln_qna_manual_save",
    }

    assert run.output.source.type == DataSourceType.synthetic
    assert run.output.source.properties == {
        "model_name": "gpt-4",
        "model_provider": "openai",
        "adapter_name": "kiln_qna_manual_save",
    }

    tags = set(run.tags)
    assert {"synthetic", "qna", "synthetic_qna_session_9876", "my_tag"}.issubset(tags)

    # Verify trace contains system, user, assistant messages
    assert isinstance(run.trace, list) and len(run.trace) == 3
    assert run.trace[0]["role"] == "system"
    assert run.trace[1]["role"] == "user" and run.trace[1]["content"] == "What is Kiln?"
    assert (
        run.trace[2]["role"] == "assistant"
        and run.trace[2]["content"] == "Kiln is an app for building AI systems."
    )
