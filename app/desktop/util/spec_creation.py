"""Utility functions for creating specs with Kiln Copilot.

This module contains helper functions and constants for creating specs,
evals, eval configs, and task runs as part of the copilot-assisted
spec creation workflow.
"""

import random

from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.eval import EvalDataType, EvalOutputScore, EvalTemplateId
from kiln_ai.datamodel.spec_properties import SpecType
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from pydantic import BaseModel, Field

# Constants for copilot spec creation
KILN_COPILOT_MODEL_NAME = "kiln-copilot"
KILN_COPILOT_MODEL_PROVIDER = "kiln"
KILN_ADAPTER_NAME = "kiln-adapter"
NUM_SAMPLES_PER_TOPIC = 5  # TODO: Make this 15
NUM_TOPICS = 10  # TODO: Make this 15
MIN_EVAL_EXAMPLES = 20  # TODO: Make this 100
MIN_TRAIN_EXAMPLES = 20  # TODO: Make this 100
MIN_GOLDEN_EXAMPLES = 10  # TODO: Make this 25


class SampleApi(BaseModel):
    """A sample input/output pair."""

    input: str = Field(alias="input")
    output: str


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

    model_config = {"populate_by_name": True}


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


def sample_and_remove(examples: list[SampleApi], n: int) -> list[SampleApi]:
    """Randomly sample and remove n items from a list.

    Mutates the input list by removing the sampled elements.
    Uses swap-and-pop for O(1) removal.
    """
    sampled: list[SampleApi] = []
    count = min(n, len(examples))

    for _ in range(count):
        if not examples:
            break
        random_index = random.randint(0, len(examples) - 1)
        # Swap with last element and pop
        examples[random_index], examples[-1] = examples[-1], examples[random_index]
        sampled.append(examples.pop())

    return sampled


def create_task_run_from_sample(sample: SampleApi, tag: str) -> TaskRun:
    """Create a TaskRun from a SampleApi (without parent set)."""
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "adapter_name": KILN_ADAPTER_NAME,
            "model_name": KILN_COPILOT_MODEL_NAME,
            "model_provider": KILN_COPILOT_MODEL_PROVIDER,
        },
    )

    # Access input using model_dump since SampleApi uses alias
    sample_dict = sample.model_dump(by_alias=True)
    return TaskRun(
        input=sample_dict["input"],
        input_source=data_source,
        output=TaskOutput(
            output=sample.output,
            source=data_source,
        ),
        tags=[tag],
    )


def create_task_run_from_reviewed(
    example: ReviewedExample, tag: str, spec_name: str
) -> TaskRun:
    """Create a TaskRun from a reviewed example with rating (without parent set)."""
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "adapter_name": KILN_ADAPTER_NAME,
            "model_name": KILN_COPILOT_MODEL_NAME,
            "model_provider": KILN_COPILOT_MODEL_PROVIDER,
        },
    )

    rating_key = f"named::{spec_name}"
    rating_value = 1.0 if example.user_says_meets_spec else 0.0

    return TaskRun(
        input=example.input,
        input_source=data_source,
        output=TaskOutput(
            output=example.output,
            source=data_source,
            rating=TaskOutputRating(
                type=TaskOutputRatingType.five_star,
                value=5.0,  # Default value, actual rating is in requirement_ratings
                requirement_ratings={
                    rating_key: RequirementRating(
                        type=TaskOutputRatingType.pass_fail,
                        value=rating_value,
                    )
                },
            ),
        ),
        tags=[tag],
    )


def create_dataset_task_runs(
    all_examples: list[SampleApi],
    reviewed_examples: list[ReviewedExample],
    eval_tag: str,
    train_tag: str,
    golden_tag: str,
    spec_name: str,
) -> list[TaskRun]:
    """Create TaskRuns for eval, train, and golden datasets.

    Samples from all_examples (mutating it) and creates TaskRuns for:
    - Eval dataset (MIN_EVAL_EXAMPLES)
    - Train dataset (MIN_TRAIN_EXAMPLES)
    - Golden dataset (reviewed examples + unrated examples to reach MIN_GOLDEN_EXAMPLES)

    Returns TaskRuns without parent set - caller must set parent.
    """
    task_runs: list[TaskRun] = []

    # Sample examples for eval and train datasets
    eval_examples = sample_and_remove(all_examples, MIN_EVAL_EXAMPLES)
    train_examples = sample_and_remove(all_examples, MIN_TRAIN_EXAMPLES)

    # Create TaskRuns for eval examples
    for example in eval_examples:
        task_runs.append(create_task_run_from_sample(example, eval_tag))

    # Create TaskRuns for train examples
    for example in train_examples:
        task_runs.append(create_task_run_from_sample(example, train_tag))

    # Create unrated golden examples from remaining pool if needed
    unrated_golden_count = max(0, MIN_GOLDEN_EXAMPLES - len(reviewed_examples))
    if unrated_golden_count > 0:
        unrated_golden_examples = sample_and_remove(all_examples, unrated_golden_count)
        for example in unrated_golden_examples:
            task_runs.append(create_task_run_from_sample(example, golden_tag))

    # Create TaskRuns for reviewed examples with ratings
    for reviewed in reviewed_examples:
        task_runs.append(create_task_run_from_reviewed(reviewed, golden_tag, spec_name))

    return task_runs
