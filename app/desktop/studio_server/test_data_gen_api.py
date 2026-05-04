from unittest.mock import AsyncMock, MagicMock, patch

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
from kiln_ai.datamodel.extraction import Document
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties

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
    connect_custom_errors(app)
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
def test_project(tmp_path) -> Project:
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def test_task(test_project) -> Task:
    task = Task(name="Test Task", instruction="Test Instruction", parent=test_project)
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
def mock_project_from_id(test_project):
    with patch("app.desktop.studio_server.data_gen_api.project_from_id") as mock:
        mock.return_value = test_project
        yield mock


@pytest.fixture
def mock_task_from_id(test_task):
    with patch("app.desktop.studio_server.data_gen_api.task_from_id") as mock:
        mock.return_value = test_task
        yield mock


def test_generate_categories_success(
    mock_task_from_id,
    mock_project_from_id,
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
        run_config_properties=KilnAgentRunConfigProperties(
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
    mock_project_from_id,
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
        run_config_properties=KilnAgentRunConfigProperties(
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


def test_generate_categories_rejects_mcp_run_config(
    mock_task_from_id,
    mock_project_from_id,
    client,
):
    input_data = {
        "node_path": ["parent", "child"],
        "num_subtopics": 4,
        "guidance": "Generate tech categories",
        "gen_type": "eval",
        "run_config_properties": {
            "type": "mcp",
            "tool_reference": {
                "tool_id": "mcp::local::server_id::tool_name",
            },
        },
    }

    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_categories",
        json=input_data,
    )

    assert response.status_code == 422


def test_generate_samples_rejects_mcp_run_config(
    mock_task_from_id,
    mock_project_from_id,
    client,
):
    input_data = {
        "topic": ["technology", "AI"],
        "gen_type": "training",
        "guidance": "Make long samples",
        "run_config_properties": {
            "type": "mcp",
            "tool_reference": {
                "tool_id": "mcp::local::server_id::tool_name",
            },
        },
    }

    response = client.post(
        "/api/projects/proj-ID/tasks/task-ID/generate_inputs",
        json=input_data,
    )

    assert response.status_code == 422


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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
        run_config_properties=KilnAgentRunConfigProperties(
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
            run_config_properties=KilnAgentRunConfigProperties(
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
            run_config_properties=KilnAgentRunConfigProperties(
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


def test_generate_qna_rejects_mcp_run_config(
    mock_task_from_id,
    client,
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

        input_data = {
            "document_id": "doc1",
            "part_text": ["section a", "section b"],
            "num_samples": 3,
            "run_config_properties": {
                "type": "mcp",
                "tool_reference": {
                    "tool_id": "mcp::local::server_id::tool_name",
                },
            },
        }

        response = client.post(
            "/api/projects/proj-ID/tasks/task-ID/generate_qna?session_id=abcd",
            json=input_data,
        )

        assert response.status_code == 422


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


def test_get_data_gen_guide_none(
    mock_task_from_id,
    client,
):
    response = client.get("/api/projects/test_project/tasks/test_task/data_gen_guide")
    assert response.status_code == 200
    assert response.json() is None


def test_save_and_get_data_gen_guide(
    mock_task_from_id,
    test_task,
    client,
):
    response = client.put(
        "/api/projects/test_project/tasks/test_task/data_gen_guide",
        json={
            "examples_md": "## Example 1\n```input\nx\n```\n\n```output\ny\n```",
            "rules_md": "<output_semantic>\n\n## Cholesterol\nIf cholesterol is high, never have low LDL.\n\n</output_semantic>",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert "x" in result["examples_md"]
    assert "cholesterol" in result["rules_md"].lower()

    # Verify it's persisted via GET
    get_response = client.get(
        "/api/projects/test_project/tasks/test_task/data_gen_guide"
    )
    assert get_response.status_code == 200
    get_result = get_response.json()
    assert "x" in get_result["examples_md"]
    assert "cholesterol" in get_result["rules_md"].lower()

    # Verify task was actually saved to disk
    reloaded_task = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded_task is not None
    current = reloaded_task.current_data_guide()
    assert current is not None
    assert "x" in current.examples_md
    assert "cholesterol" in current.rules_md.lower()
    # Only one DataGuide should exist on disk — saves overwrite in place
    # rather than accumulating new files.
    assert len(reloaded_task.data_guides()) == 1


def test_delete_data_gen_guide(
    mock_task_from_id,
    test_task,
    client,
):
    # First save a guide
    client.put(
        "/api/projects/test_project/tasks/test_task/data_gen_guide",
        json={"examples_md": "examples", "rules_md": "Some rules"},
    )

    # Delete it
    response = client.delete(
        "/api/projects/test_project/tasks/test_task/data_gen_guide"
    )
    assert response.status_code == 200

    # Verify it's gone
    get_response = client.get(
        "/api/projects/test_project/tasks/test_task/data_gen_guide"
    )
    assert get_response.json() is None


def test_save_data_gen_guide_overwrites_previous(
    mock_task_from_id,
    test_task,
    client,
):
    # Save first guide
    first_response = client.put(
        "/api/projects/test_project/tasks/test_task/data_gen_guide",
        json={"examples_md": "first ex", "rules_md": "first rules"},
    )
    first_id = first_response.json()["id"]

    # Overwrite with second
    response = client.put(
        "/api/projects/test_project/tasks/test_task/data_gen_guide",
        json={"examples_md": "second ex", "rules_md": "second rules"},
    )
    assert response.status_code == 200

    get_response = client.get(
        "/api/projects/test_project/tasks/test_task/data_gen_guide"
    )
    result = get_response.json()
    assert result["examples_md"] == "second ex"
    assert result["rules_md"] == "second rules"

    # Same file — second save reuses the first DataGuide rather than creating
    # a new one. Keeps git history of the guide localized to one file.
    assert result["id"] == first_id
    reloaded_task = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded_task is not None
    assert len(reloaded_task.data_guides()) == 1


# --- _compose_guide_md helper ---


def test_compose_guide_md_both_populated():
    """Both halves render with their canonical headings, separated by a
    blank line. Internal whitespace on each body is trimmed by .strip() but
    the bodies themselves come through verbatim."""
    from app.desktop.studio_server.data_gen_api import _compose_guide_md

    out = _compose_guide_md(
        "## Example 1\n```input\nx\n```\n\n```output\ny\n```",
        "<output_semantic>\n\n## Length\nOutputs are 1-3 sentences.\n\n</output_semantic>",
    )
    assert (
        out
        == "# Reference Examples\n\n## Example 1\n```input\nx\n```\n\n```output\ny\n```\n\n# Guidelines & Rules\n\n<output_semantic>\n\n## Length\nOutputs are 1-3 sentences.\n\n</output_semantic>"
    )


def test_compose_guide_md_only_examples():
    """No rules → only the Reference Examples section, no trailing
    Guidelines & Rules heading."""
    from app.desktop.studio_server.data_gen_api import _compose_guide_md

    assert _compose_guide_md("## Example 1\nbody", "") == (
        "# Reference Examples\n\n## Example 1\nbody"
    )


def test_compose_guide_md_only_rules():
    """No examples → only the Guidelines & Rules section."""
    from app.desktop.studio_server.data_gen_api import _compose_guide_md

    assert _compose_guide_md("", "## Foo\nbar") == (
        "# Guidelines & Rules\n\n## Foo\nbar"
    )


def test_compose_guide_md_both_empty():
    """Two empty strings collapse to an empty string — neither heading is
    rendered, so `_resolve_data_guide` can treat the result as falsy and
    skip the framing entirely."""
    from app.desktop.studio_server.data_gen_api import _compose_guide_md

    assert _compose_guide_md("", "") == ""
    assert _compose_guide_md("   ", "\n\n") == ""


# --- _resolve_data_guide / _combine_guidance helpers ---


def test_resolve_data_guide_override_replaces_persisted(test_task):
    """An explicit override (non-empty) replaces the persisted guide."""
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _resolve_data_guide

    saved = DataGuide(parent=test_task, examples_md="persisted")
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    assert _resolve_data_guide(reloaded, "override text") == "override text"


def test_resolve_data_guide_blank_override_returns_none(test_task):
    """A blank/whitespace override is treated as 'don't include any guide for
    this call' even if there's a persisted one."""
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _resolve_data_guide

    saved = DataGuide(parent=test_task, examples_md="persisted")
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    assert _resolve_data_guide(reloaded, "") is None
    assert _resolve_data_guide(reloaded, "   \n  ") is None


def test_resolve_data_guide_falls_back_to_persisted(test_task):
    """`None` means 'no override provided' → fall back to the saved guide."""
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _resolve_data_guide

    saved = DataGuide(
        parent=test_task,
        examples_md="examples body",
        rules_md="rules body",
    )
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    out = _resolve_data_guide(reloaded, None)
    assert out is not None
    assert "# Reference Examples\n\nexamples body" in out
    assert "# Guidelines & Rules\n\nrules body" in out


def test_resolve_data_guide_no_persisted_returns_none(test_task):
    from app.desktop.studio_server.data_gen_api import _resolve_data_guide

    assert _resolve_data_guide(test_task, None) is None


def test_combine_guidance_with_data_guide_only(test_task):
    """With a saved guide and no session guidance, the helper wraps the
    guide with the framing paragraph + stage hint."""
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _combine_guidance

    saved = DataGuide(parent=test_task, examples_md="GUIDE_BODY")
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    out = _combine_guidance(reloaded, None, "inputs")
    assert out is not None
    assert "# Task Data Guide" in out
    assert "GUIDE_BODY" in out
    assert "mirror their structure and value patterns" in out


def test_combine_guidance_data_guide_and_session(test_task):
    """When both a guide and session guidance exist, both blocks are present
    separated by a blank line."""
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _combine_guidance

    saved = DataGuide(parent=test_task, examples_md="GUIDE_BODY")
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    out = _combine_guidance(reloaded, "EXTRA_SESSION_GUIDANCE", "outputs")
    assert out is not None
    assert "GUIDE_BODY" in out
    assert "EXTRA_SESSION_GUIDANCE" in out
    # session guidance should appear after the data guide block
    assert out.index("GUIDE_BODY") < out.index("EXTRA_SESSION_GUIDANCE")


def test_combine_guidance_session_only(test_task):
    """With no saved guide and a session guidance, the helper just returns
    the session guidance — no Task Data Guide framing."""
    from app.desktop.studio_server.data_gen_api import _combine_guidance

    out = _combine_guidance(test_task, "SESSION_ONLY", "topics")
    assert out == "SESSION_ONLY"


def test_combine_guidance_empty_returns_none(test_task):
    """No saved guide, no session guidance, no override → None."""
    from app.desktop.studio_server.data_gen_api import _combine_guidance

    assert _combine_guidance(test_task, None, "topics") is None


def test_combine_guidance_override_wins_over_persisted(test_task):
    from kiln_ai.datamodel.data_guide import DataGuide

    from app.desktop.studio_server.data_gen_api import _combine_guidance

    saved = DataGuide(parent=test_task, examples_md="PERSISTED_GUIDE")
    saved.save_to_file()
    reloaded = Task.from_id_and_parent_path(test_task.id, test_task.parent.path)
    assert reloaded is not None

    out = _combine_guidance(
        reloaded,
        None,
        "inputs",
        data_guide_override="OVERRIDE_GUIDE",
    )
    assert out is not None
    assert "OVERRIDE_GUIDE" in out
    assert "PERSISTED_GUIDE" not in out


# --- /data_gen_guide_preview endpoint ---


def test_preview_data_gen_guide_success(
    mock_task_from_id,
    mock_project_from_id,
    test_task,
    client,
):
    """Happy path: the input adapter returns a JSON sample list, the output
    adapter returns one output per sample, and we get a flat list of
    GuidePreviewSample objects back."""
    import json

    sample_input_run = MagicMock()
    sample_input_run.output = MagicMock()
    sample_input_run.output.output = json.dumps(
        {"generated_samples": ["input one", "input two"]}
    )

    output_run_a = MagicMock()
    output_run_a.output = MagicMock()
    output_run_a.output.output = "output one"
    output_run_b = MagicMock()
    output_run_b.output = MagicMock()
    output_run_b.output.output = "output two"

    invoke_mock = AsyncMock(side_effect=[sample_input_run, output_run_a, output_run_b])

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = invoke_mock
        mock_adapter_for_task.return_value = mock_adapter

        with patch(
            "app.desktop.studio_server.data_gen_api.load_skills_for_task",
            return_value=[],
        ):
            response = client.post(
                "/api/projects/test_project/tasks/test_task/data_gen_guide_preview",
                json={
                    "examples_md": "Some examples",
                    "rules_md": "Some rules",
                    "run_config_properties": {
                        "type": "kiln_agent",
                        "model_name": "gpt-4",
                        "model_provider_name": ModelProviderName.openai.value,
                        "prompt_id": PromptGenerators.SIMPLE.value,
                        "structured_output_mode": StructuredOutputMode.default.value,
                    },
                    "num_samples": 2,
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {"input": "input one", "output": "output one"},
        {"input": "input two", "output": "output two"},
    ]


def test_preview_data_gen_guide_empty_output_returns_500(
    mock_task_from_id,
    mock_project_from_id,
    client,
):
    """If the input-generating adapter returns no output, surface a 500 with
    a helpful detail rather than crashing later in the pipeline."""
    sample_run = MagicMock()
    sample_run.output = None

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=sample_run)
        mock_adapter_for_task.return_value = mock_adapter

        with patch(
            "app.desktop.studio_server.data_gen_api.load_skills_for_task",
            return_value=[],
        ):
            response = client.post(
                "/api/projects/test_project/tasks/test_task/data_gen_guide_preview",
                json={
                    "examples_md": "Some examples",
                    "rules_md": "Some rules",
                    "run_config_properties": {
                        "type": "kiln_agent",
                        "model_name": "gpt-4",
                        "model_provider_name": ModelProviderName.openai.value,
                        "prompt_id": PromptGenerators.SIMPLE.value,
                        "structured_output_mode": StructuredOutputMode.default.value,
                    },
                    "num_samples": 1,
                },
            )

    assert response.status_code == 500
    assert "preview" in response.json()["message"].lower()


def test_preview_data_gen_guide_unparseable_samples_returns_500(
    mock_task_from_id,
    mock_project_from_id,
    client,
):
    """Adapter returned non-JSON in the slot we expect parsed samples in →
    500 rather than letting JSONDecodeError bubble up."""
    sample_run = MagicMock()
    sample_run.output = MagicMock()
    sample_run.output.output = "not json at all"

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=sample_run)
        mock_adapter_for_task.return_value = mock_adapter

        with patch(
            "app.desktop.studio_server.data_gen_api.load_skills_for_task",
            return_value=[],
        ):
            response = client.post(
                "/api/projects/test_project/tasks/test_task/data_gen_guide_preview",
                json={
                    "examples_md": "Some examples",
                    "rules_md": "Some rules",
                    "run_config_properties": {
                        "type": "kiln_agent",
                        "model_name": "gpt-4",
                        "model_provider_name": ModelProviderName.openai.value,
                        "prompt_id": PromptGenerators.SIMPLE.value,
                        "structured_output_mode": StructuredOutputMode.default.value,
                    },
                    "num_samples": 1,
                },
            )

    assert response.status_code == 500
    assert "parse" in response.json()["message"].lower()


# --- /data_gen_guide_refine endpoint ---


def test_refine_data_gen_guide_success(
    mock_task_from_id,
    client,
):
    """Happy path: the metaprompter LLM returns a structured JSON object with
    a `rules` key; the endpoint stitches it into the refined guide."""
    import json

    refine_run = MagicMock()
    refine_run.output = MagicMock()
    refine_run.output.output = json.dumps({"rules": "REFINED RULES BODY"})

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=refine_run)
        mock_adapter_for_task.return_value = mock_adapter

        response = client.post(
            "/api/projects/test_project/tasks/test_task/data_gen_guide_refine",
            json={
                "current_examples_md": "## Example 1\n```input\nx\n```\n\n```output\ny\n```",
                "current_rules_md": "<output_semantic>\n\n## Old\nOld rule.\n\n</output_semantic>",
                "feedback": "Please make outputs shorter",
                "preview_samples": [
                    {"input": "i1", "output": "o1", "looks_good": True},
                    {"input": "i2", "output": "o2", "looks_good": False},
                ],
                "run_config_properties": {
                    "type": "kiln_agent",
                    "model_name": "gpt-4",
                    "model_provider_name": ModelProviderName.openai.value,
                    "prompt_id": PromptGenerators.SIMPLE.value,
                    "structured_output_mode": StructuredOutputMode.default.value,
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"refined_rules_md": "REFINED RULES BODY"}


def test_refine_data_gen_guide_falls_back_to_current_when_missing_key(
    mock_task_from_id,
    client,
):
    """If the LLM JSON doesn't include the `rules` key, fall back to the
    current rules body rather than returning an empty string."""
    import json

    refine_run = MagicMock()
    refine_run.output = MagicMock()
    refine_run.output.output = json.dumps({"unrelated": "field"})

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=refine_run)
        mock_adapter_for_task.return_value = mock_adapter

        response = client.post(
            "/api/projects/test_project/tasks/test_task/data_gen_guide_refine",
            json={
                "current_examples_md": "",
                "current_rules_md": "Original rules",
                "feedback": "fb",
                "preview_samples": [],
                "run_config_properties": {
                    "type": "kiln_agent",
                    "model_name": "gpt-4",
                    "model_provider_name": ModelProviderName.openai.value,
                    "prompt_id": PromptGenerators.SIMPLE.value,
                    "structured_output_mode": StructuredOutputMode.default.value,
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"refined_rules_md": "Original rules"}


def test_refine_data_gen_guide_empty_output_returns_500(
    mock_task_from_id,
    client,
):
    refine_run = MagicMock()
    refine_run.output = None

    with patch(
        "app.desktop.studio_server.data_gen_api.adapter_for_task"
    ) as mock_adapter_for_task:
        mock_adapter = AsyncMock()
        mock_adapter.invoke = AsyncMock(return_value=refine_run)
        mock_adapter_for_task.return_value = mock_adapter

        response = client.post(
            "/api/projects/test_project/tasks/test_task/data_gen_guide_refine",
            json={
                "current_examples_md": "",
                "current_rules_md": "Original",
                "feedback": "fb",
                "preview_samples": [],
                "run_config_properties": {
                    "type": "kiln_agent",
                    "model_name": "gpt-4",
                    "model_provider_name": ModelProviderName.openai.value,
                    "prompt_id": PromptGenerators.SIMPLE.value,
                    "structured_output_mode": StructuredOutputMode.default.value,
                },
            },
        )

    assert response.status_code == 500
    assert "refine" in response.json()["message"].lower()
