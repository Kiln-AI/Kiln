from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.ml_model_list import KilnModelProvider, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter
from kiln_ai.datamodel import Task
from kiln_ai.datamodel.task import RunConfig


class MockAdapter(BaseAdapter):
    """Concrete implementation of BaseAdapter for testing"""

    async def _run(self, input):
        return None

    def adapter_name(self) -> str:
        return "test"


@pytest.fixture
def mock_provider():
    return KilnModelProvider(
        name="openai",
    )


@pytest.fixture
def base_task():
    return Task(name="test_task", instruction="test_instruction")


@pytest.fixture
def adapter(base_task):
    return MockAdapter(
        run_config=RunConfig(
            task=base_task,
            model_name="test_model",
            model_provider_name="test_provider",
            prompt_id="simple_prompt_builder",
        ),
    )


async def test_model_provider_uses_cache(adapter, mock_provider):
    """Test that cached provider is returned if it exists"""
    # Set up cached provider
    adapter._model_provider = mock_provider

    # Mock the provider loader to ensure it's not called
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.kiln_model_provider_from"
    ) as mock_loader:
        provider = adapter.model_provider()

        assert provider == mock_provider
        mock_loader.assert_not_called()


async def test_model_provider_loads_and_caches(adapter, mock_provider):
    """Test that provider is loaded and cached if not present"""
    # Ensure no cached provider
    adapter._model_provider = None

    # Mock the provider loader
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.kiln_model_provider_from"
    ) as mock_loader:
        mock_loader.return_value = mock_provider

        # First call should load and cache
        provider1 = adapter.model_provider()
        assert provider1 == mock_provider
        mock_loader.assert_called_once_with("test_model", "test_provider")

        # Second call should use cache
        mock_loader.reset_mock()
        provider2 = adapter.model_provider()
        assert provider2 == mock_provider
        mock_loader.assert_not_called()


async def test_model_provider_missing_names(base_task):
    """Test error when model or provider name is missing"""
    # Test with missing model name
    adapter = MockAdapter(
        run_config=RunConfig(
            task=base_task,
            model_name="",
            model_provider_name="",
            prompt_id="simple_prompt_builder",
        ),
    )
    with pytest.raises(
        ValueError, match="model_name and model_provider_name must be provided"
    ):
        await adapter.model_provider()

    # Test with missing provider name
    adapter = MockAdapter(
        run_config=RunConfig(
            task=base_task,
            model_name="test_model",
            model_provider_name="",
            prompt_id="simple_prompt_builder",
        ),
    )
    with pytest.raises(
        ValueError, match="model_name and model_provider_name must be provided"
    ):
        await adapter.model_provider()


async def test_model_provider_not_found(adapter):
    """Test error when provider loader returns None"""
    # Mock the provider loader to return None
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.kiln_model_provider_from"
    ) as mock_loader:
        mock_loader.return_value = None

        with pytest.raises(
            ValueError,
            match="model_provider_name test_provider not found for model test_model",
        ):
            await adapter.model_provider()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output_schema,structured_output_mode,expected_json_instructions",
    [
        (False, StructuredOutputMode.json_instructions, False),
        (True, StructuredOutputMode.json_instructions, True),
        (False, StructuredOutputMode.json_instruction_and_object, False),
        (True, StructuredOutputMode.json_instruction_and_object, True),
        (True, StructuredOutputMode.json_mode, False),
        (False, StructuredOutputMode.json_mode, False),
    ],
)
async def test_prompt_builder_json_instructions(
    base_task,
    adapter,
    output_schema,
    structured_output_mode,
    expected_json_instructions,
):
    """Test that prompt builder is called with correct include_json_instructions value"""
    # Mock the prompt builder and has_structured_output method
    mock_prompt_builder = MagicMock()
    adapter.prompt_builder = mock_prompt_builder
    adapter.model_provider_name = "openai"
    adapter.has_structured_output = MagicMock(return_value=output_schema)

    # provider mock
    provider = MagicMock()
    provider.structured_output_mode = structured_output_mode
    adapter.model_provider = MagicMock(return_value=provider)

    # Test
    adapter.build_prompt()
    mock_prompt_builder.build_prompt.assert_called_with(
        include_json_instructions=expected_json_instructions
    )


@pytest.mark.parametrize(
    "cot_prompt,has_structured_output,reasoning_capable,expected",
    [
        # COT and normal LLM
        ("think carefully", False, False, ("cot_two_call", "think carefully")),
        # Structured output with thinking-capable LLM
        ("think carefully", True, True, ("cot_as_message", "think carefully")),
        # Structured output with normal LLM
        ("think carefully", True, False, ("cot_two_call", "think carefully")),
        # Basic cases - no COT
        (None, True, True, ("basic", None)),
        (None, False, False, ("basic", None)),
        (None, True, False, ("basic", None)),
        (None, False, True, ("basic", None)),
        # Edge case - COT prompt exists but structured output is False and reasoning_capable is True
        ("think carefully", False, True, ("cot_as_message", "think carefully")),
    ],
)
async def test_run_strategy(
    adapter, cot_prompt, has_structured_output, reasoning_capable, expected
):
    """Test that run_strategy returns correct strategy based on conditions"""
    # Mock dependencies
    adapter.prompt_builder.chain_of_thought_prompt = MagicMock(return_value=cot_prompt)
    adapter.has_structured_output = MagicMock(return_value=has_structured_output)

    provider = MagicMock()
    provider.reasoning_capable = reasoning_capable
    adapter.model_provider = MagicMock(return_value=provider)

    # Test
    result = adapter.run_strategy()
    assert result == expected
