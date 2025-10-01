from unittest.mock import MagicMock, patch

import pytest

from kiln_ai.adapters.ml_model_list import KilnModelProvider, StructuredOutputMode
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter, RunOutput
from kiln_ai.datamodel import Task
from kiln_ai.datamodel.datamodel_enums import ChatStrategy
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import ToolsRunConfig
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnToolInterface


class MockAdapter(BaseAdapter):
    """Concrete implementation of BaseAdapter for testing"""

    async def _run(self, input):
        return None, None

    def adapter_name(self) -> str:
        return "test"


@pytest.fixture
def mock_provider():
    return KilnModelProvider(
        name="openai",
    )


@pytest.fixture
def base_project():
    return Project(name="test_project", description="test project description")


@pytest.fixture
def base_task(base_project):
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)
    return task


@pytest.fixture
def adapter(base_task):
    return MockAdapter(
        task=base_task,
        run_config=RunConfigProperties(
            model_name="test_model",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
        ),
    )


@pytest.fixture
def mock_formatter():
    formatter = MagicMock()
    formatter.format_input.return_value = {"formatted": "input"}
    return formatter


@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.parse_output.return_value = RunOutput(
        output="test output", intermediate_outputs={}
    )
    return parser


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
        mock_loader.assert_called_once_with("test_model", "openai")

        # Second call should use cache
        mock_loader.reset_mock()
        provider2 = adapter.model_provider()
        assert provider2 == mock_provider
        mock_loader.assert_not_called()


