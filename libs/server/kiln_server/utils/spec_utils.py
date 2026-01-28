"""Shared utility functions for spec and eval creation.

This module contains helper functions for creating specs and their associated evals.
These functions are used by both the core spec API and the desktop copilot API.
"""

from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalDataType, EvalOutputScore, EvalTemplateId
from kiln_ai.datamodel.spec_properties import SpecType


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


def generate_spec_eval_tags(spec_name: str) -> tuple[str, str, str]:
    """Generate eval, train, and golden tags for a spec.

    Args:
        spec_name: The name of the spec

    Returns:
        Tuple of (eval_tag, train_tag, golden_tag)
    """
    tag_suffix = spec_name.lower().replace(" ", "_")
    eval_tag = f"eval_{tag_suffix}"
    train_tag = f"train_{tag_suffix}"
    golden_tag = f"eval_golden_{tag_suffix}"
    return eval_tag, train_tag, golden_tag


def generate_spec_eval_filter_ids(
    eval_tag: str, train_tag: str, golden_tag: str
) -> tuple[str, str, str]:
    """Generate filter IDs for eval set, train set, and eval configs.

    Args:
        eval_tag: The eval dataset tag
        train_tag: The train dataset tag
        golden_tag: The golden dataset tag

    Returns:
        Tuple of (eval_set_filter_id, train_set_filter_id, eval_configs_filter_id)
    """
    return f"tag::{eval_tag}", f"tag::{train_tag}", f"tag::{golden_tag}"
