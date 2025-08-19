import pytest
from mcp.types import TextContent

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_server_tool import MCPServerTool


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
