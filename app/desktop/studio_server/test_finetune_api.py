import unittest.mock
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.adapters.fine_tune.base_finetune import FineTuneParameter
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat
from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.datamodel import (
    DatasetSplit,
    Finetune,
    FinetuneDataStrategy,
    Project,
    Task,
)
from kiln_ai.datamodel.dataset_filters import DatasetFilterId
from kiln_ai.datamodel.dataset_split import (
    AllSplitDefinition,
    Train60Test20Val20SplitDefinition,
    Train80Test10Val10SplitDefinition,
    Train80Test20SplitDefinition,
)
from pydantic import BaseModel

from app.desktop.studio_server.finetune_api import (
    CreateDatasetSplitRequest,
    CreateFinetuneRequest,
    DatasetSplitType,
    connect_fine_tune_api,
    thinking_instructions_from_request,
)


@pytest.fixture
def test_task(tmp_path):
    project_path = tmp_path / "project.kiln"

    project = Project(name="Test Project", path=str(project_path))
    project.save_to_file()

    task = Task(
        name="Test Task",
        instruction="This is a test instruction",
        description="This is a test task",
        parent=project,
    )
    task.save_to_file()

    tunes = [
        Finetune(
            id="ft1",
            name="Finetune 1",
            provider="openai",
            base_model_id="model1",
            dataset_split_id="split1",
            system_message="System prompt 1",
        ),
        Finetune(
            id="ft2",
            name="Finetune 2",
            provider="openai",
            base_model_id="model2",
            dataset_split_id="split2",
            system_message="System prompt 2",
        ),
    ]
    for tune in tunes:
        tune.parent = task
        tune.save_to_file()

    splits = [
        DatasetSplit(
            id="split1",
            name="Split 1",
            split_contents={"train": ["1", "2"]},
            splits=AllSplitDefinition,
        ),
        DatasetSplit(
            id="split2",
            name="Split 2",
            split_contents={"test": ["3"]},
            splits=AllSplitDefinition,
        ),
    ]
    for split in splits:
        split.parent = task
        split.save_to_file()

    return task


@pytest.fixture
def mock_task_from_id_disk_backed(test_task, monkeypatch):
    mock_func = Mock(return_value=test_task)
    monkeypatch.setattr(
        "app.desktop.studio_server.finetune_api.task_from_id", mock_func
    )
    return mock_func


@pytest.fixture
def client():
    app = FastAPI()
    connect_fine_tune_api(app)
    return TestClient(app)


def test_get_dataset_splits(client, mock_task_from_id_disk_backed, test_task):
    response = client.get("/api/projects/project1/tasks/task1/dataset_splits")

    assert response.status_code == 200
    splits = response.json()
    assert len(splits) == 2

    assert splits[0]["id"] in ["split1", "split2"]
    assert splits[1]["id"] in ["split1", "split2"]
    assert splits[0]["id"] != splits[1]["id"]

    mock_task_from_id_disk_backed.assert_called_once_with("project1", "task1")


def test_get_finetunes(client, mock_task_from_id_disk_backed, test_task):
    response = client.get("/api/projects/project1/tasks/task1/finetunes")

    assert response.status_code == 200
    finetunes = response.json()
    assert len(finetunes) == 2
    assert finetunes[0]["id"] in ["ft1", "ft2"]
    assert finetunes[1]["id"] in ["ft1", "ft2"]
    assert finetunes[0]["id"] != finetunes[1]["id"]

    mock_task_from_id_disk_backed.assert_called_once_with("project1", "task1")


@pytest.fixture
def mock_built_in_models():
    models = [
        KilnModel(
            name="model1",
            family="family1",
            friendly_name="Model 1",
            providers=[
                KilnModelProvider(name="groq", provider_finetune_id="ft_model1"),
                KilnModelProvider(name="openai", provider_finetune_id="ft_model1_p2"),
            ],
        ),
        KilnModel(
            name="model2",
            family="family2",
            friendly_name="Model 2",
            providers=[
                KilnModelProvider(name="groq", provider_finetune_id="ft_model2"),
                KilnModelProvider(
                    name="openai",
                    provider_finetune_id=None,  # This one should be skipped
                ),
            ],
        ),
    ]
    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.built_in_models", models
    ):
        yield models


