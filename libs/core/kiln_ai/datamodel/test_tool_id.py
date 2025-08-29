import pytest
from pydantic import BaseModel, ValidationError

from kiln_ai.datamodel.tool_id import (
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    ToolId,
    _check_tool_id,
    mcp_server_and_tool_name_from_id,
)


class TestKilnBuiltInToolId:
    """Test the KilnBuiltInToolId enum."""

    def test_enum_values(self):
        """Test that enum has expected values."""
        assert KilnBuiltInToolId.ADD_NUMBERS == "kiln_tool::add_numbers"
        assert KilnBuiltInToolId.SUBTRACT_NUMBERS == "kiln_tool::subtract_numbers"
        assert KilnBuiltInToolId.MULTIPLY_NUMBERS == "kiln_tool::multiply_numbers"
        assert KilnBuiltInToolId.DIVIDE_NUMBERS == "kiln_tool::divide_numbers"
        for enum_value in KilnBuiltInToolId.__members__.values():
            assert _check_tool_id(enum_value) == enum_value

    def test_enum_membership(self):
        """Test enum membership checks."""
        assert "kiln_tool::add_numbers" in KilnBuiltInToolId.__members__.values()
        assert "invalid_tool" not in KilnBuiltInToolId.__members__.values()


class TestCheckToolId:
    """Test the _check_tool_id validation function."""

    def test_valid_builtin_tools(self):
        """Test validation of valid built-in tools."""
        for tool_id in KilnBuiltInToolId:
            result = _check_tool_id(tool_id.value)
            assert result == tool_id.value

    def test_valid_mcp_remote_tools(self):
        """Test validation of valid MCP remote tools."""
        valid_ids = [
            "mcp::remote::server1::tool1",
            "mcp::remote::my_server::my_tool",
            "mcp::remote::test::function_name",
        ]
        for tool_id in valid_ids:
            result = _check_tool_id(tool_id)
            assert result == tool_id

    def test_valid_mcp_local_tools(self):
        """Test validation of valid MCP local tools."""
        valid_ids = [
            "mcp::local::server1::tool1",
            "mcp::local::my_server::my_tool",
            "mcp::local::test::function_name",
        ]
        for tool_id in valid_ids:
            result = _check_tool_id(tool_id)
            assert result == tool_id

    def test_invalid_empty_or_none(self):
        """Test validation fails for empty or None values."""
        with pytest.raises(ValueError, match="Invalid tool ID"):
            _check_tool_id("")

        with pytest.raises(ValueError, match="Invalid tool ID"):
            _check_tool_id(None)  # type: ignore

    def test_invalid_non_string(self):
        """Test validation fails for non-string values."""
        with pytest.raises(ValueError, match="Invalid tool ID"):
            _check_tool_id(123)  # type: ignore

        with pytest.raises(ValueError, match="Invalid tool ID"):
            _check_tool_id(["tool"])  # type: ignore

    def test_invalid_unknown_tool(self):
        """Test validation fails for unknown tool IDs."""
        with pytest.raises(ValueError, match="Invalid tool ID: unknown_tool"):
            _check_tool_id("unknown_tool")

    def test_invalid_mcp_format(self):
        """Test validation fails for invalid MCP tool formats."""
        # These IDs start with the MCP remote prefix but have invalid formats
        mcp_remote_invalid_ids = [
            "mcp::remote::",  # Missing server and tool
            "mcp::remote::server",  # Missing tool
            "mcp::remote::server::",  # Empty tool name
            "mcp::remote::::tool",  # Empty server name
            "mcp::remote::server::tool::extra",  # Too many parts
        ]

        for invalid_id in mcp_remote_invalid_ids:
            with pytest.raises(ValueError, match="Invalid remote MCP tool ID"):
                _check_tool_id(invalid_id)

        # These IDs start with the MCP local prefix but have invalid formats
        mcp_local_invalid_ids = [
            "mcp::local::",  # Missing server and tool
            "mcp::local::server",  # Missing tool
            "mcp::local::server::",  # Empty tool name
            "mcp::local::::tool",  # Empty server name
            "mcp::local::server::tool::extra",  # Too many parts
        ]

        for invalid_id in mcp_local_invalid_ids:
            with pytest.raises(ValueError, match="Invalid local MCP tool ID"):
                _check_tool_id(invalid_id)

        # This ID doesn't start with MCP prefix so gets generic error
        with pytest.raises(ValueError, match="Invalid tool ID"):
            _check_tool_id("mcp::wrong::server::tool")


