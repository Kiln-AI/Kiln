import re
from enum import Enum
from typing import Annotated, ClassVar, List, Protocol

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


class MultiDatasetFilter:
    """
    A filter that combines multiple filters using AND logic.
    The filters are specified in a query string format after 'multi_filter::'
    Example: multi_filter::high_rating&thinking_model&tag::tag_name

    Ampersands in filter IDs can be escaped with a backslash.
    """

    PREFIX: ClassVar[str] = "multi_filter::"
    ESCAPED_AMPERSAND: ClassVar[str] = r"\&"
    UNESCAPED_AMPERSAND: ClassVar[str] = "&"

    @classmethod
    def parse_filter_string(cls, filter_string: str) -> List[str]:
        """
        Parse a filter string into individual filter IDs, handling escaped ampersands.
        """
        if not filter_string.startswith(cls.PREFIX):
            raise ValueError(f"Filter string must start with {cls.PREFIX}")

        # Remove the prefix
        content = filter_string[len(cls.PREFIX) :]
        if not content:
            raise ValueError("No filters specified after prefix")

        # Split on unescaped ampersands
        # This regex matches & that are not preceded by a backslash
        parts = re.split(r"(?<!\\)&", content)

        # Unescape ampersands in each part
        filter_ids = [
            part.replace(cls.ESCAPED_AMPERSAND, cls.UNESCAPED_AMPERSAND)
            for part in parts
        ]

        # Validate each filter ID using the existing validation
        for fid in filter_ids:
            _check_dataset_filter_id(fid)

        return filter_ids

    @classmethod
    def is_valid_filter_string(cls, filter_string: str) -> bool:
        """Check if a filter string is valid."""
        try:
            cls.parse_filter_string(filter_string)
            return True
        except ValueError:
            return False

    def __init__(self, filter_id: str):
        filter_ids = MultiDatasetFilter.parse_filter_string(filter_id)
        self.filters = [dataset_filter_from_id(fid) for fid in filter_ids]

    def __call__(self, task_run: TaskRun) -> bool:
        return all(f(task_run) for f in self.filters)


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

    if id.startswith(MultiDatasetFilter.PREFIX):
        if not MultiDatasetFilter.is_valid_filter_string(id):
            raise ValueError(f"Invalid multi-filter string: {id}")
        return id

    raise ValueError(f"Invalid dataset filter ID: {id}")


def dataset_filter_from_id(id: DatasetFilterId) -> DatasetFilter:
    """
    Get a dataset filter from an ID.
    """
    if id.startswith("tag::") and len(id) > 5:
        return TagFilter(id[5:])

    if id.startswith(MultiDatasetFilter.PREFIX):
        return MultiDatasetFilter(id)

    if id in static_dataset_filters:
        return static_dataset_filters[id]

    raise ValueError(f"Invalid dataset filter ID: {id}")
