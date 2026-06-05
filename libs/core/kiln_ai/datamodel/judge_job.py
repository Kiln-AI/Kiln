from enum import Enum
from typing import TYPE_CHECKING, List, Union

from pydantic import BaseModel, Field

from kiln_ai.datamodel.basemodel import (
    ID_TYPE,
    FilenameString,
    KilnParentedModel,
    KilnParentModel,
)
from kiln_ai.datamodel.eval import EvalScores

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class JudgeJobStatus(str, Enum):
    """The lifecycle status of a judge job."""

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JudgeJobRun(KilnParentedModel):
    """The judge's result for a single sampled dataset item (a child of a JudgeJob)."""

    dataset_id: ID_TYPE = Field(
        description="The ID of the dataset item (TaskRun) that was judged."
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


class JudgeJobOutcome(BaseModel):
    """A summary of a completed judge job."""

    train_set_size: int = Field(
        description="Total number of dataset items matching the target tags."
    )
    num_judged: int = Field(
        description="How many items were examined while searching for failures."
    )
    failing_count: int = Field(
        description="How many of the judged items failed the judge."
    )
    hit_cap: bool = Field(
        description="True if max_samples was reached before finding the requested count of failures.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the job failed.",
    )


class JudgeJob(
    KilnParentedModel,
    KilnParentModel,
    parent_of={"runs": JudgeJobRun},
):
    """
    A runnable job that samples dataset items by tag, judges them with an evaluator
    (eval config), and records each item's pass/fail and the judge's feedback.

    Used to surface a minibatch of failing examples — with feedback — for reflective
    prompt optimization. A child of a Task; a parent of JudgeJobRun results.
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
    count: int = Field(
        default=5,
        description="The number of failing examples to find before the job stops.",
    )
    max_samples: int = Field(
        default=50,
        description="The maximum number of items to judge while searching for failures.",
    )
    threshold: float = Field(
        default=0.75,
        description="The normalized (0-1) pass bar. A score below this counts as failing.",
    )
    latest_status: JudgeJobStatus = Field(
        default=JudgeJobStatus.pending,
        description="The latest known status of this judge job (pending, running, succeeded, failed, cancelled).",
    )
    outcome: JudgeJobOutcome | None = Field(
        default=None,
        description="A summary of the job's results, populated after a run.",
    )

    def parent_task(self) -> Union["Task", None]:
        if self.parent is not None and self.parent.__class__.__name__ != "Task":
            raise ValueError("parent must be a Task")
        return self.parent  # type: ignore

    def runs(self, readonly: bool = False) -> list[JudgeJobRun]:
        return super().runs(readonly=readonly)  # type: ignore
