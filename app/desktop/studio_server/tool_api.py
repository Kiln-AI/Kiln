from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.tool_id import (
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    RAG_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    ToolId,
)
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_server.project_api import project_from_id
from mcp.types import Tool as MCPTool
from pydantic import BaseModel, Field


class KilnToolServerDescription(BaseModel):
    """
    This class is used to describe the external tool server under Settings -> Manage Tools UI.
    """

    name: str
    id: ID_TYPE
    type: ToolServerType
    description: str | None
    missing_secrets: list[str]


class ExternalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    server_url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    secret_header_keys: List[str] = Field(default_factory=list)


class LocalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    command: str
    args: List[str]
    env_vars: Dict[str, str] = Field(default_factory=dict)
    secret_env_var_keys: List[str] = Field(default_factory=list)


class ExternalToolApiDescription(BaseModel):
    """
    This class is a wrapper of MCP's Tool object to be displayed in the UI under tool_server/[tool_server_id].
    """

    name: str
    description: str | None
    inputSchema: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def tool_from_mcp_tool(cls, tool: MCPTool):
        """Create an ExternalToolApiDescription from an MCP Tool object."""

        return cls(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.inputSchema or {},
        )


class ExternalToolServerApiDescription(BaseModel):
    """
    This class is used to describe the external tool server under tool_servers/[tool_server_id] UI. It is based of ExternalToolServer.
    """

    id: ID_TYPE
    type: ToolServerType
    name: str
    description: str | None
    created_at: datetime | None
    created_by: str | None
    properties: Dict[str, Any]
    available_tools: list[ExternalToolApiDescription]
    missing_secrets: list[str]


class ToolApiDescription(BaseModel):
    id: ToolId
    name: str
    description: str | None


class ToolSetApiDescription(BaseModel):
    set_name: str
    tools: list[ToolApiDescription]


class SearchToolApiDescription(BaseModel):
    id: ID_TYPE
    tool_name: str
    name: str
    description: str | None


def tool_server_from_id(project_id: str, tool_server_id: str) -> ExternalToolServer:
    project = project_from_id(project_id)
    for tool_server in project.external_tool_servers(readonly=True):
        if tool_server.id == tool_server_id:
            return tool_server

    raise HTTPException(status_code=404, detail="Tool server not found")


async def available_mcp_tools(
    server: ExternalToolServer,
) -> list[ToolApiDescription]:
    """
    Get the available tools from an MCP server (remote or local)
    """
    # Determine the prefix based on server type
    match server.type:
        case ToolServerType.remote_mcp:
            prefix = MCP_REMOTE_TOOL_ID_PREFIX
        case ToolServerType.local_mcp:
            prefix = MCP_LOCAL_TOOL_ID_PREFIX
        case _:
            raise_exhaustive_enum_error(server.type)

    async with MCPSessionManager.shared().mcp_client(server) as session:
        tools_result = await session.list_tools()
        return [
            ToolApiDescription(
                id=f"{prefix}{server.id}::{tool.name}",
                name=tool.name,
                description=tool.description,
            )
            for tool in tools_result.tools
        ]


async def validate_tool_server_connectivity(tool_server: ExternalToolServer):
    """
    Validate that the tool server is reachable by attempting to connect.
    Basic field validation is now handled by Pydantic validators in CreationRequest.
    """
    match tool_server.type:
        case ToolServerType.remote_mcp | ToolServerType.local_mcp:
            # Validate the server is reachable
            async with MCPSessionManager.shared().mcp_client(tool_server) as session:
                # Use list tools to validate the server is reachable
                await session.list_tools()
        case _:
            raise_exhaustive_enum_error(tool_server.type)


