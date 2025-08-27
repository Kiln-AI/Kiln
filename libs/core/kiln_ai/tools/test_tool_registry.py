import pytest

from kiln_ai.tools.built_in_tools.math_tools import (
    AddTool,
    DivideTool,
    MultiplyTool,
    SubtractTool,
)
from kiln_ai.tools.tool_id import (
    MCP_REMOTE_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    _check_tool_id,
    mcp_server_and_tool_name_from_id,
)
from kiln_ai.tools.tool_registry import tool_from_id


class TestToolRegistry:
    """Test the tool registry functionality."""

    async def test_tool_from_id_add_numbers(self):
        """Test that ADD_NUMBERS tool ID returns AddTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS, "test-project")

        assert isinstance(tool, AddTool)
        assert await tool.id() == KilnBuiltInToolId.ADD_NUMBERS
        assert await tool.name() == "add"
        assert "Add two numbers" in await tool.description()

    async def test_tool_from_id_subtract_numbers(self):
        """Test that SUBTRACT_NUMBERS tool ID returns SubtractTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.SUBTRACT_NUMBERS, "test-project")

        assert isinstance(tool, SubtractTool)
        assert await tool.id() == KilnBuiltInToolId.SUBTRACT_NUMBERS
        assert await tool.name() == "subtract"

    async def test_tool_from_id_multiply_numbers(self):
        """Test that MULTIPLY_NUMBERS tool ID returns MultiplyTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.MULTIPLY_NUMBERS, "test-project")

        assert isinstance(tool, MultiplyTool)
        assert await tool.id() == KilnBuiltInToolId.MULTIPLY_NUMBERS
        assert await tool.name() == "multiply"

    async def test_tool_from_id_divide_numbers(self):
        """Test that DIVIDE_NUMBERS tool ID returns DivideTool instance."""
        tool = tool_from_id(KilnBuiltInToolId.DIVIDE_NUMBERS, "test-project")

        assert isinstance(tool, DivideTool)
        assert await tool.id() == KilnBuiltInToolId.DIVIDE_NUMBERS
        assert await tool.name() == "divide"

    async def test_tool_from_id_with_string_values(self):
        """Test that tool_from_id works with string values of enum members."""
        tool = tool_from_id("kiln_tool::add_numbers", "test-project")

        assert isinstance(tool, AddTool)
        assert await tool.id() == KilnBuiltInToolId.ADD_NUMBERS

    async def test_tool_from_id_invalid_tool_id(self):
        """Test that invalid tool ID raises ValueError."""
        with pytest.raises(
            ValueError, match="Tool ID invalid_tool_id not found in tool registry"
        ):
            tool_from_id("invalid_tool_id", "test-project")

    def test_tool_from_id_empty_string(self):
        """Test that empty string tool ID raises ValueError."""
        with pytest.raises(ValueError, match="Tool ID  not found in tool registry"):
            tool_from_id("", "test-project")

    def test_all_built_in_tools_are_registered(self):
        """Test that all KilnBuiltInToolId enum members are handled by the registry."""
        for tool_id in KilnBuiltInToolId:
            # This should not raise an exception
            tool = tool_from_id(tool_id.value, "test-project")
            assert tool is not None

    async def test_registry_returns_new_instances(self):
        """Test that registry returns new instances each time (not singletons)."""
        tool1 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS, "test-project")
        tool2 = tool_from_id(KilnBuiltInToolId.ADD_NUMBERS, "test-project")

        assert tool1 is not tool2  # Different instances
        assert type(tool1) is type(tool2)  # Same type
        assert await tool1.id() == await tool2.id()  # Same id

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
                ValueError, match=f"Invalid MCP remote tool ID: {invalid_id}"
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

    def test_mcp_server_and_tool_name_from_id_valid_inputs(self):
        """Test that mcp_server_and_tool_name_from_id correctly parses valid MCP tool IDs."""
        test_cases = [
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
                match=r"Invalid MCP remote tool ID:.*Expected format.*mcp::remote::<server_id>::<tool_name>",
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
                match=r"Invalid MCP local tool ID:.*Expected format.*mcp::local::<server_id>::<tool_name>",
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
        ],
    )
    def test_mcp_server_and_tool_name_from_id_parametrized(
        self, tool_id, expected_server, expected_tool
    ):
        """Parametrized test for mcp_server_and_tool_name_from_id with various valid inputs."""
        server_id, tool_name = mcp_server_and_tool_name_from_id(tool_id)
        assert server_id == expected_server
        assert tool_name == expected_tool
