"""Utility functions for creating specs with Kiln Copilot.

This module contains helper functions and constants for creating specs,
evals, eval configs, and task runs as part of the copilot-assisted
spec creation workflow.
"""

import logging
import random
from typing import TypeVar

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
    DrivenSyntheticCaseApi,
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
from kiln_ai.datamodel.eval import (
    EvalInput,
    MultiTurnSyntheticEvalInputData,
    UserMessage,
)
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    RequirementRating,
    TaskOutput,
    TaskOutputRating,
)
from kiln_ai.synthetic_user.parser import (
    SyntheticUserInfoParseError,
    parse_synthetic_user_info,
)
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

# Tag scheme the multi-turn synthetic-user runner stamps on each chain's leaf
# TaskRun — see kiln_ai.synthetic_user.runner. Kept in sync manually; if the
# runner ever changes its tag scheme these constants move too.
_TAG_PREFIX_SU_BATCH = "synthetic_user_batch:"
_TAG_SU_CASE = "synthetic_user_case"

# Constants for copilot spec creation
KILN_COPILOT_MODEL_NAME = "kiln-copilot"
KILN_COPILOT_MODEL_PROVIDER = "kiln"
KILN_ADAPTER_NAME = "kiln-adapter"

# Single-turn synthetic generation sizes: how many examples the copilot API is
# asked to produce for the review + eval datasets. Owned here; the review UI
# advertises the resulting dataset size to the user off these.
NUM_SAMPLES_PER_TOPIC = 20
NUM_TOPICS = 15

# Dataset split — the 50/25/25 spec (train / eval / golden). Golden is the
# human-rated answer key, filled from RATED items only (never padded with
# unrated ones). Multi-turn: golden is capped at GOLDEN_TARGET_FRACTION of
# the chains (select_golden_leaves) and the remainder is all train — the
# eval slice is EvalInput items minted from the driven cases, not chains.
# Single-turn: golden is the reviewed examples (structurally small, no cap
# needed) and the unrated pool splits train:eval at 2:1 (the 50:25), with
# the validation split then carved out of the train share at 2:1
# (split_pool_train_val_eval) so the eval share is unchanged. If
# fewer than the target fraction are rated the answer key is simply smaller
# (warned). One owner so the golden fraction can't drift between the
# single-turn and multi-turn splitters.
TRAIN_SPLIT_WEIGHT = 2
EVAL_SPLIT_WEIGHT = 1
GOLDEN_SPLIT_WEIGHT = 1
GOLDEN_TARGET_FRACTION = 0.25


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


T = TypeVar("T")


def split_pool_train_eval(pool: list[T], rng: random.Random) -> tuple[list[T], list[T]]:
    """Divide the non-golden pool into (train, eval) at 2:1 — the 50:25 of
    the split. Golden never comes from this pool: it is the human-reviewed
    examples, selected before this call.

    eval takes the smaller floor share so train is never starved on small
    pools. The pool is shuffled through the injected rng, so the assignment is
    random in production and deterministic under a seeded rng in tests. The
    input list is not mutated.
    """
    shuffled = list(pool)
    rng.shuffle(shuffled)
    eval_count = (
        len(shuffled) * EVAL_SPLIT_WEIGHT // (TRAIN_SPLIT_WEIGHT + EVAL_SPLIT_WEIGHT)
    )
    return shuffled[eval_count:], shuffled[:eval_count]


def split_pool_train_val_eval(
    pool: list[T], rng: random.Random
) -> tuple[list[T], list[T], list[T]]:
    """Divide the non-golden pool into (train, val, eval).

    Eval keeps the same 1-in-3 share as split_pool_train_eval (the 25 of the
    50/25/25 split); the former train share then splits 2:1 into train and
    val — the validation set is carved out of train so the eval share is
    unchanged. val takes the floor share so train is never starved on small
    pools. The input list is not mutated.
    """
    remainder, eval_examples = split_pool_train_eval(pool, rng)
    val_count = len(remainder) // 3
    return remainder[val_count:], remainder[:val_count], eval_examples