def connect_tool_servers_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_tools")
    async def get_available_tools(
        project_id: str,
    ) -> List[ToolSetApiDescription]:
        project = project_from_id(project_id)

        tool_sets = []

        # Add search tools (RAG)
        rag_configs = project.rag_configs(readonly=True)
        if rag_configs:
            tools = [
                ToolApiDescription(
                    id=f"{RAG_TOOL_ID_PREFIX}{rag_config.id}",
                    name=rag_config.tool_name,
                    description=f"{rag_config.name}: {rag_config.tool_description}",
                )
                for rag_config in rag_configs
                if not rag_config.is_archived
            ]
            if tools and len(tools) > 0:
                tool_sets.append(
                    ToolSetApiDescription(
                        set_name="Search Tools (RAG)",
                        tools=tools,
                    )
                )

        # Get available tools from MCP servers
        for server in project.external_tool_servers(readonly=True):
            server_tools = []
            match server.type:
                case ToolServerType.remote_mcp | ToolServerType.local_mcp:
                    try:
                        server_tools = await available_mcp_tools(server)
                    except Exception:
                        # Skip the tool when we can't connect to the server
                        continue
                case _:
                    raise_exhaustive_enum_error(server.type)

            if server_tools:
                tool_sets.append(
                    ToolSetApiDescription(
                        set_name="MCP Server: " + server.name,
                        tools=server_tools,
                    )
                )

        # Add demo tools if enabled
        if Config.shared().enable_demo_tools:
            tool_sets.append(
                ToolSetApiDescription(
                    set_name="Kiln Demo Tools",
                    tools=[
                        ToolApiDescription(
                            id=f"{KilnBuiltInToolId.ADD_NUMBERS.value}",
                            name="Addition",
                            description="Add two numbers together",
                        ),
                        ToolApiDescription(
                            id=f"{KilnBuiltInToolId.SUBTRACT_NUMBERS.value}",
                            name="Subtraction",
                            description="Subtract two numbers",
                        ),
                        ToolApiDescription(
                            id=f"{KilnBuiltInToolId.MULTIPLY_NUMBERS.value}",
                            name="Multiplication",
                            description="Multiply two numbers",
                        ),
                        ToolApiDescription(
                            id=f"{KilnBuiltInToolId.DIVIDE_NUMBERS.value}",
                            name="Division",
                            description="Divide two numbers",
                        ),
                    ],
                )
            )

        return tool_sets

    @app.get("/api/projects/{project_id}/available_tool_servers")
    async def get_available_tool_servers(
        project_id: str,
    ) -> List[KilnToolServerDescription]:
        project = project_from_id(project_id)

        results = []
        for tool in project.external_tool_servers():
            _, missing_secrets = tool.retrieve_secrets()
            results.append(
                KilnToolServerDescription(
                    name=tool.name,
                    id=tool.id,
                    type=tool.type,
                    description=tool.description,
                    missing_secrets=missing_secrets,
                )
            )
        return results

    @app.get("/api/projects/{project_id}/tool_servers/{tool_server_id}")
    async def get_tool_server(
        project_id: str, tool_server_id: str
    ) -> ExternalToolServerApiDescription:
        tool_server = tool_server_from_id(project_id, tool_server_id)

        # Check if the tool server has missing secretes (e.g. new user syncing exisiting project)
        # If there are missing secrets, add a requirement to the result and skip getting available tools.
        _, missing_secrets = tool_server.retrieve_secrets()
        if missing_secrets:
            return ExternalToolServerApiDescription(
                id=tool_server.id,
                name=tool_server.name,
                type=tool_server.type,
                description=tool_server.description,
                created_at=tool_server.created_at,
                created_by=tool_server.created_by,
                properties=tool_server.properties,
                available_tools=[],
                missing_secrets=list(missing_secrets),
            )

        # If there are no missing secrets, get available tools
        # Get available tools based on server type
        available_tools = []
        match tool_server.type:
            case ToolServerType.remote_mcp | ToolServerType.local_mcp:
                async with MCPSessionManager.shared().mcp_client(
                    tool_server
                ) as session:
                    tools_result = await session.list_tools()

                    available_tools = [
                        ExternalToolApiDescription.tool_from_mcp_tool(tool)
                        for tool in tools_result.tools
                    ]
            case _:
                raise_exhaustive_enum_error(tool_server.type)

        # return the result with the available tools
        return ExternalToolServerApiDescription(
            id=tool_server.id,
            name=tool_server.name,
            type=tool_server.type,
            description=tool_server.description,
            created_at=tool_server.created_at,
            created_by=tool_server.created_by,
            properties=tool_server.properties,
            available_tools=available_tools,
            missing_secrets=[],
        )

    @app.post("/api/projects/{project_id}/connect_remote_mcp")
    async def connect_remote_mcp(
        project_id: str, tool_data: ExternalToolServerCreationRequest
    ) -> ExternalToolServer:
        project = project_from_id(project_id)

        tool_server = ExternalToolServer(
            name=tool_data.name,
            type=ToolServerType.remote_mcp,
            description=tool_data.description,
            properties=_remote_tool_server_properties(tool_data),
            parent=project,
        )

        # Validate the tool server connectivity
        await validate_tool_server_connectivity(tool_server)

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server

    @app.patch("/api/projects/{project_id}/edit_remote_mcp/{tool_server_id}")
    async def edit_remote_mcp(
        project_id: str,
        tool_server_id: str,
        tool_data: ExternalToolServerCreationRequest,
    ) -> ExternalToolServer:
        existing_tool_server = tool_server_from_id(project_id, tool_server_id)
        if existing_tool_server.type != ToolServerType.remote_mcp:
            raise HTTPException(
                status_code=400,
                detail="Existing tool server is not a remote MCP server. You can't edit a non-remote MCP server with this endpoint.",
            )

        # Create a deep copy of the existing tool server so if any validation fails we don't cache the bad data in memory
        existing_tool_server = existing_tool_server.model_copy(deep=True)
        existing_tool_server.name = tool_data.name
        existing_tool_server.description = tool_data.description
        existing_tool_server.properties = _remote_tool_server_properties(tool_data)

        # Validate the tool server connectivity
        await validate_tool_server_connectivity(existing_tool_server)

        # Save the tool to file
        existing_tool_server.save_to_file()

        return existing_tool_server

    def _remote_tool_server_properties(
        tool_data: ExternalToolServerCreationRequest,
    ) -> dict[str, str | Dict[str, str] | List[str]]:
        # Create the ExternalToolServer with all data for validation
        return {
            "server_url": tool_data.server_url,
            "headers": tool_data.headers,
            "secret_header_keys": tool_data.secret_header_keys,
        }

    @app.post("/api/projects/{project_id}/connect_local_mcp")
    async def connect_local_mcp(
        project_id: str, tool_data: LocalToolServerCreationRequest
    ) -> ExternalToolServer:
        project = project_from_id(project_id)

        tool_server = ExternalToolServer(
            name=tool_data.name,
            type=ToolServerType.local_mcp,
            description=tool_data.description,
            properties=_local_tool_server_properties(tool_data),
            parent=project,
        )

        # Validate the tool server connectivity
        MCPSessionManager.shared().clear_shell_path_cache()
        await validate_tool_server_connectivity(tool_server)

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server

    @app.patch("/api/projects/{project_id}/edit_local_mcp/{tool_server_id}")
    async def edit_local_mcp(
        project_id: str, tool_server_id: str, tool_data: LocalToolServerCreationRequest
    ) -> ExternalToolServer:
        existing_tool_server = tool_server_from_id(project_id, tool_server_id)
        if existing_tool_server.type != ToolServerType.local_mcp:
            raise HTTPException(
                status_code=400,
                detail="Existing tool server is not a local MCP server. You can't edit a non-local MCP server with this endpoint.",
            )

        # Create a deep copy of the existing tool server so if any validation fails we don't cache the bad data in memory
        tool_server = existing_tool_server.model_copy(deep=True)
        tool_server.name = tool_data.name
        tool_server.description = tool_data.description
        tool_server.properties = _local_tool_server_properties(tool_data)

        # Validate the tool server connectivity
        MCPSessionManager.shared().clear_shell_path_cache()
        await validate_tool_server_connectivity(tool_server)

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server

    def _local_tool_server_properties(
        tool_data: LocalToolServerCreationRequest,
    ) -> dict[str, str | Dict[str, str] | List[str]]:
        return {
            "command": tool_data.command,
            "args": tool_data.args,
            "env_vars": tool_data.env_vars,
            "secret_env_var_keys": tool_data.secret_env_var_keys,
        }

    @app.delete("/api/projects/{project_id}/tool_servers/{tool_server_id}")
    async def delete_tool_server(project_id: str, tool_server_id: str):
        tool_server = tool_server_from_id(project_id, tool_server_id)
        # Delete the secrets from the settings
        tool_server.delete_secrets()
        # Delete the tool server from the file system
        tool_server.delete()

    @app.get("/api/demo_tools")
    async def get_demo_tools() -> bool:
        return Config.shared().enable_demo_tools

    @app.post("/api/demo_tools")
    async def set_demo_tools(enable_demo_tools: bool) -> bool:
        Config.shared().enable_demo_tools = enable_demo_tools
        return Config.shared().enable_demo_tools

    @app.get("/api/projects/{project_id}/search_tools")
    async def get_search_tools(project_id: str) -> list[SearchToolApiDescription]:
        project = project_from_id(project_id)
        return [
            SearchToolApiDescription(
                id=rag_config.id,
                tool_name=rag_config.tool_name,
                name=rag_config.name,
                description=rag_config.tool_description,
            )
            for rag_config in project.rag_configs(readonly=True)
            if not rag_config.is_archived
        ]
