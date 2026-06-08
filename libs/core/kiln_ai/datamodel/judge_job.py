from typing import TYPE_CHECKING, List, Union

from pydantic import Field

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.eval import EvalScores

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class JudgeJobRun(KilnParentedModel):
    """The judge's result for a single sampled dataset item (a child of a JudgeJob)."""

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

    def parent_judge_job(self) -> Union["JudgeJob", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "JudgeJob":
            raise ValueError("parent must be a JudgeJob")
        return self.parent  # type: ignore


class JudgeJob(
    KilnParentedModel,
    KilnParentModel,
    parent_of={"runs": JudgeJobRun},
):
    """
    A reusable config that samples dataset items by tag, judges them with an evaluator
    (eval config), and records each item's pass/fail and the judge's feedback.

    Used to surface a minibatch of failing examples — with feedback — for reflective prompt
    optimization. A child of a Task; a parent of the JudgeJobRun results it produces.
    """

    name: FilenameString = Field(description="The name of the judge job.")
    description: str | None = Field(
        default=None,
        description="A description of the judge job for you and your team.",
    )
    target_tags: List[str] = Field(
        description="Dataset items must carry all of these tags to be sampled for this job."
    )
    eval_config_id: str = Field(
        description="The ID of the eval config (the judge) used to score the sampled items."
    )
    run_config_id: str | None = Field(
        default=None,
        description="The ID of the run config whose outputs are being judged. Metadata only; the existing dataset outputs are judged (the task is not re-run).",
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

    def parent_task(self) -> Union["Task", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "Task":
            raise ValueError("parent must be a Task")
        return self.parent  # type: ignore

    def runs(self, readonly: bool = False) -> list[JudgeJobRun]:
        return super().runs(readonly=readonly)  # type: ignore
