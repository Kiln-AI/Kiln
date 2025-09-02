from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from kiln_server.project_api import project_from_id
from kiln_server.task_api import task_from_id


# TODO: Move all this to app/desktop/studio_server/tool_api.py
class TaskToolInfo(BaseModel):
    """Information about a task that can be used as a tool."""

    task_id: str
    task_name: str
    task_description: str | None
    tool_id: str
    tool_name: str
    tool_description: str
    has_structured_input: bool
    has_structured_output: bool


class TaskToolConfig(BaseModel):
    """Configuration for using a task as a tool."""

    task_id: str
    default_model_name: str = "gpt-4o-mini"
    default_model_provider: str = "openai"
    default_temperature: float = 0.7
    default_top_p: float = 1.0
    default_prompt_id: str = "simple_prompt_builder"


def get_task_tools_for_project(project) -> List[TaskToolInfo]:
    """Get all tasks in a project that can be used as tools."""
    task_tools = []
    for task in project.tasks():
        # Generate tool info for each task
        tool_id = f"kiln_task::{project.id}::{task.id}"
        tool_name = f"run_{task.name.lower().replace(' ', '_')}"

        description = f"Run the Kiln task '{task.name}'"
        if task.description:
            description += f": {task.description}"

        if task.id is not None:
            task_tools.append(
                TaskToolInfo(
                    task_id=task.id,
                    task_name=task.name,
                    task_description=task.description,
                    tool_id=tool_id,
                    tool_name=tool_name,
                    tool_description=description,
                    has_structured_input=task.input_json_schema is not None,
                    has_structured_output=task.output_json_schema is not None,
                )
            )

    return task_tools


def connect_task_tool_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/available_task_tools")
    async def get_available_task_tools(project_id: str) -> List[TaskToolInfo]:
        """Get all tasks in a project that can be used as tools."""
        project = project_from_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        task_tools = []
        for task in project.tasks():
            # Generate tool info for each task
            tool_id = f"kiln_task::{project_id}::{task.id}"
            tool_name = f"run_{task.name.lower().replace(' ', '_')}"

            description = f"Run the Kiln task '{task.name}'"
            if task.description:
                description += f": {task.description}"

            if task.id is not None:
                task_tools.append(
                    TaskToolInfo(
                        task_id=task.id,
                        task_name=task.name,
                        task_description=task.description,
                        tool_id=tool_id,
                        tool_name=tool_name,
                        tool_description=description,
                        has_structured_input=task.input_json_schema is not None,
                        has_structured_output=task.output_json_schema is not None,
                    )
                )

        return task_tools

    @app.get("/api/projects/{project_id}/tasks/{task_id}/tool_info")
    async def get_task_tool_info(project_id: str, task_id: str) -> TaskToolInfo:
        """Get information about a specific task as a tool."""
        task = task_from_id(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        tool_id = f"kiln_task::{project_id}::{task_id}"
        tool_name = f"run_{task.name.lower().replace(' ', '_')}"

        description = f"Run the Kiln task '{task.name}'"
        if task.description:
            description += f": {task.description}"

        if task.id is None:
            raise HTTPException(status_code=400, detail="Task ID is None")

        return TaskToolInfo(
            task_id=task.id,
            task_name=task.name,
            task_description=task.description,
            tool_id=tool_id,
            tool_name=tool_name,
            tool_description=description,
            has_structured_input=task.input_json_schema is not None,
            has_structured_output=task.output_json_schema is not None,
        )

    @app.post("/api/projects/{project_id}/tasks/{task_id}/test_as_tool")
    async def test_task_as_tool(
        project_id: str, task_id: str, test_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test a task as a tool with sample input."""
        from kiln_ai.tools.kiln_task_tool import KilnTaskTool

        task = task_from_id(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        try:
            # Create the tool and test it
            tool = KilnTaskTool(task_id, project_id)
            result = await tool.run(**test_input)

            return {
                "success": True,
                "output": result,
                "tool_name": await tool.name(),
                "tool_description": await tool.description(),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_name": f"run_{task.name.lower().replace(' ', '_')}",
                "tool_description": f"Run the Kiln task '{task.name}'",
            }
