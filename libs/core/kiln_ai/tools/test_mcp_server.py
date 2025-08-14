import pytest

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_server import MCPServer


class TestMCPServerIntegration:
    """Integration tests for MCPServer using real services."""

    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
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
        tools = await mcp_server.list_tools()
        assert tools is not None
        assert len(tools.tools) > 0
        assert "echo" in [tool.name for tool in tools.tools]
