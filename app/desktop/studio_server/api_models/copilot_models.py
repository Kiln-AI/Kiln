"""Shared Pydantic models for the Copilot API."""

from typing import Annotated, Literal

from kiln_ai.datamodel.claim_review import GradedClaim
from kiln_ai.datamodel.datamodel_enums import ModelProviderName
from pydantic import BaseModel, Field, StringConstraints, model_validator
from typing_extensions import Self


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


class ClaimReviewApi(BaseModel):
    """The reviewer's grades on one trace's claim/evidence distillation.

    Mirrors the persisted ClaimReview shape (judge verdict + per-claim
    agree/disagree with optional whys) so the save path can write it onto
    the golden TaskRun and judge refinement can consume it later.
    """

    judge_score: Literal["pass", "fail"]
    judge_reasoning: str
    claims: list[GradedClaim]
    final_judgement: GradedClaim

    @model_validator(mode="after")
    def validate_final_judgement_pinned(self) -> Self:
        # Same invariant the persisted ClaimReview enforces; checking here
        # turns a corrupt payload into a 422 before any model is written.
        if self.final_judgement.expected_result != self.judge_score:
            raise ValueError(
                "final_judgement.expected_result must equal judge_score "
                f"(got {self.final_judgement.expected_result!r} vs "
                f"{self.judge_score!r})"
            )
        return self


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
    claim_review: ClaimReviewApi | None = Field(
        default=None,
        description="Per-claim grades from the claim/evidence review, when "
        "the example was reviewed that way (v2 builder).",
    )

    model_config = {"populate_by_name": True}


class ReviewedChainApi(BaseModel):
    """A reviewer's verdict on one multi-turn chain, keyed by its leaf run.

    The leaf TaskRun id is the durable identity that rides from the drive
    batch through review to save — the save path writes the golden rating
    (and the claim review) onto that leaf.
    """

    leaf_run_id: str
    user_says_meets_spec: bool
    feedback: str = ""
    claim_review: ClaimReviewApi | None = None


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


# Input Data Guide draft job
#
# The draft runs as a kiln_server background job so the heavy
# summarize+aggregate work survives a flaky connection and the user can leave
# the page and come back. The studio server exposes the job's start / status /
# result lifecycle so the web UI owns polling. Preview inputs are no longer
# bundled here — once the draft is ready the UI generates them via the existing
# `/data_gen_guide_preview` endpoint.

DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLES = 200
# Per-example character ceiling. Each example becomes one summarize LLM call;
# 200k chars stays well under the model's context window even for prose. The
# client mirrors this and blocks before sending, so hitting it here is a guard.
DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH = 200_000


class StartDataGuideJobApiInput(BaseModel):
    """Input to kick off the input data guide draft job.

    Carries only the input examples. All task info the job needs — the runtime
    prompt and the input JSON schema — is derived server-side from the task
    identified by the route, so the client can't supply a manipulated prompt or
    schema, and the output schema / description never reach the guide LLM.
    """

    input_examples: list[
        Annotated[
            str,
            StringConstraints(max_length=DRAFT_INPUT_DATA_GUIDE_MAX_EXAMPLE_LENGTH),
        ]
    ] = Field(
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


class StartDataGuideJobApiOutput(BaseModel):
    """Identifier for the started data guide draft job."""

    job_id: str = Field(description="Identifier for the started data guide draft job.")


class DataGuideJobStatusApiOutput(BaseModel):
    """Current status of a data guide draft job."""

    status: str = Field(
        description=(
            "Current job status (e.g. running, succeeded, failed, cancelled)."
        ),
    )


class DataGuideJobResultApiOutput(BaseModel):
    """Result of a completed data guide draft job."""

    draft_guide: str = Field(description="Full draft input data guide markdown.")


class ParseImportFileApiOutput(BaseModel):
    """Result of parsing an uploaded bulk-import file of input examples.

    Plaintext tasks parse a single-column CSV; structured-input tasks parse one
    JSON object per line, validated against the task's input schema. A non-null
    `error` means the whole file was rejected; `warning` means it was accepted
    but some examples were skipped (e.g. over the length limit).
    """

    rows: list[str] = Field(
        description="Parsed example input strings, ready to add. Empty when error is set.",
    )
    error: str | None = Field(
        default=None,
        description="Set when the whole file was rejected (invalid format/encoding).",
    )
    warning: str | None = Field(
        default=None,
        description="Set when the file was accepted but some examples were skipped.",
    )
