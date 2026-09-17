"""Synthetic tools presented under the real tool's id.

The registry returns one of these in place of the real tool while a synthetic instance
is active. Both answer ``id()`` with the *real* tool id, so traces, tool-call checks
and fingerprints look exactly as they would against the real tool.

``SyntheticToolProxy`` plays one tool: ``name()`` / ``toolcall_definition()`` come from
the world's ``SyntheticTool`` (whose function name and schema the binding requires to
match the real one) and ``run()`` executes its Python code in the sandbox.

``SyntheticServerToolProxy`` plays every tool of a replaced MCP server: the launched
instance serves the same tool names over its connection, so the proxy is an MCP client
against the instance, with the real tool's id.
"""

from __future__ import annotations

from typing import Any

from kiln_ai.datamodel.external_tool_server import (
    ExternalToolServer,
    LocalServerProperties,
    RemoteServerProperties,
    ToolServerType,
)
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import (
    SyntheticInstance,
    SyntheticInstanceConnection,
    SyntheticTool,
)
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)
from kiln_ai.tools.code_tool import PythonCodeTool
from kiln_ai.tools.mcp_server_tool import MCPServerTool


class SyntheticToolProxy(KilnToolInterface):
    def __init__(
        self,
        real_tool_id: ToolId,
        synthetic_tool: SyntheticTool,
        project: Project,
        task: Task | None = None,
    ):
        self._real_tool_id = real_tool_id
        self._synthetic_tool = synthetic_tool
        self._impl = PythonCodeTool(synthetic_tool, project, task)

    @property
    def synthetic_tool(self) -> SyntheticTool:
        return self._synthetic_tool

    async def id(self) -> ToolId:
        return self._real_tool_id

    async def name(self) -> str:
        return await self._impl.name()

    async def description(self) -> str:
        return await self._impl.description()

    async def toolcall_definition(self) -> ToolCallDefinition:
        return await self._impl.toolcall_definition()

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        return await self._impl.run(context, **kwargs)


def instance_tool_server(
    instance: SyntheticInstance, real_server_name: str
) -> ExternalToolServer:
    """An in-memory MCP server config pointing at a launched instance.

    Never saved: it exists so `MCPServerTool` and the session manager can talk to the
    instance exactly as they would to the real server. The id is derived from the
    instance so sessions are cached per instance, and the credentials from the
    connection stay in memory with it.
    """
    connection = instance.connection
    if connection is None:
        raise ValueError(
            f"Synthetic instance {instance.instance_id} has no connection; it cannot "
            "stand in for a tool server"
        )
    server_id = f"syn{instance.instance_id}"[:12].replace("-", "0")
    if connection.transport == "stdio":
        if not connection.command:
            raise ValueError(
                f"Synthetic instance {instance.instance_id} declares a stdio "
                "connection without a command"
            )
        local: LocalServerProperties = {
            "command": connection.command,
            "args": list(connection.args),
            "env_vars": dict(connection.env),
            "is_archived": False,
        }
        return ExternalToolServer(
            id=server_id,
            name=real_server_name,
            type=ToolServerType.local_mcp,
            properties=local,
        )
    if not connection.url:
        raise ValueError(
            f"Synthetic instance {instance.instance_id} declares an HTTP connection "
            "without a url"
        )
    remote: RemoteServerProperties = {
        "server_url": connection.url,
        "headers": dict(connection.headers),
        "is_archived": False,
    }
    return ExternalToolServer(
        id=server_id,
        name=real_server_name,
        type=ToolServerType.remote_mcp,
        properties=remote,
    )


class SyntheticServerToolProxy(KilnToolInterface):
    """One tool of a replaced MCP server, served by the launched instance."""

    def __init__(
        self,
        real_tool_id: ToolId,
        tool_name: str,
        instance: SyntheticInstance,
        real_server_name: str,
    ):
        self._real_tool_id = real_tool_id
        self._instance = instance
        self._server = instance_tool_server(instance, real_server_name)
        self._impl = MCPServerTool(self._server, tool_name)

    @property
    def connection(self) -> SyntheticInstanceConnection:
        assert self._instance.connection is not None
        return self._instance.connection

    @property
    def tool_server(self) -> ExternalToolServer:
        return self._server

    async def id(self) -> ToolId:
        return self._real_tool_id

    async def name(self) -> str:
        return await self._impl.name()

    async def description(self) -> str:
        return await self._impl.description()

    async def toolcall_definition(self) -> ToolCallDefinition:
        return await self._impl.toolcall_definition()

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        return await self._impl.run(context, **kwargs)