def warn_if_golden_below_target(golden_count: int, total_count: int) -> None:
    """Warn when the human-rated golden set is under the 25% target.

    Golden is never padded to hit the target (an unrated golden calibrates
    nothing), so a small rated set just yields a smaller answer key — worth a
    warning because the 50/25/25 split can't hold once golden is short.
    """
    if total_count <= 0:
        return
    fraction = golden_count / total_count
    if fraction < GOLDEN_TARGET_FRACTION:
        logger.warning(
            "Golden (human-rated) set is %d of %d examples (%.0f%%), below the "
            "%.0f%% target — the answer key is smaller than the 50/25/25 split "
            "intends; it is not padded with unrated examples.",
            golden_count,
            total_count,
            fraction * 100,
            GOLDEN_TARGET_FRACTION * 100,
        )


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
    val_tag: str,
    golden_tag: str,
    spec_name: str,
    rng: random.Random | None = None,
) -> DatasetTaskRuns:
    """Create TaskRuns for the golden, eval, val, and train datasets (disjoint).

    - Golden: the human-rated reviewed examples ONLY (the answer key). Never
      padded with unrated machine examples — an unrated golden calibrates
      nothing.
    - Eval + val + train: the unrated machine pool — eval keeps its 1-in-3
      share (the 25 of the 50/25/25 split), then the former train share
      splits 2:1 into train and val.

    The four tag sets never overlap. `rng` is injected for deterministic
    tests; None uses a fresh system-seeded Random. `all_examples` is not
    mutated. Returns DatasetTaskRuns without parent set — the caller sets
    parent and calls save_pending_children after saving each run.
    """
    rng = rng or random.Random()
    result = DatasetTaskRuns()

    # One session tag stamps every run in this batch.
    session_tag = f"synthetic_session_{rng.randint(0, 999999999999)}"
    extra_tags = [session_tag]

    # Golden = human-rated only.
    for reviewed in reviewed_examples:
        task_run, feedback_text = create_task_run_from_reviewed(
            reviewed, golden_tag, spec_name, extra_tags
        )
        result.add_run(task_run, feedback_text, reviewed.claim_review)

    # The unrated machine pool fills eval + val + train (disjoint from golden).
    # The single-turn golden set is the reviewed examples only (a small
    # human-rated pool from a separate source), so it is structurally well
    # under the 25% cap — no cap needed here, unlike the multi-turn all-rated
    # case.
    train_examples, val_examples, eval_examples = split_pool_train_val_eval(
        all_examples, rng
    )
    write_eval_slice(result, eval_examples, eval_tag, extra_tags)

    for example in val_examples:
        result.add_run(create_task_run_from_sample(example, val_tag, extra_tags))

    for example in train_examples:
        result.add_run(create_task_run_from_sample(example, train_tag, extra_tags))

    warn_if_golden_below_target(
        len(reviewed_examples), len(reviewed_examples) + len(all_examples)
    )
    return result


def write_eval_slice(
    result: DatasetTaskRuns,
    eval_examples: list[SampleApi],
    eval_tag: str,
    extra_tags: list[str],
) -> None:
    """Materialize the single-turn eval slice as eval-tagged TaskRuns.

    Isolated from the split logic on purpose: when the eval dataset moves to
    persisted EvalInput items, only this writer changes — the partitioning
    stays put.
    """
    for example in eval_examples:
        result.add_run(create_task_run_from_sample(example, eval_tag, extra_tags))


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


