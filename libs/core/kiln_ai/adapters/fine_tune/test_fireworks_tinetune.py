from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from kiln_ai.adapters.fine_tune.base_finetune import (
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.adapters.fine_tune.fireworks_finetune import FireworksFinetune
from kiln_ai.datamodel import (
    DatasetSplit,
    Task,
    Train80Test20SplitDefinition,
)
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.utils.config import Config


@pytest.fixture
def fireworks_finetune(tmp_path):
    tmp_file = tmp_path / "test-finetune.kiln"
    finetune = FireworksFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="fireworks",
            provider_id="fw-123",
            base_model_id="llama-v2-7b",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            path=tmp_file,
            properties={"undeployed_model_id": "ftm-123"},
        ),
    )
    return finetune


@pytest.fixture
def mock_response():
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = {
        "state": "COMPLETED",
        "model": "llama-v2-7b",
    }
    return response


@pytest.fixture
def mock_client():
    client = MagicMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def mock_api_key():
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = "test-api-key"
        mock_config.return_value.fireworks_account_id = "test-account-id"
        yield


async def test_setup(fireworks_finetune, mock_api_key):
    if (
        not Config.shared().fireworks_api_key
        or not Config.shared().fireworks_account_id
    ):
        pytest.skip("Fireworks API key or account ID not set")

    # Real API call, with fake ID
    status = await fireworks_finetune.status()
    assert status.status == FineTuneStatusType.unknown
    assert "Error retrieving fine-tuning job status" in status.message


async def test_status_missing_credentials(fireworks_finetune):
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = None
        mock_config.return_value.fireworks_account_id = None

        status = await fireworks_finetune.status()
        assert status.status == FineTuneStatusType.unknown
        assert "Fireworks API key or account ID not set" == status.message


async def test_status_missing_provider_id(fireworks_finetune, mock_api_key):
    fireworks_finetune.datamodel.provider_id = None

    status = await fireworks_finetune.status()
    assert status.status == FineTuneStatusType.unknown
    assert "Fine-tuning job ID not set" in status.message


@pytest.mark.parametrize(
    "status_code,expected_status,expected_message",
    [
        (
            401,
            FineTuneStatusType.unknown,
            "Error retrieving fine-tuning job status: [401]",
        ),
        (
            404,
            FineTuneStatusType.unknown,
            "Error retrieving fine-tuning job status: [404]",
        ),
        (
            500,
            FineTuneStatusType.unknown,
            "Error retrieving fine-tuning job status: [500]",
        ),
    ],
)
async def test_status_api_errors(
    fireworks_finetune,
    mock_response,
    mock_client,
    status_code,
    expected_status,
    expected_message,
    mock_api_key,
):
    mock_response.status_code = status_code
    mock_response.text = "Error message"
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_client
        status = await fireworks_finetune.status()
        assert status.status == expected_status
        assert expected_message in status.message


@pytest.mark.parametrize(
    "state,expected_status,message",
    [
        ("FAILED", FineTuneStatusType.failed, "Fine-tuning job failed"),
        ("DELETING", FineTuneStatusType.failed, "Fine-tuning job failed"),
        ("COMPLETED", FineTuneStatusType.completed, "Fine-tuning job completed"),
        (
            "CREATING",
            FineTuneStatusType.running,
            "Fine-tuning job is running [CREATING]",
        ),
        ("PENDING", FineTuneStatusType.running, "Fine-tuning job is running [PENDING]"),
        ("RUNNING", FineTuneStatusType.running, "Fine-tuning job is running [RUNNING]"),
        (
            "UNKNOWN_STATE",
            FineTuneStatusType.unknown,
            "Unknown fine-tuning job status [UNKNOWN_STATE]",
        ),
        (
            "UNSPECIFIED_STATE",
            FineTuneStatusType.unknown,
            "Unknown fine-tuning job status [UNSPECIFIED_STATE]",
        ),
    ],
)
async def test_status_job_states(
    fireworks_finetune,
    mock_response,
    mock_client,
    state,
    expected_status,
    message,
    mock_api_key,
):
    mock_response.json.return_value = {"state": state}
    mock_client.get.return_value = mock_response

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(fireworks_finetune, "_deploy", return_value=True),
    ):
        mock_client_class.return_value.__aenter__.return_value = mock_client
        status = await fireworks_finetune.status()
        assert status.status == expected_status
        assert message == status.message


