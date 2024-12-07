import unittest.mock
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kiln_ai.adapters.fine_tune.base_finetune import FineTuneParameter
from kiln_ai.adapters.ml_model_list import KilnModel, KilnModelProvider
from kiln_ai.datamodel import (
    AllDatasetFilter,
    AllSplitDefinition,
    DatasetSplit,
    Finetune,
    HighRatingDatasetFilter,
    Train60Test20Val20SplitDefinition,
    Train80Test20SplitDefinition,
)

from app.desktop.studio_server.finetune_api import (
    CreateDatasetSplitRequest,
    CreateFinetuneRequest,
    DatasetFilterType,
    DatasetSplitType,
    connect_fine_tune_api,
)


@pytest.fixture
def mock_task():
    task = Mock()
    task.dataset_splits.return_value = [
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
    task.finetunes.return_value = [
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
    return task


@pytest.fixture
def mock_task_from_id(mock_task, monkeypatch):
    mock_func = Mock(return_value=mock_task)
    monkeypatch.setattr(
        "app.desktop.studio_server.finetune_api.task_from_id", mock_func
    )
    return mock_func


@pytest.fixture
def client():
    app = FastAPI()
    connect_fine_tune_api(app)
    return TestClient(app)


def test_get_dataset_splits(client, mock_task_from_id, mock_task):
    response = client.get("/api/projects/project1/tasks/task1/dataset_splits")

    assert response.status_code == 200
    splits = response.json()
    assert len(splits) == 2
    assert splits[0]["id"] == "split1"
    assert splits[1]["id"] == "split2"

    mock_task_from_id.assert_called_once_with("project1", "task1")
    mock_task.dataset_splits.assert_called_once()


def test_get_finetunes(client, mock_task_from_id, mock_task):
    response = client.get("/api/projects/project1/tasks/task1/finetunes")

    assert response.status_code == 200
    finetunes = response.json()
    assert len(finetunes) == 2
    assert finetunes[0]["id"] == "ft1"
    assert finetunes[1]["id"] == "ft2"

    mock_task_from_id.assert_called_once_with("project1", "task1")
    mock_task.finetunes.assert_called_once()


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
    assert DatasetSplitType.ALL.value == "all"


def test_dataset_filter_type_enum():
    assert DatasetFilterType.ALL.value == "all"
    assert DatasetFilterType.HIGH_RATING.value == "high_rating"


def test_api_split_types_mapping():
    from app.desktop.studio_server.finetune_api import api_split_types

    assert api_split_types[DatasetSplitType.TRAIN_TEST] == Train80Test20SplitDefinition
    assert (
        api_split_types[DatasetSplitType.TRAIN_TEST_VAL]
        == Train60Test20Val20SplitDefinition
    )
    assert api_split_types[DatasetSplitType.ALL] == AllSplitDefinition
    for split_type in DatasetSplitType:
        assert split_type in api_split_types


def test_api_filter_types_mapping():
    from app.desktop.studio_server.finetune_api import api_filter_types

    assert api_filter_types[DatasetFilterType.ALL] == AllDatasetFilter
    assert api_filter_types[DatasetFilterType.HIGH_RATING] == HighRatingDatasetFilter
    for filter_type in DatasetFilterType:
        assert filter_type in api_filter_types


@pytest.fixture
def mock_dataset_split():
    split = DatasetSplit(
        id="new_split",
        name="Test Split",
        split_contents={"train": ["1", "2"], "test": ["3"]},
        splits=AllSplitDefinition,
    )
    return split


def test_create_dataset_split(client, mock_task_from_id, mock_dataset_split):
    # Mock DatasetSplit.from_task and save_to_file
    mock_from_task = unittest.mock.patch.object(
        DatasetSplit, "from_task", return_value=mock_dataset_split
    )
    mock_save = unittest.mock.patch.object(DatasetSplit, "save_to_file")

    with mock_from_task as from_task_mock, mock_save as save_mock:
        request_data = {
            "dataset_split_type": "train_test",
            "filter_type": "all",
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
        mock_task_from_id.assert_called_once_with("project1", "task1")
        from_task_mock.assert_called_once()
        save_mock.assert_called_once()


def test_create_dataset_split_auto_name(client, mock_task_from_id, mock_dataset_split):
    # Mock DatasetSplit.from_task and save_to_file
    mock_from_task = unittest.mock.patch.object(
        DatasetSplit, "from_task", return_value=mock_dataset_split
    )
    mock_save = unittest.mock.patch.object(DatasetSplit, "save_to_file")

    with mock_from_task as from_task_mock, mock_save as save_mock:
        request_data = {"dataset_split_type": "train_test", "filter_type": "all"}

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
        filter_type=DatasetFilterType.ALL,
        name="Test Split",
        description="Test description",
    )
    assert request.dataset_split_type == DatasetSplitType.TRAIN_TEST
    assert request.filter_type == DatasetFilterType.ALL
    assert request.name == "Test Split"
    assert request.description == "Test description"

    # Test optional fields
    request = CreateDatasetSplitRequest(
        dataset_split_type=DatasetSplitType.TRAIN_TEST,
        filter_type=DatasetFilterType.ALL,
    )
    assert request.name is None
    assert request.description is None

    # Test invalid dataset split type
    with pytest.raises(ValueError):
        CreateDatasetSplitRequest(
            dataset_split_type="invalid_type", filter_type=DatasetFilterType.ALL
        )

    # Test invalid filter type
    with pytest.raises(ValueError):
        CreateDatasetSplitRequest(
            dataset_split_type=DatasetSplitType.TRAIN_TEST, filter_type="invalid_type"
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
            ),
        )
    )
    return adapter


