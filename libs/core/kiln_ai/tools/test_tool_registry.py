from pathlib import Path
from unittest.mock import Mock

import pytest

from kiln_ai.datamodel.external_tool_server import (
    ExternalToolServer,
    ToolServerType,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import (
    KILN_TASK_TOOL_ID_PREFIX,
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    RAG_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    _check_tool_id,
    kiln_task_server_id_from_tool_id,
    mcp_server_and_tool_name_from_id,
)
from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.kiln_task_tool import KilnTaskTool
from kiln_ai.tools.mcp_server_tool import MCPServerTool
from kiln_ai.tools.tool_registry import tool_definitions_from_ids, tool_from_id


class TestToolRegistry:
    """Test the tool registry functionality."""

    async def test_tool_from_id_add_numbers(self):
        """Test that ADD_NUMBERS tool ID returns AddTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)

        assert isinstance(tool, AddTool)
        assert await tool.id() == KilnBuiltInToolId.ADD_NUMBERS
        assert await tool.name() == "add"
        assert "Add two numbers" in await tool.description()

    async def test_tool_from_id_subtract_numbers(self):
        """Test that SUBTRACT_NUMBERS tool ID returns SubtractTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.SUBTRACT_NUMBERS)

        assert isinstance(tool, SubtractTool)
        assert await tool.id() == KilnBuiltInToolId.SUBTRACT_NUMBERS
        assert await tool.name() == "subtract"

    async def test_tool_from_id_multiply_numbers(self):
        """Test that MULTIPLY_NUMBERS tool ID returns MultiplyTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.MULTIPLY_NUMBERS)

        assert isinstance(tool, MultiplyTool)
        assert await tool.id() == KilnBuiltInToolId.MULTIPLY_NUMBERS
        assert await tool.name() == "multiply"

    async def test_tool_from_id_divide_numbers(self):
        """Test that DIVIDE_NUMBERS tool ID returns DivideTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.DIVIDE_NUMBERS)

        assert isinstance(tool, DivideTool)
        assert await tool.id() == KilnBuiltInToolId.DIVIDE_NUMBERS
        assert await tool.name() == "divide"

    async def test_tool_from_id_with_string_values(self):
        """Test that tool_from_id works with string values of enum members."""
        tool = tool_from_id("kiln_tool::add_numbers")

        assert isinstance(tool, AddTool)
        assert await tool.id() == KilnBuiltInToolId.ADD_NUMBERS

    async def test_tool_from_id_invalid_tool_id(self):
        """Test that invalid tool ID raises ValueError."""
        with pytest.raises(
            ValueError, match="Tool ID invalid_tool_id not found in tool registry"
        ):
            tool_from_id("invalid_tool_id")

    def test_tool_from_id_empty_string(self):
        """Test that empty string tool ID raises ValueError."""
        with pytest.raises(ValueError, match="Tool ID  not found in tool registry"):
            tool_from_id("")

    def test_tool_from_id_mcp_remote_tool_success(self):
        """Test that tool_from_id works with MCP remote tool IDs."""
        # Create mock external tool server
        mock_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Test with remote MCP tool ID
        tool_id = f"{MCP_REMOTE_TOOL_ID_PREFIX}{mock_server.id}::echo"
        tool = tool_from_id(tool_id, task=mock_task)

        # Verify the tool is MCPServerTool
        assert isinstance(tool, MCPServerTool)
        assert tool._tool_server_model == mock_server
        assert tool._name == "echo"

    def test_tool_from_id_mcp_local_tool_success(self):
        """Test that tool_from_id works with MCP local tool IDs."""
        # Create mock external tool server
        mock_server = ExternalToolServer(
            name="local_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["server.py", "--port", "8080"],
                "env_vars": {},
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Test with local MCP tool ID
        tool_id = f"{MCP_LOCAL_TOOL_ID_PREFIX}{mock_server.id}::calculate"
        tool = tool_from_id(tool_id, task=mock_task)

        # Verify the tool is MCPServerTool
        assert isinstance(tool, MCPServerTool)
        assert tool._tool_server_model == mock_server
        assert tool._name == "calculate"

    def test_tool_from_id_mcp_tool_project_not_found(self):
        """Test that tool_from_id raises ValueError when task is not provided."""
        tool_id = f"{MCP_LOCAL_TOOL_ID_PREFIX}test_server::test_tool"
        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(tool_id, task=None)

    def test_tool_from_id_mcp_tool_server_not_found(self):
        """Test that tool_from_id raises ValueError when tool server is not found."""
        # Create mock external tool server with different ID
        mock_server = ExternalToolServer(
            name="different_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Test with both remote and local tool IDs that reference nonexistent servers
        test_cases = [
            f"{MCP_REMOTE_TOOL_ID_PREFIX}missing_server::test_tool",
            f"{MCP_LOCAL_TOOL_ID_PREFIX}missing_server::test_tool",
        ]

        for tool_id in test_cases:
            with pytest.raises(
                ValueError,
                match="External tool server not found: missing_server in project ID test_project_id",
            ):
                tool_from_id(tool_id, task=mock_task)

    def test_tool_from_id_rag_tool_success(self):
        """Test that tool_from_id works with RAG tool IDs."""
        # Create mock RAG config
        from unittest.mock import patch

        with (
            patch("kiln_ai.tools.tool_registry.RagConfig") as mock_rag_config_class,
            patch("kiln_ai.tools.rag_tools.RagTool") as mock_rag_tool_class,
        ):
            # Setup mock RAG config
            mock_rag_config = Mock()
            mock_rag_config.id = "test_rag_config"
            mock_rag_config_class.from_id_and_parent_path.return_value = mock_rag_config

            # Setup mock RAG tool
            mock_rag_tool = Mock()
            mock_rag_tool_class.return_value = mock_rag_tool

            # Create mock project
            mock_project = Mock(spec=Project)
            mock_project.id = "test_project_id"
            mock_project.path = Path("/test/path")

            # Create mock task with parent project
            mock_task = Mock(spec=Task)
            mock_task.parent_project.return_value = mock_project

            # Test with RAG tool ID
            tool_id = f"{RAG_TOOL_ID_PREFIX}test_rag_config"
            tool = tool_from_id(tool_id, task=mock_task)

            # Verify the tool is RagTool
            assert tool == mock_rag_tool
            mock_rag_config_class.from_id_and_parent_path.assert_called_once_with(
                "test_rag_config", Path("/test/path")
            )
            mock_rag_tool_class.assert_called_once_with(tool_id, mock_rag_config)

    def test_tool_from_id_rag_tool_no_task(self):
        """Test that RAG tool ID without task raises ValueError."""
        tool_id = f"{RAG_TOOL_ID_PREFIX}test_rag_config"

        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(tool_id, task=None)

    def test_tool_from_id_rag_tool_no_project(self):
        """Test that RAG tool ID with task but no project raises ValueError."""
        # Create mock task without parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = None

        tool_id = f"{RAG_TOOL_ID_PREFIX}test_rag_config"

        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(tool_id, task=mock_task)

    def test_tool_from_id_rag_config_not_found(self):
        """Test that RAG tool ID with missing RAG config raises ValueError."""
        from unittest.mock import patch

        with patch("kiln_ai.tools.tool_registry.RagConfig") as mock_rag_config_class:
            # Setup mock to return None (config not found)
            mock_rag_config_class.from_id_and_parent_path.return_value = None

            # Create mock project
            mock_project = Mock(spec=Project)
            mock_project.id = "test_project_id"
            mock_project.path = Path("/test/path")

            # Create mock task with parent project
            mock_task = Mock(spec=Task)
            mock_task.parent_project.return_value = mock_project

            tool_id = f"{RAG_TOOL_ID_PREFIX}missing_rag_config"

            with pytest.raises(
                ValueError,
                match="RAG config not found: missing_rag_config in project test_project_id for tool",
            ):
                tool_from_id(tool_id, task=mock_task)

    def test_all_built_in_tools_are_registered(self):
        """Test that all KilnBuiltInToolId enum members are handled by the registry."""
        for tool_id in KilnBuiltInToolId:
            # This should not raise an exception
            tool = tool_from_id(tool_id.value)
            assert tool is not None

    async def test_registry_returns_new_instances(self):
        """Test that registry returns new instances each time (not singletons)."""
        tool1 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)
        tool2 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS)

        assert tool1 is not tool2  # Different instances
        assert type(tool1) is type(tool2)  # Same type
        assert await tool1.id() == await tool2.id()  # Same id

    async def test_tool_definitions_for_math_tools(self):
        """Test sync helper returns the same definitions as direct async calls."""
        tool_ids = [
            KilnBuiltInToolId.ADD_NUMBERS.value,
            KilnBuiltInToolId.SUBTRACT_NUMBERS.value,
            KilnBuiltInToolId.MULTIPLY_NUMBERS.value,
            KilnBuiltInToolId.DIVIDE_NUMBERS.value,
        ]

        definitions = await tool_definitions_from_ids(tool_ids)

        assert len(definitions) == 4
        assert all(definition["type"] == "function" for definition in definitions)

        tool_names = [definition["function"]["name"] for definition in definitions]
        assert "add" in tool_names
        assert "subtract" in tool_names
        assert "multiply" in tool_names
        assert "divide" in tool_names

    async def test_check_tool_id_valid_built_in_tools(self):
        """Test that _check_tool_id accepts valid built-in tool IDs."""
        for tool_id in KilnBuiltInToolId:
            result = _check_tool_id(tool_id.value)
            assert result == tool_id.value

    def test_check_tool_id_invalid_tool_id(self):
        """Test that _check_tool_id raises ValueError for invalid tool ID."""
        with pytest.raises(ValueError, match="Invalid tool ID: invalid_tool_id"):
            _check_tool_id("invalid_tool_id")

    def test_check_tool_id_empty_string(self):
        """Test that _check_tool_id raises ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid tool ID: "):
            _check_tool_id("")

    def test_check_tool_id_none_value(self):
        """Test that _check_tool_id raises ValueError for None."""
        with pytest.raises(ValueError, match="Invalid tool ID: None"):
            _check_tool_id(None)  # type: ignore

    def test_check_tool_id_valid_mcp_remote_tool_id(self):
        """Test that _check_tool_id accepts valid MCP remote tool IDs."""
        valid_mcp_ids = [
            f"{MCP_REMOTE_TOOL_ID_PREFIX}server123::tool_name",
            f"{MCP_REMOTE_TOOL_ID_PREFIX}my_server::echo",
            f"{MCP_REMOTE_TOOL_ID_PREFIX}123456789::test_tool",
            f"{MCP_REMOTE_TOOL_ID_PREFIX}server_with_underscores::complex_tool_name",
        ]

        for tool_id in valid_mcp_ids:
            result = _check_tool_id(tool_id)
            assert result == tool_id

    def test_check_tool_id_valid_mcp_local_tool_id(self):
        """Test that _check_tool_id accepts valid MCP local tool IDs."""
        valid_mcp_local_ids = [
            f"{MCP_LOCAL_TOOL_ID_PREFIX}server123::tool_name",
            f"{MCP_LOCAL_TOOL_ID_PREFIX}my_local_server::calculate",
            f"{MCP_LOCAL_TOOL_ID_PREFIX}local_tool_server::process_data",
            f"{MCP_LOCAL_TOOL_ID_PREFIX}server_with_underscores::complex_tool_name",
        ]

        for tool_id in valid_mcp_local_ids:
            result = _check_tool_id(tool_id)
            assert result == tool_id

    def test_check_tool_id_invalid_mcp_remote_tool_id(self):
        """Test that _check_tool_id rejects invalid MCP-like tool IDs."""
        # These start with the prefix but have wrong format - get specific MCP error
        invalid_mcp_format_ids = [
            "mcp::remote::server",  # Missing tool name (only 3 parts instead of 4)
            "mcp::remote::",  # Missing server and tool name (only 3 parts)
            "mcp::remote::::tool",  # Empty server name (5 parts instead of 4)
            "mcp::remote::server::tool::extra",  # Too many parts (5 instead of 4)
        ]

        for invalid_id in invalid_mcp_format_ids:
            with pytest.raises(
                ValueError, match=f"Invalid remote MCP tool ID: {invalid_id}"
            ):
                _check_tool_id(invalid_id)

        # These don't match the prefix - get generic error
        invalid_generic_ids = [
            "mcp::remote:",  # Missing last colon (doesn't match full prefix)
            "mcp:remote::server::tool",  # Wrong prefix format
            "mcp::remote_server::tool",  # Wrong prefix format
            "remote::server::tool",  # Missing mcp prefix
        ]

        for invalid_id in invalid_generic_ids:
            with pytest.raises(ValueError, match=f"Invalid tool ID: {invalid_id}"):
                _check_tool_id(invalid_id)

    def test_check_tool_id_valid_kiln_task_tool_id(self):
        """Test that _check_tool_id accepts valid Kiln task tool IDs."""
        valid_kiln_task_ids = [
            f"{KILN_TASK_TOOL_ID_PREFIX}server123",
            f"{KILN_TASK_TOOL_ID_PREFIX}my_task_server",
            f"{KILN_TASK_TOOL_ID_PREFIX}123456789",
            f"{KILN_TASK_TOOL_ID_PREFIX}server_with_underscores",
            f"{KILN_TASK_TOOL_ID_PREFIX}server-with-dashes",
        ]

        for tool_id in valid_kiln_task_ids:
            result = _check_tool_id(tool_id)
            assert result == tool_id

    def test_check_tool_id_invalid_kiln_task_tool_id(self):
        """Test that _check_tool_id rejects invalid Kiln task tool IDs."""
        # These start with the prefix but have wrong format
        invalid_kiln_task_format_ids = [
            f"{KILN_TASK_TOOL_ID_PREFIX}",  # Missing server ID
            f"{KILN_TASK_TOOL_ID_PREFIX}::",  # Empty server ID
            f"{KILN_TASK_TOOL_ID_PREFIX}server::tool",  # Too many parts (3 instead of 2)
            f"{KILN_TASK_TOOL_ID_PREFIX}server::tool::extra",  # Too many parts (4 instead of 2)
        ]

        for invalid_id in invalid_kiln_task_format_ids:
            with pytest.raises(
                ValueError, match=f"Invalid Kiln task tool ID format: {invalid_id}"
            ):
                _check_tool_id(invalid_id)

        # These don't match the prefix - get generic error
        invalid_generic_ids = [
            "kiln_task:",  # Missing last colon (doesn't match full prefix)
            "kiln:task::server",  # Wrong prefix format
            "kiln_task_server",  # Missing colons
            "task::server",  # Missing kiln prefix
        ]

        for invalid_id in invalid_generic_ids:
            with pytest.raises(ValueError, match=f"Invalid tool ID: {invalid_id}"):
                _check_tool_id(invalid_id)

    def test_mcp_server_and_tool_name_from_id_valid_inputs(self):
        """Test that mcp_server_and_tool_name_from_id correctly parses valid MCP tool IDs."""
        test_cases = [
            # Remote MCP tool IDs
            ("mcp::remote::server123::tool_name", ("server123", "tool_name")),
            ("mcp::remote::my_server::echo", ("my_server", "echo")),
            ("mcp::remote::123456789::test_tool", ("123456789", "test_tool")),
            (
                "mcp::remote::server_with_underscores::complex_tool_name",
                ("server_with_underscores", "complex_tool_name"),
            ),
            ("mcp::remote::a::b", ("a", "b")),  # Minimal valid case
            (
                "mcp::remote::server-with-dashes::tool-with-dashes",
                ("server-with-dashes", "tool-with-dashes"),
            ),
            # Local MCP tool IDs
            ("mcp::local::local_server::calculate", ("local_server", "calculate")),
            ("mcp::local::my_local_tool::process", ("my_local_tool", "process")),
            (
                "mcp::local::123456789::local_test_tool",
                ("123456789", "local_test_tool"),
            ),
            (
                "mcp::local::local_server_with_underscores::complex_local_tool",
                ("local_server_with_underscores", "complex_local_tool"),
            ),
            ("mcp::local::x::y", ("x", "y")),  # Minimal valid case for local
        ]

        for tool_id, expected in test_cases:
            result = mcp_server_and_tool_name_from_id(tool_id)
            assert result == expected, (
                f"Failed for {tool_id}: expected {expected}, got {result}"
            )

    def test_mcp_server_and_tool_name_from_id_invalid_inputs(self):
        """Test that mcp_server_and_tool_name_from_id raises ValueError for invalid MCP tool IDs."""
        # Test remote MCP format errors
        remote_invalid_inputs = [
            "mcp::remote::server",  # Only 3 parts instead of 4
            "mcp::remote::",  # Only 3 parts, missing server and tool
            "mcp::remote::server::tool::extra",  # 5 parts instead of 4
        ]

        for invalid_id in remote_invalid_inputs:
            with pytest.raises(
                ValueError,
                match=r"Invalid remote MCP tool ID:.*Expected format.*mcp::remote::<server_id>::<tool_name>",
            ):
                mcp_server_and_tool_name_from_id(invalid_id)

        # Test local MCP format errors
        local_invalid_inputs = [
            "mcp::local::server",  # Only 3 parts instead of 4
            "mcp::local::",  # Only 3 parts, missing server and tool
            "mcp::local::server::tool::extra",  # 5 parts instead of 4
        ]

        for invalid_id in local_invalid_inputs:
            with pytest.raises(
                ValueError,
                match=r"Invalid local MCP tool ID:.*Expected format.*mcp::local::<server_id>::<tool_name>",
            ):
                mcp_server_and_tool_name_from_id(invalid_id)

        # Test generic MCP format errors (no valid prefix)
        generic_invalid_inputs = [
            "invalid::format::here",  # 3 parts, wrong prefix
            "",  # Empty string
            "single_part",  # No separators
            "two::parts",  # Only 2 parts
        ]

        for invalid_id in generic_invalid_inputs:
            with pytest.raises(
                ValueError,
                match=r"Invalid MCP tool ID:.*Expected format.*mcp::\(remote\|local\)::<server_id>::<tool_name>",
            ):
                mcp_server_and_tool_name_from_id(invalid_id)

    def test_mcp_server_and_tool_name_from_id_edge_cases(self):
        """Test that mcp_server_and_tool_name_from_id handles edge cases (empty parts allowed by parser)."""
        # These are valid according to the parser (exactly 4 parts),
        # but empty server_id/tool_name validation is handled by _check_tool_id
        edge_cases = [
            ("mcp::remote::::tool", ("", "tool")),  # Empty server name
            ("mcp::remote::server::", ("server", "")),  # Empty tool name
            ("mcp::remote::::", ("", "")),  # Both empty
        ]

        for tool_id, expected in edge_cases:
            result = mcp_server_and_tool_name_from_id(tool_id)
            assert result == expected, (
                f"Failed for {tool_id}: expected {expected}, got {result}"
            )

    @pytest.mark.parametrize(
        "tool_id,expected_server,expected_tool",
        [
            ("mcp::remote::test_server::test_tool", "test_server", "test_tool"),
            ("mcp::remote::s::t", "s", "t"),
            (
                "mcp::remote::long_server_name_123::complex_tool_name_456",
                "long_server_name_123",
                "complex_tool_name_456",
            ),
            (
                "mcp::local::local_test_server::local_test_tool",
                "local_test_server",
                "local_test_tool",
            ),
            ("mcp::local::l::l", "l", "l"),
            (
                "mcp::local::long_local_server_123::complex_local_tool_456",
                "long_local_server_123",
                "complex_local_tool_456",
            ),
        ],
    )
    def test_mcp_server_and_tool_name_from_id_parametrized(
        self, tool_id, expected_server, expected_tool
    ):
        """Parametrized test for mcp_server_and_tool_name_from_id with various valid inputs."""
        server_id, tool_name = mcp_server_and_tool_name_from_id(tool_id)
        assert server_id == expected_server
        assert tool_name == expected_tool

    def test_kiln_task_server_id_from_tool_id_valid_inputs(self):
        """Test that kiln_task_server_id_from_tool_id correctly parses valid Kiln task tool IDs."""
        test_cases = [
            ("kiln_task::server123", "server123"),
            ("kiln_task::my_task_server", "my_task_server"),
            ("kiln_task::123456789", "123456789"),
            ("kiln_task::server_with_underscores", "server_with_underscores"),
            ("kiln_task::server-with-dashes", "server-with-dashes"),
            ("kiln_task::a", "a"),  # Minimal valid case
            (
                "kiln_task::very_long_server_name_with_numbers_123",
                "very_long_server_name_with_numbers_123",
            ),
        ]

        for tool_id, expected_server_id in test_cases:
            result = kiln_task_server_id_from_tool_id(tool_id)
            assert result == expected_server_id, (
                f"Failed for {tool_id}: expected {expected_server_id}, got {result}"
            )

    def test_kiln_task_server_id_from_tool_id_invalid_inputs(self):
        """Test that kiln_task_server_id_from_tool_id raises ValueError for invalid Kiln task tool IDs."""
        invalid_inputs = [
            "kiln_task::",  # Empty server ID
            "kiln_task::server::tool",  # Too many parts (3 instead of 2)
            "kiln_task::server::tool::extra",  # Too many parts (4 instead of 2)
            "invalid::format",  # Wrong prefix
            "",  # Empty string
            "single_part",  # No separators
            "two::parts",  # Only 2 parts but wrong prefix
            "kiln_task",  # Missing colons
        ]

        for invalid_id in invalid_inputs:
            with pytest.raises(
                ValueError,
                match=r"Invalid Kiln task tool ID format:.*Expected format.*kiln_task::<server_id>",
            ):
                kiln_task_server_id_from_tool_id(invalid_id)

    @pytest.mark.parametrize(
        "tool_id,expected_server_id",
        [
            ("kiln_task::test_server", "test_server"),
            ("kiln_task::s", "s"),
            ("kiln_task::long_server_name_123", "long_server_name_123"),
            ("kiln_task::server-with-dashes", "server-with-dashes"),
            ("kiln_task::server_with_underscores", "server_with_underscores"),
        ],
    )
    def test_kiln_task_server_id_from_tool_id_parametrized(
        self, tool_id, expected_server_id
    ):
        """Parametrized test for kiln_task_server_id_from_tool_id with various valid inputs."""
        server_id = kiln_task_server_id_from_tool_id(tool_id)
        assert server_id == expected_server_id

    def test_tool_from_id_mcp_missing_task_raises_error(self):
        """Test that MCP tool ID with missing task raises ValueError."""
        mcp_tool_id = f"{MCP_REMOTE_TOOL_ID_PREFIX}test_server::test_tool"

        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(mcp_tool_id, task=None)

    def test_tool_from_id_mcp_functional_case(self):
        """Test that MCP tool ID with valid task and project returns MCPServerTool."""
        # Create mock external tool server
        mock_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test MCP server",
            properties={
                "server_url": "https://example.com",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        mcp_tool_id = f"{MCP_REMOTE_TOOL_ID_PREFIX}{mock_server.id}::test_tool"

        tool = tool_from_id(mcp_tool_id, task=mock_task)

        assert isinstance(tool, MCPServerTool)
        # Verify the tool was created with the correct server and tool name
        assert tool._tool_server_model == mock_server
        assert tool._name == "test_tool"

    def test_tool_from_id_mcp_no_server_found_raises_error(self):
        """Test that MCP tool ID with server not found raises ValueError."""
        # Create mock external tool server with different ID
        mock_server = ExternalToolServer(
            name="different_server",
            type=ToolServerType.remote_mcp,
            description="Different MCP server",
            properties={
                "server_url": "https://example.com",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Use a tool ID with a server that doesn't exist in the project
        mcp_tool_id = f"{MCP_REMOTE_TOOL_ID_PREFIX}nonexistent_server::test_tool"

        with pytest.raises(
            ValueError,
            match="External tool server not found: nonexistent_server in project ID test_project_id",
        ):
            tool_from_id(mcp_tool_id, task=mock_task)

    def test_tool_from_id_kiln_task_tool_success(self):
        """Test that tool_from_id works with Kiln task tool IDs."""
        # Create mock external tool server for Kiln task
        mock_server = ExternalToolServer(
            name="test_kiln_task_server",
            type=ToolServerType.kiln_task,
            description="Test Kiln task server",
            properties={
                "name": "test_task_tool",
                "description": "A test task tool",
                "task_id": "test_task_123",
                "run_config_id": "test_config_456",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Test with Kiln task tool ID
        tool_id = f"{KILN_TASK_TOOL_ID_PREFIX}{mock_server.id}"
        tool = tool_from_id(tool_id, task=mock_task)

        # Verify the tool is KilnTaskTool
        assert isinstance(tool, KilnTaskTool)
        assert tool._project_id == "test_project_id"
        assert tool._tool_id == tool_id
        assert tool._tool_server_model == mock_server

    def test_tool_from_id_kiln_task_tool_no_task(self):
        """Test that Kiln task tool ID without task raises ValueError."""
        tool_id = f"{KILN_TASK_TOOL_ID_PREFIX}test_server"
        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(tool_id, task=None)

    def test_tool_from_id_kiln_task_tool_no_project(self):
        """Test that Kiln task tool ID with task but no project raises ValueError."""
        # Create mock task without parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = None

        tool_id = f"{KILN_TASK_TOOL_ID_PREFIX}test_server"

        with pytest.raises(
            ValueError,
            match=r"Unable to resolve tool from id.*Requires a parent project/task",
        ):
            tool_from_id(tool_id, task=mock_task)

    def test_tool_from_id_kiln_task_tool_server_not_found(self):
        """Test that Kiln task tool ID with server not found raises ValueError."""
        # Create mock external tool server with different ID
        mock_server = ExternalToolServer(
            name="different_server",
            type=ToolServerType.kiln_task,
            description="Different Kiln task server",
            properties={
                "name": "different_tool",
                "description": "A different task tool",
                "task_id": "different_task_123",
                "run_config_id": "different_config_456",
                "is_archived": False,
            },
        )

        # Create mock project with the external tool server
        mock_project = Mock(spec=Project)
        mock_project.id = "test_project_id"
        mock_project.external_tool_servers.return_value = [mock_server]

        # Create mock task with parent project
        mock_task = Mock(spec=Task)
        mock_task.parent_project.return_value = mock_project

        # Use a tool ID with a server that doesn't exist in the project
        tool_id = f"{KILN_TASK_TOOL_ID_PREFIX}nonexistent_server"

        with pytest.raises(
            ValueError,
            match="Kiln Task External tool server not found: nonexistent_server in project ID test_project_id",
        ):
            tool_from_id(tool_id, task=mock_task)
