from typing import TYPE_CHECKING, List, Union

from pydantic import Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.eval import EvalScores
from kiln_ai.datamodel.usage import Usage

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class JudgeFeedbackBatchRun(KilnParentedModel):
    """The judge's result for a single sampled dataset item (a child of a JudgeFeedbackBatch)."""

    task_run_id: ID_TYPE = Field(
        description="The ID of the task run (dataset item) that was judged."
    )
    scores: EvalScores = Field(
        description="The scores produced by the judge for this dataset item."
    )
    feedback: str | None = Field(
        default=None,
        description="The judge's plaintext reasoning for the scores, if available.",
    )
    passed: bool = Field(
        description="Whether this item passed the judge (i.e. it is not a failing example)."
    )
    run_config_id: str | None = Field(
        default=None,
        description="If the judged output was generated (generate_outputs), the run config that "
        "produced it. None when the item's existing dataset output was judged.",
    )
    usage: Usage | None = Field(
        default=None,
        description="Token usage, cost, and LLM latency for generating this item's output. "
        "Populated only when generate_outputs=true (the candidate config was run to produce a "
        "fresh output); None when an existing dataset output was judged (nothing was generated).",
    )

    def parent_judge_feedback_batch(self) -> Union["JudgeFeedbackBatch", None]:
        if (
            self.parent is not None
            and self.parent.__class__.__name__ != "JudgeFeedbackBatch"
        ):
            raise ValueError("parent must be a JudgeFeedbackBatch")
        return self.parent  # type: ignore


class JudgeFeedbackBatch(
    KilnParentedModel,
    KilnParentModel,
    parent_of={"runs": JudgeFeedbackBatchRun},
):
    """
    A reusable config that samples dataset items by tag, judges them with an evaluator
    (eval config), and records each item's pass/fail and the judge's feedback.

    Used to surface a minibatch of failing examples — with feedback — for reflective prompt
    optimization. A child of a Task; a parent of the JudgeFeedbackBatchRun results it produces.
    """

    name: FilenameString = Field(description="The name of the judge feedback batch.")
    description: str | None = Field(
        default=None,
        description="A description of the judge feedback batch for you and your team.",
    )
    target_tags: List[str] = Field(
        description="Dataset items must carry all of these tags to be sampled for this job."
    )
    eval_config_id: str = Field(
        description="The ID of the eval config (the judge) used to score the sampled items."
    )
    run_config_id: str | None = Field(
        default=None,
        description="The ID of the run config. With generate_outputs=false it's metadata (the "
        "existing dataset output is judged). With generate_outputs=true it's run on each sampled "
        "item to produce the output that is judged.",
    )
    generate_outputs: bool = Field(
        default=False,
        description="If true, run `run_config_id` on each sampled item to generate a fresh output "
        "and judge that (gate a candidate config, scoped to the tagged items). If false (default), "
        "judge each item's existing dataset output (the task is not re-run).",
    )
    stop_after_failures: int | None = Field(
        default=None,
        ge=1,
        description=(
            "If set, stop once this many failing examples are found (a cheap minibatch for the "
            "train signal). If null (default), judge the whole matching set up to max_samples "
            "(full coverage — required for a val gate paired by task_run_id)."
        ),
    )
    max_samples: int = Field(
        default=50,
        ge=1,
        description="The maximum number of items to judge.",
    )
    threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="The normalized (0-1) pass bar. A score below this counts as failing.",
    )

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        # generate_outputs runs run_config_id on each item, so it must be set (defense in depth: the
        # API request model validates this too, but the datamodel can be built directly).
        if self.generate_outputs and not self.run_config_id:
            raise ValueError("run_config_id is required when generate_outputs is true")
        # Empty target_tags matches every item (empty subset), which is an ambiguous footgun for a
        # "sample by tag" config — require at least one, mirroring the field description.
        if not self.target_tags:
            raise ValueError("target_tags must contain at least one tag")
        return self

    def parent_task(self) -> Union["Task", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "Task":
            raise ValueError("parent must be a Task")
        return self.parent  # type: ignore

    def runs(self, readonly: bool = False) -> list[JudgeFeedbackBatchRun]:
        return super().runs(readonly=readonly)  # type: ignore