async def test_create_finetune(
    client, mock_task_from_id, mock_task, mock_finetune_registry, mock_finetune_adapter
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

    # Verify the adapter was called correctly
    mock_finetune_adapter.create_and_start.assert_awaited_once_with(
        dataset=mock_task.dataset_splits.return_value[0],  # First split from our mock
        provider_id="test_provider",
        provider_base_model_id="base_model_1",
        train_split_name="train",
        system_message="Test system message",
        parameters={"learning_rate": 0.001, "epochs": 10},
        name="New Finetune",
        description="Test description",
        validation_split_name="validation",
    )


def test_create_finetune_invalid_provider(client, mock_task_from_id):
    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "invalid_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "Fine tune provider 'invalid_provider' not found"
    )


def test_create_finetune_invalid_dataset(
    client, mock_task_from_id, mock_finetune_registry, mock_finetune_adapter
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "dataset_id": "invalid_split_id",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
        "custom_system_message": "Test system message",
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
    client, mock_task_from_id, mock_finetune_registry, mock_finetune_adapter
):
    mock_finetune_registry["test_provider"] = mock_finetune_adapter

    request_data = {
        "dataset_id": "split1",
        "train_split_name": "train",
        "parameters": {},
        "provider": "test_provider",
        "base_model_id": "base_model_1",
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "System message generator or custom system message is required"
    )


@pytest.fixture
def mock_prompt_builder():
    builder = Mock()
    builder.build_prompt.return_value = "Generated system message"
    builder_class = Mock(return_value=builder)

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.prompt_builder_from_ui_name",
        return_value=builder_class,
    ) as mock:
        yield mock, builder


async def test_create_finetune_with_prompt_builder(
    client,
    mock_task_from_id,
    mock_task,
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
    }

    response = client.post(
        "/api/projects/project1/tasks/task1/finetunes", json=request_data
    )

    assert response.status_code == 200
    result = response.json()
    assert result["id"] == "new_ft"

    # Verify prompt builder was called correctly
    prompt_builder_mock.assert_called_once_with("test_prompt_builder")
    builder.build_prompt.assert_called_once()

    # Verify the adapter was called with the generated system message
    mock_finetune_adapter.create_and_start.assert_awaited_once()
    call_kwargs = mock_finetune_adapter.create_and_start.await_args[1]
    assert call_kwargs["system_message"] == "Generated system message"


