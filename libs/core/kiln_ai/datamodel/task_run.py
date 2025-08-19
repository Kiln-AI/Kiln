import json
from typing import TYPE_CHECKING, Dict, List, Union

from pydantic import BaseModel, Field, ValidationInfo, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.json_schema import validate_schema_with_value_error
from kiln_ai.datamodel.strict_mode import strict_mode
from kiln_ai.datamodel.task_output import DataSource, TaskOutput
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class Usage(BaseModel):
    input_tokens: int | None = Field(
        default=None,
        description="The number of input tokens used in the task run.",
        ge=0,
    )
    output_tokens: int | None = Field(
        default=None,
        description="The number of output tokens used in the task run.",
        ge=0,
    )
    total_tokens: int | None = Field(
        default=None,
        description="The total number of tokens used in the task run.",
        ge=0,
    )
    cost: float | None = Field(
        default=None,
        description="The cost of the task run in US dollars, saved at runtime (prices can change over time).",
        ge=0,
    )

    def __add__(self, other: "Usage") -> "Usage":
        """Add two Usage objects together, handling None values gracefully.

        None + None = None
        None + value = value
        value + None = value
        value1 + value2 = value1 + value2
        """
        if not isinstance(other, Usage):
            raise TypeError(f"Cannot add Usage with {type(other).__name__}")

        def _add_optional_int(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            if a is None:
                return b
            if b is None:
                return a
            return a + b

        def _add_optional_float(a: float | None, b: float | None) -> float | None:
            if a is None and b is None:
                return None
            if a is None:
                return b
            if b is None:
                return a
            return a + b

        return Usage(
            input_tokens=_add_optional_int(self.input_tokens, other.input_tokens),
            output_tokens=_add_optional_int(self.output_tokens, other.output_tokens),
            total_tokens=_add_optional_int(self.total_tokens, other.total_tokens),
            cost=_add_optional_float(self.cost, other.cost),
        )


class TaskRun(KilnParentedModel):
    """
    Represents a single execution of a Task.

    Contains the input used, its source, the output produced, and optional
    repair information if the output needed correction.
    """

    input: str = Field(
        description="The inputs to the task. JSON formatted for structured input, plaintext for unstructured input."
    )
    input_source: DataSource | None = Field(
        default=None, description="The source of the input: human or synthetic."
    )

    output: TaskOutput = Field(description="The output of the task run.")
    repair_instructions: str | None = Field(
        default=None,
        description="Instructions for fixing the output. Should define what is wrong, and how to fix it. Will be used by models for both generating a fixed output, and evaluating future models.",
    )
    repaired_output: TaskOutput | None = Field(
        default=None,
        description="An version of the output with issues fixed. This must be a 'fixed' version of the existing output, and not an entirely new output. If you wish to generate an ideal curatorial output for this task unrelated to this output, generate a new TaskOutput with type 'human' instead of using this field.",
    )
    intermediate_outputs: Dict[str, str] | None = Field(
        default=None,
        description="Intermediate outputs from the task run. Keys are the names of the intermediate output steps (cot=chain of thought, etc), values are the output data.",
    )
    tags: List[str] = Field(
        default=[],
        description="Tags for the task run. Tags are used to categorize task runs for filtering and reporting.",
    )
    usage: Usage | None = Field(
        default=None,
        description="Usage information for the task run. This includes the number of input tokens, output tokens, and total tokens used.",
    )
    trace: list[ChatCompletionMessageParam] | None = Field(
        default=None,
        description="The trace of the task run in OpenAI format. This is the list of messages that were sent to/from the model.",
    )

    def thinking_training_data(self) -> str | None:
        """
        Get the thinking training data from the task run.
        """
        if self.intermediate_outputs is None:
            return None
        return self.intermediate_outputs.get(
            "reasoning"
        ) or self.intermediate_outputs.get("chain_of_thought")

    def has_thinking_training_data(self) -> bool:
        """
        Does this run have thinking data that we can use to train a thinking model?
        """
        return self.thinking_training_data() is not None

    # Workaround to return typed parent without importing Task
    def parent_task(self) -> Union["Task", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Task":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_input_format(self, info: ValidationInfo) -> Self:
        # Don't validate if loading from file (not new). Too slow.
        # We don't allow changing task schema, so this is redundant validation.
        # Note: we still validate if editing a loaded model
        if self.loading_from_file(info):
            # Consider loading an existing model as validated.
            self._last_validated_input = self.input
            return self

        # Don't validate if input has not changed. Too slow to run this every time.
        if (
            hasattr(self, "_last_validated_input")
            and self.input == self._last_validated_input
        ):
            return self

        task = self.parent_task()
        if task is None:
            # don't validate this relationship until we have a path or parent. Give them time to build it (but will catch it before saving)
            return self

        # validate input
        if task.input_json_schema is not None:
            try:
                input_parsed = json.loads(self.input)
            except json.JSONDecodeError:
                raise ValueError("Input is not a valid JSON object")

            validate_schema_with_value_error(
                input_parsed,
                task.input_json_schema,
                "Input does not match task input schema.",
            )

        self._last_validated_input = self.input
        return self

    @model_validator(mode="after")
    def validate_output_format(self, info: ValidationInfo) -> Self:
        # Don't validate if loading from file (not new). Too slow.
        # Note: we still validate if editing a loaded model's output.
        if self.loading_from_file(info):
            # Consider loading an existing model as validated.
            self._last_validated_output = self.output.output if self.output else None
            return self

        # Don't validate unless output has changed since last validation.
        # The validator is slow and costly, don't want it running when setting other fields.
        if (
            hasattr(self, "_last_validated_output")
            and self.output is not None
            and self.output.output == self._last_validated_output
        ):
            return self

        task = self.parent_task()
        if task is None:
            return self

        self.output.validate_output_format(task)
        self._last_validated_output = self.output.output if self.output else None
        return self

    @model_validator(mode="after")
    def validate_repaired_output(self) -> Self:
        if self.repaired_output is not None:
            if self.repaired_output.rating is not None:
                raise ValueError(
                    "Repaired output rating must be None. Repaired outputs are assumed to have a perfect rating, as they have been fixed."
                )

            task = self.parent_task()
            if (
                task is not None
                and self.repaired_output.output is not None
                and task.output_json_schema is not None
            ):
                try:
                    output_parsed = json.loads(self.repaired_output.output)
                except json.JSONDecodeError:
                    raise ValueError("Repaired output is not a valid JSON object")

                validate_schema_with_value_error(
                    output_parsed,
                    task.output_json_schema,
                    "Repaired output does not match task output schema.",
                )

        if self.repair_instructions is None and self.repaired_output is not None:
            raise ValueError(
                "Repair instructions are required if providing a repaired output."
            )
        if self.repair_instructions is not None and self.repaired_output is None:
            raise ValueError(
                "A repaired output is required if providing repair instructions."
            )

        return self

    @model_validator(mode="after")
    def validate_input_source(self, info: ValidationInfo) -> Self:
        # On strict mode and not loaded from file, we validate input_source is not None.
        # We want to be able to load any data, even if it's not perfect. But we want to create perfect data when adding new data.
        if not strict_mode():
            return self
        if self.loaded_from_file(info):
            return self
        if self.input_source is None:
            raise ValueError("input_source is required when strict mode is enabled")
        return self

    @model_validator(mode="after")
    def validate_tags(self) -> Self:
        for tag in self.tags:
            if not tag:
                raise ValueError("Tags cannot be empty strings")
            if " " in tag:
                raise ValueError("Tags cannot contain spaces. Try underscores.")

        return self
