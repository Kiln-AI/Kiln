from enum import Enum
from typing import Annotated, Protocol

from pydantic import AfterValidator

from kiln_ai.datamodel.task_run import TaskRun


class DatasetFilter(Protocol):
    """A protocol defining the interface for dataset filters.

    This allows both stateless function-based filters and stateful class-based filters
    to be used interchangeably, as long as they implement the __call__ method.
    """

    def __call__(self, task_run: TaskRun) -> bool:
        """Return True if the task run should be included in the dataset."""
        ...


def AllDatasetFilter(_: TaskRun) -> bool:
    return True


def HighRatingDatasetFilter(task_run: TaskRun) -> bool:
    if task_run.output is None:
        return False
    if task_run.repaired_output is not None:
        # Repairs always considered high quality
        return True
    if task_run.output.rating is None:
        return False
    return task_run.output.rating.is_high_quality()


def ThinkingModelDatasetFilter(task_run: TaskRun) -> bool:
    """
    A filter that returns True if the task has intermediate outputs we can training a 'thinking' model on (reasoning or chain of thought)
    """
    return task_run.has_thinking_training_data()


def ThinkingModelHighRatedFilter(task_run: TaskRun) -> bool:
    """
    A filter that returns True if the task has thinking data and the output is high quality
    """
    return ThinkingModelDatasetFilter(task_run) and HighRatingDatasetFilter(task_run)


class TagFilter:
    """
    A filter that returns True if the task has a tag matching the given tag.
    """

    def __init__(self, tag: str):
        self.tag = tag

    def __call__(self, task_run: TaskRun) -> bool:
        return self.tag in task_run.tags


class StaticDatasetFilters(str, Enum):
    """Dataset filter names."""

    ALL = "all"
    HIGH_RATING = "high_rating"
    THINKING_MODEL = "thinking_model"
    THINKING_MODEL_HIGH_RATED = "thinking_model_high_rated"


static_dataset_filters = {
    StaticDatasetFilters.ALL: AllDatasetFilter,
    StaticDatasetFilters.HIGH_RATING: HighRatingDatasetFilter,
    StaticDatasetFilters.THINKING_MODEL: ThinkingModelDatasetFilter,
    StaticDatasetFilters.THINKING_MODEL_HIGH_RATED: ThinkingModelHighRatedFilter,
}

DatasetFilterId = Annotated[
    str,
    AfterValidator(lambda v: _check_dataset_filter_id(v)),
]
"""
A pydantic type that validates strings containing a valid dataset filter ID.

Dataset filter IDs can be one of:
- A built-in dataset filter name
- A tag::<tag> filter, where <tag> is a string
"""


def _check_dataset_filter_id(id: str) -> str:
    """
    Check that the dataset filter ID is valid.
    """
    if id in static_dataset_filters:
        return id

    if id.startswith("tag::") and len(id) > 5:
        return id

    raise ValueError(f"Invalid dataset filter ID: {id}")


def dataset_filter_from_id(id: DatasetFilterId) -> DatasetFilter:
    """
    Get a dataset filter from an ID.
    """
    if id.startswith("tag::") and len(id) > 5:
        return TagFilter(id[5:])

    if id in static_dataset_filters:
        return static_dataset_filters[id]

    raise ValueError(f"Invalid dataset filter ID: {id}")
