"""Utility functions for creating specs with Kiln Copilot.

This module contains helper functions and constants for creating specs,
evals, eval configs, and task runs as part of the copilot-assisted
spec creation workflow.
"""

import json
import random

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    generate_batch_v1_copilot_generate_batch_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    GenerateBatchInput,
    GenerateBatchOutput,
    HTTPValidationError,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.types import Response
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.api_models.copilot_models import (
    ReviewedExample,
    SampleApi,
    SyntheticDataGenerationSessionConfigApi,
    TaskInfoApi,
)
from fastapi import HTTPException
from kiln_ai.datamodel import TaskRun
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from kiln_ai.utils.config import Config

# Constants for copilot spec creation
KILN_COPILOT_MODEL_NAME = "kiln-copilot"
KILN_COPILOT_MODEL_PROVIDER = "kiln"
KILN_ADAPTER_NAME = "kiln-adapter"
NUM_SAMPLES_PER_TOPIC = 20
NUM_TOPICS = 15
MIN_GOLDEN_EXAMPLES = 25


def get_copilot_api_key() -> str:
    """Get the Kiln Copilot API key from config, raising an error if not set."""
    api_key = Config.shared().kiln_copilot_api_key
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Kiln Copilot API key not configured. Please connect your API key in settings.",
        )
    return api_key


async def generate_copilot_examples(
    api_key: str,
    target_task_info: TaskInfoApi,
    sdg_session_config: SyntheticDataGenerationSessionConfigApi,
    spec_definition: str,
) -> list[SampleApi]:
    """Generate examples via the Kiln Copilot API.

    Calls the copilot generate_batch endpoint and returns a flat list of SampleApi objects.
    Raises HTTPException on API errors.

    Args:
        api_key: The Kiln Copilot API key
        target_task_info: Task info for the target task
        sdg_session_config: Session config for synthetic data generation
        spec_definition: The rendered spec definition
    """
    client = get_authenticated_client(api_key)

    generate_input = GenerateBatchInput.from_dict(
        {
            "target_task_info": target_task_info.model_dump(),
            "sdg_session_config": sdg_session_config.model_dump(),
            "target_specification": spec_definition,
            "num_samples_per_topic": NUM_SAMPLES_PER_TOPIC,
            "num_topics": NUM_TOPICS,
        }
    )

    detailed_result = (
        await generate_batch_v1_copilot_generate_batch_post.asyncio_detailed(
            client=client,
            body=generate_input,
        )
    )
    check_response_error(detailed_result)

    result = detailed_result.parsed
    if result is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate synthetic data for spec. Please try again.",
        )

    if isinstance(result, HTTPValidationError):
        raise HTTPException(
            status_code=422,
            detail="Validation error.",
        )

    if not isinstance(result, GenerateBatchOutput):
        raise HTTPException(
            status_code=500,
            detail="Unknown error.",
        )

    # Convert result to flat list of SampleApi
    examples: list[SampleApi] = []
    data_dict = result.to_dict().get("data_by_topic", {})
    for topic_examples in data_dict.values():
        for ex in topic_examples:
            examples.append(
                SampleApi(
                    input=ex.get("input", ""),
                    output=ex.get("output", ""),
                )
            )

    return examples


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


def create_task_run_from_sample(
    sample: SampleApi, tag: str, extra_tags: list[str] | None = None
) -> TaskRun:
    """Create a TaskRun from a SampleApi (without parent set)."""
    data_source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "adapter_name": KILN_ADAPTER_NAME,
            "model_name": KILN_COPILOT_MODEL_NAME,
            "model_provider": KILN_COPILOT_MODEL_PROVIDER,
        },
    )

    tags = [tag]
    if extra_tags:
        tags.extend(extra_tags)

    # Access input using model_dump since SampleApi uses alias
    sample_dict = sample.model_dump(by_alias=True)
    return TaskRun(
        input=sample_dict["input"],
        input_source=data_source,
        output=TaskOutput(
            output=sample.output,
            source=data_source,
        ),
        tags=tags,
    )


def create_task_run_from_reviewed(
    example: ReviewedExample,
    tag: str,
    spec_name: str,
    extra_tags: list[str] | None = None,
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

    tags = [tag]
    if extra_tags:
        tags.extend(extra_tags)

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
        tags=tags,
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
    - Eval dataset
    - Train dataset
    - Golden dataset (reviewed examples + unrated examples to reach MIN_GOLDEN_EXAMPLES)

    Returns TaskRuns without parent set - caller must set parent.
    """
    task_runs: list[TaskRun] = []

    # Generate a session tag for all task runs in this batch
    session_id = random.randint(0, 999999999999)
    session_tag = f"synthetic_session_{session_id}"
    extra_tags = [session_tag]

    # Create TaskRuns for reviewed examples with ratings
    for reviewed in reviewed_examples:
        task_runs.append(
            create_task_run_from_reviewed(reviewed, golden_tag, spec_name, extra_tags)
        )

    # Create more unrated golden examples from remaining pool if needed
    unrated_golden_count = max(0, MIN_GOLDEN_EXAMPLES - len(reviewed_examples))
    if unrated_golden_count > 0:
        unrated_golden_examples = sample_and_remove(all_examples, unrated_golden_count)
        for example in unrated_golden_examples:
            task_runs.append(
                create_task_run_from_sample(example, golden_tag, extra_tags)
            )

    # Sample half the remaining examples for eval vs train datasets
    example_count = len(all_examples)
    eval_count = example_count // 2
    train_count = example_count - eval_count
    eval_examples = sample_and_remove(all_examples, eval_count)
    train_examples = sample_and_remove(all_examples, train_count)

    # Create TaskRuns for eval examples
    for example in eval_examples:
        task_runs.append(create_task_run_from_sample(example, eval_tag, extra_tags))

    # Create TaskRuns for train examples
    for example in train_examples:
        task_runs.append(create_task_run_from_sample(example, train_tag, extra_tags))

    return task_runs


def check_response_error(
    response: Response, default_detail: str = "Unknown error."
) -> None:
    """Check if the response is an error with user centric message."""
    if response.status_code != 200:
        # response.content is a bytes object
        # We check if it's a JSON object with a user_message field
        detail = default_detail
        if response.content.startswith(b"{"):
            try:
                json_data = json.loads(response.content)
                detail = json_data.get("user_message", default_detail)
            except json.JSONDecodeError:
                pass
        raise HTTPException(
            status_code=response.status_code,
            detail=detail,
        )
