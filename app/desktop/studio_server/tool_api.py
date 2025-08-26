import re
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.tools.tool_id import MCP_REMOTE_TOOL_ID_PREFIX, KilnBuiltInToolId, ToolId
from kiln_ai.utils.config import Config
from kiln_ai.utils.dataset_import import format_validation_error
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_server.project_api import project_from_id
from mcp.types import Tool as MCPTool
from pydantic import BaseModel, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails


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
    server_url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    description: str | None = None

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


async def available_remote_mcp_tools(
    server: ExternalToolServer,
) -> list[ToolApiDescription]:
    """
    Get the available tools from a remote MCP server. If the server is not reachable, return an empty list.
    """
    try:
        async with MCPSessionManager.shared().mcp_client(server) as session:
            tools_result = await session.list_tools()
            return [
                ToolApiDescription(
                    id=f"{MCP_REMOTE_TOOL_ID_PREFIX}{server.id}::{tool.name}",
                    name=tool.name,
                    description=tool.description,
                )
                for tool in tools_result.tools
            ]
    except Exception:
        # Skip the tool when we can't connect to the server
        return []


async def validate_tool_server_connectivity(tool_server: ExternalToolServer):
    """
    Validate that the tool server is reachable by attempting to connect.
    Basic field validation is now handled by Pydantic validators in ExternalToolServerCreationRequest.
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
            except Exception:
                raise ValidationError.from_exception_data(
                    "ValidationError",
                    [
                        InitErrorDetails(
                            type="value_error",
                            loc=("server url",),
                            input=None,
                            ctx={"error": "Failed to connect to the server"},
                        )
                    ],
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

        # Get available tools from remote MCP servers only
        for server in project.external_tool_servers(readonly=True):
            available_mcp_tools = []
            match server.type:
                case ToolServerType.remote_mcp:
                    available_mcp_tools = await available_remote_mcp_tools(server)
                case _:
                    raise_exhaustive_enum_error(server.type)

            if available_mcp_tools:
                tool_sets.append(
                    ToolSetApiDescription(
                        set_name="MCP Server: " + server.name,
                        tools=available_mcp_tools,
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
            case ToolServerType.remote_mcp:
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

        try:
            # Create the ExternalToolServer with required fields
            properties = {
                "server_url": tool_data.server_url,
                "headers": tool_data.headers,
            }

            tool = ExternalToolServer(
                name=tool_data.name,
                type=ToolServerType.remote_mcp,  # Default to remote MCP type
                description=tool_data.description,
                properties=properties,
                parent=project,
            )

            # Validate the tool server connectivity
            await validate_tool_server_connectivity(tool)

            # Save the tool to file
            tool.save_to_file()

            return tool
        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=format_validation_error(e),
            )