@pytest.fixture
def mock_provider_enabled():
    async def mock_enabled(provider: str) -> bool:
        return provider == "groq"

    mock = Mock()
    mock.side_effect = mock_enabled

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.provider_enabled", mock
    ):
        yield mock


@pytest.fixture
def mock_provider_name_from_id():
    def mock_name(provider_id: str) -> str:
        return f"Provider {provider_id.replace('provider', '')}"

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.provider_name_from_id", mock_name
    ):
        yield mock_name


async def test_get_finetune_providers(
    client, mock_built_in_models, mock_provider_name_from_id, mock_provider_enabled
):
    response = client.get("/api/finetune_providers")

    assert response.status_code == 200
    providers = response.json()
    assert len(providers) == 2

    # Check provider1
    provider1 = next(p for p in providers if p["id"] == "groq")
    assert provider1["name"] == "Provider groq"
    assert provider1["enabled"] is True
    assert len(provider1["models"]) == 2
    assert provider1["models"][0]["name"] == "Model 1"
    assert provider1["models"][0]["id"] == "ft_model1"
    assert provider1["models"][1]["name"] == "Model 2"
    assert provider1["models"][1]["id"] == "ft_model2"

    # Check provider2
    provider2 = next(p for p in providers if p["id"] == "openai")
    assert provider2["name"] == "Provider openai"
    assert provider2["enabled"] is False
    assert len(provider2["models"]) == 1
    assert provider2["models"][0]["name"] == "Model 1"
    assert provider2["models"][0]["id"] == "ft_model1_p2"


@pytest.fixture
def mock_finetune_registry():
    mock_adapter = Mock()
    mock_adapter.available_parameters.return_value = [
        FineTuneParameter(
            name="learning_rate",
            type="float",
            description="Learning rate for training",
            optional=True,
        ),
        FineTuneParameter(
            name="epochs",
            type="int",
            description="Number of training epochs",
            optional=False,
        ),
    ]

    mock_registry = {"test_provider": mock_adapter}

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.finetune_registry", mock_registry
    ):
        yield mock_registry


def test_get_finetune_hyperparameters(client, mock_finetune_registry):
    response = client.get("/api/finetune/hyperparameters/test_provider")

    assert response.status_code == 200
    parameters = response.json()
    assert len(parameters) == 2

    assert parameters[0]["name"] == "learning_rate"
    assert parameters[0]["type"] == "float"
    assert parameters[0]["description"] == "Learning rate for training"
    assert parameters[0]["optional"] is True

    assert parameters[1]["name"] == "epochs"
    assert parameters[1]["type"] == "int"
    assert parameters[1]["description"] == "Number of training epochs"
    assert parameters[1]["optional"] is False


def test_get_finetune_hyperparameters_invalid_provider(client, mock_finetune_registry):
    response = client.get("/api/finetune/hyperparameters/invalid_provider")

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Fine tune provider 'invalid_provider' not found"
    )


def test_dataset_split_type_enum():
    assert DatasetSplitType.TRAIN_TEST.value == "train_test"
    assert DatasetSplitType.TRAIN_TEST_VAL.value == "train_test_val"
    assert DatasetSplitType.TRAIN_TEST_VAL_80.value == "train_test_val_80"
    assert DatasetSplitType.ALL.value == "all"


class ModelTester(BaseModel):
    dataset_id: DatasetFilterId


# Check these stings from UI exist
@pytest.mark.parametrize(
    "id,expect_error",
    [
        ("all", False),
        ("high_rating", False),
        ("thinking_model", False),
        ("thinking_model_high_rated", False),
        ("invalid", True),
    ],
)
def test_dataset_filter_ids(id, expect_error):
    if expect_error:
        with pytest.raises(ValueError):
            ModelTester(dataset_id=id)
    else:
        model = ModelTester(dataset_id=id)
        assert model.dataset_id == id


def test_api_split_types_mapping():
    from app.desktop.studio_server.finetune_api import api_split_types

    assert api_split_types[DatasetSplitType.TRAIN_TEST] == Train80Test20SplitDefinition
    assert (
        api_split_types[DatasetSplitType.TRAIN_TEST_VAL]
        == Train60Test20Val20SplitDefinition
    )
    assert (
        api_split_types[DatasetSplitType.TRAIN_TEST_VAL_80]
        == Train80Test10Val10SplitDefinition
    )
    assert api_split_types[DatasetSplitType.ALL] == AllSplitDefinition
    for split_type in DatasetSplitType:
        assert split_type in api_split_types


