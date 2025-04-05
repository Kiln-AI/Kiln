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
    FinetuneDataStrategy,
    StructuredOutputMode,
    Task,
)
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.datamodel.dataset_split import Train80Test20SplitDefinition
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


@pytest.mark.parametrize(
    "data_strategy,thinking_instructions",
    [
        (FinetuneDataStrategy.final_and_intermediate, "thinking instructions"),
        (FinetuneDataStrategy.final_only, None),
    ],
)
async def test_generate_and_upload_jsonl_success(
    mock_dataset,
    mock_task,
    mock_api_key,
    data_strategy,
    thinking_instructions,
    tmp_path,
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

    # Set the data strategy on the finetune model
    tmp_file = tmp_path / "test-finetune.kiln"
    fireworks_finetune = FireworksFinetune(
        datamodel=FinetuneModel(
            name="test-finetune",
            provider="fireworks",
            provider_id="fw-123",
            base_model_id="llama-v2-7b",
            train_split_name="train",
            dataset_split_id="dataset-123",
            system_message="Test system message",
            path=tmp_file,
            data_strategy=data_strategy,
            thinking_instructions=thinking_instructions,
        ),
    )

    with (
        patch(
            "kiln_ai.adapters.fine_tune.fireworks_finetune.DatasetFormatter",
        ) as mock_formatter_constructor,
        patch("httpx.AsyncClient") as mock_client_class,
        patch("builtins.open"),
        patch(
            "kiln_ai.adapters.fine_tune.fireworks_finetune.uuid4",
            return_value=mock_dataset_id,
        ),
    ):
        mock_formatter_constructor.return_value = mock_formatter
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[create_response, upload_response])
        mock_client.get = AsyncMock(return_value=status_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
        )

        # Verify formatter was created with correct parameters
        assert mock_formatter_constructor.call_count == 1
        assert mock_formatter_constructor.call_args[1] == {
            "dataset": mock_dataset,
            "system_message": "Test system message",
            "thinking_instructions": thinking_instructions,
        }

        # Verify the thinking instructions were set on the formatter
        mock_formatter.method_calls[0][0] == "dump_to_file"
        mock_formatter.method_calls[0][1] == {
            "dataset": mock_dataset,
            "thinking_instructions": thinking_instructions,
        }

        assert result == mock_dataset_id
        assert mock_client.post.call_count == 2
        assert mock_client.get.call_count == 1


@pytest.mark.parametrize(
    "output_schema,expected_mode,expected_format",
    [
        (
            '{"type": "object", "properties": {"key": {"type": "string"}}}',
            StructuredOutputMode.json_mode,
            DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
        ),
        (None, None, DatasetFormat.OPENAI_CHAT_JSONL),
    ],
)
async def test_start_success(
    fireworks_finetune,
    mock_dataset,
    mock_task,
    mock_api_key,
    output_schema,
    expected_mode,
    expected_format,
):
    Config.shared().wandb_api_key = "test-api-key"
    mock_task.output_json_schema = output_schema

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
            mock_dataset,
            fireworks_finetune.datamodel.train_split_name,
            mock_task,
            expected_format,
        )

        # Verify model ID was updated
        assert fireworks_finetune.datamodel.provider_id == mock_model_id
        assert fireworks_finetune.datamodel.structured_output_mode == expected_mode
        assert fireworks_finetune.datamodel.properties["endpoint_version"] == "v2"

        # check mockclent.post call values
        assert mock_client.post.call_count == 1
        submit_call_values = mock_client.post.call_args[1]
        assert submit_call_values["json"]["wandbConfig"] == {
            "enabled": True,
            "project": "Kiln_AI",
            "apiKey": "test-api-key",
        }
        assert submit_call_values["json"]["baseModel"] == "llama-v2-7b"
        assert (
            submit_call_values["json"]["dataset"]
            == f"accounts/{Config.shared().fireworks_account_id}/datasets/{mock_dataset_id}"
        )
        assert (
            submit_call_values["json"]["displayName"]
            == f"Kiln AI fine-tuning [ID:{fireworks_finetune.datamodel.id}][name:{fireworks_finetune.datamodel.name}]"
        )


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


