"""
Data models for the Input Data Guide copilot.

The Input Data Guide copilot takes a heterogeneous mix of input examples (short
manual entries, selected task runs, uploaded text documents) and produces a
draft markdown guide describing what realistic inputs to the task look like.

Preview inputs are not produced here: the studio_server proxy combines this
draft with a separate call to its existing preview endpoint to generate inputs
the user can rate.

Models live in /lib so they can be shared across lib, server, and client.
"""

from pydantic import BaseModel, ConfigDict, Field


class InputDataGuideDraftInput(BaseModel):
    """Request payload for the draft step of the Input Data Guide copilot."""

    model_config = ConfigDict(extra="forbid")

    task_prompt: str = Field(
        ...,
        description="The task's runtime system prompt — used to ground the analysis in what the task is actually for.",
        title="task_prompt",
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
            "run, or the full text of an uploaded document. Every entry is "
            "treated as a candidate 'reference input' regardless of source."
        ),
        title="input_examples",
        min_length=1,
        max_length=200,
    )


class InputDataGuideDraftOutput(BaseModel):
    """Response payload for the draft step of the Input Data Guide copilot."""

    model_config = ConfigDict(extra="forbid")

    draft_guide: str = Field(
        ...,
        description=(
            "Full draft input data guide markdown. Contains exactly three "
            "top-level sections in order: `# Semantics`, `# Style`, "
            "`# Presentation Defaults`."
        ),
        title="draft_guide",
    )
