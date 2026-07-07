"""Tests for app/desktop/studio_server/utils/copilot_utils.py."""

from unittest.mock import patch

import pytest
from app.desktop.studio_server.api_models.copilot_models import (
    ClaimReviewApi,
    ReviewedChainApi,
    ReviewedExample,
    SampleApi,
)
from app.desktop.studio_server.utils.copilot_utils import (
    KILN_ADAPTER_NAME,
    KILN_COPILOT_MODEL_NAME,
    KILN_COPILOT_MODEL_PROVIDER,
    MIN_GOLDEN_EXAMPLES,
    NUM_SAMPLES_PER_TOPIC,
    NUM_TOPICS,
    create_dataset_task_runs,
    create_task_run_from_reviewed,
    create_task_run_from_sample,
    delete_multi_turn_batch_chains,
    get_copilot_api_key,
    rate_multi_turn_chain_leaves,
    sample_and_remove,
    unrate_multi_turn_chain_leaves,
)
from fastapi import HTTPException
from kiln_ai.datamodel import GradedClaim, Project, Task, TaskRun
from kiln_ai.datamodel.datamodel_enums import (
    FeedbackSource,
    TaskOutputRatingType,
    TurnMode,
)
from kiln_ai.datamodel.task_output import (
    DataSource,
    DataSourceType,
    TaskOutput,
    TaskOutputRating,
)


class TestGetCopilotApiKey:
    def test_returns_api_key_when_configured(self):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config:
            mock_config.return_value.kiln_copilot_api_key = "test_api_key_123"
            result = get_copilot_api_key()
            assert result == "test_api_key_123"

    def test_raises_401_when_not_configured(self):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config:
            mock_config.return_value.kiln_copilot_api_key = None
            with pytest.raises(HTTPException) as exc_info:
                get_copilot_api_key()
            assert exc_info.value.status_code == 401
            assert "API key not configured" in exc_info.value.detail

    def test_raises_401_when_empty_string(self):
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.Config.shared"
        ) as mock_config:
            mock_config.return_value.kiln_copilot_api_key = ""
            with pytest.raises(HTTPException) as exc_info:
                get_copilot_api_key()
            assert exc_info.value.status_code == 401


class TestSampleAndRemove:
    def test_samples_correct_number_of_items(self):
        examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(10)
        ]
        sampled = sample_and_remove(examples, 3)
        assert len(sampled) == 3
        assert len(examples) == 7

    def test_samples_all_when_n_greater_than_length(self):
        examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(5)
        ]
        sampled = sample_and_remove(examples, 10)
        assert len(sampled) == 5
        assert len(examples) == 0

    def test_returns_empty_list_when_empty_input(self):
        examples: list[SampleApi] = []
        sampled = sample_and_remove(examples, 5)
        assert len(sampled) == 0
        assert len(examples) == 0

    def test_mutates_original_list(self):
        examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(10)
        ]
        original_length = len(examples)
        sample_and_remove(examples, 4)
        assert len(examples) == original_length - 4

    def test_samples_zero_items(self):
        examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(5)
        ]
        sampled = sample_and_remove(examples, 0)
        assert len(sampled) == 0
        assert len(examples) == 5