async def test_deploy_serverless_success(fireworks_finetune, mock_api_key):
    # Mock response for successful deployment
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    assert fireworks_finetune.datamodel.fine_tune_model_id is None

    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        "ftm-123",
    )

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(fireworks_finetune, "_status", return_value=status_response),
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = success_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_serverless()
        assert result is True
        assert fireworks_finetune.datamodel.fine_tune_model_id == "ftm-123"


async def test_deploy_serverless_already_deployed(fireworks_finetune, mock_api_key):
    # Mock response for already deployed model
    already_deployed_response = MagicMock(spec=httpx.Response)
    already_deployed_response.status_code = 400
    already_deployed_response.json.return_value = {
        "code": 9,
        "message": "Model already deployed",
    }

    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        "ftm-123",
    )

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(fireworks_finetune, "_status", return_value=status_response),
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = already_deployed_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_serverless()
        assert result is True
        assert fireworks_finetune.datamodel.fine_tune_model_id == "ftm-123"


async def test_deploy_serverless_failure(fireworks_finetune, mock_api_key):
    # Mock response for failed deployment
    failure_response = MagicMock(spec=httpx.Response)
    failure_response.status_code = 500
    failure_response.json.return_value = {"code": 1}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post.return_value = failure_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_serverless()
        assert result is False


async def test_deploy_serverless_missing_credentials(fireworks_finetune):
    # Test missing API key or account ID
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = None
        mock_config.return_value.fireworks_account_id = None

        with pytest.raises(ValueError, match="Fireworks API key or account ID not set"):
            await fireworks_finetune._deploy_serverless()


async def test_deploy_server_missing_credentials(fireworks_finetune):
    # Test missing API key or account ID
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = None
        mock_config.return_value.fireworks_account_id = None

        response = await fireworks_finetune._check_or_deploy_server()
        assert response is False


async def test_deploy_missing_model_id(fireworks_finetune, mock_api_key):
    # Mock _status to return no model ID
    status_response = (
        FineTuneStatus(
            status=FineTuneStatusType.completed, message="Fine-tuning job completed"
        ),
        None,
    )
    with (
        patch.object(fireworks_finetune, "_status", return_value=status_response),
    ):
        response = await fireworks_finetune._deploy()
        assert response is False


async def test_status_with_deploy(fireworks_finetune, mock_api_key):
    # Mock _status to return completed
    status_response = (
        FineTuneStatus(
            status=FineTuneStatusType.completed, message="Fine-tuning job completed"
        ),
        "ftm-123",
    )
    with (
        patch.object(
            fireworks_finetune, "_status", return_value=status_response
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


@pytest.mark.paid
async def test_fetch_all_deployments(fireworks_finetune):
    deployments = await fireworks_finetune._fetch_all_deployments()
    assert isinstance(deployments, list)


async def test_api_key_and_account_id(fireworks_finetune, mock_api_key):
    # Test successful retrieval of API key and account ID
    api_key, account_id = fireworks_finetune.api_key_and_account_id()
    assert api_key == "test-api-key"
    assert account_id == "test-account-id"


async def test_api_key_and_account_id_missing_credentials(fireworks_finetune):
    # Test missing API key or account ID
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.fireworks_api_key = None
        mock_config.return_value.fireworks_account_id = None

        with pytest.raises(ValueError, match="Fireworks API key or account ID not set"):
            fireworks_finetune.api_key_and_account_id()


def test_deployment_display_name(fireworks_finetune):
    # Test with default ID and name
    display_name = fireworks_finetune.deployment_display_name()
    expected = f"Kiln AI fine-tuned model [ID:{fireworks_finetune.datamodel.id}][name:test-finetune]"[
        :60
    ]
    assert display_name == expected

    # Test with a very long name to ensure 60 character limit
    fireworks_finetune.datamodel.name = "x" * 100
    display_name = fireworks_finetune.deployment_display_name()
    assert len(display_name) == 60
    assert display_name.startswith("Kiln AI fine-tuned model [ID:")


async def test_model_id_checking_status_completed(fireworks_finetune):
    # Test with completed status and valid model ID
    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        "model-123",
    )

    with patch.object(fireworks_finetune, "_status", return_value=status_response):
        model_id = await fireworks_finetune.model_id_checking_status()
        assert model_id == "model-123"


async def test_model_id_checking_status_not_completed(fireworks_finetune):
    # Test with non-completed status
    status_response = (
        FineTuneStatus(status=FineTuneStatusType.running, message=""),
        "model-123",
    )

    with patch.object(fireworks_finetune, "_status", return_value=status_response):
        model_id = await fireworks_finetune.model_id_checking_status()
        assert model_id is None


async def test_model_id_checking_status_invalid_model_id(fireworks_finetune):
    # Test with completed status but invalid model ID
    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        None,
    )

    with patch.object(fireworks_finetune, "_status", return_value=status_response):
        model_id = await fireworks_finetune.model_id_checking_status()
        assert model_id is None

    # Test with non-string model ID
    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        {"id": "model-123"},  # Not a string
    )

    with patch.object(fireworks_finetune, "_status", return_value=status_response):
        model_id = await fireworks_finetune.model_id_checking_status()
        assert model_id is None


