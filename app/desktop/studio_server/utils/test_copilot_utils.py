"""Tests for app/desktop/studio_server/utils/copilot_utils.py."""

from unittest.mock import patch

import pytest
from app.desktop.studio_server.api_models.copilot_models import (
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
    get_copilot_api_key,
    sample_and_remove,
)
from fastapi import HTTPException
from kiln_ai.datamodel.datamodel_enums import TaskOutputRatingType
from kiln_ai.datamodel.task_output import DataSourceType


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
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert task_run.input == "test input"

    def test_creates_task_run_with_correct_output(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert task_run.output.output == "test output"

    def test_creates_task_run_with_pass_rating_when_meets_spec(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
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
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
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
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        assert "golden_tag" in task_run.tags

    def test_creates_task_run_with_extra_tags(self):
        example = ReviewedExample(
            input="test input",
            output="test output",
            model_says_meets_spec=True,
            user_says_meets_spec=True,
            feedback="",
        )
        task_run = create_task_run_from_reviewed(
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
        task_run = create_task_run_from_reviewed(example, "golden_tag", "My Spec")
        rating_key = "named::My Spec"
        assert (
            task_run.output.rating.requirement_ratings[rating_key].type
            == TaskOutputRatingType.pass_fail
        )


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
        )

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
        )

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
        )

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
        )

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
        )

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
        )

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
        )

        # Should use all available examples
        assert len(task_runs) == 5
