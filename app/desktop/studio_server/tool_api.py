from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.tools.tool_id import MCP_REMOTE_TOOL_ID_PREFIX, ToolId
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error
from kiln_server.project_api import project_from_id
from mcp.types import Tool as MCPTool
from pydantic import BaseModel, Field, ValidationError


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


def connect_tool_servers_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_tools")
    async def get_available_tools(
        project_id: str,
    ) -> List[ToolApiDescription]:
        project = project_from_id(project_id)

        # Get available tools from MCP servers
        available_tools = []
        for server in project.external_tool_servers(readonly=True):
            # Get available tools from remote MCP servers only
            match server.type:
                case ToolServerType.remote_mcp:
                    async with MCPSessionManager.shared().mcp_client(server) as session:
                        tools_result = await session.list_tools()
                        available_tools.extend(
                            [
                                ToolApiDescription(
                                    id=f"{MCP_REMOTE_TOOL_ID_PREFIX}{server.id}::{tool.name}",
                                    name=tool.name,
                                    description=tool.description,
                                )
                                for tool in tools_result.tools
                            ]
                        )
                case _:
                    raise_exhaustive_enum_error(server.type)

        return available_tools

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

            # Save the tool to file
            tool.save_to_file()

            return tool
        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Validation error: {str(e)}",
            )
