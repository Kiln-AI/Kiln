"""
Tools for splitting datasets into train/test/validation splits. Includes filters for selecting which task runs to include in each split.
"""

import math
import random
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilter,
    DatasetFilterId,
    dataset_filter_from_id,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class DatasetSplitDefinition(BaseModel):
    """
    A definition of a split in a dataset.

    Example: name="train", description="The training set", percentage=0.8 (80% of the dataset)
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the dataset for you and your team. Not used in training.",
    )
    percentage: float = Field(
        ge=0.0,
        le=1.0,
        description="The percentage of the dataset that this split represents (between 0 and 1).",
    )


AllSplitDefinition: list[DatasetSplitDefinition] = [
    DatasetSplitDefinition(name="all", percentage=1.0)
]
Train80Test20SplitDefinition: list[DatasetSplitDefinition] = [
    DatasetSplitDefinition(name="train", percentage=0.8),
    DatasetSplitDefinition(name="test", percentage=0.2),
]
Train60Test20Val20SplitDefinition: list[DatasetSplitDefinition] = [
    DatasetSplitDefinition(name="train", percentage=0.6),
    DatasetSplitDefinition(name="test", percentage=0.2),
    DatasetSplitDefinition(name="val", percentage=0.2),
]
Train80Test10Val10SplitDefinition: list[DatasetSplitDefinition] = [
    DatasetSplitDefinition(name="train", percentage=0.8),
    DatasetSplitDefinition(name="test", percentage=0.1),
    DatasetSplitDefinition(name="val", percentage=0.1),
]


class DatasetSplit(KilnParentedModel):
    """
    A collection of task runs, with optional splits (train, test, validation).

    Used to freeze a dataset into train/test/validation splits for repeatable fine-tuning or other tasks.

    Maintains a list of IDs for each split, to avoid data duplication.
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the dataset for you and your team. Not used in training.",
    )
    splits: list[DatasetSplitDefinition] = Field(
        default_factory=list,
        description="The splits in the dataset.",
    )
    split_contents: dict[str, list[str]] = Field(
        description="The contents of each split in the dataset. The key is the split name, and the value is a list of task run IDs.",
    )
    filter: DatasetFilterId | None = Field(
        default=None,
        description="The filter used to build the dataset.",
    )

    @model_validator(mode="after")
    def validate_split_percentages(self) -> "DatasetSplit":
        total = sum(split.percentage for split in self.splits)
        if not math.isclose(total, 1.0, rel_tol=1e-9):
            raise ValueError(f"The sum of split percentages must be 1.0 (got {total})")
        return self

    @classmethod
    def from_task(
        cls,
        name: str,
        task: "Task",
        splits: list[DatasetSplitDefinition],
        filter_id: DatasetFilterId = "all",
        description: str | None = None,
    ):
        """
        Build a dataset split from a task.
        """
        filter = dataset_filter_from_id(filter_id)
        split_contents = cls.build_split_contents(task, splits, filter)
        return cls(
            parent=task,
            name=name,
            description=description,
            splits=splits,
            split_contents=split_contents,
            filter=filter_id,
        )

    @classmethod
    def build_split_contents(
        cls,
        task: "Task",
        splits: list[DatasetSplitDefinition],
        filter: DatasetFilter,
    ) -> dict[str, list[str]]:
        valid_ids = []
        for task_run in task.runs():
            if filter(task_run):
                valid_ids.append(task_run.id)

        # Shuffle and split by split percentage
        random.shuffle(valid_ids)
        split_contents = {}
        start_idx = 0
        remaining_items = len(valid_ids)

        # Handle all splits except the last one
        for split in splits[:-1]:
            split_size = round(len(valid_ids) * split.percentage)
            split_contents[split.name] = valid_ids[start_idx : start_idx + split_size]
            start_idx += split_size
            remaining_items -= split_size

        # Last split gets all remaining items (for rounding)
        if splits:
            split_contents[splits[-1].name] = valid_ids[start_idx:]

        return split_contents

    def parent_task(self) -> "Task | None":
        # inline import to avoid circular import
        from kiln_ai.datamodel import Task

        if not isinstance(self.parent, Task):
            return None
        return self.parent

    def missing_count(self) -> int:
        """
        Returns:
            int: the number of task runs that have an ID persisted in this dataset split, but no longer exist in the dataset
        """
        parent = self.parent_task()
        if parent is None:
            raise ValueError("DatasetSplit has no parent task")

        runs = parent.runs(readonly=True)
        all_ids = set(run.id for run in runs)
        all_ids_in_splits = set()
        for ids in self.split_contents.values():
            all_ids_in_splits.update(ids)
        missing = all_ids_in_splits - all_ids
        return len(missing)
