from __future__ import annotations

import json
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Dict, List, Type, Union

import jsonschema
import jsonschema.exceptions
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.json_schema import JsonObjectSchema, schema_from_json_str

from .basemodel import (
    ID_FIELD,
    ID_TYPE,
    KilnBaseModel,
    KilnParentedModel,
    KilnParentModel,
)
from .json_schema import validate_schema

if TYPE_CHECKING:
    from . import Task


__all__ = [
    "basemodel",
    "json_schema",
    "Task",
    "Project",
    "TaskRun",
    "TaskOutput",
    "TaskOutputRating",
    "Priority",
    "DataSource",
    "DataSourceType",
    "DataSourceProperty",
    "TaskOutputRatingType",
    "TaskRequirement",
    "TaskDeterminism",
]


# Conventions:
# 1) Names are filename safe as they may be used as file names. They are informational and not to be used in prompts/training/validation.
# 2) Descrptions are for Kiln users to describe/understanding the purpose of this object. They must never be used in prompts/training/validation. Use "instruction/requirements" instead.

# Filename compatible names
NAME_REGEX = r"^[A-Za-z0-9 _-]+$"
NAME_FIELD = Field(min_length=1, max_length=120, pattern=NAME_REGEX)
SHORT_NAME_FIELD = Field(min_length=1, max_length=20, pattern=NAME_REGEX)


class Priority(IntEnum):
    """Defines priority levels for tasks and requirements, where P0 is highest priority."""

    p0 = 0
    p1 = 1
    p2 = 2
    p3 = 3


# Only one rating type for now, but this allows for extensibility if we want to add more in the future
class TaskOutputRatingType(str, Enum):
    """Defines the types of rating systems available for task outputs."""

    five_star = "five_star"
    custom = "custom"


class TaskOutputRating(KilnBaseModel):
    """
    A rating for a task output, including an overall rating and ratings for each requirement.

    Only supports five star ratings for now, but extensible for custom values.
    """

    type: TaskOutputRatingType = Field(default=TaskOutputRatingType.five_star)
    value: float | None = Field(
        description="The overall rating value (typically 1-5 stars).",
        default=None,
    )
    requirement_ratings: Dict[ID_TYPE, float] = Field(
        default={},
        description="The ratings of the requirements of the task. The keys are the ids of the requirements. The values are the ratings (typically 1-5 stars).",
    )

    # Used to select high quality outputs for example selection (MultiShotPromptBuilder, etc)
    def is_high_quality(self) -> bool:
        if self.type == TaskOutputRatingType.five_star:
            return self.value is not None and self.value >= 4
        return False

    @model_validator(mode="after")
    def validate_rating(self) -> Self:
        if self.type not in TaskOutputRatingType:
            raise ValueError(f"Invalid rating type: {self.type}")

        if self.type == TaskOutputRatingType.five_star:
            if self.value is not None:
                self._validate_five_star(self.value, "overall rating")
            for req_id, req_rating in self.requirement_ratings.items():
                self._validate_five_star(req_rating, f"requirement rating for {req_id}")

        return self

    def _validate_five_star(self, rating: float, rating_name: str) -> None:
        if not isinstance(rating, float) or not rating.is_integer():
            raise ValueError(
                f"{rating_name.capitalize()} of type five_star must be an integer value (1.0, 2.0, 3.0, 4.0, or 5.0)"
            )
        if rating < 1 or rating > 5:
            raise ValueError(
                f"{rating_name.capitalize()} of type five_star must be between 1 and 5 stars"
            )


class TaskOutput(KilnBaseModel):
    """
    An output for a specific task run.

    Contains the actual output content, its source (human or synthetic),
    and optional rating information.
    """

    output: str = Field(
        description="The output of the task. JSON formatted for structured output, plaintext for unstructured output."
    )
    source: DataSource = Field(
        description="The source of the output: human or synthetic."
    )
    rating: TaskOutputRating | None = Field(
        default=None, description="The rating of the output"
    )

    def validate_output_format(self, task: Task) -> Self:
        # validate output
        if task.output_json_schema is not None:
            try:
                validate_schema(json.loads(self.output), task.output_json_schema)
            except json.JSONDecodeError:
                raise ValueError("Output is not a valid JSON object")
            except jsonschema.exceptions.ValidationError as e:
                raise ValueError(f"Output does not match task output schema: {e}")
        return self


class DataSourceType(str, Enum):
    """
    The source type of a piece of data.

    Human: a human created the data
    Synthetic: a model created the data
    """

    human = "human"
    synthetic = "synthetic"


class DataSourceProperty(BaseModel):
    """
    Defines a property that can be associated with a data source.

    Includes validation rules for when properties are required or not allowed
    based on the data source type.
    """

    name: str
    type: Type[Union[str, int, float]]
    required_for: List[DataSourceType] = []
    not_allowed_for: List[DataSourceType] = []


