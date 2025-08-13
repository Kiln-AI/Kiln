from typing import Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool import ExternalToolServer, ToolServerType
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, ValidationError


class KilnToolServerDescription(BaseModel):
    name: str
    id: ID_TYPE
    type: ToolServerType
    description: str | None


class ExternalToolServerCreationRequest(BaseModel):
    name: str
    server_url: str
    headers: Dict[str, str] = {}
    description: str | None = None


def connect_tool_servers_api(app: FastAPI):
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

    @app.post("/api/projects/{project_id}/connect_remote_MCP")
    async def connect_remote_MCP(
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
