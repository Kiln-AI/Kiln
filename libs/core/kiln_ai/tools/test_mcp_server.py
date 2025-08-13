from unittest.mock import AsyncMock, Mock, patch

import pytest

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_server import MCPServer


class TestMCPServer:
    """Test the MCPServer class."""

    def test_init_with_valid_external_tool_server(self):
        """Test MCPServer initialization with a valid ExternalToolServer."""
        external_tool_server = ExternalToolServer(
            name="test_mcp_server",
            type=ToolServerType.remote_mcp,
            description="A test MCP server",
            properties={
                "server_url": "https://test.example.com",
                "headers": {"Authorization": "Bearer test-token"},
            },
        )

        # Should not raise any exceptions
        mcp_server = MCPServer(external_tool_server)
        assert mcp_server is not None

    def test_init_with_no_description(self):
        """Test MCPServer initialization when ExternalToolServer has no description."""
        external_tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://test.example.com",
                "headers": {},
            },
        )

        # Should not raise any exceptions even without description
        mcp_server = MCPServer(external_tool_server)
        assert mcp_server is not None

    def test_init_with_invalid_tool_server_type(self):
        """Test MCPServer raises error when initialized with wrong server type."""
        # We can't create an ExternalToolServer with an invalid type due to enum validation,
        # so we'll test by creating a mock object
        invalid_tool_server = Mock()
        invalid_tool_server.type = "invalid_type"

        with pytest.raises(
            ValueError,
            match="MCPServer can only be initialized with a remote MCP server",
        ):
            MCPServer(invalid_tool_server)

    def test_init_missing_server_url(self):
        """Test MCPServer raises error when server_url is missing."""
        # ExternalToolServer validation prevents creation with missing server_url,
        # so we test this by creating a mock or by testing that ExternalToolServer itself validates
        from pydantic import ValidationError

        with pytest.raises(
            ValidationError,
            match="server_url must be a string for external tools of type remote_mcp",
        ):
            ExternalToolServer(
                name="test_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "headers": {},
                },
            )

    def test_init_with_empty_headers(self):
        """Test MCPServer initialization with empty headers."""
        external_tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://test.example.com",
                "headers": {},
            },
        )

        # Should not raise any exceptions with empty headers
        mcp_server = MCPServer(external_tool_server)
        assert mcp_server is not None

    @pytest.mark.asyncio
    async def test_mcp_client_missing_server_url(self):
        """Test that mcp_client raises error when server_url is missing."""
        # Create a mock external tool server with no server_url
        mock_tool_server = Mock()
        mock_tool_server.type = ToolServerType.remote_mcp
        mock_tool_server.properties = {"headers": {}}

        mcp_server = MCPServer.__new__(
            MCPServer
        )  # Create without calling __init__ validation
        mcp_server._tool_server = mock_tool_server

        with pytest.raises(ValueError, match="server_url is required"):
            async with mcp_server.mcp_client():
                pass

    @pytest.mark.asyncio
    async def test_list_tools_success(self):
        """Test successful list_tools call."""
        # Mock the MCP client session
        mock_session = AsyncMock()
        mock_tools_result = Mock()
        mock_session.list_tools.return_value = mock_tools_result

        external_tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://test.example.com",
                "headers": {"Content-Type": "application/json"},
            },
        )

        mcp_server = MCPServer(external_tool_server)

        # Mock the mcp_client context manager to return our mock session
        with patch.object(mcp_server, "mcp_client") as mock_mcp_client:
            mock_mcp_client.return_value.__aenter__.return_value = mock_session
            mock_mcp_client.return_value.__aexit__.return_value = None

            result = await mcp_server.list_tools()

            assert result == mock_tools_result
            mock_session.initialize.assert_called_once()
            mock_session.list_tools.assert_called_once()
            mock_mcp_client.assert_called_once()


class TestMCPServerIntegration:
    """Integration tests for MCPServer using real services."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Integration test, requires hitting real MCP server")
    async def test_list_tools_with_real_mcp_server(self):
        """Test list_tools with a real MCP server if available."""
        external_tool_server = ExternalToolServer(
            name="postman_echo",
            type=ToolServerType.remote_mcp,
            description="Postman Echo MCP Server for testing",
            properties={
                "server_url": "https://postman-echo-mcp.fly.dev/",
                "headers": {},
            },
        )

        mcp_server = MCPServer(external_tool_server)

        try:
            tools = await mcp_server.list_tools()
            # If we get here, the call succeeded
            # The result should be a ListToolsResult from the MCP library

            print("tools: ", tools)
            assert tools is not None
            # We can't make specific assertions about the structure since it's an MCP type
            # but at least we know the connection worked
        except Exception as e:
            # For integration tests, we allow network failures but check for implementation errors
            error_str = str(e)
            error_type = type(e).__name__
            if "server_url is required" in error_str:
                pytest.fail(
                    f"Implementation error - server_url not properly configured: {error_str}"
                )
            elif any(
                keyword in error_str.lower()
                for keyword in ["connection", "timeout", "network"]
            ) or any(
                keyword in error_type.lower()
                for keyword in [
                    "closedresourceerror",
                    "connectionerror",
                    "networkerror",
                ]
            ):
                pytest.skip(
                    f"Network connectivity issue in test environment: {error_type}: {error_str}"
                )
            else:
                # Unexpected error - should fail the test
                pytest.fail(
                    f"Unexpected error from list_tools method: {error_type}: {error_str}"
                )
