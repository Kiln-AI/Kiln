import re
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.tool_id import (
    KILN_TASK_TOOL_ID_PREFIX,
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    RAG_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    ToolId,
)
from kiln_ai.tools.kiln_task_tool import KilnTaskTool
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_server.project_api import project_from_id
from kiln_server.task_api import task_from_id
from mcp.types import Tool as MCPTool
from pydantic import BaseModel, Field, model_validator


class KilnToolServerDescription(BaseModel):
    """
    This class is used to describe the external tool server under Settings -> Manage Tools UI.
    """

    name: str
    id: ID_TYPE
    type: ToolServerType
    description: str | None
    missing_secrets: list[str]
    is_archived: bool


class KilnTaskToolDescription(BaseModel):
    """
    This class is used to describe Kiln Task tools with their associated task information.
    """

    tool_server_id: str
    tool_name: str
    tool_description: str | None
    task_id: str
    task_name: str
    task_description: str | None
    is_archived: bool
    created_at: str


class ExternalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    server_url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    secret_header_keys: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_server_details(self):
        """Validate server URL and headers format."""
        # Validate server URL
        server_url = self.server_url
        if not server_url:
            raise ValueError("Server URL is required to connect to a remote MCP server")
        # Check for leading whitespace in URL
        if server_url != server_url.lstrip():
            raise ValueError("Server URL must not have leading whitespace")
        if urlparse(server_url).scheme not in ["http", "https"]:
            raise ValueError("Server URL must start with http:// or https://")
        if not urlparse(server_url).netloc:
            raise ValueError("Server URL is not a valid URL")

        # Validate headers
        for key, value in self.headers.items():
            if not key:
                raise ValueError("Header name is required")
            if not value:
                raise ValueError("Header value is required")

            # Reject invalid header names and CR/LF in names/values
            token_re = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
            if not token_re.match(key):
                raise ValueError(f'Invalid header name: "{key}"')
            if re.search(r"\r|\n", key) or re.search(r"\r|\n", value):
                raise ValueError(
                    "Header names/values must not contain invalid characters"
                )

        # Validate secret header keys
        for key in self.secret_header_keys:
            key = key if isinstance(key, str) else str(key)
            if not key:
                raise ValueError("Secret header key is required")
            # Check if the key is in the headers
            if key not in self.headers:
                raise ValueError(f"Secret header key {key} is not in the headers")

        return self


class LocalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    command: str
    args: List[str]
    env_vars: Dict[str, str] = Field(default_factory=dict)
    secret_env_var_keys: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_command(self):
        """Validate command format."""
        if not self.command:
            raise ValueError("Command is required to start a local MCP server")

        # Validate env_vars keys are in the correct format for Environment Variables
        # According to POSIX specification, environment variable names must:
        # - Start with a letter (a-z, A-Z) or underscore (_)
        # - Contain only ASCII letters, digits, and underscores
        for key, value in self.env_vars.items():
            if not key or not (
                key[0].isascii() and (key[0].isalpha() or key[0] == "_")
            ):
                raise ValueError(
                    f"Invalid environment variable key: {key}. Must start with a letter or underscore."
                )

            if not all(c.isascii() and (c.isalnum() or c == "_") for c in key):
                raise ValueError(
                    f"Invalid environment variable key: {key}. Can only contain letters, digits, and underscores."
                )

        # Validate secret environment variable keys
        for key in self.secret_env_var_keys:
            key_str = key if isinstance(key, str) else str(key)
            if not key_str:
                raise ValueError("Secret environment variable key is required")
            # Check if the key is in the env_vars
            if key_str not in self.env_vars:
                raise ValueError(
                    f"Secret environment variable key {key_str} is not in the list of environment variables"
                )

        return self


