from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, Tool

from kiln_ai.datamodel.basemodel import ID_FIELD
from kiln_ai.tools.base_tool import KilnTool
from kiln_ai.tools.mcp_server import MCPServer


class MCPServerTool(KilnTool):
    def __init__(self, server: MCPServer, tool: Tool):
        self._server = server
        self._tool = tool
        super().__init__(
            tool_id=str(ID_FIELD),
            name=tool.name,
            description=tool.description or "No description provided",
            parameters_schema=tool.inputSchema,
        )

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

                print(f"Calling tool: {self.name()} with kwargs: {kwargs}")
                result = await session.call_tool(
                    name=self.name(),
                    arguments=kwargs,
                )
                return result