async def test_status_invalid_response(
    fireworks_finetune, mock_response, mock_client, mock_api_key
):
    mock_response.json.return_value = {"no_state_field": "value"}
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_client
        status = await fireworks_finetune.status()
        assert status.status == FineTuneStatusType.unknown
        assert "Invalid response from Fireworks" in status.message


async def test_status_request_exception(fireworks_finetune, mock_client, mock_api_key):
    mock_client.get.side_effect = Exception("Connection error")

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_class.return_value.__aenter__.return_value = mock_client
        status = await fireworks_finetune.status()
        assert status.status == FineTuneStatusType.unknown
        assert (
            "Error retrieving fine-tuning job status: Connection error"
            == status.message
        )


@pytest.fixture
def mock_dataset():
    return DatasetSplit(
        id="test-dataset-123",
        name="Test Dataset",
        splits=Train80Test20SplitDefinition,
        split_contents={"train": [], "test": []},
    )


@pytest.fixture
def mock_task():
    return Task(
        id="test-task-123",
        name="Test Task",
        output_json_schema=None,  # Can be modified in specific tests
        instruction="Test instruction",
    )


async def test_generate_and_upload_jsonl_success(
    fireworks_finetune, mock_dataset, mock_task, mock_api_key
):
    mock_path = Path("mock_path.jsonl")
    mock_dataset_id = "dataset-123"

    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock responses for the three API calls
    create_response = MagicMock(spec=httpx.Response)
    create_response.status_code = 200

    upload_response = MagicMock(spec=httpx.Response)
    upload_response.status_code = 200

    status_response = MagicMock(spec=httpx.Response)
    status_response.status_code = 200
    status_response.json.return_value = {"state": "READY"}

    with (
        patch(
            "kiln_ai.adapters.fine_tune.fireworks_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        patch("httpx.AsyncClient") as mock_client_class,
        patch("builtins.open"),
        patch(
            "kiln_ai.adapters.fine_tune.fireworks_finetune.uuid4",
            return_value=mock_dataset_id,
        ),
    ):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[create_response, upload_response])
        mock_client.get = AsyncMock(return_value=status_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task
        )

        # Verify formatter was created with correct parameters
        mock_formatter.dump_to_file.assert_called_once_with(
            "train", DatasetFormat.OPENAI_CHAT_JSONL
        )

        assert result == mock_dataset_id
        assert mock_client.post.call_count == 2
        assert mock_client.get.call_count == 1


