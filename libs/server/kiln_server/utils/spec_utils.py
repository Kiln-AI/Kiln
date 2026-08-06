"""Shared utility functions for spec and eval creation.

This module contains helper functions for creating specs and their associated evals.
These functions are used by both the core spec API and the desktop copilot API.
"""

from typing import Mapping, NamedTuple

from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.dataset_filters import DatasetFilterId
from kiln_ai.datamodel.eval import (
    Eval,
    EvalDataType,
    EvalOutputScore,
    EvalSplitName,
    EvalTemplateId,
    SplitRef,
    TaskRunSplit,
)
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_ai.datamodel.task import Task


def spec_eval_output_score(spec_name: str) -> EvalOutputScore:
    """Create an EvalOutputScore for a spec."""
    return EvalOutputScore(
        name=spec_name,
        type=TaskOutputRatingType.pass_fail,
        instruction=f"Evaluate if the model's behaviour meets the spec: {spec_name}.",
    )


def spec_eval_data_type(
    spec_type: SpecType, evaluate_full_trace: bool = False
) -> EvalDataType:
    """Determine the eval data type for a spec."""
    if spec_type == SpecType.reference_answer_accuracy:
        return EvalDataType.reference_answer

    if evaluate_full_trace:
        return EvalDataType.full_trace
    else:
        return EvalDataType.final_answer


def spec_eval_template(spec_type: SpecType) -> EvalTemplateId | None:
    """Get the eval template for a spec type."""
    match spec_type:
        case SpecType.appropriate_tool_use:
            return EvalTemplateId.tool_call
        case SpecType.reference_answer_accuracy:
            return EvalTemplateId.rag
        case SpecType.factual_correctness:
            return EvalTemplateId.factual_correctness
        case SpecType.toxicity:
            return EvalTemplateId.toxicity
        case SpecType.bias:
            return EvalTemplateId.bias
        case SpecType.maliciousness:
            return EvalTemplateId.maliciousness
        case SpecType.jailbreak:
            return EvalTemplateId.jailbreak
        case SpecType.issue:
            return EvalTemplateId.issue
        case SpecType.desired_behaviour:
            return EvalTemplateId.desired_behaviour
        case (
            SpecType.tone
            | SpecType.formatting
            | SpecType.localization
            | SpecType.hallucinations
            | SpecType.completeness
            | SpecType.nsfw
            | SpecType.taboo
            | SpecType.prompt_leakage
        ):
            return None


class SpecEvalTags(NamedTuple):
    """The dataset tags a new spec eval's items carry.

    A NamedTuple so existing positional unpacking keeps working, while callers that only
    want one of four same-typed strings can name it instead of counting positions.
    """

    eval_tag: str
    train_tag: str
    val_tag: str
    golden_tag: str


def generate_spec_eval_tags(spec_name: str) -> SpecEvalTags:
    """Generate eval, train, val, and golden tags for a spec.

    `eval_tag` names the TEST set; see spec_eval_splits for why that name persists.
    """
    tag_suffix = spec_name.lower().replace(" ", "_")
    return SpecEvalTags(
        eval_tag=f"eval_{tag_suffix}",
        train_tag=f"train_{tag_suffix}",
        val_tag=f"val_{tag_suffix}",
        golden_tag=f"eval_golden_{tag_suffix}",
    )


def tag_filter_id(tag: str) -> DatasetFilterId:
    """The dataset filter that selects the items carrying a tag."""
    return f"tag::{tag}"


def spec_eval_splits(
    *, eval_tag: str, train_tag: str, val_tag: str
) -> dict[EvalSplitName, SplitRef]:
    """The splits a new spec eval is created with, all backed by tagged TaskRuns.

    Keyword-only: three same-typed tag strings whose order has to be memorized is the
    hazard this function exists to remove, so swapping two of them is made unrepresentable
    rather than left to a reader.

    `eval_tag` names the TEST split. "eval_" is the historical prefix for the test set's
    tag, kept because it is on dataset items in shipped projects; nothing else in this
    signature carries the legacy vocabulary.

    The golden set is not a split and is not returned here: it is TaskRun-only by
    definition, and keeping it out of the splits dict is what keeps that true at the type
    level.
    """
    return {
        "test": TaskRunSplit(filter_id=tag_filter_id(eval_tag)),
        "train": TaskRunSplit(filter_id=tag_filter_id(train_tag)),
        "val": TaskRunSplit(filter_id=tag_filter_id(val_tag)),
    }


def set_spec_eval_splits(eval: Eval, splits: Mapping[EvalSplitName, SplitRef]) -> None:
    """Store each of a new spec eval's splits where the most readers can find it.

    Not a no-op on splits the eval was constructed with: Eval.set_split moves a split that
    has a legacy on-disk home into it, so a new spec eval's test and train splits stay
    readable by older Kiln builds and by the project zip handed to the remote
    prompt-optimization service. Val has no legacy home and stays in `splits`.

    The eval has to be constructed with its splits first — an eval without a test split
    fails validation — so this sets values that are already set, and changes only where
    they are written.

    Takes a Mapping rather than a dict because dict key types are invariant, and callers
    hold the narrower dict[EvalSplitName, SplitRef] that spec_eval_splits returns.
    """
    for name, split in splits.items():
        eval.set_split(name, split)


def build_spec_eval(
    *,
    task: Task,
    name: str,
    spec_type: SpecType,
    evaluate_full_trace: bool,
) -> tuple[Eval, SpecEvalTags]:
    """A new spec eval, with its splits already stored where readers look for them.

    Returns the eval alongside the dataset tags its items must carry, so a caller that
    generates those items can tag them. The eval is not saved.

    Constructing the eval and homing its splits is one operation rather than two steps a
    caller has to remember: an eval built without the second step keeps its test and train
    splits only in `splits`, where neither older Kiln builds nor the project zip handed to
    the remote prompt-optimization service can see them — and nothing about the resulting
    eval looks wrong in memory. Every spec-eval creation path goes through here so that
    cannot be forgotten.
    """
    tags = generate_spec_eval_tags(name)
    splits = spec_eval_splits(
        eval_tag=tags.eval_tag, train_tag=tags.train_tag, val_tag=tags.val_tag
    )
    # Eval.splits is keyed by str, and dict key types are invariant, so the narrower
    # mapping has to be widened rather than passed through.
    widened_splits: dict[str, SplitRef] = {
        split_name: split for split_name, split in splits.items()
    }

    eval = Eval(
        parent=task,
        name=name,
        description=None,
        template=spec_eval_template(spec_type),
        output_scores=[spec_eval_output_score(name)],
        splits=widened_splits,
        eval_configs_filter_id=tag_filter_id(tags.golden_tag),
        template_properties=None,
        evaluation_data_type=spec_eval_data_type(spec_type, evaluate_full_trace),
    )
    set_spec_eval_splits(eval, splits)

    return eval, tags