@pytest.mark.parametrize(
    "base_model_id,expected_method",
    [
        ("accounts/fireworks/models/llama-v3p1-8b-instruct", "_deploy_serverless"),
        ("accounts/fireworks/models/llama-v3p1-70b-instruct", "_deploy_serverless"),
        ("some-other-model", "_check_or_deploy_server"),
    ],
)
async def test_deploy_model_selection(
    fireworks_finetune, base_model_id, expected_method, mock_api_key
):
    # Set the base model ID
    fireworks_finetune.datamodel.base_model_id = base_model_id

    # Mock the deployment methods
    with (
        patch.object(
            fireworks_finetune, "_deploy_serverless", return_value=True
        ) as mock_serverless,
        patch.object(
            fireworks_finetune, "_check_or_deploy_server", return_value=True
        ) as mock_server,
    ):
        result = await fireworks_finetune._deploy()

        # Verify the correct method was called based on the model
        if expected_method == "_deploy_serverless":
            mock_serverless.assert_called_once()
            mock_server.assert_not_called()
        else:
            mock_serverless.assert_not_called()
            mock_server.assert_called_once()

        assert result is True


async def test_fetch_all_deployments_request_error(fireworks_finetune, mock_api_key):
    # Test with error response
    error_response = MagicMock(spec=httpx.Response)
    error_response.status_code = 500
    error_response.text = "Internal Server Error"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("API request failed")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(Exception, match="API request failed"):
            await fireworks_finetune._fetch_all_deployments()

        # Verify API was called with correct parameters
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args[1]
        assert "params" in call_args
        assert call_args["params"]["pageSize"] == 200