async def test_start_success(fireworks_finetune, mock_dataset, mock_task, mock_api_key):
    fireworks_finetune.datamodel.parent = mock_task
    mock_dataset_id = "dataset-123"
    mock_model_id = "ft-model-123"

    # Mock response for create fine-tuning job
    create_response = MagicMock(spec=httpx.Response)
    create_response.status_code = 200
    create_response.json.return_value = {"name": mock_model_id}

    with (
        patch.object(
            fireworks_finetune,
            "generate_and_upload_jsonl",
            return_value=mock_dataset_id,
        ),
        patch("httpx.AsyncClient") as mock_client_class,
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = create_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        await fireworks_finetune._start(mock_dataset)

        # Verify dataset was uploaded
        fireworks_finetune.generate_and_upload_jsonl.assert_called_once_with(
            mock_dataset, fireworks_finetune.datamodel.train_split_name, mock_task
        )

        # Verify model ID was updated
        assert fireworks_finetune.datamodel.provider_id == mock_model_id


async def test_start_api_error(
    fireworks_finetune, mock_dataset, mock_task, mock_api_key
):
    fireworks_finetune.datamodel.parent = mock_task
    mock_dataset_id = "dataset-123"

    # Mock error response
    error_response = MagicMock(spec=httpx.Response)
    error_response.status_code = 500
    error_response.text = "Internal Server Error"

    with (
        patch.object(
            fireworks_finetune,
            "generate_and_upload_jsonl",
            return_value=mock_dataset_id,
        ),
        patch("httpx.AsyncClient") as mock_client_class,
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = error_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ValueError, match="Failed to create fine-tuning job"):
            await fireworks_finetune._start(mock_dataset)


def test_available_parameters(fireworks_finetune):
    parameters = fireworks_finetune.available_parameters()
    assert len(parameters) == 4
    assert all(isinstance(p, FineTuneParameter) for p in parameters)

    payload_parameters = fireworks_finetune.create_payload_parameters(
        {"lora_rank": 16, "epochs": 3, "learning_rate": 0.001, "batch_size": 32}
    )
    assert payload_parameters == {
        "loraRank": 16,
        "epochs": 3,
        "learningRate": 0.001,
        "batchSize": 32,
    }
    payload_parameters = fireworks_finetune.create_payload_parameters({})
    assert payload_parameters == {}

    payload_parameters = fireworks_finetune.create_payload_parameters(
        {"lora_rank": 16, "epochs": 3}
    )
    assert payload_parameters == {"loraRank": 16, "epochs": 3}


async def test_deploy_success(fireworks_finetune, mock_api_key):
    # Mock response for successful deployment
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    assert fireworks_finetune.datamodel.fine_tune_model_id is None

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = success_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy()
        assert result is True
        assert fireworks_finetune.datamodel.fine_tune_model_id == "ftm-123"


async def test_deploy_already_deployed(fireworks_finetune, mock_api_key):
    # Mock response for already deployed model
    already_deployed_response = MagicMock(spec=httpx.Response)
    already_deployed_response.status_code = 400
    already_deployed_response.json.return_value = {
        "code": 9,
        "message": "Model already deployed",
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = already_deployed_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy()
        assert result is True


async def test_deploy_failure(fireworks_finetune, mock_api_key):
    # Mock response for failed deployment
    failure_response = MagicMock(spec=httpx.Response)
    failure_response.status_code = 500
    failure_response.json.return_value = {"code": 1}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = failure_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy()
        assert result is False


async def test_deploy_missing_credentials(fireworks_finetune):
    # Test missing API key or account ID
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = None
        mock_config.return_value.fireworks_account_id = None

        with pytest.raises(ValueError, match="Fireworks API key or account ID not set"):
            await fireworks_finetune._deploy()


async def test_deploy_missing_model_id(fireworks_finetune, mock_api_key):
    # Test missing model ID
    fireworks_finetune.datamodel.properties["undeployed_model_id"] = None

    response = await fireworks_finetune._deploy()
    assert response is False


async def test_status_with_deploy(fireworks_finetune, mock_api_key):
    # Mock _status to return completed
    mock_status_response = FineTuneStatus(
        status=FineTuneStatusType.completed, message="Fine-tuning job completed"
    )

    with (
        patch.object(
            fireworks_finetune, "_status", return_value=mock_status_response
        ) as mock_status,
        patch.object(fireworks_finetune, "_deploy", return_value=False) as mock_deploy,
    ):
        status = await fireworks_finetune.status()

        # Verify _status was called
        mock_status.assert_called_once()

        # Verify _deploy was called since status was completed
        mock_deploy.assert_called_once()

        # Verify message was updated due to failed deployment
        assert status.status == FineTuneStatusType.completed
        assert status.message == "Fine-tuning job completed but failed to deploy model."
