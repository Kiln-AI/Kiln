import json
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Dict

from kiln_ai.adapters.ml_model_list import KilnModelProvider, StructuredOutputMode
from kiln_ai.adapters.parsers.parser_registry import model_parser_from_id
from kiln_ai.adapters.prompt_builders import BasePromptBuilder, SimplePromptBuilder
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
from kiln_ai.utils.config import Config


@dataclass
class AdapterInfo:
    adapter_name: str
    model_name: str
    model_provider: str
    prompt_builder_name: str
    prompt_id: str | None = None


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
        kiln_task: Task,
        model_name: str,
        model_provider_name: str,
        prompt_builder: BasePromptBuilder | None = None,
        tags: list[str] | None = None,
    ):
        self.prompt_builder = prompt_builder or SimplePromptBuilder(kiln_task)
        self.kiln_task = kiln_task
        self.output_schema = self.kiln_task.output_json_schema
        self.input_schema = self.kiln_task.input_json_schema
        self.default_tags = tags
        self.model_name = model_name
        self.model_provider_name = model_provider_name
        self._model_provider: KilnModelProvider | None = None

    async def model_provider(self) -> KilnModelProvider:
        """
        Lazy load the model provider for this adapter.
        """
        if self._model_provider is not None:
            return self._model_provider
        if not self.model_name or not self.model_provider_name:
            raise ValueError("model_name and model_provider_name must be provided")
        self._model_provider = await kiln_model_provider_from(
            self.model_name, self.model_provider_name
        )
        if not self._model_provider:
            raise ValueError(
                f"model_provider_name {self.model_provider_name} not found for model {self.model_name}"
            )
        return self._model_provider

    async def invoke_returning_raw(
        self,
        input: Dict | str,
        input_source: DataSource | None = None,
    ) -> Dict | str:
        result = await self.invoke(input, input_source)
        if self.kiln_task.output_json_schema is None:
            return result.output.output
        else:
            return json.loads(result.output.output)

    async def invoke(
        self,
        input: Dict | str,
        input_source: DataSource | None = None,
    ) -> TaskRun:
        # validate input
        if self.input_schema is not None:
            if not isinstance(input, dict):
                raise ValueError(f"structured input is not a dict: {input}")
            validate_schema(input, self.input_schema)

        # Run
        run_output = await self._run(input)

        # Parse
        # TODO P0
        provider = await self.model_provider()
        parser = model_parser_from_id(provider.parser)(
            structured_output=self.has_structured_output()
        )
        parsed_output = parser.parse_output(original_output=run_output)
        print(
            f"parsed_output: {parsed_output.output} \nIntermediate outputs: {parsed_output.intermediate_outputs}"
        )

        # validate output
        if self.output_schema is not None:
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

        # Generate the run and output
        run = self.generate_run(input, input_source, parsed_output)

        # Save the run if configured to do so, and we have a path to save to
        if Config.shared().autosave_runs and self.kiln_task.path is not None:
            run.save_to_file()
        else:
            # Clear the ID to indicate it's not persisted
            run.id = None

        return run

    def has_structured_output(self) -> bool:
        return self.output_schema is not None

    @abstractmethod
    def adapter_info(self) -> AdapterInfo:
        pass

    @abstractmethod
    async def _run(self, input: Dict | str) -> RunOutput:
        pass

    async def build_prompt(self) -> str:
        provider = await self.model_provider()
        json_instructions = self.has_structured_output() and (
            provider.structured_output_mode == StructuredOutputMode.json_instructions
            or provider.structured_output_mode
            == StructuredOutputMode.json_instruction_and_object
        )
        return self.prompt_builder.build_prompt(
            include_json_instructions=json_instructions
        )

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
            parent=self.kiln_task,
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
            tags=self.default_tags or [],
        )

        return new_task_run

    def _properties_for_task_output(self) -> Dict[str, str | int | float]:
        props = {}

        # adapter info
        adapter_info = self.adapter_info()
        props["adapter_name"] = adapter_info.adapter_name
        props["model_name"] = adapter_info.model_name
        props["model_provider"] = adapter_info.model_provider
        props["prompt_builder_name"] = adapter_info.prompt_builder_name
        if adapter_info.prompt_id is not None:
            props["prompt_id"] = adapter_info.prompt_id

        return props
