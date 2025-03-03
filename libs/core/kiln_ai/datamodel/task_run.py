import json
from typing import TYPE_CHECKING, Dict, List, Union

import jsonschema
import jsonschema.exceptions
from pydantic import Field, ValidationInfo, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import KilnParentedModel
from kiln_ai.datamodel.json_schema import validate_schema
from kiln_ai.datamodel.strict_mode import strict_mode
from kiln_ai.datamodel.task_output import DataSource, TaskOutput

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


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

    def has_thinking_training_data(self) -> bool:
        """
        Does this run have thinking data that we can use to train a thinking model?
        """
        if self.intermediate_outputs is None:
            return False
        return (
            "chain_of_thought" in self.intermediate_outputs
            or "reasoning" in self.intermediate_outputs
        )

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

        # validate output
        if task.input_json_schema is not None:
            try:
                validate_schema(json.loads(self.input), task.input_json_schema)
            except json.JSONDecodeError:
                raise ValueError("Input is not a valid JSON object")
            except jsonschema.exceptions.ValidationError as e:
                raise ValueError(f"Input does not match task input schema: {e}")
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
