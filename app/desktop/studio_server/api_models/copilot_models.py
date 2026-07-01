"""Shared Pydantic models for the Copilot API."""

from typing import Literal

from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import BaseModel, ConfigDict, Field


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


# Claim/Evidence (per-trace claim builder) — proxies kiln_server
# /v1/copilot/build_claim_evidence. Shapes must match the UI contract in
# builder/claim_evidence.ts exactly.
class BuildClaimsApiInput(BaseModel):
    """One trace + its judge decision, to distill into claim/evidence pairs."""

    raw_input: str
    raw_output: str
    eval_rubric: str
    judge_reasoning: str
    judge_score: str


class CitationApi(BaseModel):
    """A start+end anchor into the trace; the UI highlights from `from` to `to`.

    `from` is a Python keyword, so the field is `from_` with an alias — the
    serialized key MUST stay `from` (the UI greps that literal JSON key).
    """

    marker: int
    source: Literal["input", "output"]
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)


class ClaimApi(BaseModel):
    """One atomic claim + its one-sentence evidence with [n] citation markers."""

    claim: str
    claim_type: Literal["inclusion", "exclusion", "assertion", "final_judgement"]
    evidence: str
    citations: list[CitationApi]


class BuildClaimsApiOutput(BaseModel):
    """All claims for one trace, ordered most- to least-important."""

    claims: list[ClaimApi]