class DataSource(BaseModel):
    """
    Represents the origin of data, either human or synthetic, with associated properties.

    Properties vary based on the source type - for synthetic sources this includes
    model information, for human sources this includes creator information.
    """

    type: DataSourceType
    properties: Dict[str, str | int | float] = Field(
        default={},
        description="Properties describing the data source. For synthetic things like model. For human, the human's name.",
    )

    _data_source_properties = [
        DataSourceProperty(
            name="created_by",
            type=str,
            required_for=[DataSourceType.human],
            not_allowed_for=[DataSourceType.synthetic],
        ),
        DataSourceProperty(
            name="model_name",
            type=str,
            required_for=[DataSourceType.synthetic],
            not_allowed_for=[DataSourceType.human],
        ),
        DataSourceProperty(
            name="model_provider",
            type=str,
            required_for=[DataSourceType.synthetic],
            not_allowed_for=[DataSourceType.human],
        ),
        DataSourceProperty(
            name="adapter_name",
            type=str,
            required_for=[DataSourceType.synthetic],
            not_allowed_for=[DataSourceType.human],
        ),
        DataSourceProperty(
            name="prompt_builder_name",
            type=str,
            not_allowed_for=[DataSourceType.human],
        ),
    ]

    @model_validator(mode="after")
    def validate_type(self) -> "DataSource":
        if self.type not in DataSourceType:
            raise ValueError(f"Invalid data source type: {self.type}")
        return self

    @model_validator(mode="after")
    def validate_properties(self) -> "DataSource":
        for prop in self._data_source_properties:
            # Check the property type is correct
            if prop.name in self.properties:
                if not isinstance(self.properties[prop.name], prop.type):
                    raise ValueError(
                        f"'{prop.name}' must be of type {prop.type.__name__} for {self.type} data source"
                    )
            # Check the property is required for the data source type
            if self.type in prop.required_for:
                if prop.name not in self.properties:
                    raise ValueError(
                        f"'{prop.name}' is required for {self.type} data source"
                    )
            # Check the property is not allowed for the data source type
            elif self.type in prop.not_allowed_for and prop.name in self.properties:
                raise ValueError(
                    f"'{prop.name}' is not allowed for {self.type} data source"
                )
        return self

    @model_validator(mode="after")
    def validate_no_empty_properties(self) -> Self:
        for prop, value in self.properties.items():
            if isinstance(value, str) and value == "":
                raise ValueError(
                    f"Property '{prop}' must be a non-empty string for {self.type} data source"
                )
        return self


class TaskRun(KilnParentedModel):
    """
    Represents a single execution of a Task.

    Contains the input used, its source, the output produced, and optional
    repair information if the output needed correction.
    """

    input: str = Field(
        description="The inputs to the task. JSON formatted for structured input, plaintext for unstructured input."
    )
    input_source: DataSource = Field(
        description="The source of the input: human or synthetic."
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

    def parent_task(self) -> Task | None:
        if not isinstance(self.parent, Task):
            return None
        return self.parent

    @model_validator(mode="after")
    def validate_input_format(self) -> Self:
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
        return self

    @model_validator(mode="after")
    def validate_output_format(self) -> Self:
        task = self.parent_task()
        if task is None:
            return self

        self.output.validate_output_format(task)
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


class TaskRequirement(BaseModel):
    """
    Defines a specific requirement that should be met by task outputs.

    Includes an identifier, name, description, instruction for meeting the requirement,
    and priority level.
    """

    id: ID_TYPE = ID_FIELD
    name: str = SHORT_NAME_FIELD
    description: str | None = Field(default=None)
    instruction: str = Field(min_length=1)
    priority: Priority = Field(default=Priority.p2)


class TaskDeterminism(str, Enum):
    """
    Defines how strictly task outputs should match expected results.

    - deterministic: Requires exact matches
    - semantic_match: Allows different wording with same meaning
    - flexible: Allows variation in both wording and meaning within requirements
    """

    deterministic = "deterministic"  # Expect exact match
    semantic_match = "semantic_match"  # Expect same meaning, but flexible on expression of the meaning
    flexible = "flexible"  # Flexible on semantic output. Eval should be custom based on parsing requirements.


class Task(
    KilnParentedModel,
    KilnParentModel,
    parent_of={"runs": TaskRun},
):
    """
    Represents a specific task to be performed, with associated requirements and validation rules.

    Contains the task definition, requirements, input/output schemas, and maintains
    a collection of task runs.
    """

    name: str = NAME_FIELD
    description: str = Field(default="")
    priority: Priority = Field(default=Priority.p2)
    determinism: TaskDeterminism = Field(default=TaskDeterminism.flexible)
    instruction: str = Field(min_length=1)
    requirements: List[TaskRequirement] = Field(default=[])
    # TODO: make this required, or formalize the default message output schema
    output_json_schema: JsonObjectSchema | None = None
    input_json_schema: JsonObjectSchema | None = None

    def output_schema(self) -> Dict | None:
        if self.output_json_schema is None:
            return None
        return schema_from_json_str(self.output_json_schema)

    def input_schema(self) -> Dict | None:
        if self.input_json_schema is None:
            return None
        return schema_from_json_str(self.input_json_schema)

    # Needed for typechecking. TODO P2: fix this in KilnParentModel
    def runs(self) -> list[TaskRun]:
        return super().runs()  # type: ignore


class Project(KilnParentModel, parent_of={"tasks": Task}):
    """
    A collection of related tasks.

    Projects organize tasks into logical groups and provide high-level descriptions
    of the overall goals.
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the project for you and your team. Will not be used in prompts/training/validation.",
    )

    # Needed for typechecking. TODO P2: fix this in KilnParentModel
    def tasks(self) -> list[Task]:
        return super().tasks()  # type: ignore