def delete_multi_turn_batch_chains(task: Task, batch_tag: str) -> int:
    """Delete every chain TaskRun of an abandoned synthetic-user batch.

    Re-driving a batch mints a new batch_tag, which would orphan the previous
    batch's chains on disk forever — the caller passes the superseded tag and
    this removes those chains (every run from leaf to root) before the new
    drive begins. Returns the number of TaskRuns deleted.

    Safety: a chain is only deleted when its leaf carries EXACTLY the
    runner's own tags, no rating, and no descendants. Any extra tag, a
    rating, or a child run means some other flow (an eval save, a manual
    rating, a continued conversation) claimed the chain — it is no longer an
    abandoned drive artifact, so it is left alone. The exact-set match fails
    CLOSED: if the runner's tag scheme ever grows, batches get skipped
    (orphaned) rather than risking deletion of claimed chains.
    """
    # include_intermediate_runs: the ancestor walk needs the complete on-disk
    # set, not the default leaves-only view. One corpus load serves the leaf
    # scan, the descendant check, and the ancestor lookups.
    all_runs = task.runs(include_intermediate_runs=True)
    runs_by_id = {str(run.id): run for run in all_runs}
    parent_ids = {
        str(run.parent_task_run_id)
        for run in all_runs
        if run.parent_task_run_id is not None
    }
    children_by_parent: dict[str, set[str]] = {}
    for run in all_runs:
        if run.parent_task_run_id is not None:
            children_by_parent.setdefault(str(run.parent_task_run_id), set()).add(
                str(run.id)
            )
    target_tag = f"{_TAG_PREFIX_SU_BATCH}{batch_tag}"
    runner_tags = {_TAG_SU_CASE, target_tag}
    deleted = 0
    for leaf in (run for run in all_runs if target_tag in (run.tags or [])):
        if (
            set(leaf.tags or []) != runner_tags
            or leaf.output.rating is not None
            or str(leaf.id) in parent_ids
        ):
            logger.info(
                "Skipping delete of chain leaf %s: claimed by another flow",
                leaf.id,
            )
            continue
        chain: list[TaskRun] = [leaf]
        current = leaf
        while current.parent_task_run_id is not None:
            parent = runs_by_id.get(str(current.parent_task_run_id))
            if parent is None:
                break
            chain.append(parent)
            current = parent
        # A mid-chain turn can parent runs OUTSIDE this chain (a conversation
        # continued from an earlier turn). Deleting it would dangle that
        # fork's parent_task_run_id, so the whole chain is left alone.
        chain_ids = {str(run.id) for run in chain}
        if any(
            not children_by_parent.get(str(run.id), set()) <= chain_ids for run in chain
        ):
            logger.info(
                "Skipping delete of chain leaf %s: a conversation outside "
                "the batch forks from this chain",
                leaf.id,
            )
            continue
        for run in chain:
            run.delete()
            deleted += 1
    return deleted


def split_and_tag_multi_turn_chains(
    leaves: list[TaskRun],
    reviewed_leaf_ids: set[str],
    train_tag: str,
    golden_tag: str,
    rng: random.Random | None = None,
    tagged_out: list[tuple[TaskRun, set[str]]] | None = None,
) -> None:
    """Assign each chain leaf to exactly ONE split (golden XOR train).

    Golden = the human-rated leaves (the answer key), capped at the target
    fraction; every remaining leaf is train. Chains carry no eval slice —
    the eval set is EvalInput items minted from the driven cases
    (write_eval_slice_multi_turn) and re-driven fresh at eval time, so
    reusing a golden chain's scenario there is not circular: golden
    validates the judge on the STORED conversation while the eval set
    scores NEW ones.

    `rng` is injected for deterministic tests. If `tagged_out` is provided,
    each leaf actually mutated is appended as `(leaf, {tag_added})` so the
    caller can reverse the mutation on failure via
    `untag_multi_turn_chains_for_eval` without disturbing pre-existing tags.
    Mutates each leaf in place and persists via save_to_file.
    """
    rng = rng or random.Random()
    golden, pool = select_golden_leaves(leaves, reviewed_leaf_ids, rng)

    tag_chain_leaves(golden, golden_tag, tagged_out)
    tag_chain_leaves(pool, train_tag, tagged_out)

    warn_if_golden_below_target(len(golden), len(leaves))


