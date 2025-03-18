import json
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Dict, Literal, Tuple

from kiln_ai.adapters.ml_model_list import KilnModelProvider, StructuredOutputMode
from kiln_ai.adapters.parsers.json_parser import parse_json_string
from kiln_ai.adapters.parsers.parser_registry import model_parser_from_id
from kiln_ai.adapters.prompt_builders import prompt_builder_from_id
from kiln_ai.adapters.provider_tools import kiln_model_provider_from
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import (
    DataSource,
    DataSourceType,
    Task,
    TaskOutput,
    TaskRun,
)
from kiln_ai.datamodel.json_schema import validate_schema
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


COT_FINAL_ANSWER_PROMPT = "Considering the above, return a final result."


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
            validate_schema(input, self.input_schema)

        # Run
        run_output = await self._run(input)

        # Parse
        provider = self.model_provider()
        parser = model_parser_from_id(provider.parser)(
            structured_output=self.has_structured_output()
        )
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
            validate_schema(parsed_output.output, self.output_schema)
        else:
            if not isinstance(parsed_output.output, str):
                raise RuntimeError(
                    f"response is not a string for non-structured task: {parsed_output.output}"
                )

        # Validate reasoning content is present (if reasoning)
        if provider.reasoning_capable and (
            not parsed_output.intermediate_outputs
            or "reasoning" not in parsed_output.intermediate_outputs
        ):
            raise RuntimeError(
                "Reasoning is required for this model, but no reasoning was returned."
            )

        # Generate the run and output
        run = self.generate_run(input, input_source, parsed_output)

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
    async def _run(self, input: Dict | str) -> RunOutput:
        pass

    def build_prompt(self) -> str:
        # The prompt builder needs to know if we want to inject formatting instructions
        provider = self.model_provider()
        add_json_instructions = self.has_structured_output() and (
            provider.structured_output_mode == StructuredOutputMode.json_instructions
            or provider.structured_output_mode
            == StructuredOutputMode.json_instruction_and_object
        )

        return self.prompt_builder.build_prompt(
            include_json_instructions=add_json_instructions
        )

    def run_strategy(
        self,
    ) -> Tuple[Literal["cot_as_message", "cot_two_call", "basic"], str | None]:
        # Determine the run strategy for COT prompting. 3 options:
        # 1. "Thinking" LLM designed to output thinking in a structured format plus a COT prompt: we make 1 call to the LLM, which outputs thinking in a structured format. We include the thinking instuctions as a message.
        # 2. Normal LLM with COT prompt: we make 2 calls to the LLM - one for thinking and one for the final response. This helps us use the LLM's structured output modes (json_schema, tools, etc), which can't be used in a single call. It also separates the thinking from the final response.
        # 3. Non chain of thought: we make 1 call to the LLM, with no COT prompt.
        cot_prompt = self.prompt_builder.chain_of_thought_prompt()
        reasoning_capable = self.model_provider().reasoning_capable

        if cot_prompt and reasoning_capable:
            # 1: "Thinking" LLM designed to output thinking in a structured format
            # A simple message with the COT prompt appended to the message list is sufficient
            return "cot_as_message", cot_prompt
        elif cot_prompt:
            # 2: Unstructured output with COT
            # Two calls to separate the thinking from the final response
            return "cot_two_call", cot_prompt
        else:
            return "basic", None

    # create a run and task output
    def generate_run(
        self, input: Dict | str, input_source: DataSource | None, run_output: RunOutput
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
        )

        return new_task_run

    def _properties_for_task_output(self) -> Dict[str, str | int | float]:
        props = {}

        # adapter info
        props["adapter_name"] = self.adapter_name()
        props["model_name"] = self.run_config.model_name
        props["model_provider"] = self.run_config.model_provider_name
        props["prompt_id"] = self.run_config.prompt_id

        return props
