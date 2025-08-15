from __future__ import annotations

from typing import TYPE_CHECKING

from mcp import ClientSession, ListToolsResult
from mcp.client.streamable_http import streamablehttp_client

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType

if TYPE_CHECKING:
    from kiln_ai.tools.mcp_server_tool import MCPServerTool


class MCPServer:
    """
    A class for interacting with MCP servers.
    """

    def __init__(self, tool_server: ExternalToolServer):
        self._tool_server = tool_server
        self._tools = None

        if tool_server.type != ToolServerType.remote_mcp:
            raise ValueError(
                "MCPServer can only be initialized with a remote MCP server"
            )

    async def list_tools(self) -> ListToolsResult:
        server_url = self._tool_server.properties.get("server_url")
        if not server_url:
            raise ValueError("server_url is required")

        headers = self._tool_server.properties.get("headers", {})
        async with streamablehttp_client(server_url, headers=headers) as (
            read_stream,
            write_stream,
            _,
        ):
            # Create a session using the client streams
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize the connection
                await session.initialize()
                # List available tools
                self._tools = await session.list_tools()
                print(f"Available tools: {[tool.name for tool in self._tools.tools]}")
                return self._tools

    async def get_tool(self, tool_name: str) -> MCPServerTool:
        from kiln_ai.tools.mcp_server_tool import MCPServerTool

        if self._tools is None:
            self._tools = await self.list_tools()

        tool = next(
            (tool for tool in self._tools.tools if tool.name == tool_name), None
        )
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        return MCPServerTool(self, tool)
