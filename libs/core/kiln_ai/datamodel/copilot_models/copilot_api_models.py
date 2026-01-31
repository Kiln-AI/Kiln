from typing import Any

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import BaseModel, ConfigDict, Field

# Shared Models


class ExamplesForFeedbackItem(BaseModel):
    """A sample presented for user feedback, with model's judgment."""

    input: str = Field(alias="input")
    output: str
    fails_specification: bool

    model_config = {"populate_by_name": True}


class ExamplesWithFeedbackItem(BaseModel):
    """An example with user feedback on the judge's assessment."""

    user_agrees_with_judge: bool
    input: str = Field(alias="input")
    output: str
    fails_specification: bool
    user_feedback: str | None = None

    model_config = {"populate_by_name": True}


class JudgedSample(BaseModel):
    """A sample with the model's judgment on spec compliance."""

    input: str = Field(alias="input")
    output: str
    fails_specification: bool

    model_config = {"populate_by_name": True}


class TaskMetadata(BaseModel):
    """Metadata about a task invocation."""

    model_name: str
    model_provider_name: ModelProviderName


class SyntheticDataGenerationStepConfig(BaseModel):
    """Configuration for a synthetic data generation step."""

    task_metadata: TaskMetadata
    prompt: str


class SyntheticDataGenerationStepConfigInput(SyntheticDataGenerationStepConfig):
    """
    Same as SyntheticDataGenerationStepConfig, but new name for our SDK auto-compile tool.

    https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/#model-for-output-response-data
    """

    pass


class Sample(BaseModel):
    """A sample with input and output, without scoring."""

    input: str
    output: str

    model_config = {"populate_by_name": True}


class ReviewedExample(BaseModel):
    """A reviewed example from the spec review process.

    Extends Sample with review-specific fields for tracking
    model and user judgments on spec compliance.
    """

    input: str = Field(alias="input")
    output: str
    model_says_meets_spec: bool
    user_says_meets_spec: bool
    feedback: str

    model_config = {"populate_by_name": True}


class TopicSamples(BaseModel):
    """Samples associated with a specific topic."""

    topic: str
    samples: list[Sample]


class TopicSamplesScored(BaseModel):
    """Scored samples associated with a specific topic."""

    topic: str
    samples: list[JudgedSample]


class TaskInfo(BaseModel):
    """Shared information about a task"""

    task_prompt: str
    task_input_schema: str
    task_output_schema: str


class DynamicInputBatchOutput(BaseModel):
    """Output for dynamic input batch generation."""

    inputs: list[str | dict[str, Any]]


class SyntheticDataGenerationSessionConfig(BaseModel):
    """Configuration for a synthetic data generation session"""

    topic_generation_config: SyntheticDataGenerationStepConfig
    input_generation_config: SyntheticDataGenerationStepConfig
    output_generation_config: SyntheticDataGenerationStepConfig


class SyntheticDataGenerationSessionConfigInput(BaseModel):
    """
    Same as SyntheticDataGenerationSessionConfig, but new name for our SDK auto-compile tool.

    https://fastapi.tiangolo.com/how-to/separate-openapi-schemas/#model-for-output-response-data
    """

    topic_generation_config: SyntheticDataGenerationStepConfigInput
    input_generation_config: SyntheticDataGenerationStepConfigInput
    output_generation_config: SyntheticDataGenerationStepConfigInput


# Generate Batch Models


class GenerateBatchInput(BaseModel):
    """Input for batch generation (topics, inputs, outputs, optionally with scoring)."""

    # Prompt used for the target task
    target_task_info: TaskInfo
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    sdg_session_config: SyntheticDataGenerationSessionConfigInput


class GenerateBatchOutput(BaseModel):
    """Output from batch generation, organized by topic."""

    data_by_topic: dict[str, list[Sample]]


# Clarify Spec Models


class ClarifySpecInput(BaseModel):
    target_task_info: TaskInfo
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    num_exemplars: int = 10
    providers: list[ModelProviderName]


class ClarifySpecOutput(BaseModel):
    examples_for_feedback: list[ExamplesForFeedbackItem]
    # For judge, the task metadata is the model that was used to run the judge
    judge_result: SyntheticDataGenerationStepConfig
    # Contains prompts used for synthetic data generation
    sdg_session_config: SyntheticDataGenerationSessionConfig


# Refine Spec Models


class NewProposedSpecEdit(BaseModel):
    """A proposed edit to a spec field."""

    spec_field_name: str
    proposed_edit: str
    reason_for_edit: str


class SpecificationInput(BaseModel):
    """The specification to refine."""

    model_config = ConfigDict(extra="forbid")

    spec_fields: dict[str, str] = Field(
        ...,
        description="Dictionary mapping field names to their descriptions/purposes",
        title="spec_fields",
    )
    spec_field_current_values: dict[str, str] = Field(
        ...,
        description="Dictionary mapping field names to their current values",
        title="spec_field_current_values",
    )


class RefineSpecInput(BaseModel):
    target_task_info: TaskInfo
    target_specification: SpecificationInput
    examples_with_feedback: list[ExamplesWithFeedbackItem]


class RefineSpecOutput(BaseModel):
    new_proposed_spec_edits: list[NewProposedSpecEdit]
    not_incorporated_feedback: str | None


# Spec Questioner Models


class SpecQuestionerApiInput(BaseModel):
    target_task_info: TaskInfo
    target_specification: str
