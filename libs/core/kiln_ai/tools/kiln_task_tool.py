from functools import cached_property
from typing import Any, Dict

from kiln_ai.datamodel import Task
from kiln_ai.datamodel.external_tool_server import ExternalToolServer
from kiln_ai.datamodel.task import TaskRunConfig
from kiln_ai.datamodel.task_output import DataSource, DataSourceType
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import KilnToolInterface, ToolCallContext
from kiln_ai.utils.project_utils import project_from_id


class KilnTaskToolResult:
    output: Dict | str
    kiln_task_tool_data: str

    def __init__(self, output: str, kiln_task_tool_data: str):
        self.output = output
        self.kiln_task_tool_data = kiln_task_tool_data


class KilnTaskTool(KilnToolInterface):
    """
    A tool that wraps a Kiln task, allowing it to be called as a function.

    This tool loads a task by ID and executes it using the specified run configuration.
    """

    def __init__(
        self,
        project_id: str,
        tool_id: str,
        data_model: ExternalToolServer,
    ):
        self._project_id = project_id
        self._tool_server_model = data_model
        self._tool_id = tool_id

        self._name = data_model.properties.get("name", "")
        self._description = data_model.properties.get("description", "")
        self._task_id = data_model.properties.get("task_id", "")
        self._run_config_id = data_model.properties.get("run_config_id", "")

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description

    async def toolcall_definition(self) -> Dict[str, Any]:
        """Generate OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": self.parameters_schema,
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> KilnTaskToolResult:
        """Execute the wrapped Kiln task with the given parameters and calling context."""
        if context is None:
            raise ValueError("Context is required for running a KilnTaskTool.")

        # Determine the input format
        if self._task.input_json_schema:
            # Structured input - pass kwargs directly
            input = kwargs
        else:
            # Plaintext input - extract from 'input' parameter
            if "input" in kwargs:
                input = kwargs["input"]
            else:
                raise ValueError(f"Input not found in kwargs: {kwargs}")

        # These imports are here to avoid circular chains
        from kiln_ai.adapters.adapter_registry import adapter_for_task
        from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig

        # Create adapter and run the task using the calling task's allow_saving setting
        adapter = adapter_for_task(
            self._task,
            run_config_properties=self._run_config.run_config_properties,
            base_adapter_config=AdapterConfig(
                allow_saving=context.allow_saving,
                default_tags=["tool_call"],
            ),
        )
        task_run = await adapter.invoke(
            input,
            input_source=DataSource(
                type=DataSourceType.tool_call,
                run_config=self._run_config.run_config_properties,
            ),
        )

        return KilnTaskToolResult(
            output=task_run.output.output,
            kiln_task_tool_data=f"{self._project_id},{self._tool_id},{self._task.id},{task_run.id}",
        )

    @cached_property
    def _task(self) -> Task:
        # Load the project first
        project = project_from_id(self._project_id)
        if project is None:
            raise ValueError(f"Project not found: {self._project_id}")

        # Load the task from the project
        task = Task.from_id_and_parent_path(self._task_id, project.path)
        if task is None:
            raise ValueError(
                f"Task not found: {self._task_id} in project {self._project_id}"
            )
        return task

    @cached_property
    def _run_config(self) -> TaskRunConfig:
        run_config = next(
            (
                run_config
                for run_config in self._task.run_configs(readonly=True)
                if run_config.id == self._run_config_id
            ),
            None,
        )
        if run_config is None:
            raise ValueError(
                f"Task run config not found: {self._run_config_id} for task {self._task_id} in project {self._project_id}"
            )
        return run_config

    @cached_property
    def parameters_schema(self) -> Dict[str, Any]:
        if self._task.input_json_schema:
            # Use the task's input schema directly if it exists
            parameters_schema = self._task.input_schema()
        else:
            # For plaintext tasks, create a simple string input parameter
            parameters_schema = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Plaintext input for the tool.",
                    }
                },
                "required": ["input"],
            }
        if parameters_schema is None:
            raise ValueError(
                f"Failed to create parameters schema for tool_id {self._tool_id}"
            )
        return parameters_schema
