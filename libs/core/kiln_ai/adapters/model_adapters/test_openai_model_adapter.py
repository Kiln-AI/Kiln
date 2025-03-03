import json
from unittest.mock import Mock, patch

import pytest
from openai import AsyncOpenAI

from kiln_ai.adapters.ml_model_list import StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig
from kiln_ai.adapters.model_adapters.openai_compatible_config import (
    OpenAICompatibleConfig,
)
from kiln_ai.adapters.model_adapters.openai_model_adapter import OpenAICompatibleAdapter
from kiln_ai.datamodel import Project, Task


@pytest.fixture
def mock_task(tmp_path):
    # Create a project first since Task requires a parent
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    schema = {
        "type": "object",
        "properties": {"test": {"type": "string"}},
    }

    task = Task(
        name="Test Task",
        instruction="Test instruction",
        parent=project,
        output_json_schema=json.dumps(schema),
    )
    task.save_to_file()
    return task


@pytest.fixture
def config():
    return OpenAICompatibleConfig(
        api_key="test_key",
        base_url="https://api.test.com",
        model_name="test-model",
        provider_name="openrouter",
        default_headers={"X-Test": "test"},
    )


def test_initialization(config, mock_task):
    adapter = OpenAICompatibleAdapter(
        config=config,
        kiln_task=mock_task,
        prompt_id="simple_prompt_builder",
        base_adapter_config=AdapterConfig(default_tags=["test-tag"]),
    )

    assert isinstance(adapter.client, AsyncOpenAI)
    assert adapter.config == config
    assert adapter.run_config.task == mock_task
    assert adapter.run_config.prompt_id == "simple_prompt_builder"
    assert adapter.base_adapter_config.default_tags == ["test-tag"]
    assert adapter.run_config.model_name == config.model_name
    assert adapter.run_config.model_provider_name == config.provider_name


def test_adapter_info(config, mock_task):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    assert adapter.adapter_name() == "kiln_openai_compatible_adapter"

    assert adapter.run_config.model_name == config.model_name
    assert adapter.run_config.model_provider_name == config.provider_name
    assert adapter.run_config.prompt_id == "simple_prompt_builder"


@pytest.mark.asyncio
async def test_response_format_options_unstructured(config, mock_task):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    # Mock has_structured_output to return False
    with patch.object(adapter, "has_structured_output", return_value=False):
        options = await adapter.response_format_options()
        assert options == {}


@pytest.mark.parametrize(
    "mode",
    [
        StructuredOutputMode.json_mode,
        StructuredOutputMode.json_instruction_and_object,
    ],
)
@pytest.mark.asyncio
async def test_response_format_options_json_mode(config, mock_task, mode):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
        patch.object(adapter, "model_provider") as mock_provider,
    ):
        mock_provider.return_value.structured_output_mode = mode

        options = await adapter.response_format_options()
        assert options == {"response_format": {"type": "json_object"}}


@pytest.mark.parametrize(
    "mode",
    [
        StructuredOutputMode.default,
        StructuredOutputMode.function_calling,
    ],
)
@pytest.mark.asyncio
async def test_response_format_options_function_calling(config, mock_task, mode):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
        patch.object(adapter, "model_provider") as mock_provider,
    ):
        mock_provider.return_value.structured_output_mode = mode

        options = await adapter.response_format_options()
        assert "tools" in options
        # full tool structure validated below


@pytest.mark.asyncio
async def test_response_format_options_json_instructions(config, mock_task):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
        patch.object(adapter, "model_provider") as mock_provider,
    ):
        mock_provider.return_value.structured_output_mode = (
            StructuredOutputMode.json_instructions
        )
        options = await adapter.response_format_options()
        assert options == {}


@pytest.mark.asyncio
async def test_response_format_options_json_schema(config, mock_task):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    with (
        patch.object(adapter, "has_structured_output", return_value=True),
        patch.object(adapter, "model_provider") as mock_provider,
    ):
        mock_provider.return_value.structured_output_mode = (
            StructuredOutputMode.json_schema
        )
        options = await adapter.response_format_options()
        assert options == {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "task_response",
                    "schema": mock_task.output_schema(),
                },
            }
        }


def test_tool_call_params_weak(config, mock_task):
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    params = adapter.tool_call_params(strict=False)
    expected_schema = mock_task.output_schema()
    expected_schema["additionalProperties"] = False

    assert params == {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "task_response",
                    "parameters": expected_schema,
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "task_response"},
        },
    }


def test_tool_call_params_strict(config, mock_task):
    config.provider_name = "openai"
    adapter = OpenAICompatibleAdapter(config=config, kiln_task=mock_task)

    params = adapter.tool_call_params(strict=True)
    expected_schema = mock_task.output_schema()
    expected_schema["additionalProperties"] = False

    assert params == {
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "task_response",
                    "parameters": expected_schema,
                    "strict": True,
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "task_response"},
        },
    }
