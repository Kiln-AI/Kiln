"""Utility functions for creating specs with Kiln Copilot.

This module contains helper functions and constants for creating specs,
evals, eval configs, and task runs as part of the copilot-assisted
spec creation workflow.
"""

import logging
import random

from app.desktop.studio_server.api_client.kiln_ai_server_client.api.copilot import (
    generate_batch_v1_copilot_generate_batch_post,
)
from app.desktop.studio_server.api_client.kiln_ai_server_client.models import (
    GenerateBatchInput,
    GenerateBatchOutput,
)
from app.desktop.studio_server.api_client.kiln_server_client import (
    get_authenticated_client,
)
from app.desktop.studio_server.api_models.copilot_models import (
    ClaimReviewApi,
    ReviewedChainApi,
    ReviewedExample,
    SampleApi,
    SyntheticDataGenerationSessionConfigApi,
    TaskInfoApi,
)
from app.desktop.studio_server.utils.response_utils import unwrap_response
from fastapi import HTTPException
from kiln_ai.datamodel import ClaimReview, Feedback, FeedbackSource, Task, TaskRun
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

# Tag prefix the multi-turn synthetic-user runner stamps on each chain's leaf
# TaskRun — see kiln_ai.synthetic_user.runner._TAG_PREFIX_SU_BATCH. Kept in
# sync manually; if the runner ever changes its tag scheme this constant
# moves too.
_TAG_PREFIX_SU_BATCH = "synthetic_user_batch:"

# Constants for copilot spec creation
KILN_COPILOT_MODEL_NAME = "kiln-copilot"
KILN_COPILOT_MODEL_PROVIDER = "kiln"
KILN_ADAPTER_NAME = "kiln-adapter"
NUM_SAMPLES_PER_TOPIC = 20
NUM_TOPICS = 15
MIN_GOLDEN_EXAMPLES = 25


def spec_rating_key(spec_name: str) -> str:
    """The requirement_ratings key a spec's golden verdicts are stored under."""
    return f"named::{spec_name}"


def golden_requirement_rating(user_says_meets_spec: bool) -> RequirementRating:
    """The human's pass/fail verdict as the golden requirement rating.

    One constructor for both answer-key writers (single-turn golden runs and
    multi-turn chain leaves) so the rating shape can't drift between them.
    """
    return RequirementRating(
        type=TaskOutputRatingType.pass_fail,
        value=1.0 if user_says_meets_spec else 0.0,
    )


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
    result = unwrap_response(
        detailed_result,
        none_detail="Failed to generate synthetic data for spec. Please try again.",
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
) -> tuple[TaskRun, str | None]:
    """Create a TaskRun from a reviewed example with rating (without parent set).

    Returns a (TaskRun, feedback_text) tuple. The caller should create Feedback
    and ClaimReview children on the TaskRun after saving it (see
    DatasetTaskRuns.save_pending_children).
    """
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

    task_run = TaskRun(
        input=example.input,
        input_source=data_source,
        output=TaskOutput(
            output=example.output,
            source=data_source,
            rating=TaskOutputRating(
                type=TaskOutputRatingType.five_star,
                value=None,  # Actual rating is in requirement_ratings
                requirement_ratings={
                    spec_rating_key(spec_name): golden_requirement_rating(
                        example.user_says_meets_spec
                    )
                },
            ),
        ),
        tags=tags,
    )
    feedback_text = example.feedback if example.feedback else None
    return task_run, feedback_text


class DatasetTaskRuns:
    """Result of creating dataset task runs, with pending review children
    (feedback + claim reviews) to attach after saving."""

    def __init__(self) -> None:
        self.task_runs: list[TaskRun] = []
        self._pending_feedback: dict[str, str] = {}
        self._pending_claim_reviews: dict[str, ClaimReviewApi] = {}

    def add_run(
        self,
        task_run: TaskRun,
        feedback_text: str | None = None,
        claim_review: ClaimReviewApi | None = None,
    ) -> None:
        self.task_runs.append(task_run)
        if feedback_text and task_run.id:
            self._pending_feedback[task_run.id] = feedback_text
        if claim_review and task_run.id:
            self._pending_claim_reviews[task_run.id] = claim_review

    def save_pending_children(self, task_run: TaskRun) -> None:
        """Create Feedback / ClaimReview children for a saved TaskRun."""
        if not task_run.id:
            return
        feedback_text = self._pending_feedback.get(task_run.id)
        if feedback_text:
            fb = Feedback(
                feedback=feedback_text,
                source=FeedbackSource.spec_feedback,
                parent=task_run,
            )
            fb.save_to_file()
        claim_review = self._pending_claim_reviews.get(task_run.id)
        if claim_review:
            save_claim_review(task_run, claim_review)


