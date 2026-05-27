"""Shared Pydantic models for the Copilot API."""

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from pydantic import BaseModel, Field


# Base models
class TaskInfoApi(BaseModel):
    """Task information for copilot API calls."""

    task_prompt: str = Field(description="The task's prompt.")
    task_input_schema: str = Field(description="The task's input JSON schema.")
    task_output_schema: str = Field(description="The task's output JSON schema.")


class TaskMetadataApi(BaseModel):
    """Metadata about the model used for a task."""

    model_name: str = Field(description="The name of the AI model used.")
    model_provider_name: ModelProviderName = Field(
        description="The provider hosting the model (e.g. OpenAI, Anthropic)."
    )


class SyntheticDataGenerationStepConfigApi(BaseModel):
    """Configuration for a synthetic data generation step."""

    task_metadata: TaskMetadataApi
    prompt: str


class SyntheticDataGenerationSessionConfigApi(BaseModel):
    """Configuration for a synthetic data generation session"""

    topic_generation_config: SyntheticDataGenerationStepConfigApi
    input_generation_config: SyntheticDataGenerationStepConfigApi
    output_generation_config: SyntheticDataGenerationStepConfigApi


class SampleApi(BaseModel):
    """A sample input/output pair."""

    input: str = Field(alias="input")
    output: str

    model_config = {"populate_by_name": True}


class ReviewedExample(BaseModel):
    """A reviewed example from the spec review process.

    Extends SampleApi with review-specific fields for tracking
    model and user judgments on spec compliance.
    """

    input: str = Field(alias="input")
    output: str
    model_says_meets_spec: bool
    user_says_meets_spec: bool
    feedback: str

    model_config = {"populate_by_name": True}


# Input models
class SpecApi(BaseModel):
    """Spec field information for refinement."""

    spec_fields: dict[str, str]
    spec_field_current_values: dict[str, str]


class ExampleWithFeedbackApi(BaseModel):
    """An example with user feedback for spec refinement."""

    model_config = {"populate_by_name": True}

    user_agrees_with_judge: bool
    input: str = Field(alias="input")
    output: str
    fails_specification: bool
    user_feedback: str | None = None


class ClarifySpecApiInput(BaseModel):
    """Input for clarifying a spec with copilot."""

    target_task_info: TaskInfoApi
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    providers: list[ModelProviderName]
    num_exemplars: int = Field(default=10)


class RefineSpecApiInput(BaseModel):
    """Input for refining a spec based on feedback."""

    target_task_info: TaskInfoApi
    target_specification: SpecApi
    examples_with_feedback: list[ExampleWithFeedbackApi]


class GenerateBatchApiInput(BaseModel):
    """Input for generating a batch of examples."""

    target_task_info: TaskInfoApi
    target_specification: str
    num_samples_per_topic: int
    num_topics: int
    sdg_session_config: SyntheticDataGenerationSessionConfigApi


# Output models
class SubsampleBatchOutputItemApi(BaseModel):
    """A single item from batch output for feedback."""

    input: str = Field(alias="input")
    output: str
    fails_specification: bool

    model_config = {"populate_by_name": True}


class ClarifySpecApiOutput(BaseModel):
    """Output from clarifying a spec."""

    examples_for_feedback: list[SubsampleBatchOutputItemApi]
    judge_result: SyntheticDataGenerationStepConfigApi
    sdg_session_config: SyntheticDataGenerationSessionConfigApi


class GenerateBatchApiOutput(BaseModel):
    """Output from generating a batch of examples."""

    data_by_topic: dict[str, list[SampleApi]]


class SpecQuestionerApiInput(BaseModel):
    target_task_info: TaskInfoApi = Field(
        ...,
        description="The task info including prompt, input schema, and output schema",
        title="target_task_info",
    )
    target_specification: str = Field(
        ...,
        description="The specification to analyze",
        title="target_specification",
    )


# Analyze Input Data Guide

DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLES = 50
DRAFT_INPUT_DATA_GUIDE_MAX_PREVIEW_SAMPLES = 20


class DraftInputDataGuideApiInput(BaseModel):
    """Input for the input data guide copilot's draft step."""

    target_task_info: TaskInfoApi = Field(
        ...,
        description="The task info including prompt, input schema, and output schema.",
    )
    input_examples: list[str] = Field(
        ...,
        description=(
            "Heterogeneous list of input examples — short manual entries, the "
            "input portion of selected task runs, or full text of uploaded "
            "text documents (txt, md, csv). Every entry is a string and is "
            "treated as a candidate reference input regardless of source."
        ),
        min_length=1,
        max_length=DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLES,
    )
    num_preview_samples: int = Field(
        5,
        description="Number of preview inputs to generate alongside the draft guide.",
        ge=1,
        le=DRAFT_INPUT_DATA_GUIDE_MAX_PREVIEW_SAMPLES,
    )
    run_config_properties: KilnAgentRunConfigProperties = Field(
        description=(
            "Run config used to generate preview inputs locally with the "
            "returned draft guide. Same shape the manual preview endpoint uses."
        ),
    )


class DraftInputDataGuidePreviewSampleApi(BaseModel):
    """One preview-generated input returned alongside the draft guide."""

    input: str = Field(
        description="A generated example input the draft guide produces."
    )


class DraftInputDataGuideApiOutput(BaseModel):
    """Output of the input data guide copilot's draft step.

    Combines (a) the draft guide markdown produced by the copilot service with
    (b) preview inputs generated locally by re-running the existing
    `/data_gen_guide_preview` flow against the draft. The preview is generated
    locally so it shares the same input-generation infrastructure the manual
    refine loop uses.
    """

    draft_guide: str = Field(description="Full draft input data guide markdown.")
    preview_samples: list[DraftInputDataGuidePreviewSampleApi] = Field(
        description="Preview inputs generated using the draft guide for the user to review."
    )
