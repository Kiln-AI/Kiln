"""Tests for app/desktop/studio_server/utils/copilot_utils.py."""

import random
from unittest.mock import patch

import pytest
from app.desktop.studio_server.api_models.copilot_models import (
    ClaimReviewApi,
    DrivenSyntheticCaseApi,
    ReviewedChainApi,
    ReviewedExample,
    SampleApi,
)
from app.desktop.studio_server.utils.copilot_utils import (
    GOLDEN_TARGET_FRACTION,
    KILN_ADAPTER_NAME,
    KILN_COPILOT_MODEL_NAME,
    KILN_COPILOT_MODEL_PROVIDER,
    build_multi_turn_eval_inputs,
    create_dataset_task_runs,
    create_task_run_from_reviewed,
    create_task_run_from_sample,
    delete_multi_turn_batch_chains,
    get_copilot_api_key,
    rate_multi_turn_chain_leaves,
    select_golden_leaves,
    split_and_tag_multi_turn_chains,
    split_pool_train_eval,
    split_pool_train_val_eval,
    unrate_multi_turn_chain_leaves,
    warn_if_golden_below_target,
    write_eval_slice_multi_turn,
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


class TestSplitPoolTrainEval:
    @pytest.mark.parametrize(
        "n,expected_train,expected_eval",
        [
            (0, 0, 0),  # empty pool
            (1, 1, 0),  # 1//3 == 0 → all to train
            (2, 2, 0),  # 2//3 == 0 → all to train
            (3, 2, 1),  # exact 2:1
            (4, 3, 1),
            (6, 4, 2),
            (9, 6, 3),  # exact 2:1
        ],
    )
    def test_splits_two_to_one(self, n, expected_train, expected_eval):
        pool = list(range(n))
        train, eval_items = split_pool_train_eval(pool, random.Random(0))
        assert len(train) == expected_train
        assert len(eval_items) == expected_eval
        # Partition: disjoint and complete.
        assert sorted(train + eval_items) == pool

    def test_does_not_mutate_input(self):
        pool = list(range(9))
        original = list(pool)
        split_pool_train_eval(pool, random.Random(1))
        assert pool == original

    def test_deterministic_under_seed(self):
        pool = list(range(9))
        a = split_pool_train_eval(pool, random.Random(42))
        b = split_pool_train_eval(pool, random.Random(42))
        assert a == b


class TestSplitPoolTrainValEval:
    @pytest.mark.parametrize(
        "n,expected_train,expected_val,expected_eval",
        [
            (0, 0, 0, 0),  # empty pool
            (2, 2, 0, 0),  # no eval share; 2//3 == 0 → no val either
            (3, 2, 0, 1),  # eval 1; remainder 2 → 2//3 == 0 val
            (6, 3, 1, 2),  # eval 2; remainder 4 → val 1
            (9, 4, 2, 3),  # exact: eval 3; remainder 6 → val 2, train 4
            (60, 27, 13, 20),
        ],
    )
    def test_eval_share_unchanged_val_carved_from_train(
        self, n, expected_train, expected_val, expected_eval
    ):
        # Eval keeps split_pool_train_eval's 1-in-3 share; the remainder
        # splits 2:1 into train and val.
        pool = list(range(n))
        train, val, eval_items = split_pool_train_val_eval(pool, random.Random(0))
        assert len(train) == expected_train
        assert len(val) == expected_val
        assert len(eval_items) == expected_eval
        # Partition: disjoint and complete.
        assert sorted(train + val + eval_items) == pool

    def test_does_not_mutate_input(self):
        pool = list(range(9))
        original = list(pool)
        split_pool_train_val_eval(pool, random.Random(1))
        assert pool == original

    def test_deterministic_under_seed(self):
        pool = list(range(9))
        a = split_pool_train_val_eval(pool, random.Random(42))
        b = split_pool_train_val_eval(pool, random.Random(42))
        assert a == b


class TestSelectGoldenLeaves:
    """select_golden_leaves carves golden (rated-only, capped at 25%) off the
    leaves; the remainder feeds the train/eval split."""

    def test_all_rated_golden_capped_at_quarter(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 8)
        rated = {leaf.id for leaf in leaves}
        golden, remaining = select_golden_leaves(leaves, rated, random.Random(0))
        assert len(golden) == 2  # 8 // 4
        assert len(remaining) == 6
        # Golden is drawn from rated; disjoint from remaining; covers all.
        assert all(leaf.id in rated for leaf in golden)
        assert {leaf.id for leaf in golden}.isdisjoint({leaf.id for leaf in remaining})
        assert len(golden) + len(remaining) == 8

    def test_rated_below_cap_golden_is_all_rated(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 8)
        rated = {leaves[0].id}  # 1 rated, cap is 2
        golden, remaining = select_golden_leaves(leaves, rated, random.Random(0))
        assert {leaf.id for leaf in golden} == {leaves[0].id}
        assert len(remaining) == 7

    def test_unrated_never_enters_golden(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 8)
        golden, remaining = select_golden_leaves(leaves, set(), random.Random(0))
        assert golden == []
        assert len(remaining) == 8

    def test_excess_rated_falls_into_remaining(self, multiturn_task):
        # All 8 rated, cap 2 → 6 rated leaves land in remaining (still held out).
        leaves = _make_su_leaves(multiturn_task, 8)
        rated = {leaf.id for leaf in leaves}
        golden, remaining = select_golden_leaves(leaves, rated, random.Random(1))
        assert len(golden) == 2
        assert all(leaf.id in rated for leaf in remaining)


class TestWarnIfGoldenBelowTarget:
    def test_warns_when_below_target(self, caplog):
        # 1 of 10 rated == 10%, below the 25% floor.
        with caplog.at_level("WARNING"):
            warn_if_golden_below_target(1, 10)
        assert any("below the" in r.message for r in caplog.records)

    def test_silent_at_or_above_target(self, caplog):
        # 25% is the target — not below it.
        target_count = int(GOLDEN_TARGET_FRACTION * 100)
        with caplog.at_level("WARNING"):
            warn_if_golden_below_target(target_count, 100)
        assert caplog.records == []

    def test_silent_when_total_zero(self, caplog):
        with caplog.at_level("WARNING"):
            warn_if_golden_below_target(0, 0)
        assert caplog.records == []


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


def _samples(n: int) -> list[SampleApi]:
    return [SampleApi(input=f"input_{i}", output=f"output_{i}") for i in range(n)]


def _reviewed(n: int) -> list[ReviewedExample]:
    return [
        ReviewedExample(
            input=f"reviewed_input_{i}",
            output=f"reviewed_output_{i}",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        for i in range(n)
    ]


def _make_dataset(
    all_examples: list[SampleApi],
    reviewed_examples: list[ReviewedExample],
    seed: int = 0,
):
    return create_dataset_task_runs(
        all_examples,
        reviewed_examples,
        "eval_tag",
        "train_tag",
        "val_tag",
        "golden_tag",
        "Test Spec",
        rng=random.Random(seed),
    ).task_runs


def _by_split(task_runs):
    """Bucket runs by their single split tag."""
    return {
        "eval": [tr for tr in task_runs if "eval_tag" in tr.tags],
        "train": [tr for tr in task_runs if "train_tag" in tr.tags],
        "val": [tr for tr in task_runs if "val_tag" in tr.tags],
        "golden": [tr for tr in task_runs if "golden_tag" in tr.tags],
    }


class TestCreateDatasetTaskRuns:
    def test_total_runs_is_pool_plus_rated(self):
        # Golden holds the rated examples; the unrated pool fills eval + train.
        task_runs = _make_dataset(_samples(300), _reviewed(4))
        assert len(task_runs) == 304

    def test_reviewed_examples_are_golden_and_rated(self):
        task_runs = _make_dataset(_samples(60), _reviewed(1))
        golden = _by_split(task_runs)["golden"]
        # Golden == exactly the rated set, no unrated padding.
        assert len(golden) == 1
        assert golden[0].input == "reviewed_input_0"
        assert golden[0].output.rating is not None

    def test_golden_is_rated_only_no_unrated_padding(self):
        # Golden holds exactly the rated count — never topped up with unrated
        # machine examples, even when that leaves it small.
        task_runs = _make_dataset(_samples(60), _reviewed(2))
        golden = _by_split(task_runs)["golden"]
        assert len(golden) == 2
        assert all(tr.output.rating is not None for tr in golden)

    def test_zero_rated_yields_no_golden(self):
        task_runs = _make_dataset(_samples(30), _reviewed(0))
        assert _by_split(task_runs)["golden"] == []

    def test_splits_are_disjoint_and_complete(self):
        task_runs = _make_dataset(_samples(60), _reviewed(4))
        for tr in task_runs:
            split_tags = {"eval_tag", "train_tag", "val_tag", "golden_tag"} & set(
                tr.tags
            )
            assert len(split_tags) == 1, f"run {tr.input} has splits {split_tags}"
        buckets = _by_split(task_runs)
        assert len(buckets["eval"]) + len(buckets["train"]) + len(buckets["val"]) + len(
            buckets["golden"]
        ) == len(task_runs)

    def test_unrated_pool_split_counts(self):
        # eval keeps its 1-in-3 share; the remainder splits 2:1 train:val.
        task_runs = _make_dataset(_samples(60), _reviewed(0))
        buckets = _by_split(task_runs)
        assert len(buckets["eval"]) == 20  # 60 // 3
        assert len(buckets["val"]) == 13  # 40 // 3
        assert len(buckets["train"]) == 27

    def test_one_rated_small_pool(self):
        # golden=1 (rated); the 3 unrated → eval 1, then 2//3 == 0 val, train 2.
        task_runs = _make_dataset(_samples(3), _reviewed(1))
        buckets = _by_split(task_runs)
        assert len(buckets["golden"]) == 1
        assert len(buckets["train"]) == 2
        assert len(buckets["val"]) == 0
        assert len(buckets["eval"]) == 1

    def test_tiny_pool_all_train_no_eval(self):
        # 2 unrated → 2//3 == 0 eval, 0 val, both to train (small-N edge).
        task_runs = _make_dataset(_samples(2), _reviewed(0))
        buckets = _by_split(task_runs)
        assert len(buckets["train"]) == 2
        assert len(buckets["val"]) == 0
        assert len(buckets["eval"]) == 0

    def test_handles_insufficient_examples(self):
        task_runs = _make_dataset(_samples(5), _reviewed(0))
        assert len(task_runs) == 5

    def test_does_not_mutate_all_examples(self):
        all_examples = _samples(30)
        original = list(all_examples)
        _make_dataset(all_examples, _reviewed(2))
        assert all_examples == original

    def test_all_task_runs_have_one_shared_session_tag(self):
        task_runs = _make_dataset(_samples(60), _reviewed(2))
        session_tags = {
            tag
            for tr in task_runs
            for tag in tr.tags
            if tag.startswith("synthetic_session_")
        }
        assert len(session_tags) == 1
        for tr in task_runs:
            assert sum(t.startswith("synthetic_session_") for t in tr.tags) == 1

    def test_warns_when_golden_below_target(self, caplog):
        with caplog.at_level("WARNING"):
            _make_dataset(_samples(99), _reviewed(1))  # golden 1% << 25%
        assert any("below the" in r.message for r in caplog.records)


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
            [], [reviewed], "eval_tag", "train_tag", "val_tag", "golden_tag", "My Spec"
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


def _make_su_leaves(task: Task, n: int) -> list[TaskRun]:
    """Persist n synthetic-user chain leaves under a task, tagged like the runner."""
    source = DataSource(
        type=DataSourceType.synthetic,
        properties={
            "model_name": "haiku",
            "model_provider": "openrouter",
            "adapter_name": "kiln_synthetic_user_runner",
        },
    )
    leaves = []
    for i in range(n):
        run = TaskRun(
            parent=task,
            input=f"input {i}",
            input_source=source,
            output=TaskOutput(output=f"output {i}", source=source),
            tags=["synthetic_user_case", "synthetic_user_batch:b1"],
        )
        run.save_to_file()
        leaves.append(run)
    return leaves


def _leaf_split(leaves: list[TaskRun]) -> dict[str, list[TaskRun]]:
    return {
        "eval": [x for x in leaves if "eval_tag" in (x.tags or [])],
        "train": [x for x in leaves if "train_tag" in (x.tags or [])],
        "golden": [x for x in leaves if "golden_tag" in (x.tags or [])],
    }


class TestSplitAndTagMultiTurnChains:
    def test_all_reviewed_splits_golden_cap_rest_train(self, multiturn_task):
        # Mirrors the real UI: every chain reviewed before save. golden caps
        # at 25%; every remaining chain is train (the eval slice is EvalInput
        # items minted from the cases, not chains).
        leaves = _make_su_leaves(multiturn_task, 8)
        reviewed_ids = {leaf.id for leaf in leaves}

        split_and_tag_multi_turn_chains(
            leaves,
            reviewed_ids,
            "train_tag",
            "golden_tag",
            rng=random.Random(0),
        )

        buckets = _leaf_split(leaves)
        assert len(buckets["golden"]) == 2
        assert buckets["eval"] == []
        assert len(buckets["train"]) == 6
        # Golden is a subset of the reviewed leaves (rated-only answer key).
        assert {x.id for x in buckets["golden"]} <= reviewed_ids

    def test_each_leaf_gets_exactly_one_split_tag(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 5)
        split_and_tag_multi_turn_chains(
            leaves,
            {leaves[0].id},
            "train_tag",
            "golden_tag",
            rng=random.Random(1),
        )
        for leaf in leaves:
            split_tags = {"train_tag", "golden_tag"} & set(leaf.tags)
            assert len(split_tags) == 1

    def test_golden_capped_even_when_all_reviewed(self, multiturn_task):
        # 4 leaves all reviewed → golden caps at 1 (not 4); train is never
        # starved to empty (the bug the cap fixes).
        leaves = _make_su_leaves(multiturn_task, 4)
        split_and_tag_multi_turn_chains(
            leaves,
            {leaf.id for leaf in leaves},
            "train_tag",
            "golden_tag",
            rng=random.Random(7),
        )
        buckets = _leaf_split(leaves)
        assert len(buckets["golden"]) == 1
        assert len(buckets["train"]) == 3

    def test_zero_rated_no_golden(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 3)
        split_and_tag_multi_turn_chains(
            leaves,
            set(),
            "train_tag",
            "golden_tag",
            rng=random.Random(2),
        )
        buckets = _leaf_split(leaves)
        assert buckets["golden"] == []
        assert len(buckets["train"]) == 3

    def test_preserves_existing_runner_tags(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 4)
        split_and_tag_multi_turn_chains(
            leaves,
            {leaf.id for leaf in leaves},
            "train_tag",
            "golden_tag",
            rng=random.Random(3),
        )
        for leaf in leaves:
            assert "synthetic_user_case" in leaf.tags
            assert "synthetic_user_batch:b1" in leaf.tags

    def test_tagged_out_captures_additions_for_rollback(self, multiturn_task):
        leaves = _make_su_leaves(multiturn_task, 4)
        tagged_out: list = []
        split_and_tag_multi_turn_chains(
            leaves,
            {leaf.id for leaf in leaves},
            "train_tag",
            "golden_tag",
            rng=random.Random(4),
            tagged_out=tagged_out,
        )
        # Every leaf was mutated exactly once (one split tag added each).
        assert len(tagged_out) == 4
        assert all(len(added) == 1 for _, added in tagged_out)


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

    def test_skips_chain_forked_mid_conversation(self, multiturn_task):
        """A conversation continued from a MID-chain turn parents a run
        outside the chain — deleting the ancestors would dangle the fork's
        parent_task_run_id, so the whole chain is left alone."""
        chain = _build_chain(multiturn_task, "old-batch", turns=3)
        fork = TaskRun(
            parent=multiturn_task,
            input="fork from the first turn",
            input_source=_su_source(9),
            output=TaskOutput(output="reply", source=_su_source(9)),
            parent_task_run_id=str(chain[0].id),
        )
        fork.save_to_file()

        deleted = delete_multi_turn_batch_chains(multiturn_task, "old-batch")

        assert deleted == 0
        assert len(multiturn_task.runs(include_intermediate_runs=True)) == 4


# ───────────────── multi-turn eval slice (EvalInput writer) ─────────────────


def _driven_case(idx: int, scenario_index: int | None = None) -> DrivenSyntheticCaseApi:
    return DrivenSyntheticCaseApi(
        seed_prompt=f"seed {idx}",
        synthetic_user_info=(
            f"<persona>persona {idx}</persona>"
            f"<goal>goal {idx}</goal>"
            f"<behavior_guidance>guidance {idx}</behavior_guidance>"
        ),
        scenario_index=scenario_index,
    )


class TestBuildMultiTurnEvalInputs:
    def test_mints_one_eval_input_per_case(self, multiturn_task):
        cases = [_driven_case(0, scenario_index=2), _driven_case(1)]
        eval_inputs = build_multi_turn_eval_inputs(
            cases, "batch99", multiturn_task, "eval_myspec"
        )

        assert len(eval_inputs) == 2
        first = eval_inputs[0]
        assert first.data.type == "multi_turn_synthetic"
        assert first.data.first_message is not None
        assert first.data.first_message.text == "seed 0"
        assert first.data.synthetic_user_info.persona == "persona 0"
        assert first.data.synthetic_user_info.goal == "goal 0"
        assert first.data.synthetic_user_info.behavior_guidance == "guidance 0"
        # Slice tag + provenance: the synthetic-user batch the case was
        # driven in, and the batch-plan scenario it came from.
        assert first.tags == [
            "eval_myspec",
            "synthetic_user_batch:batch99",
            "scenario:2",
        ]
        # No scenario_index → no scenario tag.
        assert eval_inputs[1].tags == ["eval_myspec", "synthetic_user_batch:batch99"]
        # Built, validated, NOT saved — persistence is the unit of work's job.
        assert multiturn_task.eval_inputs(readonly=True) == []

    def test_malformed_blob_is_422(self, multiturn_task):
        bad = DrivenSyntheticCaseApi(
            seed_prompt="seed", synthetic_user_info="no tags at all"
        )
        with pytest.raises(HTTPException) as exc:
            build_multi_turn_eval_inputs(
                [_driven_case(0), bad], "b1", multiturn_task, "eval_x"
            )
        assert exc.value.status_code == 422
        assert "Case 1" in exc.value.detail
        assert multiturn_task.eval_inputs(readonly=True) == []


class TestWriteEvalSliceMultiTurn:
    def test_persists_and_ledgers_each_item(self, multiturn_task):
        eval_inputs = build_multi_turn_eval_inputs(
            [_driven_case(0), _driven_case(1)], "b1", multiturn_task, "eval_x"
        )
        saved_out: list = []
        write_eval_slice_multi_turn(eval_inputs, saved_out)

        on_disk = multiturn_task.eval_inputs(readonly=True)
        assert len(on_disk) == 2
        # Every persisted item is in the rollback ledger.
        assert saved_out == eval_inputs
