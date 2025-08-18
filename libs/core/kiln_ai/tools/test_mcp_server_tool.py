from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.project import Project
from kiln_ai.tools.mcp_server import MCPServer
from kiln_ai.tools.mcp_server_tool import MCPServerTool


@pytest.fixture
def mock_project(tmp_path):
    """Create a mock project for testing."""
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()

    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    return project


@pytest.fixture
def mock_external_tool_server(mock_project):
    """Create a mock external tool server for testing."""
    return ExternalToolServer(
        name="test_mcp_server",
        type=ToolServerType.remote_mcp,
        description="Test MCP server",
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer test-token"},
        },
        parent=mock_project,
    )


@pytest.fixture
def mock_mcp_server(mock_external_tool_server):
    """Create a mock MCP server for testing."""
    return MCPServer(mock_external_tool_server)


@pytest.fixture
def mock_tool():
    """Create a mock Tool object for testing."""
    return Tool(
        name="test_tool",
        description="A test tool for unit testing",
        inputSchema={"type": "object", "properties": {}},
    )


class TestMCPServerTool:
    """Test the MCPServerTool class."""

    def test_init(self, mock_mcp_server, mock_tool):
        """Test MCPServerTool initialization."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)

        assert tool._server == mock_mcp_server
        assert tool._tool == mock_tool
        assert tool.name() == "test_tool"

    def test_run(self, mock_mcp_server, mock_tool):
        """Test the run method returns expected value."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)
        result = tool.run()

        assert result == "Hello, world!"

    def test_run_with_kwargs(self, mock_mcp_server, mock_tool):
        """Test the run method ignores kwargs."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)
        result = tool.run(param1="value1", param2="value2")

        assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_mcp_server, mock_tool):
        """Test successful call_tool execution."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)

        # Mock the expected return value
        mock_result = CallToolResult(content=[])

        with (
            patch("kiln_ai.tools.mcp_server_tool.streamablehttp_client") as mock_client,
            patch("kiln_ai.tools.mcp_server_tool.ClientSession") as mock_session_class,
        ):
            # Setup mock context managers
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_client.return_value.__aenter__.return_value = mock_streams

            mock_session = AsyncMock()
            mock_session.call_tool.return_value = mock_result
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Call the method
            result = await tool.call_tool(param1="value1", param2="value2")

            # Verify the result
            assert result == mock_result

            # Verify the session was called correctly
            mock_session.initialize.assert_called_once()
            mock_session.call_tool.assert_called_once_with(
                name="test_tool", arguments={"param1": "value1", "param2": "value2"}
            )

    @pytest.mark.asyncio
    async def test_call_tool_empty_kwargs(self, mock_mcp_server, mock_tool):
        """Test call_tool works with no arguments."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)
        mock_result = CallToolResult(content=[])

        with (
            patch("kiln_ai.tools.mcp_server_tool.streamablehttp_client") as mock_client,
            patch("kiln_ai.tools.mcp_server_tool.ClientSession") as mock_session_class,
        ):
            # Setup mock context managers
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_client.return_value.__aenter__.return_value = mock_streams

            mock_session = AsyncMock()
            mock_session.call_tool.return_value = mock_result
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Call the method with no arguments
            result = await tool.call_tool()

            # Verify the session was called correctly
            mock_session.call_tool.assert_called_once_with(
                name="test_tool", arguments={}
            )
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_call_tool_session_error(self, mock_mcp_server, mock_tool):
        """Test call_tool handles session errors properly."""
        tool = MCPServerTool(mock_mcp_server, mock_tool)

        with (
            patch("kiln_ai.tools.mcp_server_tool.streamablehttp_client") as mock_client,
            patch("kiln_ai.tools.mcp_server_tool.ClientSession") as mock_session_class,
        ):
            # Setup mock context managers
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_client.return_value.__aenter__.return_value = mock_streams

            mock_session = AsyncMock()
            mock_session.call_tool.side_effect = Exception("Connection failed")
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Verify the exception propagates
            with pytest.raises(Exception, match="Connection failed"):
                await tool.call_tool()


class TestMCPServerToolIntegration:
    """Integration tests for MCPServerTool using real services."""

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_call_tool_success(self):
        """Test successful call_tool execution."""
        external_tool_server = ExternalToolServer(
            name="postman_echo",
            type=ToolServerType.remote_mcp,
            description="Postman Echo MCP Server for testing",
            properties={
                "server_url": "https://postman-echo-mcp.fly.dev/",
                "headers": {},
            },
        )

        # Create MCP server using Postman Echo MCP server with 'echo' tool
        mcp_server = MCPServer(external_tool_server)
        tool = await mcp_server.get_tool("echo")

        test_message = "Hello, world!"
        result = await tool.call_tool(message=test_message)

        # First block should be TextContent
        assert len(result.content) > 0
        text_content = result.content[0]
        assert isinstance(text_content, TextContent)
        print("text_content: ", text_content)
        assert (
            text_content.text == "Tool echo: " + test_message
        )  # 'Tool echo: Hello, world!'