@pytest.fixture
def mock_dataset_split():
    split = DatasetSplit(
        id="new_split",
        name="Test Split",
        split_contents={"train": ["1", "2"], "test": ["3"]},
        splits=AllSplitDefinition,
    )
    return split


def test_create_dataset_split(
    client, mock_task_from_id_disk_backed, mock_dataset_split
):
    # Mock DatasetSplit.from_task and save_to_file
    mock_from_task = unittest.mock.patch.object(
        DatasetSplit, "from_task", return_value=mock_dataset_split
    )
    mock_save = unittest.mock.patch.object(DatasetSplit, "save_to_file")

    with mock_from_task as from_task_mock, mock_save as save_mock:
        request_data = {
            "dataset_split_type": "train_test",
            "filter_id": "high_rating",
            "name": "Test Split",
            "description": "Test description",
        }

        response = client.post(
            "/api/projects/project1/tasks/task1/dataset_splits", json=request_data
        )

        assert response.status_code == 200
        result = response.json()
        assert result["id"] == "new_split"
        assert result["name"] == "Test Split"

        # Verify the mocks were called correctly
        mock_task_from_id_disk_backed.assert_called_once_with("project1", "task1")
        from_task_mock.assert_called_once()
        args, kwargs = from_task_mock.call_args
        assert kwargs["filter_id"] == "high_rating"
        save_mock.assert_called_once()


def test_create_dataset_split_auto_name(
    client, mock_task_from_id_disk_backed, mock_dataset_split
):
    # Mock DatasetSplit.from_task and save_to_file
    mock_from_task = unittest.mock.patch.object(
        DatasetSplit, "from_task", return_value=mock_dataset_split
    )
    mock_save = unittest.mock.patch.object(DatasetSplit, "save_to_file")

    with mock_from_task as from_task_mock, mock_save as save_mock:
        request_data = {"dataset_split_type": "train_test", "filter_id": "all"}

        response = client.post(
            "/api/projects/project1/tasks/task1/dataset_splits", json=request_data
        )

        assert response.status_code == 200

        # Verify auto-generated name format
        from_task_mock.assert_called_once()
        args = from_task_mock.call_args[0]
        name = args[0]
        assert len(name.split()) == 2  # 2 word memorable name
        assert len(name) > 5  # Not too short
        save_mock.assert_called_once()


def test_create_dataset_split_request_validation():
    # Test valid request
    request = CreateDatasetSplitRequest(
        dataset_split_type=DatasetSplitType.TRAIN_TEST,
        filter_id="all",
        name="Test Split",
        description="Test description",
    )
    assert request.dataset_split_type == DatasetSplitType.TRAIN_TEST
    assert request.filter_id == "all"
    assert request.name == "Test Split"
    assert request.description == "Test description"

    # Test optional fields
    request = CreateDatasetSplitRequest(
        dataset_split_type=DatasetSplitType.TRAIN_TEST,
        filter_id="all",
    )
    assert request.name is None
    assert request.description is None

    # Test invalid dataset split type
    with pytest.raises(ValueError):
        CreateDatasetSplitRequest(dataset_split_type="invalid_type", filter_id="all")

    # Test invalid filter type
    with pytest.raises(ValueError):
        CreateDatasetSplitRequest(
            dataset_split_type=DatasetSplitType.TRAIN_TEST, filter_id="invalid_type"
        )


@pytest.fixture
def mock_finetune_adapter():
    adapter = Mock()
    adapter.create_and_start = AsyncMock(
        return_value=(
            None,  # First return value is ignored in the API
            Finetune(
                id="new_ft",
                name="New Finetune",
                provider="test_provider",
                base_model_id="base_model_1",
                dataset_split_id="split1",
                system_message="Test system message",
                thinking_instructions=None,
            ),
        )
    )
    return adapter


