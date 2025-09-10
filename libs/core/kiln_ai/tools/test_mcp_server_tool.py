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

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.tool_id import MCP_REMOTE_TOOL_ID_PREFIX
from kiln_ai.tools.mcp_server_tool import MCPServerTool


class TestMCPServerTool:
    """Unit tests for MCPServerTool."""

    @pytest.mark.asyncio
    async def test_constructor(self):
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
        tool_id = await tool.id()
        assert tool_id.startswith(MCP_REMOTE_TOOL_ID_PREFIX)
        assert tool_id.endswith("::test_tool")
        assert await tool.name() == "test_tool"
        # Note: description() now loads properties, so we can't test "Not Loaded" state
        # Instead we verify that _tool is initially None before properties are loaded
        assert tool._tool_server_model == server
        assert tool._tool is None

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_run_success(self, mock_session_manager):
        """Test successful run() execution."""
        # Setup mocks
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Success result")]
        call_result = CallToolResult(content=result_content, isError=False)  # type: ignore
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

        result = await tool.run(param1="value1", param2="value2")

        assert result == "Success result"
        mock_session.call_tool.assert_called_once_with(
            name="test_tool", arguments={"param1": "value1", "param2": "value2"}
        )

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_run_empty_content(self, mock_session_manager):
        """Test run() with empty content raises ValueError."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        call_result = CallToolResult(
            content=list[ContentBlock]([]),
            isError=False,  # type: ignore
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
            await tool.run()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_run_non_text_content_error(self, mock_session_manager):
        """Test run() raises error when first content is not TextContent."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [
            ImageContent(type="image", data="base64data", mimeType="image/png")
        ]
        call_result = CallToolResult(content=result_content, isError=False)  # type: ignore
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
            await tool.run()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_run_error_result(self, mock_session_manager):
        """Test run() raises error when tool returns isError=True."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Error occurred")]
        call_result = CallToolResult(
            content=list[ContentBlock](result_content),
            isError=True,  # type: ignore
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
            await tool.run()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_run_multiple_content_blocks_error(self, mock_session_manager):
        """Test run() raises error when tool returns multiple content blocks."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [
            TextContent(type="text", text="First block"),
            TextContent(type="text", text="Second block"),
        ]
        call_result = CallToolResult(content=result_content, isError=False)  # type: ignore
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
            await tool.run()

    @pytest.mark.asyncio
    @patch("kiln_ai.tools.mcp_server_tool.MCPSessionManager")
    async def test_call_tool_success(self, mock_session_manager):
        """Test _call_tool() method."""
        mock_session = AsyncMock()
        mock_session_manager.shared.return_value.mcp_client.return_value.__aenter__.return_value = mock_session

        result_content = [TextContent(type="text", text="Async result")]
        call_result = CallToolResult(content=result_content, isError=False)  # type: ignore
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

        # Verify initial state - _tool is None before loading
        assert tool._tool is None

        # After loading properties, verify state
        description = await tool.description()
        assert description == "Loaded tool description"
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

        assert await tool.description() == "N/A"

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

    @pytest.mark.asyncio
    async def test_toolcall_definition(self):
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
        # Mark tool as loaded to avoid triggering _load_tool_properties()
        from mcp.types import Tool as MCPTool

        tool._tool = MCPTool(
            name="test_tool", description="Test tool description", inputSchema={}
        )

        definition = await tool.toolcall_definition()

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
        assert run_result == "Tool echo: " + test_message

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_get_tool(self):
        tool = MCPServerTool(self.external_tool_server, "echo")
        mcp_tool = await tool._get_tool("echo")
        assert mcp_tool.name == "echo"
