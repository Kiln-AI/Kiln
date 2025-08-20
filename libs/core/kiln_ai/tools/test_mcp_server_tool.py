from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import (
    CallToolResult,
    ContentBlock,
    ImageContent,
    ListToolsResult,
    TextContent,
    Tool,
)

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_server_tool import MCPServerTool
from kiln_ai.tools.tool_id import MCP_REMOTE_TOOL_ID_PREFIX


class TestMCPServerTool:
    """Unit tests for MCPServerTool."""

    def test_constructor(self):
        """Test MCPServerTool initialization."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )

        tool = MCPServerTool(server, "test_tool")

        # Check ID pattern - uses server's generated ID, not name
        assert tool.id().startswith(MCP_REMOTE_TOOL_ID_PREFIX)
        assert tool.id().endswith("::test_tool")
        assert tool.name() == "test_tool"
        assert tool.description() == "Not Loaded"
        assert tool._parameters_schema == {"type": "object", "properties": {}}
        assert tool._tool_server_model == server
        assert tool._tool is None

    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    def test_run_success(self, mock_session_manager):
        """Test successful run() execution."""
        # Setup mocks
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Success result")]
        call_result = CallToolResult(
            content=cast(list[ContentBlock], result_content), isError=False
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        result = tool.run(param1="value1", param2="value2")

        assert result == "Success result"
        mock_session.call_tool.assert_called_once_with(
            name="test_tool", arguments={"param1": "value1", "param2": "value2"}
        )

    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    def test_run_empty_content(self, mock_session_manager):
        """Test run() with empty content raises ValueError."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        call_result = CallToolResult(
            content=cast(list[ContentBlock], []), isError=False
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        with pytest.raises(ValueError, match="Tool returned no content"):
            tool.run()

    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    def test_run_non_text_content_error(self, mock_session_manager):
        """Test run() raises error when first content is not TextContent."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [
            ImageContent(type="image", data="base64data", mimeType="image/png")
        ]
        call_result = CallToolResult(
            content=cast(list[ContentBlock], result_content), isError=False
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        with pytest.raises(ValueError, match="First block must be a text block"):
            tool.run()

    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    def test_run_error_result(self, mock_session_manager):
        """Test run() raises error when tool returns isError=True."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Error occurred")]
        call_result = CallToolResult(
            content=cast(list[ContentBlock], result_content), isError=True
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        with pytest.raises(ValueError, match="Tool test_tool returned an error"):
            tool.run()

    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    def test_run_multiple_content_blocks_error(self, mock_session_manager):
        """Test run() raises error when tool returns multiple content blocks."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [
            TextContent(type="text", text="First block"),
            TextContent(type="text", text="Second block"),
        ]
        call_result = CallToolResult(
            content=cast(list[ContentBlock], result_content), isError=False
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        with pytest.raises(
            ValueError, match="Tool returned multiple content blocks, expected one"
        ):
            tool.run()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_call_tool_success(self, mock_session_manager):
        """Test _call_tool() method."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Async result")]
        call_result = CallToolResult(
            content=cast(list[ContentBlock], result_content), isError=False
        )
        mock_session.call_tool.return_value = call_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        result = await tool._call_tool(arg1="test", arg2=123)

        assert result == call_result
        mock_session.call_tool.assert_called_once_with(
            name="test_tool", arguments={"arg1": "test", "arg2": 123}
        )

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_get_tool_success(self, mock_session_manager):
        """Test _get_tool() method finds tool successfully."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        # Mock tools list
        target_tool = Tool(
            name="target_tool",
            description="Target tool description",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        )
        other_tool = Tool(name="other_tool", description="Other tool", inputSchema={})

        tools_result = ListToolsResult(tools=[other_tool, target_tool])
        mock_session.list_tools.return_value = tools_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "target_tool")

        result = await tool._get_tool("target_tool")

        assert result == target_tool
        mock_session.list_tools.assert_called_once()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_get_tool_not_found(self, mock_session_manager):
        """Test _get_tool() raises error when tool not found."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        # Mock tools list without target tool
        other_tool = Tool(name="other_tool", description="Other tool", inputSchema={})
        tools_result = ListToolsResult(tools=[other_tool])
        mock_session.list_tools.return_value = tools_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "missing_tool")

        with pytest.raises(ValueError, match="Tool missing_tool not found"):
            await tool._get_tool("missing_tool")

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_load_tool_properties_success(self, mock_session_manager):
        """Test _load_tool_properties() updates tool properties."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        # Mock tool with properties
        tool_def = Tool(
            name="test_tool",
            description="Loaded tool description",
            inputSchema={"type": "object", "properties": {"param": {"type": "string"}}},
        )
        tools_result = ListToolsResult(tools=[tool_def])
        mock_session.list_tools.return_value = tools_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        # Verify initial state
        assert tool.description() == "Not Loaded"
        assert tool._parameters_schema == {"type": "object", "properties": {}}
        assert tool._tool is None

        await tool._load_tool_properties()

        # Verify updated state
        assert tool.description() == "Loaded tool description"
        assert tool._parameters_schema == {
            "type": "object",
            "properties": {"param": {"type": "string"}},
        }
        assert tool._tool == tool_def

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_load_tool_properties_no_description(self, mock_session_manager):
        """Test _load_tool_properties() handles missing description."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        # Mock tool without description
        tool_def = Tool(name="test_tool", description=None, inputSchema={})
        tools_result = ListToolsResult(tools=[tool_def])
        mock_session.list_tools.return_value = tools_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        await tool._load_tool_properties()

        assert tool.description() == "N/A"

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_load_tool_properties_no_input_schema(self, mock_session_manager):
        """Test _load_tool_properties() handles missing inputSchema."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        # Mock tool without inputSchema - actually test with empty dict since None is not allowed
        tool_def = Tool(name="test_tool", description="Test tool", inputSchema={})
        tools_result = ListToolsResult(tools=[tool_def])
        mock_session.list_tools.return_value = tools_result

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        await tool._load_tool_properties()

        # Should be empty object for now, our JSON schema validation will fail if properties are missing
        assert tool._parameters_schema == {"type": "object", "properties": {}}

    def test_toolcall_definition(self):
        """Test toolcall_definition() returns proper OpenAI format."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com",
                "headers": {},
            },
        )
        tool = MCPServerTool(server, "test_tool")

        # Update properties to test the definition
        tool._description = "Test tool description"
        tool._parameters_schema = {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "First parameter"}
            },
            "required": ["param1"],
        }

        definition = tool.toolcall_definition()

        expected = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Test tool description",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "First parameter"}
                    },
                    "required": ["param1"],
                },
            },
        }

        assert definition == expected