@pytest.mark.parametrize(
    "data_strategy,custom_thinking_instructions,expected_thinking_instructions",
    [
        (FinetuneDataStrategy.final_only, None, None),
        (
            FinetuneDataStrategy.final_and_intermediate,
            None,
            "Think step by step, explaining your reasoning.",
        ),  # Our default
        (FinetuneDataStrategy.final_and_intermediate, "CTI", "CTI"),
    ],
)
async def test_create_finetune(
    client,
    mock_task_from_id_disk_backed,
    test_task,
    mock_finetune_registry,
    mock_finetune_adapter,
    data_strategy,
    custom_thinking_instructions,
    expected_thinking_instructions,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "name": "New Finetune",
        "description": "Test description",
        "dataset_id": "split1",
        "train_split_name": "train",
        "validation_split_name": "validation",
        "parameters": {"learning_rate": 0.001, "epochs": 10},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
        "custom_thinking_instructions": custom_thinking_instructions,
        "data_strategy": data_strategy.value,
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "new_ft"
    assert result["name"] == "New Finetune"
    assert result["provider"] == "test_provider"
    assert result["base_model_id"] == "base_model_1"

    split1 = next(split for split in test_task.dataset_splits() if split.id == "split1")

    # Verify the adapter was called correctly
    mock_finetune_adapter.create_and_start.assert_awaited_once_with(
        dataset=split1,
        provider_id="test_provider",
        provider_base_model_id="base_model_1",
        train_split_name="train",
        system_message="Test system message",
        thinking_instructions=expected_thinking_instructions,
        parameters={"learning_rate": 0.001, "epochs": 10},
        name="New Finetune",
        description="Test description",
        validation_split_name="validation",
        data_strategy=data_strategy,
    )


def test_create_finetune_invalid_provider(client, mock_task_from_id_disk_backed):
    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "invalid_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
        "data_strategy": "final_only",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Fine tune provider 'invalid_provider' not found"
    )


def test_create_finetune_invalid_dataset(
    client,
    mock_task_from_id_disk_backed,
    mock_finetune_registry,
    mock_finetune_adapter,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "dataset_id": "invalid_split_id",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
        "data_strategy": "final_only",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "Dataset split with ID 'invalid_split_id' not found"
    )


def test_create_finetune_request_validation():
    # Test valid request with all fields
    request = CreateFinetuneRequest(
        name="Test Finetune",
        description="Test description",
        dataset_id="split1",
        train_split_name="train",
        validation_split_name="validation",
        parameters={"param1": "value1"},
        provider="test_provider",
        base_model_id="base_model_1",
        custom_system_message="Test system message",
        data_strategy=FinetuneDataStrategy.final_only,
    )
    assert request.name == "Test Finetune"
    assert request.description == "Test description"
    assert request.dataset_id == "split1"
    assert request.validation_split_name == "validation"

    # Test valid request with only required fields
    request = CreateFinetuneRequest(
        dataset_id="split1",
        train_split_name="train",
        parameters={},
        provider="test_provider",
        base_model_id="base_model_1",
        custom_system_message="Test system message",
        data_strategy=FinetuneDataStrategy.final_only,
    )
    assert request.name is None
    assert request.description is None
    assert request.validation_split_name is None

    # Test invalid request (missing required field)
    with pytest.raises(ValueError):
        CreateFinetuneRequest(
            dataset_id="split1",  # Missing other required fields
        )


def test_create_finetune_no_system_message(
    client,
    mock_task_from_id_disk_backed,
    mock_finetune_registry,
    mock_finetune_adapter,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "data_strategy": "final_only",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "System message generator or custom system message is required"
    )


def test_create_finetune_no_data_strategy(
    client,
    mock_task_from_id_disk_backed,
    mock_finetune_registry,
    mock_finetune_adapter,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 422


@pytest.fixture
def mock_prompt_builder():
    builder = Mock()
    builder.build_prompt.return_value = "Generated system message"

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.prompt_builder_from_id",
        return_value=builder,
    ) as mock:
        yield mock, builder


async def test_create_finetune_with_prompt_builder(
    client,
    mock_task_from_id_disk_backed,
    mock_finetune_registry,
    mock_finetune_adapter,
    mock_prompt_builder,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter
    prompt_builder_mock, builder = mock_prompt_builder

    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "system_message_generator": "test_prompt_builder",
        "data_strategy": "final_only",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "new_ft"

    # Verify prompt builder was called correctly
    prompt_builder_mock.assert_called_once()
    builder.build_prompt.assert_called_once()

    # Verify the adapter was called with the generated system message
    mock_finetune_adapter.create_and_start.assert_awaited_once()
    call_kwargs = mock_finetune_adapter.create_and_start.await_args[1]
    assert call_kwargs["system_message"] == "Generated system message"


def test_create_finetune_prompt_builder_error(
    client,
    mock_task_from_id_disk_backed,
    mock_finetune_registry,
    mock_finetune_adapter,
    mock_prompt_builder,
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter
    prompt_builder_mock, builder = mock_prompt_builder

    # Make the prompt builder raise an error
    builder.build_prompt.side_effect = ValueError("Invalid prompt configuration")

    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "system_message_generator": "test_prompt_builder",
        "data_strategy": "final_only",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Error generating system message using generator: test_prompt_builder. Source error: Invalid prompt configuration"
    )


@pytest.fixture
def mock_dataset_formatter():
    formatter = Mock()
    formatter.dump_to_file.return_value = Path("path/to/dataset.jsonl")

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.DatasetFormatter",
        return_value=formatter,
    ) as mock_class:
        yield mock_class, formatter


