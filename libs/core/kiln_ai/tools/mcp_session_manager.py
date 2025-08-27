from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class MCPSessionManager:
    """
    This class is a singleton that manages MCP sessions for remote MCP servers.
    """

    _shared_instance = None

    @classmethod
    def shared(cls):
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @asynccontextmanager
    async def mcp_client(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[
        ClientSession,
        None,
    ]:
        # Only support remote MCP servers for now
        match tool_server.type:
            case ToolServerType.remote_mcp:
                # Make sure the server_url is set
                server_url = tool_server.properties.get("server_url")
                if not server_url:
                    raise ValueError("server_url is required")

                headers = tool_server.properties.get("headers", {})

                async with streamablehttp_client(server_url, headers=headers) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    # Create a session using the client streams
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
            case ToolServerType.local_mcp:
                command = tool_server.properties.get("command")
                if not command:
                    raise ValueError("command is required")

                args = tool_server.properties.get("args", [])
                if not args:
                    raise ValueError("argument is required")

                env_vars = tool_server.properties.get("env_vars", {})

                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env_vars,
                )

                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
            case _:
                raise_exhaustive_enum_error(tool_server.type)