def save_claim_review(task_run: TaskRun, claim_review: ClaimReviewApi) -> ClaimReview:
    """Persist a reviewer's per-claim grades as a ClaimReview child of the run.

    This is the durable half of the answer key: the golden rating records the
    human's verdict, the ClaimReview records WHY (per-claim agree/disagree +
    whys) in the shape judge-prompt refinement consumes.
    """
    # model_dump instead of a field-by-field copy: the API model mirrors the
    # datamodel, so a new field flows through without a silent drop here.
    review = ClaimReview(**claim_review.model_dump(), parent=task_run)
    review.save_to_file()
    return review


def create_dataset_task_runs(
    all_examples: list[SampleApi],
    reviewed_examples: list[ReviewedExample],
    eval_tag: str,
    train_tag: str,
    golden_tag: str,
    spec_name: str,
) -> DatasetTaskRuns:
    """Create TaskRuns for eval, train, and golden datasets.

    Samples from all_examples (mutating it) and creates TaskRuns for:
    - Eval dataset
    - Train dataset
    - Golden dataset (reviewed examples + unrated examples to reach MIN_GOLDEN_EXAMPLES)

    Returns DatasetTaskRuns without parent set - caller must set parent and call
    save_pending_children after saving each run.
    """
    result = DatasetTaskRuns()

    # Generate a session tag for all task runs in this batch
    session_id = random.randint(0, 999999999999)
    session_tag = f"synthetic_session_{session_id}"
    extra_tags = [session_tag]

    # Create TaskRuns for reviewed examples with ratings
    for reviewed in reviewed_examples:
        task_run, feedback_text = create_task_run_from_reviewed(
            reviewed, golden_tag, spec_name, extra_tags
        )
        result.add_run(task_run, feedback_text, reviewed.claim_review)

    # Create more unrated golden examples from remaining pool if needed
    unrated_golden_count = max(0, MIN_GOLDEN_EXAMPLES - len(reviewed_examples))
    if unrated_golden_count > 0:
        unrated_golden_examples = sample_and_remove(all_examples, unrated_golden_count)
        for example in unrated_golden_examples:
            result.add_run(create_task_run_from_sample(example, golden_tag, extra_tags))

    # Sample half the remaining examples for eval vs train datasets
    example_count = len(all_examples)
    eval_count = example_count // 2
    train_count = example_count - eval_count
    eval_examples = sample_and_remove(all_examples, eval_count)
    train_examples = sample_and_remove(all_examples, train_count)

    # Create TaskRuns for eval examples
    for example in eval_examples:
        result.add_run(create_task_run_from_sample(example, eval_tag, extra_tags))

    # Create TaskRuns for train examples
    for example in train_examples:
        result.add_run(create_task_run_from_sample(example, train_tag, extra_tags))

    return result


def find_multi_turn_chain_leaves(task: Task, batch_tag: str) -> list[TaskRun]:
    """Return the leaf TaskRuns of all chains tagged with the given batch_tag.

    The multi-turn runner tags only the leaf of each chain with
    "synthetic_user_batch:{batch_tag}". Walking parent_task_run_id from the
    leaf reconstructs the full conversation if a caller needs it; for eval
    purposes the leaf alone is enough because its `.trace` field already
    holds the cumulative OpenAI-format conversation.
    """
    target_tag = f"{_TAG_PREFIX_SU_BATCH}{batch_tag}"
    return [run for run in task.runs() if target_tag in (run.tags or [])]


def tag_multi_turn_chains_for_eval(
    leaves: list[TaskRun],
    eval_tag: str,
    golden_tag: str,
    tagged_out: list[tuple[TaskRun, set[str]]] | None = None,
) -> None:
    """Add eval and golden filter tags to existing chain leaves.

    Every leaf gets BOTH eval and golden tags so the chain is part of the
    eval dataset AND the golden ratings set — no train tag is applied
    (multi-turn evals don't have a train set in MVP — see
    specs/projects/eval_builder_v2/design.md).

    If `tagged_out` is provided, each leaf actually mutated is appended as
    `(leaf, set_of_tags_added_by_this_call)`. The caller can reverse the
    mutation on failure via `untag_multi_turn_chains_for_eval` without
    removing tags that already existed on the leaf.

    Mutates each leaf in place and persists via save_to_file.
    """
    for leaf in leaves:
        current = set(leaf.tags or [])
        added = {eval_tag, golden_tag} - current
        if not added:
            continue
        leaf.tags = sorted(current | added)
        leaf.save_to_file()
        if tagged_out is not None:
            tagged_out.append((leaf, added))