class TestMCPServerToolIntegration:
    """Integration tests for MCPServerTool using real services."""

    external_tool_server = ExternalToolServer(
        name="postman_echo",
        type=ToolServerType.remote_mcp,
        description="Postman Echo MCP Server for testing",
        properties={
            "server_url": "https://postman-echo-mcp.fly.dev/",
            "headers": {},
        },
    )

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_call_tool_success(self):
        """Test successful call_tool execution."""
        # Create MCP server using Postman Echo MCP server with 'echo' tool
        tool = MCPServerTool(self.external_tool_server, "echo")

        test_message = "Hello, world!"
        result = await tool._call_tool(message=test_message)

        # First block should be TextContent
        assert len(result.content) > 0
        text_content = result.content[0]
        assert isinstance(text_content, TextContent)
        print("text_content: ", text_content)
        assert (
            text_content.text == "Tool echo: " + test_message
        )  # 'Tool echo: Hello, world!'

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    def test_tool_run(self):
        tool = MCPServerTool(self.external_tool_server, "echo")
        test_message = "Hello, world!"

        run_result = tool.run(message=test_message)
        print("run_result: ", run_result)
        assert run_result == "Tool echo: " + test_message

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_get_tool(self):
        tool = MCPServerTool(self.external_tool_server, "echo")
        mcp_tool = await tool._get_tool("echo")
        print("mcp_tool: ", mcp_tool)
        assert mcp_tool.name == "echo"