async def test_fetch_all_deployments_standard_case(fireworks_finetune, mock_api_key):
    # Test with single page of results
    mock_deployments = [
        {"id": "deploy-1", "baseModel": "model-1", "state": "READY"},
        {"id": "deploy-2", "baseModel": "model-2", "state": "READY"},
    ]

    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.json.return_value = {
        "deployments": mock_deployments,
        "nextPageToken": None,
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = success_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        deployments = await fireworks_finetune._fetch_all_deployments()

        # Verify API was called correctly
        mock_client.get.assert_called_once()

        # Verify correct deployments were returned
        assert deployments == mock_deployments
        assert len(deployments) == 2
        assert deployments[0]["id"] == "deploy-1"
        assert deployments[1]["id"] == "deploy-2"


async def test_fetch_all_deployments_paged_case(fireworks_finetune, mock_api_key):
    # Test with multiple pages of results
    mock_deployments_page1 = [
        {"id": "deploy-1", "baseModel": "model-1", "state": "READY"},
        {"id": "deploy-2", "baseModel": "model-2", "state": "READY"},
    ]

    mock_deployments_page2 = [
        {"id": "deploy-3", "baseModel": "model-3", "state": "READY"},
        {"id": "deploy-4", "baseModel": "model-4", "state": "READY"},
    ]

    page1_response = MagicMock(spec=httpx.Response)
    page1_response.status_code = 200
    page1_response.json.return_value = {
        "deployments": mock_deployments_page1,
        "nextPageToken": "page2token",
    }

    page2_response = MagicMock(spec=httpx.Response)
    page2_response.status_code = 200
    page2_response.json.return_value = {
        "deployments": mock_deployments_page2,
        "nextPageToken": None,
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.side_effect = [page1_response, page2_response]
        mock_client_class.return_value.__aenter__.return_value = mock_client

        deployments = await fireworks_finetune._fetch_all_deployments()

        # Verify API was called twice (once for each page)
        assert mock_client.get.call_count == 2

        # Verify first call had no page token
        first_call_args = mock_client.get.call_args_list[0][1]
        assert "pageToken" not in first_call_args["params"]

        # Verify second call included the page token
        second_call_args = mock_client.get.call_args_list[1][1]
        assert second_call_args["params"]["pageToken"] == "page2token"

        # Verify all deployments from both pages were returned
        assert len(deployments) == 4
        assert deployments == mock_deployments_page1 + mock_deployments_page2
        for deployment in deployments:
            assert deployment["id"] in [
                "deploy-1",
                "deploy-2",
                "deploy-3",
                "deploy-4",
            ]


async def test_deploy_server_success(fireworks_finetune, mock_api_key):
    # Mock response for successful deployment
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.json.return_value = {"baseModel": "model-123"}

    status_response = (
        FineTuneStatus(status=FineTuneStatusType.completed, message=""),
        "model-123",
    )

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(
            fireworks_finetune, "model_id_checking_status", return_value="model-123"
        ),
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = success_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_server()

        # Verify result
        assert result is True

        # Verify fine_tune_model_id was updated
        assert fireworks_finetune.datamodel.fine_tune_model_id == "model-123"

        # Verify API was called with correct parameters
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args[1]
        assert "json" in call_args
        assert call_args["json"]["baseModel"] == "model-123"
        assert call_args["json"]["minReplicaCount"] == 0
        assert "autoscalingPolicy" in call_args["json"]
        assert call_args["json"]["autoscalingPolicy"]["scaleToZeroWindow"] == "300s"

        # load the datamodel from the file and confirm the fine_tune_model_id was updated
        loaded_datamodel = FinetuneModel.load_from_file(
            fireworks_finetune.datamodel.path
        )
        assert loaded_datamodel.fine_tune_model_id == "model-123"


async def test_deploy_server_failure(fireworks_finetune, mock_api_key):
    # Mock response for failed deployment
    failure_response = MagicMock(spec=httpx.Response)
    failure_response.status_code = 500
    failure_response.text = "Internal Server Error"

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(
            fireworks_finetune, "model_id_checking_status", return_value="model-123"
        ),
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = failure_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_server()

        # Verify result
        assert result is False

        # Verify API was called
        mock_client.post.assert_called_once()


async def test_deploy_server_non_200_but_valid_response(
    fireworks_finetune, mock_api_key
):
    # Mock response with non-200 status but valid JSON response
    mixed_response = MagicMock(spec=httpx.Response)
    mixed_response.status_code = 200
    mixed_response.json.return_value = {"not_baseModel": "something-else"}

    with (
        patch("httpx.AsyncClient") as mock_client_class,
        patch.object(
            fireworks_finetune, "model_id_checking_status", return_value="model-123"
        ),
    ):
        mock_client = AsyncMock()
        mock_client.post.return_value = mixed_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await fireworks_finetune._deploy_server()

        # Verify result - should fail because baseModel is missing
        assert result is False


async def test_deploy_server_missing_model_id(fireworks_finetune, mock_api_key):
    # Test when model_id_checking_status returns None
    with patch.object(
        fireworks_finetune, "model_id_checking_status", return_value=None
    ):
        result = await fireworks_finetune._deploy_server()

        # Verify result - should fail because model ID is missing
        assert result is False


@pytest.mark.parametrize(
    "state,expected_already_deployed",
    [
        ("READY", True),
        ("CREATING", True),
        ("FAILED", False),
    ],
)
async def test_check_or_deploy_server_already_deployed(
    fireworks_finetune, mock_api_key, state, expected_already_deployed
):
    # Test when model is already deployed (should return True without calling _deploy_server)

    # Set a fine_tune_model_id so we search for deployments
    fireworks_finetune.datamodel.fine_tune_model_id = "model-123"

    # Mock deployments including one matching our model ID
    mock_deployments = [
        {"id": "deploy-1", "baseModel": "different-model", "state": "READY"},
        {"id": "deploy-2", "baseModel": "model-123", "state": state},
    ]

    with (
        patch.object(
            fireworks_finetune, "_fetch_all_deployments", return_value=mock_deployments
        ) as mock_fetch,
        patch.object(fireworks_finetune, "_deploy_server") as mock_deploy,
    ):
        mock_deploy.return_value = True
        result = await fireworks_finetune._check_or_deploy_server()
        # Even true if the model is in a non-ready state, as we'll call deploy (checked below)
        assert result is True

        if expected_already_deployed:
            assert mock_deploy.call_count == 0
        else:
            assert mock_deploy.call_count == 1

        # Verify _fetch_all_deployments was called
        mock_fetch.assert_called_once()


async def test_check_or_deploy_server_not_deployed(fireworks_finetune, mock_api_key):
    # Test when model exists but isn't deployed (should call _deploy_server)

    # Set a fine_tune_model_id so we search for deployments
    fireworks_finetune.datamodel.fine_tune_model_id = "model-123"

    # Mock deployments without our model ID
    mock_deployments = [
        {"id": "deploy-1", "baseModel": "different-model-1", "state": "READY"},
        {"id": "deploy-2", "baseModel": "different-model-2", "state": "READY"},
    ]

    with (
        patch.object(
            fireworks_finetune, "_fetch_all_deployments", return_value=mock_deployments
        ) as mock_fetch,
        patch.object(
            fireworks_finetune, "_deploy_server", return_value=True
        ) as mock_deploy,
    ):
        result = await fireworks_finetune._check_or_deploy_server()

        # Verify method returned True (from _deploy_server)
        assert result is True

        # Verify _fetch_all_deployments was called
        mock_fetch.assert_called_once()

        # Verify _deploy_server was called since model is not deployed
        mock_deploy.assert_called_once()


async def test_check_or_deploy_server_no_model_id(fireworks_finetune, mock_api_key):
    # Test when no fine_tune_model_id exists (should skip fetch and call _deploy_server directly)

    # Ensure no fine_tune_model_id is set
    fireworks_finetune.datamodel.fine_tune_model_id = None

    with (
        patch.object(fireworks_finetune, "_fetch_all_deployments") as mock_fetch,
        patch.object(
            fireworks_finetune, "_deploy_server", return_value=True
        ) as mock_deploy,
    ):
        result = await fireworks_finetune._check_or_deploy_server()

        # Verify method returned True (from _deploy_server)
        assert result is True

        # Verify _fetch_all_deployments was NOT called
        mock_fetch.assert_not_called()

        # Verify _deploy_server was called directly
        mock_deploy.assert_called_once()


async def test_check_or_deploy_server_deploy_fails(fireworks_finetune, mock_api_key):
    # Test when deployment fails

    # Ensure no fine_tune_model_id is set
    fireworks_finetune.datamodel.fine_tune_model_id = None

    with (
        patch.object(
            fireworks_finetune, "_deploy_server", return_value=False
        ) as mock_deploy,
    ):
        result = await fireworks_finetune._check_or_deploy_server()

        # Verify method returned False (from _deploy_server)
        assert result is False

        # Verify _deploy_server was called
        mock_deploy.assert_called_once()


async def test_fetch_all_deployments_invalid_json(fireworks_finetune, mock_api_key):
    # Test with invalid JSON response (missing 'deployments' key)
    invalid_response = MagicMock(spec=httpx.Response)
    invalid_response.status_code = 200
    invalid_response.json.return_value = {
        "some_other_key": "value",
        # No 'deployments' key
    }
    invalid_response.text = '{"some_other_key": "value"}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = invalid_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        with pytest.raises(
            ValueError,
            match="Invalid response from Fireworks. Expected list of deployments in 'deployments' key",
        ):
            await fireworks_finetune._fetch_all_deployments()

        # Verify API was called
        mock_client.get.assert_called_once()
