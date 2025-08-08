from typing import Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool import ExternalTool, ToolType
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, ValidationError


class KilnToolDescription(BaseModel):
    name: str
    id: ID_TYPE
    type: ToolType
    description: str | None


class ExternalToolCreationRequest(BaseModel):
    name: str
    server_url: str
    headers: Dict[str, str] = {}
    description: str | None = None


def connect_tools_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_tools")
    async def get_available_tools(
        project_id: str,
    ) -> List[KilnToolDescription]:
        project = project_from_id(project_id)

        return [
            KilnToolDescription(
                name=tool.name,
                id=tool.id,
                type=tool.type,
                description=tool.description,
            )
            for tool in project.external_tools()
        ]

    @app.get("/api/projects/{project_id}/tools/{tool_id}")
    async def get_tool(project_id: str, tool_id: str) -> ExternalTool:
        project = project_from_id(project_id)
        tool = next(
            (t for t in project.external_tools(readonly=True) if t.id == tool_id), None
        )
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")

        return tool

    @app.post("/api/projects/{project_id}/connect_remote_MCP")
    async def connect_remote_MCP(
        project_id: str, tool_data: ExternalToolCreationRequest
    ) -> ExternalTool:
        project = project_from_id(project_id)

        try:
            # Create the ExternalTool with required fields
            properties = {
                "server_url": tool_data.server_url,
                "headers": tool_data.headers,
            }

            tool = ExternalTool(
                name=tool_data.name,
                type=ToolType.remote_mcp,  # Default to remote MCP type
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
