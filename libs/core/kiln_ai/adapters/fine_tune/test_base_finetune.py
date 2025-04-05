from unittest.mock import Mock

import pytest

from kiln_ai.adapters.fine_tune.base_finetune import (
    BaseFinetuneAdapter,
    FinetuneDataStrategy,
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.datamodel import DatasetSplit, Task
from kiln_ai.datamodel import Finetune as FinetuneModel


class MockFinetune(BaseFinetuneAdapter):
    """Mock implementation of BaseFinetune for testing"""

    async def _start(self, dataset: DatasetSplit) -> None:
        pass

    async def status(self) -> FineTuneStatus:
        return FineTuneStatus(status=FineTuneStatusType.pending, message="loading...")

    @classmethod
    def available_parameters(cls) -> list[FineTuneParameter]:
        return [
            FineTuneParameter(
                name="learning_rate",
                type="float",
                description="Learning rate for training",
            ),
            FineTuneParameter(
                name="epochs",
                type="int",
                description="Number of training epochs",
                optional=False,
            ),
        ]


@pytest.fixture
def sample_task(tmp_path):
    task_path = tmp_path / "task.kiln"
    task = Task(
        name="Test Task",
        path=task_path,
        description="Test task for fine-tuning",
        instruction="Test instruction",
    )
    task.save_to_file()
    return task


@pytest.fixture
def basic_finetune(sample_task):
    return MockFinetune(
        datamodel=FinetuneModel(
            parent=sample_task,
            name="test_finetune",
            provider="test_provider",
            provider_id="model_1234",
            base_model_id="test_model",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
        ),
    )


async def test_finetune_status(basic_finetune):
    status = await basic_finetune.status()
    assert status.status == FineTuneStatusType.pending
    assert status.message == "loading..."
    assert isinstance(status, FineTuneStatus)


def test_available_parameters():
    params = MockFinetune.available_parameters()
    assert len(params) == 2

    learning_rate_param = params[0]
    assert learning_rate_param.name == "learning_rate"
    assert learning_rate_param.type == "float"
    assert learning_rate_param.optional is True

    epochs_param = params[1]
    assert epochs_param.name == "epochs"
    assert epochs_param.type == "int"
    assert epochs_param.optional is False


def test_validate_parameters_valid():
    # Test valid parameters
    valid_params = {
        "learning_rate": 0.001,
        "epochs": 10,
    }
    MockFinetune.validate_parameters(valid_params)  # Should not raise


def test_validate_parameters_missing_required():
    # Test missing required parameter
    invalid_params = {
        "learning_rate": 0.001,
        # missing required 'epochs'
    }
    with pytest.raises(ValueError, match="Parameter epochs is required"):
        MockFinetune.validate_parameters(invalid_params)


def test_validate_parameters_wrong_type():
    # Test wrong parameter types
    invalid_params = {
        "learning_rate": "0.001",  # string instead of float
        "epochs": 10,
    }
    with pytest.raises(ValueError, match="Parameter learning_rate must be a float"):
        MockFinetune.validate_parameters(invalid_params)

    invalid_params = {
        "learning_rate": 0.001,
        "epochs": 10.5,  # float instead of int
    }
    with pytest.raises(ValueError, match="Parameter epochs must be an integer"):
        MockFinetune.validate_parameters(invalid_params)


def test_validate_parameters_unknown_parameter():
    # Test unknown parameter
    invalid_params = {
        "learning_rate": 0.001,
        "epochs": 10,
        "unknown_param": "value",
    }
    with pytest.raises(ValueError, match="Parameter unknown_param is not available"):
        MockFinetune.validate_parameters(invalid_params)


@pytest.fixture
def mock_dataset(sample_task):
    dataset = Mock(spec=DatasetSplit)
    dataset.id = "dataset_123"
    dataset.parent_task.return_value = sample_task
    dataset.split_contents = {"train": [], "validation": [], "test": []}
    return dataset


async def test_create_and_start_success(mock_dataset):
    # Test successful creation with minimal parameters
    adapter, datamodel = await MockFinetune.create_and_start(
        dataset=mock_dataset,
        provider_id="openai",
        provider_base_model_id="gpt-4o-mini-2024-07-18",
        train_split_name="train",
        parameters={"epochs": 10},  # Required parameter
        system_message="Test system message",
        data_strategy=FinetuneDataStrategy.final_only,
        thinking_instructions=None,
    )

    assert isinstance(adapter, MockFinetune)
    assert isinstance(datamodel, FinetuneModel)
    assert len(datamodel.name.split()) == 2  # 2 word memorable name
    assert datamodel.provider == "openai"
    assert datamodel.base_model_id == "gpt-4o-mini-2024-07-18"
    assert datamodel.dataset_split_id == mock_dataset.id
    assert datamodel.train_split_name == "train"
    assert datamodel.parameters == {"epochs": 10}
    assert datamodel.system_message == "Test system message"
    assert datamodel.path.exists()
    assert datamodel.data_strategy == FinetuneDataStrategy.final_only
    assert datamodel.thinking_instructions is None


async def test_create_and_start_with_all_params(mock_dataset):
    # Test creation with all optional parameters
    adapter, datamodel = await MockFinetune.create_and_start(
        dataset=mock_dataset,
        provider_id="openai",
        provider_base_model_id="gpt-4o-mini-2024-07-18",
        train_split_name="train",
        parameters={"epochs": 10, "learning_rate": 0.001},
        name="Custom Name",
        description="Custom Description",
        validation_split_name="test",
        system_message="Test system message",
        data_strategy=FinetuneDataStrategy.final_and_intermediate,
        thinking_instructions="Custom thinking instructions",
    )

    assert datamodel.name == "Custom Name"
    assert datamodel.description == "Custom Description"
    assert datamodel.validation_split_name == "test"
    assert datamodel.parameters == {"epochs": 10, "learning_rate": 0.001}
    assert datamodel.system_message == "Test system message"
    assert adapter.datamodel == datamodel
    assert datamodel.data_strategy == FinetuneDataStrategy.final_and_intermediate
    assert datamodel.thinking_instructions == "Custom thinking instructions"

    # load the datamodel from the file, confirm it's saved
    loaded_datamodel = FinetuneModel.load_from_file(datamodel.path)
    assert loaded_datamodel.model_dump_json() == datamodel.model_dump_json()


async def test_create_and_start_invalid_parameters(mock_dataset):
    # Test with invalid parameters
    with pytest.raises(ValueError, match="Parameter epochs is required"):
        await MockFinetune.create_and_start(
            dataset=mock_dataset,
            provider_id="openai",
            provider_base_model_id="gpt-4o-mini-2024-07-18",
            train_split_name="train",
            parameters={"learning_rate": 0.001},  # Missing required 'epochs'
            system_message="Test system message",
            thinking_instructions=None,
            data_strategy=FinetuneDataStrategy.final_only,
        )


async def test_create_and_start_no_parent_task():
    # Test with dataset that has no parent task
    dataset = Mock(spec=DatasetSplit)
    dataset.id = "dataset_123"
    dataset.parent_task.return_value = None
    dataset.split_contents = {"train": [], "validation": [], "test": []}

    with pytest.raises(ValueError, match="Dataset must have a parent task with a path"):
        await MockFinetune.create_and_start(
            dataset=dataset,
            provider_id="openai",
            provider_base_model_id="gpt-4o-mini-2024-07-18",
            train_split_name="train",
            parameters={"epochs": 10},
            system_message="Test system message",
            data_strategy=FinetuneDataStrategy.final_only,
            thinking_instructions=None,
        )


async def test_create_and_start_no_parent_task_path():
    # Test with dataset that has parent task but no path
    task = Mock(spec=Task)
    task.path = None

    dataset = Mock(spec=DatasetSplit)
    dataset.id = "dataset_123"
    dataset.parent_task.return_value = task
    dataset.split_contents = {"train": [], "validation": [], "test": []}

    with pytest.raises(ValueError, match="Dataset must have a parent task with a path"):
        await MockFinetune.create_and_start(
            dataset=dataset,
            provider_id="openai",
            provider_base_model_id="gpt-4o-mini-2024-07-18",
            train_split_name="train",
            parameters={"epochs": 10},
            system_message="Test system message",
            data_strategy=FinetuneDataStrategy.final_only,
            thinking_instructions=None,
        )


async def test_create_and_start_invalid_train_split(mock_dataset):
    # Test with an invalid train split name
    mock_dataset.split_contents = {"valid_train": [], "valid_test": []}

    with pytest.raises(
        ValueError, match="Train split invalid_train not found in dataset"
    ):
        await MockFinetune.create_and_start(
            dataset=mock_dataset,
            provider_id="openai",
            provider_base_model_id="gpt-4o-mini-2024-07-18",
            train_split_name="invalid_train",  # Invalid train split
            parameters={"epochs": 10},
            system_message="Test system message",
            data_strategy=FinetuneDataStrategy.final_only,
            thinking_instructions=None,
        )


async def test_create_and_start_invalid_validation_split(mock_dataset):
    # Test with an invalid validation split name
    mock_dataset.split_contents = {"valid_train": [], "valid_test": []}

    with pytest.raises(
        ValueError, match="Validation split invalid_test not found in dataset"
    ):
        await MockFinetune.create_and_start(
            dataset=mock_dataset,
            provider_id="openai",
            provider_base_model_id="gpt-4o-mini-2024-07-18",
            train_split_name="valid_train",
            validation_split_name="invalid_test",  # Invalid validation split
            parameters={"epochs": 10},
            system_message="Test system message",
            data_strategy=FinetuneDataStrategy.final_only,
            thinking_instructions=None,
        )