def test_create_finetune_prompt_builder_error(
    client,
    mock_task_from_id,
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
    formatter.dump_to_file.return_value = "path/to/dataset.jsonl"

    with unittest.mock.patch(
        "app.desktop.studio_server.finetune_api.DatasetFormatter",
        return_value=formatter,
    ) as mock_class:
        yield mock_class, formatter


def test_download_dataset_jsonl(
    client,
    mock_task_from_id,
    mock_task,
    mock_dataset_formatter,
    tmp_path,
):
    mock_formatter_class, mock_formatter = mock_dataset_formatter

    # Create a temporary file to simulate the dataset
    test_file = tmp_path / "dataset.jsonl"
    test_file.write_text('{"test": "data"}')
    mock_formatter.dump_to_file.return_value = str(test_file)

    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "train",
            "format_type": "openai_chat_jsonl",
            "custom_system_message": "Test system message",
        },
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/jsonl"
    assert (
        response.headers["Content-Disposition"]
        == 'attachment; filename="dataset_split1_train_openai_chat_jsonl.jsonl"'
    )
    assert response.content == b'{"test": "data"}'

    # Verify the formatter was created and used correctly
    mock_formatter_class.assert_called_once()
    mock_formatter.dump_to_file.assert_called_once_with("train", "openai_chat_jsonl")


def test_download_dataset_jsonl_invalid_format(client, mock_task_from_id):
    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "train",
            "format_type": "invalid_format",
            "custom_system_message": "Test system message",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Dataset format 'invalid_format' not found"


def test_download_dataset_jsonl_invalid_dataset(client, mock_task_from_id):
    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "invalid_split",
            "split_name": "train",
            "format_type": "openai_chat_jsonl",
            "custom_system_message": "Test system message",
        },
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Dataset split with ID 'invalid_split' not found"
    )


def test_download_dataset_jsonl_invalid_split(client, mock_task_from_id, mock_task):
    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "invalid_split",
            "format_type": "openai_chat_jsonl",
            "custom_system_message": "Test system message",
        },
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Dataset split with name 'invalid_split' not found"
    )


def test_download_dataset_jsonl_with_prompt_builder(
    client,
    mock_task_from_id,
    mock_task,
    mock_dataset_formatter,
    mock_prompt_builder,
    tmp_path,
):
    mock_formatter_class, mock_formatter = mock_dataset_formatter
    prompt_builder_mock, builder = mock_prompt_builder

    # Create a temporary file to simulate the dataset
    test_file = tmp_path / "dataset.jsonl"
    test_file.write_text('{"test": "data"}')
    mock_formatter.dump_to_file.return_value = str(test_file)

    response = client.get(
        "/api/download_dataset_jsonl",
        params={
            "project_id": "project1",
            "task_id": "task1",
            "dataset_id": "split1",
            "split_name": "train",
            "format_type": "openai_chat_jsonl",
            "system_message_generator": "test_prompt_builder",
        },
    )

    assert response.status_code == 200

    # Verify prompt builder was used
    prompt_builder_mock.assert_called_once_with("test_prompt_builder")
    builder.build_prompt.assert_called_once()

    # Verify formatter was created with generated system message
    mock_formatter_class.assert_called_once_with(
        mock_task.dataset_splits.return_value[0], "Generated system message"
    )


async def test_get_finetune(client, mock_task_from_id, mock_task):
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

    mock_task_from_id.assert_called_once_with("project1", "task1")
    mock_task.finetunes.assert_called_once()


def test_get_finetune_not_found(client, mock_task_from_id, mock_task):
    response = client.get("/api/projects/project1/tasks/task1/finetunes/nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Finetune with ID 'nonexistent' not found"

    mock_task_from_id.assert_called_once_with("project1", "task1")
    mock_task.finetunes.assert_called_once()


async def test_get_finetunes_with_status_update(
    client, mock_task_from_id, mock_task, mock_finetune_registry, monkeypatch
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
    mock_task.finetunes.return_value[0].latest_status = "pending"  # Should be updated
    mock_task.finetunes.return_value[1].latest_status = "completed"  # Should be skipped

    response = client.get(
        "/api/projects/project1/tasks/task1/finetunes?update_status=true"
    )

    assert response.status_code == 200
    finetunes = response.json()
    assert len(finetunes) == 2

    # Verify that status was only checked for the pending finetune
    mock_adapter_class.assert_called_once_with(mock_task.finetunes.return_value[0])
    mock_adapter.status.assert_called_once()
