from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiln_ai.datamodel import Task
from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.run_config import RunConfigProperties
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.kiln_task_tool import KilnTaskTool, KilnTaskToolResult


class TestKilnTaskToolResult:
    """Test the KilnTaskToolResult class."""

    def test_init(self):
        """Test KilnTaskToolResult initialization."""
        output = "test output"
        kiln_task_tool_data = "project_id:::tool_id:::task_id:::run_id"

        result = KilnTaskToolResult(output, kiln_task_tool_data)

        assert result.output == output
        assert result.kiln_task_tool_data == kiln_task_tool_data

    def test_init_with_empty_strings(self):
        """Test KilnTaskToolResult initialization with empty strings."""
        result = KilnTaskToolResult("", "")

        assert result.output == ""
        assert result.kiln_task_tool_data == ""


class TestKilnTaskTool:
    """Test the KilnTaskTool class."""

    @pytest.fixture
    def mock_external_tool_server(self):
        """Create a mock ExternalToolServer for testing."""
        return ExternalToolServer(
            name="test_tool",
            type=ToolServerType.kiln_task,
            description="Test Kiln task tool",
            properties={
                "name": "test_task_tool",
                "description": "A test task tool",
                "task_id": "test_task_123",
                "run_config_id": "test_config_456",
                "is_archived": False,
            },
        )

    @pytest.fixture
    def mock_task(self):
        """Create a mock Task for testing."""
        task = MagicMock(spec=Task)
        task.id = "test_task_123"
        task.input_json_schema = None
        task.input_schema.return_value = None
        task.run_configs.return_value = []
        return task

    @pytest.fixture
    def mock_run_config(self):
        """Create a mock TaskRunConfig for testing."""
        run_config = MagicMock(spec=TaskRunConfig)
        run_config.id = "test_config_456"
        run_config.run_config_properties = {
            "model_name": "gpt-4",
            "model_provider_name": "openai",
            "prompt_id": "simple_prompt_builder",
            "structured_output_mode": "default",
        }
        return run_config

    @pytest.fixture
    def mock_context(self):
        """Create a mock ToolCallContext for testing."""
        context = MagicMock(spec=ToolCallContext)
        context.allow_saving = True
        return context

    @pytest.fixture
    def kiln_task_tool(self, mock_external_tool_server):
        """Create a KilnTaskTool instance for testing."""
        return KilnTaskTool(
            project_id="test_project",
            tool_id="test_tool_id",
            data_model=mock_external_tool_server,
        )

    @pytest.mark.asyncio
    async def test_init(self, mock_external_tool_server):
        """Test KilnTaskTool initialization."""
        tool = KilnTaskTool(
            project_id="test_project",
            tool_id="test_tool_id",
            data_model=mock_external_tool_server,
        )

        assert tool._project_id == "test_project"
        assert tool._tool_id == "test_tool_id"
        assert tool._tool_server_model == mock_external_tool_server
        assert tool._name == "test_task_tool"
        assert tool._description == "A test task tool"
        assert tool._task_id == "test_task_123"
        assert tool._run_config_id == "test_config_456"

    @pytest.mark.asyncio
    async def test_init_with_missing_properties(self):
        """Test KilnTaskTool initialization with missing properties."""
        # Create a server with minimal required properties
        server = ExternalToolServer(
            name="test_tool",
            type=ToolServerType.kiln_task,
            description="Test tool",
            properties={
                "name": "minimal_tool",
                "description": "",
                "task_id": "",
                "run_config_id": "",
                "is_archived": False,
            },
        )

        tool = KilnTaskTool(
            project_id="test_project",
            tool_id="test_tool_id",
            data_model=server,
        )

        assert tool._name == "minimal_tool"
        assert tool._description == ""
        assert tool._task_id == ""
        assert tool._run_config_id == ""

    @pytest.mark.asyncio
    async def test_id(self, kiln_task_tool):
        """Test the id method."""
        result = await kiln_task_tool.id()
        assert result == "test_tool_id"

    @pytest.mark.asyncio
    async def test_name(self, kiln_task_tool):
        """Test the name method."""
        result = await kiln_task_tool.name()
        assert result == "test_task_tool"

    @pytest.mark.asyncio
    async def test_description(self, kiln_task_tool):
        """Test the description method."""
        result = await kiln_task_tool.description()
        assert result == "A test task tool"

    @pytest.mark.asyncio
    async def test_toolcall_definition(self, kiln_task_tool):
        """Test the toolcall_definition method."""
        # Mock the parameters_schema property directly
        kiln_task_tool.parameters_schema = {"type": "object"}

        definition = await kiln_task_tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "test_task_tool"
        assert definition["function"]["description"] == "A test task tool"
        assert definition["function"]["parameters"] == {"type": "object"}

    @pytest.mark.asyncio
    async def test_run_with_plaintext_input(
        self, kiln_task_tool, mock_context, mock_task, mock_run_config
    ):
        """Test the run method with plaintext input."""
        # Setup mocks
        kiln_task_tool._task = mock_task
        kiln_task_tool._run_config = mock_run_config

        with (
            patch(
                "kiln_ai.adapters.adapter_registry.adapter_for_task"
            ) as mock_adapter_for_task,
            patch(
                "kiln_ai.adapters.model_adapters.base_adapter.AdapterConfig"
            ) as mock_adapter_config,
        ):
            # Mock adapter and task run
            mock_adapter = AsyncMock()
            mock_adapter_for_task.return_value = mock_adapter

            mock_task_run = MagicMock()
            mock_task_run.id = "run_789"
            mock_task_run.output.output = "Task completed successfully"
            mock_adapter.invoke.return_value = mock_task_run

            # Test with plaintext input
            result = await kiln_task_tool.run(context=mock_context, input="test input")

            # Verify adapter was created correctly
            mock_adapter_for_task.assert_called_once_with(
                mock_task,
                run_config_properties={
                    "model_name": "gpt-4",
                    "model_provider_name": "openai",
                    "prompt_id": "simple_prompt_builder",
                    "structured_output_mode": "default",
                },
                base_adapter_config=mock_adapter_config.return_value,
            )

            # Verify adapter config
            mock_adapter_config.assert_called_once_with(
                allow_saving=True,
                default_tags=["tool_call"],
            )

            # Verify adapter invoke was called
            mock_adapter.invoke.assert_called_once_with(
                "test input",
                input_source=DataSource(
                    type=DataSourceType.tool_call,
                    run_config=RunConfigProperties(
                        model_name="gpt-4",
                        model_provider_name=ModelProviderName.openai,
                        prompt_id="simple_prompt_builder",
                        structured_output_mode=StructuredOutputMode.default,
                    ),
                ),
            )

            # Verify result
            assert isinstance(result, KilnTaskToolResult)
            assert result.output == "Task completed successfully"
            assert (
                result.kiln_task_tool_data
                == "test_project:::test_tool_id:::test_task_123:::run_789"
            )

    @pytest.mark.asyncio
    async def test_run_with_structured_input(
        self, kiln_task_tool, mock_context, mock_task, mock_run_config
    ):
        """Test the run method with structured input."""
        # Setup task with JSON schema
        mock_task.input_json_schema = {
            "type": "object",
            "properties": {"param1": {"type": "string"}},
        }

        # Setup mocks
        kiln_task_tool._task = mock_task
        kiln_task_tool._run_config = mock_run_config

        with patch(
            "kiln_ai.adapters.adapter_registry.adapter_for_task"
        ) as mock_adapter_for_task:
            # Mock adapter and task run
            mock_adapter = AsyncMock()
            mock_adapter_for_task.return_value = mock_adapter

            mock_task_run = MagicMock()
            mock_task_run.id = "run_789"
            mock_task_run.output.output = "Structured task completed"
            mock_adapter.invoke.return_value = mock_task_run

            # Test with structured input
            result = await kiln_task_tool.run(
                context=mock_context, param1="value1", param2="value2"
            )

            # Verify adapter invoke was called with kwargs
            mock_adapter.invoke.assert_called_once_with(
                {"param1": "value1", "param2": "value2"},
                input_source=DataSource(
                    type=DataSourceType.tool_call,
                    run_config=RunConfigProperties(
                        model_name="gpt-4",
                        model_provider_name=ModelProviderName.openai,
                        prompt_id="simple_prompt_builder",
                        structured_output_mode=StructuredOutputMode.default,
                    ),
                ),
            )

            # Verify result
            assert result.output == "Structured task completed"

    @pytest.mark.asyncio
    async def test_run_without_context(self, kiln_task_tool):
        """Test the run method without context raises ValueError."""
        with pytest.raises(
            ValueError, match="Context is required for running a KilnTaskTool"
        ):
            await kiln_task_tool.run(input="test input")

    @pytest.mark.asyncio
    async def test_run_plaintext_missing_input(
        self, kiln_task_tool, mock_context, mock_task
    ):
        """Test the run method with plaintext task but missing input parameter."""
        # Setup mocks
        kiln_task_tool._task = mock_task

        with pytest.raises(ValueError, match="Input not found in kwargs"):
            await kiln_task_tool.run(context=mock_context, wrong_param="value")

    @pytest.mark.asyncio
    async def test_task_property_project_not_found(self, kiln_task_tool):
        """Test _task property when project is not found."""
        with patch("kiln_ai.tools.kiln_task_tool.project_from_id", return_value=None):
            with pytest.raises(ValueError, match="Project not found: test_project"):
                _ = kiln_task_tool._task

    @pytest.mark.asyncio
    async def test_task_property_task_not_found(self, kiln_task_tool):
        """Test _task property when task is not found."""
        mock_project = MagicMock()
        mock_project.path = "/test/path"

        with (
            patch(
                "kiln_ai.tools.kiln_task_tool.project_from_id",
                return_value=mock_project,
            ),
            patch(
                "kiln_ai.tools.kiln_task_tool.Task.from_id_and_parent_path",
                return_value=None,
            ),
        ):
            with pytest.raises(
                ValueError,
                match="Task not found: test_task_123 in project test_project",
            ):
                _ = kiln_task_tool._task

    @pytest.mark.asyncio
    async def test_task_property_success(self, kiln_task_tool, mock_task):
        """Test _task property when task is found successfully."""
        mock_project = MagicMock()
        mock_project.path = "/test/path"

        with (
            patch(
                "kiln_ai.tools.kiln_task_tool.project_from_id",
                return_value=mock_project,
            ),
            patch(
                "kiln_ai.tools.kiln_task_tool.Task.from_id_and_parent_path",
                return_value=mock_task,
            ),
        ):
            result = kiln_task_tool._task
            assert result == mock_task

    @pytest.mark.asyncio
    async def test_run_config_property_not_found(self, kiln_task_tool, mock_task):
        """Test _run_config property when run config is not found."""
        mock_task.run_configs.return_value = []

        # Setup mocks
        kiln_task_tool._task = mock_task

        with pytest.raises(
            ValueError,
            match="Task run config not found: test_config_456 for task test_task_123 in project test_project",
        ):
            _ = kiln_task_tool._run_config

    @pytest.mark.asyncio
    async def test_run_config_property_success(
        self, kiln_task_tool, mock_task, mock_run_config
    ):
        """Test _run_config property when run config is found successfully."""
        mock_task.run_configs.return_value = [mock_run_config]

        # Setup mocks
        kiln_task_tool._task = mock_task

        result = kiln_task_tool._run_config
        assert result == mock_run_config

    @pytest.mark.asyncio
    async def test_parameters_schema_with_json_schema(self, kiln_task_tool, mock_task):
        """Test parameters_schema property with JSON schema."""
        expected_schema = {
            "type": "object",
            "properties": {"param": {"type": "string"}},
        }
        mock_task.input_json_schema = expected_schema
        mock_task.input_schema.return_value = expected_schema

        # Setup mocks
        kiln_task_tool._task = mock_task

        result = kiln_task_tool.parameters_schema
        assert result == expected_schema

    @pytest.mark.asyncio
    async def test_parameters_schema_plaintext(self, kiln_task_tool, mock_task):
        """Test parameters_schema property for plaintext task."""
        mock_task.input_json_schema = None

        # Setup mocks
        kiln_task_tool._task = mock_task

        result = kiln_task_tool.parameters_schema

        expected = {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Plaintext input for the tool.",
                }
            },
            "required": ["input"],
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_parameters_schema_none_raises_error(self, kiln_task_tool, mock_task):
        """Test parameters_schema property when schema is None raises ValueError."""
        # Set up a task with JSON schema but input_schema returns None
        mock_task.input_json_schema = {
            "type": "object",
            "properties": {"param": {"type": "string"}},
        }
        mock_task.input_schema.return_value = None

        # Setup mocks - directly assign the task to bypass cached property
        kiln_task_tool._task = mock_task

        with pytest.raises(
            ValueError,
            match="Failed to create parameters schema for tool_id test_tool_id",
        ):
            _ = kiln_task_tool.parameters_schema

    @pytest.mark.asyncio
    async def test_cached_properties(self, kiln_task_tool, mock_task, mock_run_config):
        """Test that cached properties work correctly."""
        mock_project = MagicMock()
        mock_project.path = "/test/path"

        with (
            patch(
                "kiln_ai.tools.kiln_task_tool.project_from_id",
                return_value=mock_project,
            ),
            patch(
                "kiln_ai.tools.kiln_task_tool.Task.from_id_and_parent_path",
                return_value=mock_task,
            ),
        ):
            # First access should call the methods
            task1 = kiln_task_tool._task
            task2 = kiln_task_tool._task

            # Should be the same object (cached)
            assert task1 is task2

            # Verify the methods were called only once
            assert mock_project is not None  # project_from_id was called
            # Task.from_id_and_parent_path should have been called once
            with patch(
                "kiln_ai.tools.kiln_task_tool.Task.from_id_and_parent_path"
            ) as mock_from_id:
                mock_from_id.return_value = mock_task
                _ = kiln_task_tool._task
                # Should not be called again due to caching
                mock_from_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_adapter_exception(
        self, kiln_task_tool, mock_context, mock_task, mock_run_config
    ):
        """Test the run method when adapter raises an exception."""
        # Setup mocks
        kiln_task_tool._task = mock_task
        kiln_task_tool._run_config = mock_run_config

        with patch(
            "kiln_ai.adapters.adapter_registry.adapter_for_task"
        ) as mock_adapter_for_task:
            # Mock adapter to raise an exception
            mock_adapter = AsyncMock()
            mock_adapter.invoke.side_effect = Exception("Adapter failed")
            mock_adapter_for_task.return_value = mock_adapter

            with pytest.raises(Exception, match="Adapter failed"):
                await kiln_task_tool.run(context=mock_context, input="test input")

    @pytest.mark.asyncio
    async def test_run_with_different_allow_saving(
        self, kiln_task_tool, mock_task, mock_run_config
    ):
        """Test the run method with different allow_saving values."""
        mock_context_false = MagicMock(spec=ToolCallContext)
        mock_context_false.allow_saving = False

        # Setup mocks
        kiln_task_tool._task = mock_task
        kiln_task_tool._run_config = mock_run_config

        with (
            patch(
                "kiln_ai.adapters.adapter_registry.adapter_for_task"
            ) as mock_adapter_for_task,
            patch(
                "kiln_ai.adapters.model_adapters.base_adapter.AdapterConfig"
            ) as mock_adapter_config,
        ):
            mock_adapter = AsyncMock()
            mock_adapter_for_task.return_value = mock_adapter

            mock_task_run = MagicMock()
            mock_task_run.id = "run_789"
            mock_task_run.output.output = "Task completed"
            mock_adapter.invoke.return_value = mock_task_run

            await kiln_task_tool.run(context=mock_context_false, input="test input")

            # Verify adapter config was called with allow_saving=False
            mock_adapter_config.assert_called_once_with(
                allow_saving=False,
                default_tags=["tool_call"],
            )
