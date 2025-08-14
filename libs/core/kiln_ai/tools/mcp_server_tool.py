from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from kiln_ai.tools.base_tool import KilnTool
from kiln_ai.tools.mcp_server import MCPServer


class MCPServerTool(KilnTool):
    def __init__(self, server: MCPServer, tool_name: str):
        self._server = server
        self._tool_name = tool_name

    def run(self, **kwargs) -> str:
        return "Hello, world!"

    async def call_tool(self, **kwargs) -> CallToolResult:
        server_url = self._server._tool_server.properties.get("server_url")
        if not server_url:
            raise ValueError("server_url is required")

        headers = self._server._tool_server.properties.get("headers", {})
        async with streamablehttp_client(server_url, headers=headers) as (
            read_stream,
            write_stream,
            _,
        ):
            # Create a session using the client streams
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize the connection
                await session.initialize()

                print(f"Calling tool: {self._tool_name} with kwargs: {kwargs}")
                result = await session.call_tool(
                    name=self._tool_name,
                    arguments=kwargs,
                )
                return result