class KilnTaskToolServerCreationRequest(BaseModel):
    name: str
    description: str
    task_id: str
    run_config_id: str
    is_archived: bool

    # TODO: Add validation


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

    @classmethod
    async def tool_from_kiln_task_tool(cls, tool: KilnTaskTool):
        """Create an ExternalToolApiDescription from an MCP Tool object."""

        return cls(
            name=await tool.name(),
            description=await tool.description(),
            inputSchema=await tool.get_parameters_schema() or {},
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
        case ToolServerType.kiln_task:
            raise ValueError("Kiln task tools are not available from an MCP server")
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
        case ToolServerType.kiln_task:
            # TODO: Validate the task and run config are still valid (e.g. task is not deleted, run config is not deleted, etc.)
            pass
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
            tool_sets.append(
                ToolSetApiDescription(
                    set_name="Search Tools (RAG)",
                    tools=[
                        ToolApiDescription(
                            id=f"{RAG_TOOL_ID_PREFIX}{rag_config.id}",
                            name=rag_config.tool_name,
                            description=f"{rag_config.name}: {rag_config.tool_description}",
                        )
                        for rag_config in rag_configs
                        if not rag_config.is_archived
                    ],
                )
            )

        # Get available tools from MCP servers and Kiln task tools
        task_tools = []
        for server in project.external_tool_servers(readonly=True):
            server_tools = []
            match server.type:
                case ToolServerType.remote_mcp | ToolServerType.local_mcp:
                    try:
                        server_tools = await available_mcp_tools(server)
                    except Exception:
                        # Skip the tool when we can't connect to the server
                        continue
                case ToolServerType.kiln_task:
                    task_tools.append(
                        # TODO: Should project id be stored in server.properties?
                        ToolApiDescription(
                            id=f"{KILN_TASK_TOOL_ID_PREFIX}{server.id}",
                            name=server.properties.get("name") or "",
                            description=server.properties.get("description") or "",
                        )
                    )
                case _:
                    raise_exhaustive_enum_error(server.type)

            if server_tools:
                tool_sets.append(
                    ToolSetApiDescription(
                        set_name="MCP Server: " + server.name,
                        tools=server_tools,
                    )
                )

        # Add task tools
        if len(task_tools) > 0:
            tool_sets.append(
                ToolSetApiDescription(
                    set_name="Kiln Tasks",
                    tools=task_tools,
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
                    is_archived=tool.properties.get("is_archived", False),
                )
            )
        return results

    @app.get("/api/projects/{project_id}/kiln_task_tools")
    async def get_kiln_task_tools(
        project_id: str,
    ) -> List[KilnTaskToolDescription]:
        project = project_from_id(project_id)

        results = []
        for tool_server in project.external_tool_servers():
            if tool_server.type == ToolServerType.kiln_task:
                try:
                    task_id = tool_server.properties.get("task_id")
                    if task_id:
                        task = task_from_id(project_id, task_id)
                        results.append(
                            KilnTaskToolDescription(
                                tool_server_id=str(tool_server.id),
                                tool_name=tool_server.properties.get("name", ""),
                                tool_description=tool_server.properties.get(
                                    "description"
                                ),
                                task_id=task_id,
                                task_name=task.name,
                                task_description=task.description,
                                is_archived=tool_server.properties.get(
                                    "is_archived", False
                                ),
                                created_at=tool_server.created_at.isoformat(),
                            )
                        )
                except HTTPException:
                    # Skip tools with invalid task references
                    continue
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
            case ToolServerType.kiln_task:
                available_tools = [
                    await ExternalToolApiDescription.tool_from_kiln_task_tool(
                        KilnTaskTool(project_id, tool_server.id or "", tool_server)
                    )
                ]
                pass
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

    @app.post("/api/projects/{project_id}/add_kiln_task_tool")
    async def add_kiln_task_tool(
        project_id: str, tool_data: KilnTaskToolServerCreationRequest
    ) -> ExternalToolServer:
        project = project_from_id(project_id)

        tool_server = ExternalToolServer(
            name=tool_data.name,
            type=ToolServerType.kiln_task,
            description=tool_data.description,
            properties={
                "name": tool_data.name,
                "description": tool_data.description,
                "task_id": tool_data.task_id,
                "run_config_id": tool_data.run_config_id,
                "is_archived": tool_data.is_archived,
            },
            parent=project,
        )

        # Save the tool server to file
        tool_server.save_to_file()

        return tool_server

    @app.patch("/api/projects/{project_id}/edit_kiln_task/{tool_server_id}")
    async def edit_kiln_task(
        project_id: str,
        tool_server_id: str,
        tool_data: KilnTaskToolServerCreationRequest,
    ) -> ExternalToolServer:
        existing_tool_server = tool_server_from_id(project_id, tool_server_id)
        if existing_tool_server.type != ToolServerType.kiln_task:
            raise HTTPException(
                status_code=400,
                detail="Existing tool server is not a kiln task tool. You can't edit a non-kiln task tool with this endpoint.",
            )

        # Create a deep copy of the existing tool server so if any validation fails we don't cache the bad data in memory
        tool_server = existing_tool_server.model_copy(deep=True)
        tool_server.name = tool_data.name
        tool_server.description = tool_data.description
        tool_server.properties = {
            "name": tool_data.name,
            "description": tool_data.description,
            "task_id": tool_data.task_id,
            "run_config_id": tool_data.run_config_id,
            "is_archived": tool_data.is_archived,
        }

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server

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
