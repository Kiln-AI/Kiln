import pytest
from pydantic import ValidationError

# import datamodel first or we get circular import errors
from kiln_ai.datamodel import (
    AllDatasetFilter,
    AllSplitDefinition,
    DatasetSplit,
    DatasetSplitDefinition,
    DataSource,
    DataSourceType,
    HighRatingDatasetFilter,
    Task,
    TaskOutput,
    TaskOutputRating,
    TaskOutputRatingType,
    TaskRun,
    Train60Test20Val20SplitDefinition,
    Train80Test20SplitDefinition,
)


@pytest.fixture
def sample_task(tmp_path):
    task_path = tmp_path / "task.kiln"
    task = Task(
        name="Test Task",
        path=task_path,
        description="Test task for dataset splitting",
        instruction="Test instruction",
    )
    task.save_to_file()
    return task


@pytest.fixture
def sample_task_runs(sample_task):
    # Create 10 task runs with different ratings
    task_runs = []
    for i in range(10):
        rating = 5 if i < 6 else 1  # 6 high, 4 low ratings
        task_run = TaskRun(
            parent=sample_task,
            input=f"input_{i}",
            input_source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "test-user"},
            ),
            output=TaskOutput(
                output=f"output_{i}",
                source=DataSource(
                    type=DataSourceType.human,
                    properties={"created_by": "test-user"},
                ),
                rating=TaskOutputRating(
                    value=rating, type=TaskOutputRatingType.five_star
                ),
            ),
        )
        task_run.save_to_file()
        task_runs.append(task_run)
    return task_runs


@pytest.fixture
def standard_splitstandard_splitss():
    return [
        DatasetSplitDefinition(name="train", percentage=0.8),
        DatasetSplitDefinition(name="test", percentage=0.2),
    ]


@pytest.fixture
def task_run():
    return TaskRun(
        input="test input",
        input_source=DataSource(
            type=DataSourceType.human,
            properties={"created_by": "test-user"},
        ),
        output=TaskOutput(
            output="test output",
            source=DataSource(
                type=DataSourceType.human,
                properties={"created_by": "test-user"},
            ),
            rating=TaskOutputRating(rating=5, type=TaskOutputRatingType.five_star),
        ),
    )


def test_dataset_split_definition():
    split = DatasetSplitDefinition(name="train", percentage=0.8)
    assert split.name == "train"
    assert split.percentage == 0.8
    assert split.description is None

    # Test validation
    with pytest.raises(ValidationError):
        DatasetSplitDefinition(name="train", percentage=1.5)


def test_dataset_split_validation():
    # Test valid percentages
    splits = [
        DatasetSplitDefinition(name="train", percentage=0.8),
        DatasetSplitDefinition(name="test", percentage=0.2),
    ]
    dataset = DatasetSplit(
        name="test_split",
        splits=splits,
        split_contents={"train": [], "test": []},
    )
    assert dataset.splits == splits

    # Test invalid percentages
    invalid_splits = [
        DatasetSplitDefinition(name="train", percentage=0.8),
        DatasetSplitDefinition(name="test", percentage=0.3),
    ]
    with pytest.raises(ValueError, match="sum of split percentages must be 1.0"):
        DatasetSplit(
            name="test_split",
            splits=invalid_splits,
            split_contents={"train": [], "test": []},
        )


def test_all_dataset_filter(task_run):
    assert AllDatasetFilter(task_run) is True


def test_high_rating_dataset_filter(sample_task_runs):
    for task_run in sample_task_runs:
        assert HighRatingDatasetFilter(task_run) is (
            task_run.output.rating.is_high_quality()
        )


@pytest.mark.parametrize(
    "splits,expected_sizes",
    [
        (Train80Test20SplitDefinition, {"train": 8, "test": 2}),
        (AllSplitDefinition, {"all": 10}),
        (Train60Test20Val20SplitDefinition, {"train": 6, "test": 2, "val": 2}),
        (
            [
                DatasetSplitDefinition(name="train", percentage=0.7),
                DatasetSplitDefinition(name="validation", percentage=0.2),
                DatasetSplitDefinition(name="test", percentage=0.1),
            ],
            {"train": 7, "validation": 2, "test": 1},
        ),
    ],
)
def test_dataset_split_from_task(sample_task, sample_task_runs, splits, expected_sizes):
    assert sample_task_runs is not None
    dataset = DatasetSplit.from_task("Split Name", sample_task, splits)
    assert dataset.name == "Split Name"

    # Check split sizes match expected
    for split_name, expected_size in expected_sizes.items():
        assert len(dataset.split_contents[split_name]) == expected_size

    # Verify total size matches input size
    total_size = sum(len(ids) for ids in dataset.split_contents.values())
    assert total_size == len(sample_task_runs)


def test_dataset_split_with_high_rating_filter(sample_task, sample_task_runs):
    assert len(sample_task_runs) == 10
    dataset = DatasetSplit.from_task(
        "Split Name",
        sample_task,
        Train80Test20SplitDefinition,
        filter=HighRatingDatasetFilter,
    )

    # Check that only high-rated task runs are included
    all_ids = []
    for ids in dataset.split_contents.values():
        all_ids.extend(ids)
    assert len(all_ids) == 6  # We created 6 high-rated task runs

    # Check split proportions
    train_size = len(dataset.split_contents["train"])
    test_size = len(dataset.split_contents["test"])
    assert train_size == 5  # ~80% of 6
    assert test_size == 1  # ~20% of 6


def test_dataset_split_with_single_split(sample_task, sample_task_runs):
    splits = [DatasetSplitDefinition(name="all", percentage=1.0)]
    dataset = DatasetSplit.from_task("Split Name", sample_task, splits)

    assert len(dataset.split_contents["all"]) == len(sample_task_runs)


def test_missing_count(sample_task, sample_task_runs):
    assert sample_task_runs is not None
    # Create a dataset split with all task runs
    dataset = DatasetSplit.from_task(
        "Split Name", sample_task, Train80Test20SplitDefinition
    )

    # Initially there should be no missing runs
    assert dataset.missing_count() == 0

    # Add some IDs to the split, that aren't on disk
    dataset.split_contents["test"].append("1")
    dataset.split_contents["test"].append("2")
    dataset.split_contents["test"].append("3")
    # shouldn't happen, but should not double count if it does
    dataset.split_contents["train"].append("3")

    # Now we should have 3 missing runs
    assert dataset.missing_count() == 3


def test_smaller_sample(sample_task, sample_task_runs):
    assert sample_task_runs is not None
    # Create a dataset split with all task runs
    dataset = DatasetSplit.from_task(
        "Split Name", sample_task, Train80Test20SplitDefinition
    )

    # Initially there should be no missing runs
    assert dataset.missing_count() == 0

    dataset.split_contents["test"].pop()
    dataset.split_contents["train"].pop()

    # Now we should have 0 missing runs. It's okay that dataset has newer data.
    assert dataset.missing_count() == 0
