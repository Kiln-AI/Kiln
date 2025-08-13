from contextlib import asynccontextmanager

from mcp import ClientSession, ListToolsResult
from mcp.client.streamable_http import streamablehttp_client

from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class MCPServer:
    """
    A class for interacting with MCP servers.
    """

    def __init__(self, tool_server: ExternalToolServer):
        self._tool_server = tool_server

        if tool_server.type != ToolServerType.remote_mcp:
            raise ValueError(
                "MCPServer can only be initialized with a remote MCP server"
            )

    @asynccontextmanager
    async def mcp_client(self):
        match self._tool_server.type:
            case ToolServerType.remote_mcp:
                server_url = self._tool_server.properties.get("server_url")
                if not server_url:
                    raise ValueError(
                        "server_url is required in external tool properties for remote MCP servers"
                    )
                async with streamablehttp_client(server_url) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    server_session = ClientSession(read_stream, write_stream)
                yield server_session
            case _:
                # This should be unreachable due to the type check in __init__,
                # but makes the match exhaustive for future tool server types
                raise_exhaustive_enum_error(self._tool_server.type)

    async def list_tools(self) -> ListToolsResult:
        async with self.mcp_client() as server_session:
            await server_session.initialize()
            tools = await server_session.list_tools()
            return tools