@pytest.mark.parametrize(
    "data_strategy",
    [FinetuneDataStrategy.final_only, FinetuneDataStrategy.final_and_intermediate],
)
def test_download_dataset_jsonl(
    client,
    mock_task_from_id_disk_backed,
    mock_dataset_formatter,
    tmp_path,
    data_strategy,
):
    mock_formatter_class, mock_formatter = mock_dataset_formatter

    # Create a temporary file to simulate the dataset
    test_file = tmp_path / "dataset.jsonl"
    test_file.write_text('{"test": "data"}')
    mock_formatter.dump_to_file.return_value = test_file

    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "train",
            "format_type": "openai_chat_jsonl",
            "custom_system_message": "Test system message",
            "data_strategy": data_strategy.value,
        },
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/jsonl"
    assert (
        response.headers["Content-Disposition"]
        == f'attachment; filename="{test_file.name}"'
    )
    assert response.content == b'{"test": "data"}'

    # Verify the formatter was created and used correctly
    mock_formatter_class.assert_called_once()
    mock_formatter.dump_to_file.assert_called_once_with(
        "train",
        DatasetFormat.OPENAI_CHAT_JSONL,
        data_strategy,
    )


@pytest.fixture
def valid_download_params():
    return {
        "project_id": "project1",
        "task_id": "task1",
        "dataset_id": "split1",
        "split_name": "train",
        "format_type": "openai_chat_jsonl",
        "custom_system_message": "Test system message",
        "data_strategy": "final_only",
    }


def test_download_dataset_jsonl_invalid_format(
    client, mock_task_from_id_disk_backed, valid_download_params
):
    valid_download_params["format_type"] = "invalid_format"
    response = client.get(
        "/api/download_dataset_jsonl",
        params=valid_download_params,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Dataset format 'invalid_format' not found"


def test_download_dataset_jsonl_data_strategy_invalid(
    client, mock_task_from_id_disk_backed, valid_download_params
):
    valid_download_params["data_strategy"] = "invalid_data_strategy"
    response = client.get(
        "/api/download_dataset_jsonl",
        params=valid_download_params,
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Data strategy 'invalid_data_strategy' not found"
    )


def test_download_dataset_jsonl_invalid_dataset(
    client, mock_task_from_id_disk_backed, valid_download_params
):
    valid_download_params["dataset_id"] = "invalid_split"
    response = client.get(
        "/api/download_dataset_jsonl",
        params=valid_download_params,
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Dataset split with ID 'invalid_split' not found"
    )


def test_download_dataset_jsonl_invalid_split(
    client, mock_task_from_id_disk_backed, valid_download_params
):
    valid_download_params["split_name"] = "invalid_split"
    response = client.get(
        "/api/download_dataset_jsonl",
        params=valid_download_params,
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Dataset split with name 'invalid_split' not found"
    )


def test_download_dataset_jsonl_with_prompt_builder(
    client,
    mock_task_from_id_disk_backed,
    test_task,
    mock_dataset_formatter,
    mock_prompt_builder,
    tmp_path,
):
    mock_formatter_class, mock_formatter = mock_dataset_formatter
    prompt_builder_mock, builder = mock_prompt_builder

    # Create a temporary file to simulate the dataset
    test_file = tmp_path / "dataset.jsonl"
    test_file.write_text('{"test": "data"}')
    mock_formatter.dump_to_file.return_value = test_file

    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "train",
            "format_type": "openai_chat_jsonl",
            "system_message_generator": "test_prompt_builder",
            "custom_thinking_instructions": "custom thinking instructions",
            "data_strategy": "final_only",
        },
    )

    assert response.status_code == 200

    # Verify prompt builder was used
    prompt_builder_mock.assert_called_once_with("test_prompt_builder", test_task)
    builder.build_prompt.assert_called_once()

    split1 = next(split for split in test_task.dataset_splits() if split.id == "split1")
    # Verify formatter was created with generated system message
    mock_formatter_class.assert_called_once_with(
        dataset=split1,
        system_message="Generated system message",
        thinking_instructions=None,
    )


