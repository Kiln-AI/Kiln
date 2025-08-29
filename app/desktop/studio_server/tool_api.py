import re
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.datamodel.tool_id import (
    MCP_LOCAL_TOOL_ID_PREFIX,
    MCP_REMOTE_TOOL_ID_PREFIX,
    KilnBuiltInToolId,
    ToolId,
)
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_server.project_api import project_from_id
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


class ExternalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    server_url: str
    headers: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_server_details(self):
        """Validate server URL and headers format."""
        # Validate server URL
        server_url = self.server_url
        if not server_url:
            raise ValueError("Server URL is required")

        # Enforce absolute http(s) URLs only
        parsed_url = urlparse(server_url.strip())
        if not parsed_url.scheme:
            raise ValueError("Server URL must start with http:// or https://")
        if not parsed_url.netloc:
            raise ValueError("Server URL is not a valid URL")

        if parsed_url.scheme not in ("http", "https"):
            raise ValueError("Server URL must start with http:// or https://")

        # Update server_url to stripped version
        self.server_url = server_url.strip()

        # Validate headers
        if isinstance(self.headers, dict):
            validated_headers = {}
            for key, value in self.headers.items():
                # Convert to string and strip
                key_str = key.strip() if isinstance(key, str) else str(key).strip()
                value_str = (
                    value.strip() if isinstance(value, str) else str(value).strip()
                )

                if not key_str:
                    raise ValueError("Header name is required")
                if not value_str:
                    raise ValueError("Header value is required")

                # Reject invalid header names and CR/LF in names/values
                token_re = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
                if not token_re.match(key_str):
                    raise ValueError(f'Invalid header name: "{key_str}"')
                if re.search(r"\r|\n", key_str) or re.search(r"\r|\n", value_str):
                    raise ValueError(
                        "Header names/values must not contain invalid characters"
                    )

                validated_headers[key_str] = value_str

            # Update headers to validated version
            self.headers = validated_headers

        return self


class LocalToolServerCreationRequest(BaseModel):
    name: str
    description: str | None = None
    command: str
    args: List[str]
    env_vars: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_command(self):
        """Validate command format."""
        if not self.command:
            raise ValueError("Command is required")

        # Validate args
        if not self.args:
            raise ValueError("Args are required")

        return self


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


class ToolApiDescription(BaseModel):
    id: ToolId
    name: str
    description: str | None


class ToolSetApiDescription(BaseModel):
    set_name: str
    tools: list[ToolApiDescription]


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
        case ToolServerType.remote_mcp:
            # Validate the server is reachable
            try:
                async with MCPSessionManager.shared().mcp_client(
                    tool_server
                ) as session:
                    # Use list tools to validate the server is reachable
                    await session.list_tools()
            except ConnectionError:
                raise HTTPException(
                    status_code=422,
                    detail="Unable to connect to the server. Please check that the server is running and accessible.",
                )
            except Exception as e:
                # For any other error, include the original message
                raise HTTPException(
                    status_code=422,
                    detail=f"Failed to connect to the server: {str(e)}",
                )
        case ToolServerType.local_mcp:
            try:
                async with MCPSessionManager.shared().mcp_client(
                    tool_server
                ) as session:
                    # Use list tools to validate the server is reachable
                    await session.list_tools()
            except Exception as e:
                # For any other error, include the original message
                raise HTTPException(
                    status_code=422,
                    detail=f"Failed to connect to the server: {str(e)}",
                )
        case _:
            raise_exhaustive_enum_error(tool_server.type)


def connect_tool_servers_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_tools")
    async def get_available_tools(
        project_id: str,
    ) -> List[ToolSetApiDescription]:
        project = project_from_id(project_id)

        tool_sets = []

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

        return [
            KilnToolServerDescription(
                name=tool.name,
                id=tool.id,
                type=tool.type,
                description=tool.description,
            )
            for tool in project.external_tool_servers()
        ]

    @app.get("/api/projects/{project_id}/tool_servers/{tool_server_id}")
    async def get_tool_server(
        project_id: str, tool_server_id: str
    ) -> ExternalToolServerApiDescription:
        project = project_from_id(project_id)
        tool_server = next(
            (
                t
                for t in project.external_tool_servers(readonly=True)
                if t.id == tool_server_id
            ),
            None,
        )
        if not tool_server:
            raise HTTPException(status_code=404, detail="Tool not found")

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

        return ExternalToolServerApiDescription(
            id=tool_server.id,
            name=tool_server.name,
            type=tool_server.type,
            description=tool_server.description,
            created_at=tool_server.created_at,
            created_by=tool_server.created_by,
            properties=tool_server.properties,
            available_tools=available_tools,
        )

    @app.post("/api/projects/{project_id}/connect_remote_mcp")
    async def connect_remote_mcp(
        project_id: str, tool_data: ExternalToolServerCreationRequest
    ) -> ExternalToolServer:
        project = project_from_id(project_id)

        # Create the ExternalToolServer with required fields
        properties = {
            "server_url": tool_data.server_url,
            "headers": tool_data.headers,
        }

        tool_server = ExternalToolServer(
            name=tool_data.name,
            type=ToolServerType.remote_mcp,  # Default to remote MCP type
            description=tool_data.description,
            properties=properties,
            parent=project,
        )

        # Validate the tool server connectivity
        await validate_tool_server_connectivity(tool_server)

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server

    @app.post("/api/projects/{project_id}/connect_local_mcp")
    async def connect_local_mcp(
        project_id: str, tool_data: LocalToolServerCreationRequest
    ) -> ExternalToolServer:
        project = project_from_id(project_id)

        # Create the ExternalToolServer with required fields
        properties = {
            "command": tool_data.command,
            "args": tool_data.args,
            "env_vars": tool_data.env_vars,
        }

        tool_server = ExternalToolServer(
            name=tool_data.name,
            type=ToolServerType.local_mcp,
            description=tool_data.description,
            properties=properties,
            parent=project,
        )

        # Validate the tool server connectivity
        await validate_tool_server_connectivity(tool_server)

        # Save the tool to file
        tool_server.save_to_file()

        return tool_server
