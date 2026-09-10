"""Shared utility functions for spec and eval creation.

This module contains helper functions for creating specs and their associated evals.
These functions are used by both the core spec API and the desktop copilot API.
"""

from typing import NamedTuple

from kiln_ai.datamodel.datamodel_enums import (
    EvalStatus,
    Priority,
    TaskOutputRatingType,
)
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


def eval_pass_fail_output_score(eval_name: str) -> EvalOutputScore:
    """Default score for an eval created without a spec.

    Same shape as spec_eval_output_score, kept beside it so the two creation
    paths can't drift; only the instruction wording differs (there is no spec
    to refer to).
    """
    return EvalOutputScore(
        name=eval_name,
        type=TaskOutputRatingType.pass_fail,
        instruction=f"Evaluate whether the model's behaviour passes the eval: {eval_name}.",
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
    """Get the eval template for a spec type.

    Tool use deliberately maps to None: the legacy "tool_call" template means a
    pre-spec LLM judge over the full trace, while new tool evals are scored by
    the tool_call_check programmatic judge. Recording the legacy template on
    them would conflate the two.
    """
    match spec_type:
        case SpecType.appropriate_tool_use:
            return None
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

    test_tag: str
    train_tag: str
    val_tag: str
    golden_tag: str


def generate_spec_eval_tags(spec_name: str) -> SpecEvalTags:
    """Generate test, train, val, and golden tags for a spec.

    Only newly created evals are affected by the names chosen here: an eval stores the
    concrete tag strings in its saved filters, so evals created by earlier builds keep
    the tags they were created with.
    """
    tag_suffix = spec_name.lower().replace(" ", "_")
    return SpecEvalTags(
        test_tag=f"test_{tag_suffix}",
        train_tag=f"train_{tag_suffix}",
        val_tag=f"val_{tag_suffix}",
        golden_tag=f"golden_{tag_suffix}",
    )


def tag_filter_id(tag: str) -> DatasetFilterId:
    """The dataset filter that selects the items carrying a tag."""
    return f"tag::{tag}"


def spec_eval_splits(
    *, test_tag: str, train_tag: str, val_tag: str
) -> dict[EvalSplitName, SplitRef]:
    """The splits a new spec eval is created with, all backed by tagged TaskRuns.

    Keyword-only: three same-typed tag strings whose order has to be memorized is the
    hazard this function exists to remove, so swapping two of them is made unrepresentable
    rather than left to a reader.

    The golden set is not a split and is not returned here: it is TaskRun-only by
    definition, and keeping it out of the splits dict is what keeps that true at the type
    level.
    """
    return {
        "test": TaskRunSplit(filter_id=tag_filter_id(test_tag)),
        "train": TaskRunSplit(filter_id=tag_filter_id(train_tag)),
        "val": TaskRunSplit(filter_id=tag_filter_id(val_tag)),
    }


def build_spec_eval(
    *,
    task: Task,
    name: str,
    spec_type: SpecType,
    evaluate_full_trace: bool,
    priority: Priority | None = None,
    status: EvalStatus | None = None,
) -> tuple[Eval, SpecEvalTags]:
    """A new spec eval, with its test, train and val splits already set.

    Returns the eval alongside the dataset tags its items must carry, so a caller that
    generates those items can tag them. The eval is not saved.

    Every spec-eval creation path goes through here, so the three splits and the tags
    naming their items are derived from the eval's name in one place rather than being
    reassembled per caller.

    Priority and status live on the eval. Callers that write a spec alongside it mirror
    them there so the spec file stays truthful, but the eval is the source of truth for
    reads and later edits.
    """
    tags = generate_spec_eval_tags(name)
    splits = spec_eval_splits(
        test_tag=tags.test_tag, train_tag=tags.train_tag, val_tag=tags.val_tag
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
        priority=priority,
        status=status,
    )

    return eval, tags
