from typing import Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_ai.tools.tool_id import KilnBuiltInToolId, ToolId
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, Field, ValidationError


class KilnToolServerDescription(BaseModel):
    name: str
    id: ID_TYPE
    type: ToolServerType
    description: str | None


class ExternalToolServerCreationRequest(BaseModel):
    name: str
    server_url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    description: str | None = None


class ToolApiDescription(BaseModel):
    id: ToolId
    name: str
    description: str | None


def connect_tool_servers_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_tools")
    async def get_available_tools(
        project_id: str,
    ) -> List[ToolApiDescription]:
        # TODO: add a real implementation of this
        return [
            ToolApiDescription(
                id=KilnBuiltInToolId.ADD_NUMBERS,
                name="Add Numbers",
                description="Add two numbers",
            ),
            ToolApiDescription(
                id=KilnBuiltInToolId.SUBTRACT_NUMBERS,
                name="Subtract Numbers",
                description="Subtract two numbers",
            ),
            ToolApiDescription(
                id=KilnBuiltInToolId.MULTIPLY_NUMBERS,
                name="Multiply Numbers",
                description="Multiply two numbers",
            ),
            ToolApiDescription(
                id=KilnBuiltInToolId.DIVIDE_NUMBERS,
                name="Divide Numbers",
                description="Divide two numbers",
            ),
        ]

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
    ) -> ExternalToolServer:
        project = project_from_id(project_id)
        tool = next(
            (
                t
                for t in project.external_tool_servers(readonly=True)
                if t.id == tool_server_id
            ),
            None,
        )
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")

        return tool

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