class TestMcpServerAndToolNameFromId:
    """Test the mcp_server_and_tool_name_from_id function."""

    def test_valid_mcp_ids(self):
        """Test parsing valid MCP tool IDs."""
        test_cases = [
            # Remote MCP tools
            ("mcp::remote::server1::tool1", ("server1", "tool1")),
            ("mcp::remote::my_server::my_tool", ("my_server", "my_tool")),
            ("mcp::remote::test::function_name", ("test", "function_name")),
            # Local MCP tools
            ("mcp::local::server1::tool1", ("server1", "tool1")),
            ("mcp::local::my_server::my_tool", ("my_server", "my_tool")),
            ("mcp::local::test::function_name", ("test", "function_name")),
        ]

        for tool_id, expected in test_cases:
            result = mcp_server_and_tool_name_from_id(tool_id)
            assert result == expected

    def test_invalid_mcp_ids(self):
        """Test parsing fails for invalid MCP tool IDs."""
        # Test remote MCP tool ID errors
        remote_invalid_ids = [
            "mcp::remote::",  # Only 3 parts
            "mcp::remote::server",  # Only 3 parts
            "mcp::remote::server::tool::extra",  # 5 parts
        ]

        for invalid_id in remote_invalid_ids:
            with pytest.raises(ValueError, match="Invalid remote MCP tool ID"):
                mcp_server_and_tool_name_from_id(invalid_id)

        # Test local MCP tool ID errors
        local_invalid_ids = [
            "mcp::local::",  # Only 3 parts
            "mcp::local::server",  # Only 3 parts
            "mcp::local::server::tool::extra",  # 5 parts
        ]

        for invalid_id in local_invalid_ids:
            with pytest.raises(ValueError, match="Invalid local MCP tool ID"):
                mcp_server_and_tool_name_from_id(invalid_id)

        # Test generic MCP tool ID errors (not remote or local)
        generic_invalid_ids = [
            "not_mcp_format",  # Only 1 part
            "single_part",  # Only 1 part
            "",  # Empty string
        ]

        for invalid_id in generic_invalid_ids:
            with pytest.raises(ValueError, match="Invalid MCP tool ID"):
                mcp_server_and_tool_name_from_id(invalid_id)

    def test_mcp_ids_with_wrong_prefix_still_parse(self):
        """Test that IDs with wrong prefix but correct structure still parse (validation happens elsewhere)."""
        # This function only checks structure (4 parts), not content
        result = mcp_server_and_tool_name_from_id("mcp::wrong::server::tool")
        assert result == ("server", "tool")


class TestToolIdPydanticType:
    """Test the ToolId pydantic type annotation."""

    class _ModelWithToolId(BaseModel):
        tool_id: ToolId

    def test_valid_builtin_tools(self):
        """Test ToolId validates built-in tools."""
        for tool_id in KilnBuiltInToolId:
            model = self._ModelWithToolId(tool_id=tool_id.value)
            assert model.tool_id == tool_id.value

    def test_valid_mcp_tools(self):
        """Test ToolId validates MCP remote and local tools."""
        valid_ids = [
            # Remote MCP tools
            "mcp::remote::server1::tool1",
            "mcp::remote::my_server::my_tool",
            # Local MCP tools
            "mcp::local::server1::tool1",
            "mcp::local::my_server::my_tool",
        ]

        for tool_id in valid_ids:
            model = self._ModelWithToolId(tool_id=tool_id)
            assert model.tool_id == tool_id

    def test_invalid_tools_raise_validation_error(self):
        """Test ToolId raises ValidationError for invalid tools."""
        invalid_ids = [
            "",
            "unknown_tool",
            "mcp::remote::",
            "mcp::remote::server",
            "mcp::local::",
            "mcp::local::server",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValidationError):
                self._ModelWithToolId(tool_id=invalid_id)

    def test_non_string_raises_validation_error(self):
        """Test ToolId raises ValidationError for non-string values."""
        with pytest.raises(ValidationError):
            self._ModelWithToolId(tool_id=123)  # type: ignore

        with pytest.raises(ValidationError):
            self._ModelWithToolId(tool_id=None)  # type: ignore


class TestConstants:
    """Test module constants."""

    def test_mcp_remote_tool_id_prefix(self):
        """Test the MCP remote tool ID prefix constant."""
        assert MCP_REMOTE_TOOL_ID_PREFIX == "mcp::remote::"

    def test_mcp_local_tool_id_prefix(self):
        """Test the MCP local tool ID prefix constant."""
        assert MCP_LOCAL_TOOL_ID_PREFIX == "mcp::local::"