def untag_multi_turn_chains_for_eval(
    tagged_leaves: list[tuple[TaskRun, set[str]]],
) -> None:
    """Reverse the tagging done by tag_multi_turn_chains_for_eval.

    Removes only the tags that THIS run added (passed in via `tagged_out`),
    so pre-existing tags on the leaf are preserved. Best-effort: a per-leaf
    save failure is logged and the loop continues — the original save error
    that triggered cleanup is the one the user needs to see.
    """
    for leaf, added_tags in tagged_leaves:
        try:
            leaf.tags = sorted(set(leaf.tags or []) - added_tags)
            leaf.save_to_file()
        except Exception:
            logger.exception(f"Failed to untag leaf {leaf.id} during cleanup")


def rate_multi_turn_chain_leaves(
    leaves: list[TaskRun],
    reviewed_chains: list[ReviewedChainApi],
    spec_name: str,
    rated_out: list[
        tuple[TaskRun, TaskOutputRating | None, list[Feedback | ClaimReview]]
    ]
    | None = None,
) -> None:
    """Write the human's review verdicts onto the chain-leaf TaskRuns.

    Each reviewed chain becomes a golden RequirementRating (pass_fail under
    `named::{spec_name}`) on its leaf, plus a Feedback for the disagree-why
    text and a ClaimReview child carrying the per-claim grades — the same
    answer-key shape single-turn golden runs get.

    If `rated_out` is provided, each mutated leaf is appended as
    `(leaf, rating_before_this_call, children_added)` so a failed save can
    be reversed via `unrate_multi_turn_chain_leaves`.

    Raises HTTPException(404) when a reviewed chain references a leaf id not
    in `leaves` — the review must describe the batch being saved.
    """
    leaves_by_id = {leaf.id: leaf for leaf in leaves if leaf.id}
    rating_key = spec_rating_key(spec_name)

    for reviewed in reviewed_chains:
        leaf = leaves_by_id.get(reviewed.leaf_run_id)
        if leaf is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Reviewed chain leaf '{reviewed.leaf_run_id}' is not part "
                    "of this batch."
                ),
            )

        prior_rating = (
            leaf.output.rating.model_copy(deep=True) if leaf.output.rating else None
        )
        rating = leaf.output.rating or TaskOutputRating(
            type=TaskOutputRatingType.five_star,
            value=None,  # Actual rating is in requirement_ratings
        )
        rating.requirement_ratings[rating_key] = golden_requirement_rating(
            reviewed.user_says_meets_spec
        )
        leaf.output.rating = rating
        leaf.save_to_file()

        # Record for rollback the moment the leaf is mutated on disk;
        # added_children is filled in place below, so a failure while saving
        # a child still rolls back everything already persisted.
        added_children: list[Feedback | ClaimReview] = []
        if rated_out is not None:
            rated_out.append((leaf, prior_rating, added_children))

        if reviewed.feedback:
            fb = Feedback(
                feedback=reviewed.feedback,
                source=FeedbackSource.spec_feedback,
                parent=leaf,
            )
            fb.save_to_file()
            added_children.append(fb)
        if reviewed.claim_review:
            added_children.append(save_claim_review(leaf, reviewed.claim_review))


def unrate_multi_turn_chain_leaves(
    rated_leaves: list[
        tuple[TaskRun, TaskOutputRating | None, list[Feedback | ClaimReview]]
    ],
) -> None:
    """Reverse the mutations done by rate_multi_turn_chain_leaves.

    Restores each leaf's prior rating and deletes the Feedback/ClaimReview
    children this run added. Best-effort like the untag path: per-leaf
    failures are logged and the loop continues so the original error stays
    visible.
    """
    for leaf, prior_rating, added_children in rated_leaves:
        try:
            leaf.output.rating = prior_rating
            leaf.save_to_file()
            for child in added_children:
                child.delete()
        except Exception:
            logger.exception(f"Failed to unrate leaf {leaf.id} during cleanup")
