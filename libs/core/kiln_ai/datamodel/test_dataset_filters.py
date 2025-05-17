from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from kiln_ai.datamodel.dataset_filters import (
    AllDatasetFilter,
    DatasetFilterId,
    HighRatingDatasetFilter,
    MultiDatasetFilter,
    StaticDatasetFilters,
    TagFilter,
    ThinkingModelDatasetFilter,
    ThinkingModelHighRatedFilter,
    dataset_filter_from_id,
)
from kiln_ai.datamodel.task_run import TaskRun

# Note: Many more filter tests in test_dataset_split.py


def test_all_dataset_filter_from_id():
    assert dataset_filter_from_id("all") == AllDatasetFilter


def test_high_rating_dataset_filter_from_id():
    assert dataset_filter_from_id("high_rating") == HighRatingDatasetFilter


def test_thinking_model_dataset_filter_from_id():
    assert dataset_filter_from_id("thinking_model") == ThinkingModelDatasetFilter


def test_thinking_model_high_rated_dataset_filter_from_id():
    assert (
        dataset_filter_from_id("thinking_model_high_rated")
        == ThinkingModelHighRatedFilter
    )


def test_all_static_dataset_filters():
    for filter_id in StaticDatasetFilters:
        assert dataset_filter_from_id(filter_id) is not None


class ModelTester(BaseModel):
    dsid: DatasetFilterId


@pytest.mark.parametrize(
    "tag,expected_error,expected_tag",
    [
        ("tag::test", False, "test"),
        ("tag::other", False, "other"),
        ("tag::", True, None),
        ("tag", True, None),
        ("", True, None),
    ],
)
def test_tag_filter(tag, expected_error, expected_tag):
    # Check our model validators
    if expected_error:
        with pytest.raises(ValueError):
            ModelTester(dsid=tag)
    else:
        ModelTester(dsid=tag)

    # Check the constructor
    if expected_tag is None:
        with pytest.raises(ValueError, match="Invalid dataset filter ID:"):
            dataset_filter_from_id(tag)
    else:
        filter = dataset_filter_from_id(tag)
        assert isinstance(filter, TagFilter)
        assert filter.tag == expected_tag


class TestMultiDatasetFilter:
    @pytest.mark.parametrize(
        "filter_string,expected_filters",
        [
            ("multi_filter::high_rating", ["high_rating"]),
            (
                "multi_filter::high_rating&thinking_model",
                ["high_rating", "thinking_model"],
            ),
            ("multi_filter::tag::test&high_rating", ["tag::test", "high_rating"]),
            (
                "multi_filter::high_rating&tag::tag\\&name",
                ["high_rating", "tag::tag&name"],
            ),
        ],
    )
    def test_valid_filter_string_parsing(self, filter_string, expected_filters):
        """Test that valid filter strings are parsed correctly."""
        assert MultiDatasetFilter.parse_filter_string(filter_string) == expected_filters
        assert MultiDatasetFilter.is_valid_filter_string(filter_string)

    @pytest.mark.parametrize(
        "filter_string,expected_error",
        [
            (
                "not_multi_filter::high_rating",
                "Filter string must start with multi_filter::",
            ),
            ("multi_filter::", "No filters specified after prefix"),
            ("multi_filter::high_rating&", "Invalid dataset filter ID:"),
            ("multi_filter::invalid_filter", "Invalid dataset filter ID:"),
        ],
    )
    def test_invalid_filter_string_handling(self, filter_string, expected_error):
        """Test that invalid filter strings raise appropriate errors."""
        with pytest.raises(ValueError, match=expected_error):
            MultiDatasetFilter.parse_filter_string(filter_string)
        assert not MultiDatasetFilter.is_valid_filter_string(filter_string)

    def test_filter_combination_logic(self):
        """Test that multiple filters are combined with AND logic."""
        # Create a mock task run
        task_run = Mock(spec=TaskRun)
        task_run.output = Mock()
        task_run.output.rating = Mock()
        task_run.output.rating.is_high_quality.return_value = True
        task_run.tags = ["test_tag"]
        task_run.has_thinking_training_data.return_value = True
        task_run.repaired_output = None

        # Test combining high_rating and tag filters
        filter_id = "multi_filter::high_rating&tag::test_tag"
        multi_filter = dataset_filter_from_id(filter_id)
        assert multi_filter(task_run)

        # Test that it fails if one filter fails
        task_run.tags = ["wrong_tag"]
        assert not multi_filter(task_run)
        task_run.tags = ["test_tag"]
        assert multi_filter(task_run)
        task_run.output.rating.is_high_quality.return_value = False
        assert not multi_filter(task_run)

        # Verify the mock was called as expected
        task_run.output.rating.is_high_quality.assert_called()

    def test_filter_creation_from_id(self):
        """Test that multi filters can be created via dataset_filter_from_id."""
        filter_id = "multi_filter::high_rating&thinking_model"
        filter = dataset_filter_from_id(filter_id)
        assert isinstance(filter, MultiDatasetFilter)
        assert len(filter.filters) == 2
        assert any(isinstance(f, type(HighRatingDatasetFilter)) for f in filter.filters)
        assert any(
            isinstance(f, type(ThinkingModelDatasetFilter)) for f in filter.filters
        )