class TestCreateTaskRunFromSample:
    def test_creates_task_run_with_correct_input(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(sample, "eval_tag")
        assert task_run.input == "test input"

    def test_creates_task_run_with_correct_output(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(sample, "eval_tag")
        assert task_run.output.output == "test output"

    def test_creates_task_run_with_tag(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(sample, "eval_tag")
        assert "eval_tag" in task_run.tags

    def test_creates_task_run_with_extra_tags(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(
            sample, "eval_tag", extra_tags=["session_123", "other_tag"]
        )
        assert "eval_tag" in task_run.tags
        assert "session_123" in task_run.tags
        assert "other_tag" in task_run.tags

    def test_creates_task_run_without_extra_tags(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(sample, "eval_tag", extra_tags=None)
        assert task_run.tags == ["eval_tag"]

    def test_creates_task_run_with_synthetic_data_source(self):
        sample = SampleApi(input="test input", output="test output")
        task_run = create_task_run_from_sample(sample, "eval_tag")
        assert task_run.input_source.type == DataSourceType.synthetic
        assert task_run.input_source.properties["model_name"] == KILN_COPILOT_MODEL_NAME
        assert (
            task_run.input_source.properties["model_provider"]
            == KILN_COPILOT_MODEL_PROVIDER
        )
        assert task_run.input_source.properties["adapter_name"] == KILN_ADAPTER_NAME


class TestCreateTaskRunFromReviewed:
    def test_creates_task_run_with_correct_input(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="Good example",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert task_run.input == "test input"

    def test_creates_task_run_with_correct_output(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert task_run.output.output == "test output"

    def test_creates_task_run_with_pass_rating_when_meets_spec(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        rating_key = "named::My Spec"
        assert rating_key in task_run.output.rating.requirement_ratings
        assert task_run.output.rating.requirement_ratings[rating_key].value == 1.0

    def test_creates_task_run_with_fail_rating_when_not_meets_spec(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=False,
            user_says_meets_spec=False,
            feedback="Bad example",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        rating_key = "named::My Spec"
        assert rating_key in task_run.output.rating.requirement_ratings
        assert task_run.output.rating.requirement_ratings[rating_key].value == 0.0

    def test_creates_task_run_with_tag(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert "golden_tag" in task_run.tags

    def test_creates_task_run_with_extra_tags(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run, _ = create_task_run_from_reviewed(
            example, "golden_tag", "My Spec", extra_tags=["session_456"]
        )
        assert "golden_tag" in task_run.tags
        assert "session_456" in task_run.tags

    def test_creates_task_run_with_pass_fail_rating_type(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run, _ = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        rating_key = "named::My Spec"
        assert (
            task_run.output.rating.requirement_ratings[rating_key].type
            == TaskOutputRatingType.pass_fail
        )

    def test_returns_feedback_text_when_present(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=False,
            feedback="This fails because the output is too vague",
        )
        _, feedback_text = create_task_run_from_reviewed(
            example, "golden_tag", "My Spec"
        )
        assert feedback_text == "This fails because the output is too vague"

    def test_returns_none_feedback_when_empty(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        _, feedback_text = create_task_run_from_reviewed(
            example, "golden_tag", "My Spec"
        )
        assert feedback_text is None


class TestCreateDatasetTaskRuns:
    def test_creates_correct_number_of_task_runs(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        # Should have NUM_SAMPLES_PER_TOPIC * NUM_TOPICS
        expected_count = NUM_SAMPLES_PER_TOPIC * NUM_TOPICS
        assert len(task_runs) == expected_count

    def test_includes_reviewed_examples_in_golden_set(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples = [
            ReviewedExample(
                input="reviewed_input",
                output="reviewed_output",
                model_says_meets_spec=True,
                user_says_meets_spec=True,
                feedback="Great",
            )
        ]

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        # Find the reviewed example in task runs
        reviewed_run = next(
            (tr for tr in task_runs if tr.input == "reviewed_input"), None
        )
        assert reviewed_run is not None
        assert "golden_tag" in reviewed_run.tags

    def test_all_task_runs_have_session_tag(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        # All task runs should have a session tag
        for task_run in task_runs:
            session_tags = [
                tag for tag in task_run.tags if tag.startswith("synthetic_session_")
            ]
            assert len(session_tags) == 1

    def test_same_session_tag_for_all_runs(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        # All task runs should have the same session tag
        session_tags = set()
        for task_run in task_runs:
            for tag in task_run.tags:
                if tag.startswith("synthetic_session_"):
                    session_tags.add(tag)

        assert len(session_tags) == 1

    def test_eval_examples_have_eval_tag(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        eval_runs = [tr for tr in task_runs if "eval_tag" in tr.tags]
        num_runs = NUM_SAMPLES_PER_TOPIC * NUM_TOPICS
        num_eval_runs = (num_runs - MIN_GOLDEN_EXAMPLES) // 2
        assert len(eval_runs) == num_eval_runs

    def test_train_examples_have_train_tag(self):
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}")
            for i in range(NUM_SAMPLES_PER_TOPIC * NUM_TOPICS)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        train_runs = [tr for tr in task_runs if "train_tag" in tr.tags]
        num_runs = NUM_SAMPLES_PER_TOPIC * NUM_TOPICS
        num_eval_runs = (num_runs - MIN_GOLDEN_EXAMPLES) // 2
        num_train_runs = (num_runs - MIN_GOLDEN_EXAMPLES) - num_eval_runs
        assert len(train_runs) == num_train_runs

    def test_handles_insufficient_examples(self):
        # Fewer examples than needed
        all_examples = [
            SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(5)
        ]
        reviewed_examples: list[ReviewedExample] = []

        task_runs = create_dataset_task_runs(
            all_examples,
            reviewed_examples,
            "eval_tag",
            "train_tag",
            "golden_tag",
            "Test Spec",
        ).task_runs

        # Should use all available examples
        assert len(task_runs) == 5


def _claim_review_api(judge_score: str = "fail") -> ClaimReviewApi:
    return ClaimReviewApi(
        judge_score=judge_score,
        judge_reasoning="Stated an unverified policy as fact.",
        claims=[
            GradedClaim(
                claim="The agent stated a specific return window as fact.",
                evidence="The reply gives a window of 30 days [1].",
                expected_result="fail",
                human_grade="agree",
                human_feedback=None,
            )
        ],
        final_judgement=GradedClaim(
            claim="Fails Eval: fabricated policy.",
            evidence="Asserts a window it never verified [1].",
            expected_result="fail",
            human_grade="disagree",
            human_feedback="The policy quoted is actually correct.",
        ),
    )


@pytest.fixture
def task_with_leaves(tmp_path):
    project_path = tmp_path / "test_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="Test Project", path=project_path)
    project.save_to_file()
    task = Task(name="Test Task", instruction="Test instruction", parent=project)
    task.save_to_file()
    source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "haiku",
            "model_provider": "openrouter",
            "adapter_name": "kiln_synthetic_user_runner",
        },
    )
    leaves = []
    for i in range(2):
        run = TaskRun(
            parent=task,
            input=f"input {i}",
            input_source=source,
            output=TaskOutput(output=f"output {i}", source=source),
        )
        run.save_to_file()
        leaves.append(run)
    return task, leaves


class TestRateMultiTurnChainLeaves:
    def test_writes_rating_feedback_and_claim_review(self, task_with_leaves):
        _, leaves = task_with_leaves
        reviewed = [
            ReviewedChainApi(
                leaf_run_id=leaves[0].id,
                user_says_meets_spec=False,
                feedback="Fabricated the return window.",
                claim_review=_claim_review_api(),
            ),
            ReviewedChainApi(
                leaf_run_id=leaves[1].id,
                user_says_meets_spec=True,
            ),
        ]

        rated_out: list = []
        rate_multi_turn_chain_leaves(
            leaves, reviewed, spec_name="My Spec", rated_out=rated_out
        )

        # Leaf 0: FAIL rating + feedback + claim review persisted.
        rating = leaves[0].output.rating
        assert rating is not None
        req = rating.requirement_ratings["named::My Spec"]
        assert req.type == TaskOutputRatingType.pass_fail
        assert req.value == 0.0
        feedback = leaves[0].feedback()
        assert len(feedback) == 1
        assert feedback[0].source == FeedbackSource.spec_feedback
        assert feedback[0].feedback == "Fabricated the return window."
        reviews = leaves[0].claim_reviews()
        assert len(reviews) == 1
        assert reviews[0].judge_score == "fail"
        assert reviews[0].final_judgement.human_grade == "disagree"
        assert (
            reviews[0].final_judgement.human_feedback
            == "The policy quoted is actually correct."
        )

        # Leaf 1: PASS rating, no feedback/claim-review children.
        rating = leaves[1].output.rating
        assert rating is not None
        assert rating.requirement_ratings["named::My Spec"].value == 1.0
        assert leaves[1].feedback() == []
        assert leaves[1].claim_reviews() == []

        # Both mutations were captured for rollback.
        assert len(rated_out) == 2

    def test_unknown_leaf_id_raises_404(self, task_with_leaves):
        _, leaves = task_with_leaves
        reviewed = [
            ReviewedChainApi(leaf_run_id="no_such_run", user_says_meets_spec=True)
        ]
        with pytest.raises(HTTPException) as exc:
            rate_multi_turn_chain_leaves(leaves, reviewed, spec_name="My Spec")
        assert exc.value.status_code == 404

    def test_unrate_restores_prior_state(self, task_with_leaves):
        _, leaves = task_with_leaves
        # Leaf 0 starts with a pre-existing rating that must survive rollback.
        prior = TaskOutputRating(
            type=TaskOutputRatingType.five_star,
            value=None,
            requirement_ratings={
                "named::Other Spec": {
                    "type": TaskOutputRatingType.pass_fail,
                    "value": 1.0,
                }
            },
        )
        leaves[0].output.rating = prior
        leaves[0].save_to_file()

        reviewed = [
            ReviewedChainApi(
                leaf_run_id=leaves[0].id,
                user_says_meets_spec=False,
                feedback="why",
                claim_review=_claim_review_api(),
            ),
        ]
        rated_out: list = []
        rate_multi_turn_chain_leaves(
            leaves, reviewed, spec_name="My Spec", rated_out=rated_out
        )
        assert "named::My Spec" in leaves[0].output.rating.requirement_ratings
        assert len(leaves[0].feedback()) == 1
        assert len(leaves[0].claim_reviews()) == 1

        unrate_multi_turn_chain_leaves(rated_out)

        rating = leaves[0].output.rating
        assert rating is not None
        assert "named::My Spec" not in rating.requirement_ratings
        assert "named::Other Spec" in rating.requirement_ratings
        assert leaves[0].feedback() == []
        assert leaves[0].claim_reviews() == []

    def test_failure_mid_children_still_rolls_back_the_rating(self, task_with_leaves):
        # The rating is persisted before the Feedback/ClaimReview children; a
        # failure saving a child must still leave the leaf recoverable via
        # rated_out (recorded as soon as the rating hits disk).
        _, leaves = task_with_leaves
        reviewed = [
            ReviewedChainApi(
                leaf_run_id=leaves[0].id,
                user_says_meets_spec=False,
                feedback="why",
                claim_review=_claim_review_api(),
            ),
        ]
        rated_out: list = []
        with patch(
            "app.desktop.studio_server.utils.copilot_utils.save_claim_review",
            side_effect=RuntimeError("disk full"),
        ):
            with pytest.raises(RuntimeError, match="disk full"):
                rate_multi_turn_chain_leaves(
                    leaves, reviewed, spec_name="My Spec", rated_out=rated_out
                )

        # The mutated leaf was captured despite the mid-children failure...
        assert len(rated_out) == 1
        assert "named::My Spec" in leaves[0].output.rating.requirement_ratings

        # ...so rollback restores it (rating gone, feedback child deleted).
        unrate_multi_turn_chain_leaves(rated_out)
        assert leaves[0].output.rating is None
        assert leaves[0].feedback() == []
        assert leaves[0].claim_reviews() == []


class TestSavePendingChildren:
    def test_persists_feedback_and_claim_review(self, task_with_leaves):
        task, _ = task_with_leaves
        reviewed = ReviewedExample(
            input="What's the return window?",
            output="30 days.",
            model_says_meets_spec=False,
            user_says_meets_spec=False,
            feedback="Fabricated the window.",
            claim_review=_claim_review_api(),
        )
        dataset = create_dataset_task_runs(
            [], [reviewed], "eval_tag", "train_tag", "golden_tag", "My Spec"
        )
        assert len(dataset.task_runs) == 1
        run = dataset.task_runs[0]
        run.parent = task
        run.save_to_file()
        dataset.save_pending_children(run)

        feedback = run.feedback()
        assert len(feedback) == 1
        assert feedback[0].feedback == "Fabricated the window."
        reviews = run.claim_reviews()
        assert len(reviews) == 1
        assert reviews[0].judge_score == "fail"
        assert len(reviews[0].claims) == 1
        assert reviews[0].claims[0].human_grade == "agree"


# ───────────────── delete_multi_turn_batch_chains ─────────────────


def _su_source(turn_index: int) -> DataSource:
    return DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "haiku",
            "model_provider": "openrouter",
            "adapter_name": "kiln_synthetic_user_runner",
            "batch_tag": "batch1",
            "turn_index": turn_index,
        },
    )


def _build_chain(task: Task, batch_tag: str, turns: int = 2) -> list[TaskRun]:
    """A root→leaf chain shaped like the SU runner's output: only the leaf
    carries the discovery tags."""
    chain: list[TaskRun] = []
    parent_id = None
    for i in range(turns):
        run = TaskRun(
            parent=task,
            input=f"turn input {i}",
            input_source=_su_source(i + 1),
            output=TaskOutput(output=f"turn output {i}", source=_su_source(i + 1)),
            parent_task_run_id=parent_id,
        )
        run.save_to_file()
        chain.append(run)
        parent_id = str(run.id)
    leaf = chain[-1]
    leaf.tags = sorted({"synthetic_user_case", f"synthetic_user_batch:{batch_tag}"})
    leaf.save_to_file()
    return chain


@pytest.fixture
def multiturn_task(tmp_path):
    project_path = tmp_path / "mt_project" / "project.kiln"
    project_path.parent.mkdir()
    project = Project(name="MT Project", path=project_path)
    project.save_to_file()
    task = Task(
        name="MT Task",
        instruction="Test instruction",
        turn_mode=TurnMode.multiturn,
        parent=project,
    )
    task.save_to_file()
    return task


class TestDeleteMultiTurnBatchChains:
    def test_deletes_whole_chains_of_the_batch(self, multiturn_task):
        chain_a = _build_chain(multiturn_task, "old-batch", turns=3)
        chain_b = _build_chain(multiturn_task, "old-batch", turns=2)

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 5
        assert multiturn_task.runs(include_intermediate_runs=True) == []
        for run in [*chain_a, *chain_b]:
            assert run.path is not None and not run.path.exists()

    def test_other_batches_survive(self, multiturn_task):
        _build_chain(multiturn_task, "old-batch", turns=2)
        keep = _build_chain(multiturn_task, "new-batch", turns=2)

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 2
        remaining_ids = {
            str(r.id) for r in multiturn_task.runs(include_intermediate_runs=True)
        }
        assert remaining_ids == {str(r.id) for r in keep}

    def test_skips_chain_claimed_by_another_flow(self, multiturn_task):
        """A leaf with tags beyond the runner's own (an eval save tagged it)
        is part of a dataset, not an abandoned drive — left alone."""
        chain = _build_chain(multiturn_task, "old-batch", turns=2)
        leaf = chain[-1]
        leaf.tags = sorted({*(leaf.tags or []), "eval_config_my_spec"})
        leaf.save_to_file()

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 0
        assert len(multiturn_task.runs(include_intermediate_runs=True)) == 2

    def test_skips_rated_leaf(self, multiturn_task):
        """A rated leaf is answer-key material — never delete it."""
        chain = _build_chain(multiturn_task, "old-batch", turns=2)
        leaf = chain[-1]
        leaf.output.rating = TaskOutputRating(
            type=TaskOutputRatingType.pass_fail, value=1.0
        )
        leaf.save_to_file()

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 0
        assert len(multiturn_task.runs(include_intermediate_runs=True)) == 2

    def test_unknown_batch_tag_is_a_noop(self, multiturn_task):
        _build_chain(multiturn_task, "some-batch", turns=2)
        assert delete_multi_turn_batch_chains(multiturn_task, "nonexistent") == 0
        assert len(multiturn_task.runs(include_intermediate_runs=True)) == 2

    def test_skips_leaf_with_descendants(self, multiturn_task):
        """A tagged run that gained children (a continued conversation) is no
        longer a chain leaf — deleting it would strand its descendants."""
        chain = _build_chain(multiturn_task, "old-batch", turns=2)
        continued = TaskRun(
            parent=multiturn_task,
            input="follow-up turn",
            input_source=_su_source(3),
            output=TaskOutput(output="reply", source=_su_source(3)),
            parent_task_run_id=str(chain[-1].id),
        )
        continued.save_to_file()

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 0
        assert len(multiturn_task.runs(include_intermediate_runs=True)) == 3