async def test_get_finetune(client, mock_task_from_id_disk_backed):
    response = client.get("/api/projects/project1/tasks/task1/finetunes/ft1")

    assert response.status_code == 200
    finetune = response.json()["finetune"]
    assert finetune["id"] == "ft1"
    assert finetune["name"] == "Finetune 1"
    assert finetune["provider"] == "openai"
    assert finetune["base_model_id"] == "model1"
    assert finetune["dataset_split_id"] == "split1"
    assert finetune["system_message"] == "System prompt 1"

    status = response.json()["status"]
    assert status["status"] == "pending"
    assert (
        status["message"]
        == "This fine-tune has not been started or has not been assigned a provider ID."
    )

    mock_task_from_id_disk_backed.assert_called_once_with("project1", "task1")


def test_get_finetune_not_found(client, mock_task_from_id_disk_backed):
    response = client.get("/api/projects/project1/tasks/task1/finetunes/nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Finetune with ID 'nonexistent' not found"

    mock_task_from_id_disk_backed.assert_called_once_with("project1", "task1")


async def test_get_finetunes_with_status_update(
    client,
    mock_task_from_id_disk_backed,
    test_task,
    mock_finetune_registry,
    monkeypatch,
):
    # Create a mock enum class
    class MockModelProviderName:
        def __class_getitem__(cls, key):
            return "test_provider"

    monkeypatch.setattr(
        "app.desktop.studio_server.finetune_api.ModelProviderName",
        MockModelProviderName,
    )

    # Create mock adapter with status method
    mock_adapter = Mock()
    mock_adapter.status = AsyncMock(
        return_value={"status": "running", "message": "Training..."}
    )
    mock_adapter_class = Mock(return_value=mock_adapter)
    mock_finetune_registry["test_provider"] = mock_adapter_class

    # Add latest_status to mock finetunes
    tune1 = next(ft for ft in test_task.finetunes() if ft.id == "ft1")
    tune2 = next(ft for ft in test_task.finetunes() if ft.id == "ft2")
    tune1.latest_status = "pending"  # Should be updated
    tune1.save_to_file()
    tune2.latest_status = "completed"  # Should be skipped
    tune2.save_to_file()

    mock_adapter_class.assert_not_called()
    mock_adapter.status.assert_not_called()

    response = client.get(
        "/api/projects/project1/tasks/task1/finetunes?update_status=true"
    )

    assert response.status_code == 200
    finetunes = response.json()
    assert len(finetunes) == 2

    # Verify that status was only checked for the pending finetune
    mock_adapter_class.assert_called_once_with(tune1)
    mock_adapter.status.assert_called_once()


def test_thinking_instructions_non_cot_strategy():
    """Test that non-COT strategies return None regardless of other parameters"""
    task = Mock(spec=Task)
    result = thinking_instructions_from_request(
        task=task,
        data_strategy=FinetuneDataStrategy.final_only,
        custom_thinking_instructions="custom instructions",
    )
    assert result is None


def test_thinking_instructions_custom():
    """Test that custom instructions are returned when provided"""
    task = Mock(spec=Task)
    custom_instructions = "My custom thinking instructions"
    result = thinking_instructions_from_request(
        task=task,
        data_strategy=FinetuneDataStrategy.final_and_intermediate,
        custom_thinking_instructions=custom_instructions,
    )
    assert result == custom_instructions


@patch("app.desktop.studio_server.finetune_api.chain_of_thought_prompt")
def test_thinking_instructions_default(mock_cot):
    """Test that default chain of thought prompt is used when no custom instructions"""
    task = Mock(spec=Task)
    mock_cot.return_value = "Default COT instructions"

    result = thinking_instructions_from_request(
        task=task,
        data_strategy=FinetuneDataStrategy.final_and_intermediate,
        custom_thinking_instructions=None,
    )

    mock_cot.assert_called_once_with(task)
    assert result == "Default COT instructions"
