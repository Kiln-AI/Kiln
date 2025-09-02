import json
from typing import TYPE_CHECKING, Any, Dict, Union

from kiln_ai.datamodel.datamodel_enums import ModelProviderName, StructuredOutputMode
from kiln_ai.tools.base_tool import KilnToolInterface
from kiln_ai.tools.tool_id import ToolId

if TYPE_CHECKING:
    from kiln_ai.datamodel import Task
    from kiln_ai.datamodel.task import RunConfigProperties


class KilnTaskTool(KilnToolInterface):
    """
    A tool that wraps a Kiln task, allowing it to be called as a function.

    This tool loads a task by ID and executes it using a default run configuration.
    """

    def __init__(
        self,
        task_id: str,
        project_id: str,
        default_run_config: "RunConfigProperties | None" = None,
    ):
        self._task_id = task_id
        self._project_id = project_id
        self._default_run_config = default_run_config
        self._task: Union["Task", None] = None
        self._tool_id = f"kiln_task::{project_id}::{task_id}"

    async def id(self) -> ToolId:
        return self._tool_id

    async def name(self) -> str:
        task = await self._get_task()
        return f"run_{task.name.lower().replace(' ', '_')}"

    async def description(self) -> str:
        task = await self._get_task()
        description = f"Run the Kiln task '{task.name}'"
        if task.description:
            description += f": {task.description}"
        return description

    async def toolcall_definition(self) -> Dict[str, Any]:
        """Generate OpenAI-compatible tool definition."""
        task = await self._get_task()

        # Build parameters schema based on task's input schema
        parameters_schema = {"type": "object", "properties": {}, "required": []}

        if task.input_json_schema:
            # Use the task's input schema directly
            parameters_schema = task.input_schema()
        else:
            # For plaintext tasks, create a simple string input parameter
            parameters_schema = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": f"Input for the task: {task.instruction}",
                    }
                },
                "required": ["input"],
            }

        return {
            "type": "function",
            "function": {
                "name": await self.name(),
                "description": await self.description(),
                "parameters": parameters_schema,
            },
        }

    async def run(self, **kwargs) -> str:
        """Execute the wrapped Kiln task with the given parameters."""
        import logging

        logger = logging.getLogger(__name__)

        logger.info(
            f"KilnTaskTool executing task '{self._task_id}' with arguments: {kwargs}"
        )
        task = await self._get_task()

        # Determine the input format
        if task.input_json_schema:
            # Structured input - pass kwargs directly
            input_data = kwargs
        else:
            # Plaintext input - extract from 'input' parameter or convert kwargs
            if "input" in kwargs:
                input_data = kwargs["input"]
            else:
                # Convert kwargs to a descriptive string
                input_data = json.dumps(kwargs, indent=2)

        # Create run config (use default or create a basic one)
        from kiln_ai.datamodel.task import RunConfigProperties

        run_config = (
            self._default_run_config
            or RunConfigProperties(
                model_name="gpt-4o-mini",  # Default model
                model_provider_name=ModelProviderName.openai,
                prompt_id="simple_prompt_builder",  # Use string literal to avoid circular import
                structured_output_mode=StructuredOutputMode.default,  # Use 'default' to let adapter handle conflicts
                temperature=0.7,
                top_p=1.0,
            )
        )

        # Create adapter and run the task
        from kiln_ai.adapters.adapter_registry import adapter_for_task
        from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig

        adapter = adapter_for_task(
            task,
            run_config_properties=run_config,
            base_adapter_config=AdapterConfig(
                allow_saving=False,  # Don't save tool execution runs
                default_tags=["tool_execution"],
            ),
        )

        # Execute the task
        task_run = await adapter.invoke(input_data)

        # Log the result
        logger.info(
            f"KilnTaskTool '{self._task_id}' completed with output: {task_run.output.output}"
        )

        # Return the output
        return task_run.output.output

    async def _get_task(self) -> "Task":
        """Lazy load the task."""
        if self._task is None:
            # Load the project first
            from kiln_ai.utils.project_utils import project_from_id

            project = project_from_id(self._project_id)
            if project is None:
                raise ValueError(f"Project not found: {self._project_id}")

            # Load the task from the project
            from kiln_ai.datamodel import Task

            self._task = Task.from_id_and_parent_path(self._task_id, project.path)
            if self._task is None:
                raise ValueError(
                    f"Task not found: {self._task_id} in project {self._project_id}"
                )
        return self._task