async def test_model_provider_invalid_provider_model_name(base_project):
    """Test error when model or provider name is missing"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Test with missing model name
    with pytest.raises(ValueError, match="Input should be"):
        MockAdapter(
            task=task,
            run_config=RunConfigProperties(
                model_name="test_model",
                model_provider_name="invalid",
                prompt_id="simple_prompt_builder",
            ),
        )


async def test_model_provider_missing_model_names(base_project):
    """Test error when model or provider name is missing"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Test with missing model name
    adapter = MockAdapter(
        task=task,
        run_config=RunConfigProperties(
            model_name="",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
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
            match="not found for model test_model",
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
    adapter.run_config.structured_output_mode = structured_output_mode

    # Test
    adapter.build_prompt()
    mock_prompt_builder.build_prompt.assert_called_with(
        include_json_instructions=expected_json_instructions
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "formatter_id,expected_input,expected_calls",
    [
        (None, {"original": "input"}, 0),  # No formatter
        ("test_formatter", {"formatted": "input"}, 1),  # With formatter
    ],
)
async def test_input_formatting(
    adapter, mock_formatter, mock_parser, formatter_id, expected_input, expected_calls
):
    """Test that input formatting is handled correctly based on formatter configuration"""
    # Mock the model provider to return our formatter ID and parser
    provider = MagicMock()
    provider.formatter = formatter_id
    provider.parser = "test_parser"
    provider.reasoning_capable = False
    adapter.model_provider = MagicMock(return_value=provider)

    # Mock the formatter factory and parser factory
    with (
        patch(
            "kiln_ai.adapters.model_adapters.base_adapter.request_formatter_from_id"
        ) as mock_factory,
        patch(
            "kiln_ai.adapters.model_adapters.base_adapter.model_parser_from_id"
        ) as mock_parser_factory,
    ):
        mock_factory.return_value = mock_formatter
        mock_parser_factory.return_value = mock_parser

        # Mock the _run method to capture the input
        captured_input = None

        async def mock_run(input):
            nonlocal captured_input
            captured_input = input
            return RunOutput(output="test output", intermediate_outputs={}), None

        adapter._run = mock_run

        # Run the adapter
        original_input = {"original": "input"}
        await adapter.invoke_returning_run_output(original_input)

        # Verify formatter was called correctly
        assert captured_input == expected_input
        assert mock_factory.call_count == (1 if formatter_id else 0)
        assert mock_formatter.format_input.call_count == expected_calls

        # Verify original input was preserved in the run
        if formatter_id:
            mock_formatter.format_input.assert_called_once_with(original_input)


async def test_properties_for_task_output_includes_all_run_config_properties(adapter):
    """Test that all properties from RunConfigProperties are saved in task output properties"""
    # Get all field names from RunConfigProperties
    run_config_properties_fields = set(RunConfigProperties.model_fields.keys())

    # Get the properties saved by the adapter
    saved_properties = adapter._properties_for_task_output()
    saved_property_keys = set(saved_properties.keys())

    # Check which RunConfigProperties fields are missing from saved properties
    # Note: model_provider_name becomes model_provider in saved properties
    expected_mappings = {
        "model_name": "model_name",
        "model_provider_name": "model_provider",
        "prompt_id": "prompt_id",
        "temperature": "temperature",
        "top_p": "top_p",
        "structured_output_mode": "structured_output_mode",
        "tools_config": None,
    }

    missing_properties = []
    for field_name in run_config_properties_fields:
        expected_key = expected_mappings.get(field_name, field_name)
        if expected_key is not None and expected_key not in saved_property_keys:
            missing_properties.append(
                f"RunConfigProperties.{field_name} -> {expected_key}"
            )

    assert not missing_properties, (
        f"The following RunConfigProperties fields are not saved by _properties_for_task_output: {missing_properties}. Please update the method to include them."
    )


async def test_properties_for_task_output_catches_missing_new_property(adapter):
    """Test that demonstrates our test will catch when new properties are added to RunConfigProperties but not to _properties_for_task_output"""
    # Simulate what happens if a new property was added to RunConfigProperties
    # We'll mock the model_fields to include a fake new property
    original_fields = RunConfigProperties.model_fields.copy()

    # Create a mock field to simulate a new property being added
    from pydantic.fields import FieldInfo

    mock_field = FieldInfo(annotation=str, default="default_value")

    try:
        # Add a fake new field to simulate someone adding a property
        RunConfigProperties.model_fields["new_fake_property"] = mock_field

        # Get all field names from RunConfigProperties (now includes our fake property)
        run_config_properties_fields = set(RunConfigProperties.model_fields.keys())

        # Get the properties saved by the adapter (won't include our fake property)
        saved_properties = adapter._properties_for_task_output()
        saved_property_keys = set(saved_properties.keys())

        # The mappings don't include our fake property
        expected_mappings = {
            "model_name": "model_name",
            "model_provider_name": "model_provider",
            "prompt_id": "prompt_id",
            "temperature": "temperature",
            "top_p": "top_p",
            "structured_output_mode": "structured_output_mode",
            "tools_config": None,
        }

        missing_properties = []
        for field_name in run_config_properties_fields:
            expected_key = expected_mappings.get(field_name, field_name)
            if expected_key is not None and expected_key not in saved_property_keys:
                missing_properties.append(
                    f"RunConfigProperties.{field_name} -> {expected_key}"
                )

        # This should find our missing fake property
        assert missing_properties == [
            "RunConfigProperties.new_fake_property -> new_fake_property"
        ], f"Expected to find missing fake property, but got: {missing_properties}"

    finally:
        # Restore the original fields
        RunConfigProperties.model_fields.clear()
        RunConfigProperties.model_fields.update(original_fields)


@pytest.mark.parametrize(
    "cot_prompt,tuned_strategy,reasoning_capable,expected_formatter_class",
    [
        # No COT prompt -> always single turn
        (None, None, False, "SingleTurnFormatter"),
        (None, ChatStrategy.two_message_cot, False, "SingleTurnFormatter"),
        (None, ChatStrategy.single_turn_r1_thinking, True, "SingleTurnFormatter"),
        # With COT prompt:
        # - Tuned strategy takes precedence (except single turn)
        (
            "think step by step",
            ChatStrategy.two_message_cot,
            False,
            "TwoMessageCotFormatter",
        ),
        (
            "think step by step",
            ChatStrategy.single_turn_r1_thinking,
            False,
            "SingleTurnR1ThinkingFormatter",
        ),
        # - Tuned single turn is ignored when COT exists
        (
            "think step by step",
            ChatStrategy.single_turn,
            True,
            "SingleTurnR1ThinkingFormatter",
        ),
        # - Reasoning capable -> single turn R1 thinking
        ("think step by step", None, True, "SingleTurnR1ThinkingFormatter"),
        # - Not reasoning capable -> two message COT
        ("think step by step", None, False, "TwoMessageCotFormatter"),
    ],
)
def test_build_chat_formatter(
    adapter,
    cot_prompt,
    tuned_strategy,
    reasoning_capable,
    expected_formatter_class,
):
    """Test chat formatter strategy selection based on COT prompt, tuned strategy, and model capabilities"""
    # Mock the prompt builder
    mock_prompt_builder = MagicMock()
    mock_prompt_builder.chain_of_thought_prompt.return_value = cot_prompt
    mock_prompt_builder.build_prompt.return_value = "system message"
    adapter.prompt_builder = mock_prompt_builder

    # Mock the model provider
    mock_provider = MagicMock()
    mock_provider.tuned_chat_strategy = tuned_strategy
    mock_provider.reasoning_capable = reasoning_capable
    adapter.model_provider = MagicMock(return_value=mock_provider)

    # Get the formatter
    formatter = adapter.build_chat_formatter("test input")

    # Verify the formatter type
    assert formatter.__class__.__name__ == expected_formatter_class

    # Verify the formatter was created with correct parameters
    assert formatter.system_message == "system message"
    assert formatter.user_input == "test input"
    # Only check thinking_instructions for formatters that use it
    if expected_formatter_class == "TwoMessageCotFormatter":
        if cot_prompt:
            assert formatter.thinking_instructions == cot_prompt
        else:
            assert formatter.thinking_instructions is None
    # For other formatters, don't assert thinking_instructions

    # Verify prompt builder was called correctly
    mock_prompt_builder.build_prompt.assert_called_once()
    mock_prompt_builder.chain_of_thought_prompt.assert_called_once()


@pytest.mark.parametrize(
    "initial_mode,expected_mode",
    [
        (
            StructuredOutputMode.json_schema,
            StructuredOutputMode.json_schema,
        ),  # Should not change
        (
            StructuredOutputMode.unknown,
            StructuredOutputMode.json_mode,
        ),  # Should update to default
    ],
)
async def test_update_run_config_unknown_structured_output_mode(
    base_project, initial_mode, expected_mode
):
    """Test that unknown structured output mode is updated to the default for the model provider"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Create a run config with the initial mode
    run_config = RunConfigProperties(
        model_name="test_model",
        model_provider_name="openai",
        prompt_id="simple_prompt_builder",
        structured_output_mode=initial_mode,
        temperature=0.7,  # Add some other properties to verify they're preserved
        top_p=0.9,
    )

    # Mock the default mode lookup
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.default_structured_output_mode_for_model_provider"
    ) as mock_default:
        mock_default.return_value = StructuredOutputMode.json_mode

        # Create the adapter
        adapter = MockAdapter(task=task, run_config=run_config)

        # Verify the mode was updated correctly
        assert adapter.run_config.structured_output_mode == expected_mode

        # Verify other properties were preserved
        assert adapter.run_config.temperature == 0.7
        assert adapter.run_config.top_p == 0.9

        # Verify the default mode lookup was only called when needed
        if initial_mode == StructuredOutputMode.unknown:
            mock_default.assert_called_once_with("test_model", "openai")
        else:
            mock_default.assert_not_called()


@pytest.mark.parametrize(
    "tools_config,expected_tool_count,expected_tool_ids",
    [
        # No tools config
        (None, 0, []),
        # Empty tools config with None tools
        (ToolsRunConfig(tools=[]), 0, []),
        # Single tool
        ([KilnBuiltInToolId.ADD_NUMBERS], 1, [KilnBuiltInToolId.ADD_NUMBERS]),
        # Multiple tools
        (
            [KilnBuiltInToolId.ADD_NUMBERS, KilnBuiltInToolId.SUBTRACT_NUMBERS],
            2,
            [KilnBuiltInToolId.ADD_NUMBERS, KilnBuiltInToolId.SUBTRACT_NUMBERS],
        ),
        # All available built-in tools
        (
            [
                KilnBuiltInToolId.ADD_NUMBERS,
                KilnBuiltInToolId.SUBTRACT_NUMBERS,
                KilnBuiltInToolId.MULTIPLY_NUMBERS,
                KilnBuiltInToolId.DIVIDE_NUMBERS,
            ],
            4,
            [
                KilnBuiltInToolId.ADD_NUMBERS,
                KilnBuiltInToolId.SUBTRACT_NUMBERS,
                KilnBuiltInToolId.MULTIPLY_NUMBERS,
                KilnBuiltInToolId.DIVIDE_NUMBERS,
            ],
        ),
    ],
)
async def test_available_tools(
    base_project, tools_config, expected_tool_count, expected_tool_ids
):
    """Test that available_tools returns correct tools based on tools_config"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Create tools config if we have tool IDs
    if tools_config is None:
        final_tools_config = None
    elif isinstance(tools_config, list):
        final_tools_config = ToolsRunConfig(tools=tools_config)
    else:
        final_tools_config = tools_config

    # Create adapter with tools config
    adapter = MockAdapter(
        task=task,
        run_config=RunConfigProperties(
            model_name="test_model",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
            tools_config=final_tools_config,
        ),
    )

    # Get available tools
    tools = await adapter.available_tools()

    # Verify tool count
    assert len(tools) == expected_tool_count

    # Verify all tools implement KilnToolInterface
    for tool in tools:
        assert isinstance(tool, KilnToolInterface)

    # Verify tool IDs match expected
    if expected_tool_ids:
        actual_tool_ids = [await tool.id() for tool in tools]
        assert actual_tool_ids == expected_tool_ids


async def test_available_tools_with_invalid_tool_id(base_project):
    """Test that available_tools raises ValueError for invalid tool ID"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Create tools config with valid tool ID
    tools_config = ToolsRunConfig(tools=[KilnBuiltInToolId.ADD_NUMBERS])

    # Create adapter
    adapter = MockAdapter(
        task=task,
        run_config=RunConfigProperties(
            model_name="test_model",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
            tools_config=tools_config,
        ),
    )

    # Mock tool_from_id to raise ValueError for any tool ID
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.tool_from_id"
    ) as mock_tool_from_id:
        mock_tool_from_id.side_effect = ValueError(
            "Tool ID test_id not found in tool registry"
        )

        # Should raise ValueError when trying to get tools
        with pytest.raises(
            ValueError, match="Tool ID test_id not found in tool registry"
        ):
            await adapter.available_tools()


async def test_available_tools_duplicate_names_raises_error(base_project):
    """Test that available_tools raises ValueError when tools have duplicate names"""
    # Create a task with a parent project
    task = Task(name="test_task", instruction="test_instruction", parent=base_project)

    # Create tools config with two different tool IDs
    tools_config = ToolsRunConfig(
        tools=[KilnBuiltInToolId.ADD_NUMBERS, KilnBuiltInToolId.SUBTRACT_NUMBERS]
    )

    # Create adapter
    adapter = MockAdapter(
        task=task,
        run_config=RunConfigProperties(
            model_name="test_model",
            model_provider_name="openai",
            prompt_id="simple_prompt_builder",
            structured_output_mode="json_schema",
            tools_config=tools_config,
        ),
    )

    # Create mock tools with duplicate names
    async def mock_name1():
        return "duplicate_name"

    async def mock_name2():
        return "duplicate_name"

    mock_tool1 = MagicMock(spec=KilnToolInterface)
    mock_tool1.name = mock_name1
    mock_tool2 = MagicMock(spec=KilnToolInterface)
    mock_tool2.name = mock_name2  # Same name as tool1

    # Mock tool_from_id to return our mock tools with duplicate names
    with patch(
        "kiln_ai.adapters.model_adapters.base_adapter.tool_from_id"
    ) as mock_tool_from_id:
        mock_tool_from_id.side_effect = [mock_tool1, mock_tool2]

        # Should raise ValueError when tools have duplicate names
        with pytest.raises(ValueError, match="Each tool must have a unique name"):
            await adapter.available_tools()
