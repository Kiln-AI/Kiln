import json
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Dict, Tuple

from kiln_ai.adapters.chat.chat_formatter import ChatFormatter, get_chat_formatter
from kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    StructuredOutputMode,
    default_structured_output_mode_for_model_provider,
)
from kiln_ai.adapters.parsers.json_parser import parse_json_string
from kiln_ai.adapters.parsers.parser_registry import model_parser_from_id
from kiln_ai.adapters.parsers.request_formatters import request_formatter_from_id
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.adapters.provider_tools import kiln_model_provider_from
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskRun,
    Usage,
)
from kiln_ai.datamodel.datamodel_enums import ChatStrategy
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.task import RunConfig
from kiln_ai.utils.config import Config


@dataclass
class AdapterConfig:
    """
    An adapter config is config options that do NOT impact the output of the model.

    For example: if it's saved, of if we request additional data like logprobs.
    """

    allow_saving: bool = True
    top_logprobs: int | None = None
    default_tags: list[str] | None = None


class BaseAdapter(metaclass=ABCMeta):
    """Base class for AI model adapters that handle task execution.

    This abstract class provides the foundation for implementing model-specific adapters
    that can process tasks with structured or unstructured inputs/outputs. It handles
    input/output validation, prompt building, and run tracking.

    Attributes:
        prompt_builder (BasePromptBuilder): Builder for constructing prompts for the model
        kiln_task (Task): The task configuration and metadata
        output_schema (dict | None): JSON schema for validating structured outputs
        input_schema (dict | None): JSON schema for validating structured inputs
    """

    def __init__(
        self,
        run_config: RunConfig,
        config: AdapterConfig | None = None,
    ):
        self.run_config = run_config
        self.update_run_config_unknown_structured_output_mode()
        self.prompt_builder = prompt_builder_from_id(
            run_config.prompt_id, run_config.task
        )
        self._model_provider: KilnModelProvider | None = None

        self.output_schema = self.task().output_json_schema
        self.input_schema = self.task().input_json_schema
        self.base_adapter_config = config or AdapterConfig()

    def task(self) -> Task:
        return self.run_config.task

    def model_provider(self) -> KilnModelProvider:
        """
        Lazy load the model provider for this adapter.
        """
        if self._model_provider is not None:
            return self._model_provider
        if not self.run_config.model_name or not self.run_config.model_provider_name:
            raise ValueError("model_name and model_provider_name must be provided")
        self._model_provider = kiln_model_provider_from(
            self.run_config.model_name, self.run_config.model_provider_name
        )
        if not self._model_provider:
            raise ValueError(
                f"model_provider_name {self.run_config.model_provider_name} not found for model {self.run_config.model_name}"
            )
        return self._model_provider

    async def invoke(
        self,
        input: Dict | str,
        input_source: DataSource | None = None,
    ) -> TaskRun:
        run_output, _ = await self.invoke_returning_run_output(input, input_source)
        return run_output

    async def invoke_returning_run_output(
        self,
        input: Dict | str,
        input_source: DataSource | None = None,
    ) -> Tuple[TaskRun, RunOutput]:
        # validate input
        if self.input_schema is not None:
            if not isinstance(input, dict):
                raise ValueError(f"structured input is not a dict: {input}")

            validate_schema_with_value_error(
                input,
                self.input_schema,
                "This task requires a specific input schema. While the model produced JSON, that JSON didn't meet the schema. Search 'Troubleshooting Structured Data Issues' in our docs for more information.",
            )

        # Format model input for model call (we save the original input in the task without formatting)
        formatted_input = input
        formatter_id = self.model_provider().formatter
        if formatter_id is not None:
            formatter = request_formatter_from_id(formatter_id)
            formatted_input = formatter.format_input(input)

        # Run
        run_output, usage = await self._run(formatted_input)

        # Parse
        provider = self.model_provider()
        parser = model_parser_from_id(provider.parser)
        parsed_output = parser.parse_output(original_output=run_output)

        # validate output
        if self.output_schema is not None:
            # Parse json to dict if we have structured output
            if isinstance(parsed_output.output, str):
                parsed_output.output = parse_json_string(parsed_output.output)

            if not isinstance(parsed_output.output, dict):
                raise RuntimeError(
                    f"structured response is not a dict: {parsed_output.output}"
                )
            validate_schema_with_value_error(
                parsed_output.output,
                self.output_schema,
                "This task requires a specific output schema. While the model produced JSON, that JSON didn't meet the schema. Search 'Troubleshooting Structured Data Issues' in our docs for more information.",
            )
        else:
            if not isinstance(parsed_output.output, str):
                raise RuntimeError(
                    f"response is not a string for non-structured task: {parsed_output.output}"
                )

        # Validate reasoning content is present (if reasoning)
        if (
            provider.reasoning_capable
            and (
                not parsed_output.intermediate_outputs
                or "reasoning" not in parsed_output.intermediate_outputs
            )
            and not (
                provider.reasoning_optional_for_structured_output
                and self.has_structured_output()
            )
        ):
            raise RuntimeError(
                "Reasoning is required for this model, but no reasoning was returned."
            )

        # Generate the run and output
        run = self.generate_run(input, input_source, parsed_output, usage)

        # Save the run if configured to do so, and we have a path to save to
        if (
            self.base_adapter_config.allow_saving
            and Config.shared().autosave_runs
            and self.task().path is not None
        ):
            run.save_to_file()
        else:
            # Clear the ID to indicate it's not persisted
            run.id = None

        return run, run_output

    def has_structured_output(self) -> bool:
        return self.output_schema is not None

    @abstractmethod
    def adapter_name(self) -> str:
        pass

    @abstractmethod
    async def _run(self, input: Dict | str) -> Tuple[RunOutput, Usage | None]:
        pass

    def build_prompt(self) -> str:
        # The prompt builder needs to know if we want to inject formatting instructions
        structured_output_mode = self.run_config.structured_output_mode
        add_json_instructions = self.has_structured_output() and (
            structured_output_mode == StructuredOutputMode.json_instructions
            or structured_output_mode
            == StructuredOutputMode.json_instruction_and_object
        )

        return self.prompt_builder.build_prompt(
            include_json_instructions=add_json_instructions
        )

    def build_chat_formatter(self, input: Dict | str) -> ChatFormatter:
        # Determine the chat strategy to use based on the prompt the user selected, the model's capabilities, and if the model was finetuned with a specific chat strategy.

        cot_prompt = self.prompt_builder.chain_of_thought_prompt()
        system_message = self.build_prompt()

        # If no COT prompt, use the single turn strategy. Even when a tuned strategy is set, as the tuned strategy is either already single turn, or won't work without a COT prompt.
        if not cot_prompt:
            return get_chat_formatter(
                strategy=ChatStrategy.single_turn,
                system_message=system_message,
                user_input=input,
            )

        # Some models like finetunes are trained with a specific chat strategy. Use that.
        # However, don't use that if it is single turn. The user selected a COT prompt, and we give explicit prompt selection priority over the tuned strategy.
        tuned_chat_strategy = self.model_provider().tuned_chat_strategy
        if tuned_chat_strategy and tuned_chat_strategy != ChatStrategy.single_turn:
            return get_chat_formatter(
                strategy=tuned_chat_strategy,
                system_message=system_message,
                user_input=input,
                thinking_instructions=cot_prompt,
            )

        # Pick the best chat strategy for the model given it has a cot prompt.
        reasoning_capable = self.model_provider().reasoning_capable
        if reasoning_capable:
            # "Thinking" LLM designed to output thinking in a structured format. We'll use it's native format.
            # A simple message with the COT prompt appended to the message list is sufficient
            return get_chat_formatter(
                strategy=ChatStrategy.single_turn_r1_thinking,
                system_message=system_message,
                user_input=input,
                thinking_instructions=cot_prompt,
            )
        else:
            # Unstructured output with COT
            # Two calls to separate the thinking from the final response
            return get_chat_formatter(
                strategy=ChatStrategy.two_message_cot,
                system_message=system_message,
                user_input=input,
                thinking_instructions=cot_prompt,
            )

    # create a run and task output
    def generate_run(
        self,
        input: Dict | str,
        input_source: DataSource | None,
        run_output: RunOutput,
        usage: Usage | None = None,
    ) -> TaskRun:
        # Convert input and output to JSON strings if they are dictionaries
        input_str = (
            json.dumps(input, ensure_ascii=False) if isinstance(input, dict) else input
        )
        output_str = (
            json.dumps(run_output.output, ensure_ascii=False)
            if isinstance(run_output.output, dict)
            else run_output.output
        )

        # If no input source is provided, use the human data source
        if input_source is None:
            input_source = DataSource(
                type=DataSourceType.human,
                properties={"created_by": Config.shared().user_id},
            )

        new_task_run = TaskRun(
            parent=self.task(),
            input=input_str,
            input_source=input_source,
            output=TaskOutput(
                output=output_str,
                # Synthetic since an adapter, not a human, is creating this
                source=DataSource(
                    type=DataSourceType.synthetic,
                    properties=self._properties_for_task_output(),
                ),
            ),
            intermediate_outputs=run_output.intermediate_outputs,
            tags=self.base_adapter_config.default_tags or [],
            usage=usage,
        )

        return new_task_run

    def _properties_for_task_output(self) -> Dict[str, str | int | float]:
        props = {}

        # adapter info
        props["adapter_name"] = self.adapter_name()
        props["model_name"] = self.run_config.model_name
        props["model_provider"] = self.run_config.model_provider_name
        props["prompt_id"] = self.run_config.prompt_id
        props["structured_output_mode"] = self.run_config.structured_output_mode
        props["temperature"] = self.run_config.temperature
        props["top_p"] = self.run_config.top_p

        return props

    def update_run_config_unknown_structured_output_mode(self) -> None:
        structured_output_mode = self.run_config.structured_output_mode

        # Old datamodels didn't save the structured output mode. Some clients (tests, end users) might not set it.
        # Look up our recommended mode from ml_model_list if we have one
        if structured_output_mode == StructuredOutputMode.unknown:
            new_run_config = self.run_config.model_copy(deep=True)
            structured_output_mode = default_structured_output_mode_for_model_provider(
                self.run_config.model_name,
                self.run_config.model_provider_name,
            )
            new_run_config.structured_output_mode = structured_output_mode
            self.run_config = new_run_config
