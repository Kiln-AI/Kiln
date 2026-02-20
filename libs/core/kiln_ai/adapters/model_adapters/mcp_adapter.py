import json
from typing import Tuple

from kiln_ai.adapters.model_adapters.base_adapter import AdapterConfig, BaseAdapter
from kiln_ai.adapters.parsers.json_parser import parse_json_string
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import DataSource, Task, TaskRun, Usage
from kiln_ai.datamodel.datamodel_enums import InputType
from kiln_ai.datamodel.json_schema import (
    single_string_field_name,
    validate_schema_with_value_error,
)
from kiln_ai.datamodel.run_config import McpRunConfigProperties
from kiln_ai.datamodel.task import RunConfigProperties
from kiln_ai.run_context import (
    clear_agent_run_id,
    generate_agent_run_id,
    get_agent_run_id,
    set_agent_run_id,
)
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.tools.tool_registry import tool_from_id
from kiln_ai.utils.config import Config
from kiln_ai.utils.open_ai_types import (
    ChatCompletionAssistantMessageParamWrapper,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)


class MCPAdapter(BaseAdapter):
    def __init__(
        self,
        task: Task,
        run_config: RunConfigProperties,
        config: AdapterConfig | None = None,
    ):
        if run_config.type != "mcp":
            raise ValueError("MCPAdapter requires a run config with type mcp")
        super().__init__(task=task, run_config=run_config, config=config)

    def adapter_name(self) -> str:
        return "mcp_adapter"

    async def _run(self, input: InputType) -> Tuple[RunOutput, Usage | None]:
        run_config = self.run_config
        if not isinstance(run_config, McpRunConfigProperties):
            raise ValueError("MCPAdapter requires McpRunConfigProperties")

        # Get the actual tool from tool registry
        tool = tool_from_id(run_config.tool_reference.tool_id, self.task)

        tool_kwargs: dict[str, object]
        if self.input_schema is None:
            if not isinstance(input, str):
                raise ValueError("Plaintext task input must be a string")
            field_name = "input"
            tool_schema = run_config.tool_reference.input_schema
            if tool_schema is not None:
                field_name = single_string_field_name(tool_schema)
                if field_name is None:
                    raise ValueError(
                        "Plaintext task input requires MCP tool input schema with exactly one string field."
                    )
            tool_kwargs = {field_name: input}
        elif isinstance(input, dict):
            tool_kwargs = input
        else:
            tool_kwargs = {"input": input}

        result = await tool.run(context=None, **tool_kwargs)
        return RunOutput(output=result.output, intermediate_outputs=None), None

    async def invoke(
        self,
        input: InputType,
        input_source: DataSource | None = None,
    ) -> TaskRun:
        run_output, _ = await self.invoke_returning_run_output(input, input_source)
        return run_output

    async def invoke_returning_run_output(
        self,
        input: InputType,
        input_source: DataSource | None = None,
    ) -> Tuple[TaskRun, RunOutput]:
        """
        Runs the task and returns both the persisted TaskRun and raw RunOutput.
        If this call is the root of a run, it creates an agent run context, ensures MCP tool calls have a valid session scope, and cleans up the session/context on completion.
        """
        is_root_agent = get_agent_run_id() is None

        if is_root_agent:
            run_id = generate_agent_run_id()
            set_agent_run_id(run_id)

        try:
            return await self._run_and_validate_output(input, input_source)
        finally:
            if is_root_agent:
                try:
                    run_id = get_agent_run_id()
                    if run_id:
                        await MCPSessionManager.shared().cleanup_session(run_id)
                finally:
                    clear_agent_run_id()

    async def _run_and_validate_output(
        self,
        input: InputType,
        input_source: DataSource | None,
    ) -> Tuple[TaskRun, RunOutput]:
        """
        Run the MCP task and validate the output.
        """
        if self.input_schema is not None:
            validate_schema_with_value_error(
                input,
                self.input_schema,
                "This task requires a specific input schema. While the model produced JSON, that JSON didn't meet the schema. Search 'Troubleshooting Structured Data Issues' in our docs for more information.",
                require_object=False,
            )

        run_output, usage = await self._run(input)

        if self.output_schema is not None:
            if isinstance(run_output.output, str):
                parsed_output = parse_json_string(run_output.output)
            else:
                parsed_output = run_output.output
            if not isinstance(parsed_output, dict):
                raise RuntimeError(
                    f"structured response is not a dict: {parsed_output}"
                )
            validate_schema_with_value_error(
                parsed_output,
                self.output_schema,
                "This task requires a specific output schema. While the model produced JSON, that JSON didn't meet the schema. Search 'Troubleshooting Structured Data Issues' in our docs for more information.",
            )
            run_output.output = parsed_output
        else:
            if not isinstance(run_output.output, str):
                raise RuntimeError(
                    f"response is not a string for non-structured task: {run_output.output}"
                )

        # Build single turn trace
        trace = self._build_single_turn_trace(input, run_output.output)

        run = self.generate_run(input, input_source, run_output, usage, trace)

        if (
            self.base_adapter_config.allow_saving
            and Config.shared().autosave_runs
            and self.task.path is not None
        ):
            run.save_to_file()
        else:
            run.id = None

        return run, run_output

    # Helpers

    @staticmethod
    def _build_single_turn_trace(
        input: InputType, output: str | dict
    ) -> list[ChatCompletionMessageParam]:
        user_message: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": input
            if isinstance(input, str)
            else json.dumps(input, ensure_ascii=False),
        }
        assistant_message: ChatCompletionAssistantMessageParamWrapper = {
            "role": "assistant",
            "content": output
            if isinstance(output, str)
            else json.dumps(output, ensure_ascii=False),
        }
        return [user_message, assistant_message]
