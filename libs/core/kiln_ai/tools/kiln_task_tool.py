import json
from typing import Any, Dict

from kiln_ai.datamodel import Task
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.tool_id import KILN_TASK_TOOL_ID_PREFIX, ToolId
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.utils.project_utils import project_from_id


class KilnTaskTool(KilnToolInterface):
    """
    A tool that wraps a Kiln task, allowing it to be called as a function.

    This tool loads a task by ID and executes it using the specified run configuration.
    """

    def __init__(
        self,
        project_id: str,
        task_id: str,
        run_config_id: str,
    ):
        self._project_id = project_id
        self._task_id = task_id
        self._run_config_id = run_config_id
        self._task: Task | None = None
        self._run_config: TaskRunConfig | None = None
        self._parameters_schema: Dict[str, Any] | None = None
        self._tool_id = (
            f"{KILN_TASK_TOOL_ID_PREFIX}{project_id}::{task_id}::{run_config_id}"
        )

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        task = await self._get_task()
        # TODO: task.name is not meant for tool use
        return task.name

    async def description(self) -> str:
        task = await self._get_task()
        # TODO: task.description is not meant for tool use
        return task.description or "N/A"

    async def toolcall_definition(self) -> Dict[str, Any]:
        """Generate OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": await self._get_parameters_schema(),
            },
        }

    async def run(self, **kwargs) -> str:
        """Execute the wrapped Kiln task with the given parameters."""
        task = await self._get_task()
        run_config = await self._get_run_config()

        # Determine the input format
        if task.input_json_schema:
            # Structured input - pass kwargs directly
            input = kwargs
        else:
            # Plaintext input - extract from 'input' parameter or convert kwargs
            if "input" in kwargs:
                input = kwargs["input"]
            else:
                # Convert kwargs to a descriptive string
                input = json.dumps(kwargs, indent=2)

        # TODO: Moving these imports here to avoid circular imports, do we need to re-architect something to avoid this?
        from kiln_ai.adapters.adapter_registry import adapter_for_task
        from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig

        # Create adapter and run the task
        adapter = adapter_for_task(
            task,
            run_config_properties=run_config.run_config_properties,
            base_adapter_config=AdapterConfig(allow_saving=False),
        )
        task_run = await adapter.invoke(input)

        return task_run.output.output

    async def _get_task(self) -> Task:
        """Lazy load the task."""
        if self._task is None:
            # Load the project first
            project = project_from_id(self._project_id)
            if project is None:
                raise ValueError(f"Project not found: {self._project_id}")

            # Load the task from the project
            self._task = Task.from_id_and_parent_path(self._task_id, project.path)
            if self._task is None:
                raise ValueError(
                    f"Task not found: {self._task_id} in project {self._project_id}"
                )
        return self._task

    async def _get_run_config(self) -> TaskRunConfig:
        """Lazy load the task run config."""
        if self._run_config is None:
            task = await self._get_task()
            self._run_config = next(
                (
                    run_config
                    for run_config in task.run_configs(readonly=True)
                    if run_config.id == self._run_config_id
                ),
                None,
            )
            if self._run_config is None:
                raise ValueError(
                    f"Task run config not found: {self._run_config_id} for task {self._task_id} in project {self._project_id}"
                )
        return self._run_config

    async def _get_parameters_schema(self) -> Dict[str, Any]:
        """Lazy load the task parameters schema."""
        if self._parameters_schema is None:
            task = await self._get_task()

            if task.input_json_schema:
                # Use the task's input schema directly
                self._parameters_schema = task.input_schema()
            else:
                # For plaintext tasks, create a simple string input parameter
                self._parameters_schema = {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": f"Input for the task: {task.instruction}",
                        }
                    },
                    "required": ["input"],
                }
            if self._parameters_schema is None:
                raise ValueError(
                    f"Failed to create parameters schema for tool_id {self._tool_id}"
                )
        return self._parameters_schema
