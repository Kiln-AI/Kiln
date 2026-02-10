import json

from app.desktop.studio_server.tool_api import tool_server_from_id
from fastapi import FastAPI, HTTPException
from kiln_ai.adapters.ml_model_list import ModelProviderName
from kiln_ai.datamodel.datamodel_enums import StructuredOutputMode
from kiln_ai.datamodel.json_schema import schemas_compatible, single_string_field_name
from kiln_ai.datamodel.prompt_id import PromptGenerators
from kiln_ai.datamodel.run_config import MCPToolReference, RunConfigKind
from kiln_ai.datamodel.task import RunConfigProperties, Task, TaskRunConfig
from kiln_ai.datamodel.tool_id import mcp_server_and_tool_name_from_id
from kiln_ai.tools.mcp_server_tool import MCPServerTool
from kiln_ai.tools.tool_registry import is_mcp_tool_id, tool_from_id
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.project_api import project_from_id
from kiln_server.task_api import task_from_id
from pydantic import BaseModel


class CreateTaskFromToolRequest(BaseModel):
    tool_id: str
    task_name: str


class CreateMcpRunConfigRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    tool_id: str


class TaskToolCompatibility(BaseModel):
    task_id: str
    task_name: str
    compatible: bool
    incompatibility_reason: str | None = None


def _resolve_mcp_tool_from_id(project_id: str, tool_id: str) -> MCPServerTool:
    if not is_mcp_tool_id(tool_id):
        raise ValueError("Tool selected is not an MCP tool.")
    server_id, tool_name = mcp_server_and_tool_name_from_id(tool_id)
    tool_server = tool_server_from_id(project_id, server_id)
    return MCPServerTool(tool_server, tool_name)


def _load_mcp_tool(tool_id: str, task: Task) -> MCPServerTool:
    if not is_mcp_tool_id(tool_id):
        raise ValueError("Tool selected is not an MCP tool.")
    tool = tool_from_id(tool_id, task)
    if not isinstance(tool, MCPServerTool):
        raise ValueError("Failed to load MCP tool.")
    return tool


async def _load_mcp_input_schema(tool: MCPServerTool) -> dict:
    try:
        tool_input_schema = await tool.input_schema()
    except ValueError:
        raise ValueError("MCP tool definition is missing a valid input schema.")
    if not isinstance(tool_input_schema, dict):
        raise ValueError("MCP tool definition is missing a valid input schema.")
    return tool_input_schema


async def _load_mcp_output_schema(tool: MCPServerTool) -> dict | None:
    """Load the MCP tool output schema, it's optional"""
    try:
        return await tool.output_schema()
    except ValueError:
        raise ValueError("MCP tool definition has an invalid output schema.")


def _validate_mcp_input_schema(task: Task, tool_input_schema: dict) -> None:
    """Validate that the task input schema matches the MCP tool input schema"""
    if task.input_json_schema is None:
        field_name = single_string_field_name(tool_input_schema)
        if field_name is None:
            raise ValueError(
                "Plaintext tasks require the MCP tool to have exactly one string input field."
            )
        return

    task_schema = task.input_schema()
    if task_schema is None:
        raise ValueError("Task input schema must be set for structured input tasks.")
    if not schemas_compatible(task_schema, tool_input_schema):
        raise ValueError("Task input schema must be compatible with the MCP tool.")


def _validate_mcp_output_schema(task: Task, tool_output_schema: dict | None) -> None:
    """Validate that the task output schema matches the MCP tool output schema"""
    if task.output_json_schema is None or tool_output_schema is None:
        return

    task_output_schema = task.output_schema()
    if task_output_schema is None:
        raise ValueError("Task output schema must be set for structured output tasks.")
    if not schemas_compatible(task_output_schema, tool_output_schema):
        raise ValueError("Task output schema must be compatible with the MCP tool.")


def connect_run_config_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/tasks_compatible_with_tool")
    async def tasks_compatible_with_tool(
        project_id: str, tool_id: str
    ) -> list[TaskToolCompatibility]:
        project = project_from_id(project_id)

        try:
            tool = _resolve_mcp_tool_from_id(project_id, tool_id)
            tool_input_schema = await _load_mcp_input_schema(tool)
            tool_output_schema = await _load_mcp_output_schema(tool)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        results: list[TaskToolCompatibility] = []
        for task in project.tasks():
            if task.id is None:
                continue

            compatible = True
            reason: str | None = None

            # Input schema compatibility
            if task.input_json_schema is None:
                field_name = single_string_field_name(tool_input_schema)
                if field_name is None:
                    compatible = False
                    reason = "Plaintext tasks require the MCP tool to have exactly one string input field."
            else:
                task_schema = task.input_schema()
                if task_schema is None:
                    compatible = False
                    reason = "Task input schema must be set for structured input tasks."
                elif not schemas_compatible(task_schema, tool_input_schema):
                    compatible = False
                    reason = "Task input schema must be compatible with the MCP tool."

            # Output schema compatibility (only if still compatible)
            if compatible and task.output_json_schema is not None:
                if tool_output_schema is not None:
                    task_output_schema = task.output_schema()
                    if task_output_schema is None:
                        compatible = False
                        reason = "Task output schema must be set for structured output tasks."
                    elif not schemas_compatible(task_output_schema, tool_output_schema):
                        compatible = False
                        reason = (
                            "Task output schema must be compatible with the MCP tool."
                        )

            results.append(
                TaskToolCompatibility(
                    task_id=task.id,
                    task_name=task.name,
                    compatible=compatible,
                    incompatibility_reason=None if compatible else reason,
                )
            )
        return results

    @app.post("/api/projects/{project_id}/tasks/{task_id}/mcp_run_config")
    async def create_mcp_run_config(
        project_id: str,
        task_id: str,
        request: CreateMcpRunConfigRequest,
    ) -> TaskRunConfig:
        task = task_from_id(project_id, task_id)
        name = request.name or generate_memorable_name()

        try:
            tool_id = request.tool_id
            tool = _load_mcp_tool(tool_id, task)
            tool_input_schema = await _load_mcp_input_schema(tool)
            tool_output_schema = await _load_mcp_output_schema(tool)
            _validate_mcp_input_schema(task, tool_input_schema)
            _validate_mcp_output_schema(task, tool_output_schema)
            tool_name = await tool.name()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        run_config_properties = RunConfigProperties(
            kind=RunConfigKind.mcp,
            mcp_tool=MCPToolReference(
                tool_id=tool_id,
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
            name=name,
            run_config_properties=run_config_properties,
            description=request.description,
        )
        task_run_config.save_to_file()
        return task_run_config

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

        is_plaintext_input = (
            single_string_field_name(tool_input_schema) is not None
            and tool_output_schema is None
        )

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
