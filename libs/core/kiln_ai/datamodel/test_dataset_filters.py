import pytest
from pydantic import BaseModel

from kiln_ai.datamodel.dataset_filters import (
    AllDatasetFilter,
    DatasetFilterId,
    HighRatingDatasetFilter,
    StaticDatasetFilters,
    TagFilter,
    ThinkingModelDatasetFilter,
    ThinkingModelHighRatedFilter,
    dataset_filter_from_id,
)

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
