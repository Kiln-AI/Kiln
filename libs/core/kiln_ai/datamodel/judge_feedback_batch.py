# TODO (merge blocker — do not merge toward main until resolved):
# This feature grew out of a reflection helper (failing_train_examples, PR #1536) and was
# reshaped several times under review. Re-validate the design before it becomes API surface:
#
# 1. Re-validate the driving use case. Built to feed judge feedback text to reflective
#    prompt optimization. Does that consumer still exist and still need this shape?
#    If nothing needs it, delete rather than merge.
#
# 2. Selection by tags leaves user-visible, long-lived side effects. A one-off or
#    targeted run (specific items) forces the caller to mutate dataset tags — shared,
#    user-visible state — to express what is really a query parameter. If item-level
#    selection is needed, accept item IDs (and/or a named dataset split). Callers
#    should never have to write tags to make a read-shaped call.
#
# 3. Do NOT introduce a second store of eval results. JudgeFeedbackBatchRun duplicates
#    EvalRun's job (scores for eval_config × run_config × dataset item) as a parallel,
#    API-shaped model — the name is the smell: it's shaped like a request/response, not
#    like the domain. It is also lossier than what it duplicates: generate mode discards
#    the TaskRun (allow_saving=False), so no input/output/trace/usage survives for
#    debugging an item's failure, while EvalRun keeps all four. And it creates two
#    sources of truth — these scores never feed the eval score summaries, so the same
#    (eval × run config) can answer differently here vs the scorecard. If EvalRun lacks
#    something (e.g. the judge's feedback/reasoning text), EXTEND EvalRun. Extend,
#    don't duplicate.
#
# 4. Re-running identical work must hit the cache. Same run config + same input
#    (temperature aside) yields the same result — a "fresh" re-run of an unchanged
#    (eval_config × run_config × item) triple is cost without information. EvalRunner
#    already has the correct semantics (run only missing triples, return stored results
#    otherwise); this runner bypasses it: its own persisted runs are consulted only
#    within a single batch, and never in generate mode. Re-run when the run config or
#    input changed; otherwise return instantly from stored results.
#
# 5. The paired-gate capability is retrofitted onto a sampling tool. Pairing by
#    task_run_id was silently broken by random sampling whenever the matching set
#    exceeded max_samples (two runs judged disjoint subsets; patched with a
#    deterministic sort). A paired candidate-vs-baseline gate wants full, stable
#    coverage — the eval lane's shape, not a minibatch sampler's.
#
# Also before any merge: consolidate the API surface — the synchronous run /
# create-and-run endpoints were kept "for callers not yet migrated" alongside the
# job route, leaving a three-way agent-policy matrix. One blessed path.

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