def select_golden_leaves(
    leaves: list[TaskRun],
    reviewed_leaf_ids: set[str],
    rng: random.Random,
) -> tuple[list[TaskRun], list[TaskRun]]:
    """Carve the golden answer-key slice off the chain leaves.

    Golden is up to GOLDEN_TARGET_FRACTION of the leaves, drawn from RATED
    leaves only (the answer key is human-rated by definition). Because the UI
    requires every chain reviewed before save, in practice all leaves are rated
    and golden is a random 25%. Returns (golden, remaining): remaining holds
    the rated leaves beyond the cap plus any unrated leaves — the train slice.
    Every remaining leaf keeps whatever rating it has; only the golden slice
    is the answer key the judge is calibrated against.
    """
    golden_target = (
        len(leaves)
        * GOLDEN_SPLIT_WEIGHT
        // (TRAIN_SPLIT_WEIGHT + EVAL_SPLIT_WEIGHT + GOLDEN_SPLIT_WEIGHT)
    )
    rated = [leaf for leaf in leaves if leaf.id in reviewed_leaf_ids]
    unrated = [leaf for leaf in leaves if leaf.id not in reviewed_leaf_ids]
    rng.shuffle(rated)
    golden = rated[:golden_target]
    remaining = rated[golden_target:] + unrated
    return golden, remaining


def tag_chain_leaves(
    leaves: list[TaskRun],
    tag: str,
    tagged_out: list[tuple[TaskRun, set[str]]] | None = None,
) -> None:
    """Add one split tag to each leaf, recording the addition for rollback."""
    for leaf in leaves:
        current = set(leaf.tags or [])
        if tag in current:
            continue
        leaf.tags = sorted(current | {tag})
        leaf.save_to_file()
        if tagged_out is not None:
            tagged_out.append((leaf, {tag}))


def build_multi_turn_eval_inputs(
    cases: list[DrivenSyntheticCaseApi],
    batch_tag: str,
    task: Task,
    eval_tag: str,
) -> list[EvalInput]:
    """Mint one EvalInput per driven case — the multi-turn eval slice.

    Each carries the case's seed message plus the parsed synthetic-user
    persona (the structured submodel; the XML blob never persists), tagged
    with the eval-slice tag and its provenance: the synthetic-user batch the
    case was driven in and, when known, the batch-plan scenario it came from.

    Models are built and validated here, unsaved — persistence happens in
    write_eval_slice_multi_turn inside the save unit-of-work. Raises
    HTTPException(422) when a case's persona blob doesn't parse, so a
    malformed request fails before anything is written.
    """
    eval_inputs: list[EvalInput] = []
    for position, case in enumerate(cases):
        try:
            info = parse_synthetic_user_info(case.synthetic_user_info)
        except SyntheticUserInfoParseError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Case {position}: invalid synthetic_user_info: {e}",
            )
        tags = [eval_tag, f"{_TAG_PREFIX_SU_BATCH}{batch_tag}"]
        if case.scenario_index is not None:
            tags.append(f"scenario:{case.scenario_index}")
        eval_inputs.append(
            EvalInput(
                parent=task,
                data=MultiTurnSyntheticEvalInputData(
                    first_message=UserMessage(text=case.seed_prompt),
                    synthetic_user_info=info,
                ),
                tags=tags,
            )
        )
    return eval_inputs


def write_eval_slice_multi_turn(
    eval_inputs: list[EvalInput],
    saved_out: list,
) -> None:
    """Materialize the multi-turn eval slice by persisting its EvalInput items.

    Isolated from the split logic (mirrors write_eval_slice single-turn).
    Each item is appended to `saved_out` the moment it hits disk so a failed
    save rolls it back with the other created models.
    """
    for eval_input in eval_inputs:
        eval_input.save_to_file()
        saved_out.append(eval_input)


def untag_multi_turn_chains_for_eval(
    tagged_leaves: list[tuple[TaskRun, set[str]]],
) -> None:
    """Reverse the tagging done by split_and_tag_multi_turn_chains.

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
