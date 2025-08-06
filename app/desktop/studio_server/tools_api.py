from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kiln_ai.datamodel.basemodel import ID_TYPE
from kiln_ai.datamodel.external_tool import ExternalTool, ToolType
from kiln_server.project_api import project_from_id
from pydantic import BaseModel, ValidationError


class KilnToolDescription(BaseModel):
    name: str
    id: ID_TYPE
    description: str | None


class CreateToolRequest(BaseModel):
    name: str
    type: ToolType
    description: str | None = None
    properties: Dict[str, Any] = {}


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
                description=tool.description,
            )
            for tool in project.external_tools()
        ]

    @app.post("/api/projects/{project_id}/create_tool")
    async def create_tool(
        project_id: str, tool_data: CreateToolRequest
    ) -> ExternalTool:
        project = project_from_id(project_id)

        try:
            # Create the ExternalTool directly
            tool = ExternalTool(
                name=tool_data.name,
                type=tool_data.type,
                description=tool_data.description,
                properties=tool_data.properties,
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
