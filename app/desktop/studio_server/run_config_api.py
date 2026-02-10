import json

from app.desktop.studio_server.eval_api import (
    _load_mcp_input_schema,
    _load_mcp_output_schema,
)
from app.desktop.studio_server.tool_api import tool_server_from_id
from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.json_schema import single_string_field_name
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import MCPToolReference, RunConfigKind
from kiln_ai.datamodel.task import RunConfigProperties, Task, TaskRunConfig
from kiln_ai.datamodel.tool_id import mcp_server_and_tool_name_from_id
from kiln_ai.tools.mcp_server_tool import MCPServerTool
from kiln_ai.tools.tool_registry import is_mcp_tool_id
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.project_api import project_from_id
from pydantic import BaseModel


class CreateTaskFromToolRequest(BaseModel):
    tool_id: str
    task_name: str


def _resolve_mcp_tool_from_id(project_id: str, tool_id: str) -> MCPServerTool:
    if not is_mcp_tool_id(tool_id):
        raise ValueError("Tool selected is not an MCP tool.")
    server_id, tool_name = mcp_server_and_tool_name_from_id(tool_id)
    tool_server = tool_server_from_id(project_id, server_id)
    return MCPServerTool(tool_server, tool_name)


def connect_run_config_api(app: FastAPI):
    @app.post("/api/projects/{project_id}/create_task_from_tool")
    async def create_task_from_tool(
        project_id: str, request: CreateTaskFromToolRequest
    ) -> Task:
        project = project_from_id(project_id)

        try:
            tool = _resolve_mcp_tool_from_id(project_id, request.tool_id)
            tool_input_schema = await _load_mcp_input_schema(tool)
            tool_output_schema = await _load_mcp_output_schema(tool)
            tool_name = await tool.name()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        is_plaintext_input = single_string_field_name(tool_input_schema) is not None

        task = Task(
            name=request.task_name,
            instruction="Complete the task as described.",
            input_json_schema=None
            if is_plaintext_input
            else json.dumps(tool_input_schema),
            output_json_schema=json.dumps(tool_output_schema)
            if tool_output_schema
            else None,
            parent=project,
        )
        task.save_to_file()

        run_config_properties = RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id=request.tool_id,
                tool_name=tool_name,
                input_schema=tool_input_schema,
                output_schema=tool_output_schema,
            ),
            model_name="mcp_tool",
            model_provider_name=ModelProviderName.mcp_provider,
            prompt_id=PromptGenerators.SIMPLE,
            structured_output_mode=StructuredOutputMode.default,
        )

        task_run_config = TaskRunConfig(
            parent=task,
            name=generate_memorable_name(),
            run_config_properties=run_config_properties,
        )
        task_run_config.save_to_file()

        task.default_run_config_id = task_run_config.id
        task.save_to_file()

        return task
