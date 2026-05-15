"""
Data models for the Input Data Guide copilot.

The Input Data Guide copilot takes a heterogeneous mix of input examples (short
manual entries, selected task runs, uploaded text documents) and produces a
draft markdown guide describing what realistic inputs to the task look like,
plus a small set of preview-generated inputs for the user to review.

Models live in /lib so they can be shared across lib, server, and client.
"""

from pydantic import BaseModel, ConfigDict, Field


class InputDataGuideAnalysisInput(BaseModel):
    """Request payload for the analyze step of the Input Data Guide copilot."""

    model_config = ConfigDict(extra="forbid")

    task_prompt: str = Field(
        ...,
        description="The task's runtime system prompt — used to ground the analysis in what the task is actually for.",
        title="task_prompt",
    )
    task_description: str | None = Field(
        None,
        description="Optional human-facing description of the task.",
        title="task_description",
    )
    task_input_schema: str | None = Field(
        None,
        description="If the task's input must conform to a specific JSON schema, it will be provided here.",
        title="task_input_schema",
    )
    input_examples: list[str] = Field(
        ...,
        description=(
            "A heterogeneous list of input examples. Each entry is a string and "
            "may be a short manual example, the input portion of an existing task "
            "run, or the full text of an uploaded document. The analyzer treats "
            "every entry as a candidate 'reference input' regardless of source."
        ),
        title="input_examples",
        min_length=1,
        max_length=50,
    )
    num_preview_samples: int = Field(
        5,
        description="Number of preview inputs to generate alongside the draft guide.",
        ge=1,
        le=20,
        title="num_preview_samples",
    )


class InputDataGuidePreviewSample(BaseModel):
    """One preview-generated input returned by the analyze step."""

    model_config = ConfigDict(extra="forbid")

    input: str = Field(
        ...,
        description="A generated example input that the resulting draft guide produces.",
        title="input",
    )


class InputDataGuideAnalysisOutput(BaseModel):
    """Response payload for the analyze step of the Input Data Guide copilot."""

    model_config = ConfigDict(extra="forbid")

    draft_guide: str = Field(
        ...,
        description=(
            "Full draft input data guide markdown. Contains a `# Reference "
            "Inputs` section and an `# Input Guidelines & Rules` section with "
            "rules wrapped in `<input_structural>` and `<input_semantic>` "
            "groups only."
        ),
        title="draft_guide",
    )
    preview_samples: list[InputDataGuidePreviewSample] = Field(
        ...,
        description=(
            "Preview inputs generated using the draft guide so the user can "
            "rate them in the existing review/refine UI."
        ),
        title="preview_samples",
    )
