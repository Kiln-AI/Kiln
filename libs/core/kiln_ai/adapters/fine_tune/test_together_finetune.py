from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import together
from together.types.finetune import FinetuneJobStatus as TogetherFinetuneJobStatus

from kiln_ai.adapters.fine_tune.base_finetune import (
    FineTuneParameter,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.adapters.fine_tune.together_finetune import (
    TogetherFinetune,
    _completed_statuses,
    _failed_statuses,
    _pending_statuses,
    _running_statuses,
)
from kiln_ai.datamodel import (
    DatasetSplit,
    StructuredOutputMode,
    Task,
)
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.datamodel.dataset_split import Train80Test20SplitDefinition
from kiln_ai.utils.config import Config


def test_together_status_categorization():
    """
    Test that all statuses from TogetherFinetuneJobStatus are included in exactly one
    of the status categorization arrays.
    """
    # Collect all status values from the TogetherFinetuneJobStatus class
    all_statuses = list(TogetherFinetuneJobStatus)

    # Collect all statuses from the categorization arrays
    categorized_statuses = set()
    categorized_statuses.update(_pending_statuses)
    categorized_statuses.update(_running_statuses)
    categorized_statuses.update(_completed_statuses)
    categorized_statuses.update(_failed_statuses)

    # Check if any status is missing from categorization
    missing_statuses = set(all_statuses) - categorized_statuses
    assert not missing_statuses, (
        f"These statuses are not categorized: {missing_statuses}"
    )

    # Check if any status appears in multiple categories
    all_categorization_lists = [
        _pending_statuses,
        _running_statuses,
        _completed_statuses,
        _failed_statuses,
    ]

    for status in all_statuses:
        appearances = sum(status in category for category in all_categorization_lists)
        assert appearances == 1, (
            f"Status '{status}' appears in {appearances} categories (should be exactly 1)"
        )


@pytest.fixture
def finetune(tmp_path):
    tmp_file = tmp_path / "test-finetune.kiln"
    datamodel = FinetuneModel(
        name="test-finetune",
        provider="together",
        provider_id="together-123",
        base_model_id="llama-v2-7b",
        train_split_name="train",
        dataset_split_id="dataset-123",
        system_message="Test system message",
        path=tmp_file,
    )
    return datamodel


@pytest.fixture
def together_finetune(finetune, mock_together_client, mock_api_key):
    finetune = TogetherFinetune(datamodel=finetune)
    return finetune


@pytest.fixture
def mock_together_client():
    with patch(
        "kiln_ai.adapters.fine_tune.together_finetune.Together"
    ) as mock_together:
        mock_client = MagicMock()
        mock_together.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_api_key():
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.together_api_key = "test-api-key"
        yield


def test_init_missing_api_key(finetune):
    with patch.object(Config, "shared") as mock_config:
        mock_config.return_value.together_api_key = None
        with pytest.raises(ValueError, match="Together.ai API key not set"):
            TogetherFinetune(datamodel=finetune)


def test_init_success(mock_api_key, mock_together_client, finetune):
    # no exception should be raised
    TogetherFinetune(datamodel=finetune)


def test_available_parameters():
    parameters = TogetherFinetune.available_parameters()
    assert len(parameters) == 11
    assert all(isinstance(p, FineTuneParameter) for p in parameters)

    # Check specific parameters
    param_names = [p.name for p in parameters]
    assert "epochs" in param_names
    assert "learning_rate" in param_names
    assert "batch_size" in param_names
    assert "num_checkpoints" in param_names
    assert "min_lr_ratio" in param_names
    assert "warmup_ratio" in param_names
    assert "max_grad_norm" in param_names
    assert "weight_decay" in param_names
    assert "lora_rank" in param_names
    assert "lora_dropout" in param_names
    assert "lora_alpha" in param_names


async def test_status_missing_provider_id(together_finetune, mock_api_key):
    together_finetune.datamodel.provider_id = None

    status = await together_finetune.status()
    assert status.status == FineTuneStatusType.unknown
    assert "Fine-tuning job ID not set" in status.message


@pytest.mark.parametrize(
    "together_status,expected_status,expected_message",
    [
        (
            TogetherFinetuneJobStatus.STATUS_PENDING,
            FineTuneStatusType.pending,
            f"Fine-tuning job is pending [{TogetherFinetuneJobStatus.STATUS_PENDING}]",
        ),
        (
            TogetherFinetuneJobStatus.STATUS_RUNNING,
            FineTuneStatusType.running,
            f"Fine-tuning job is running [{TogetherFinetuneJobStatus.STATUS_RUNNING}]",
        ),
        (
            TogetherFinetuneJobStatus.STATUS_COMPLETED,
            FineTuneStatusType.completed,
            "Fine-tuning job completed",
        ),
        (
            TogetherFinetuneJobStatus.STATUS_ERROR,
            FineTuneStatusType.failed,
            f"Fine-tuning job failed [{TogetherFinetuneJobStatus.STATUS_ERROR}]",
        ),
        (
            "UNKNOWN_STATUS",
            FineTuneStatusType.unknown,
            "Unknown fine-tuning job status [UNKNOWN_STATUS]",
        ),
    ],
)
async def test_status_job_states(
    mock_together_client,
    together_finetune,
    together_status,
    expected_status,
    expected_message,
    mock_api_key,
):
    # Mock the retrieve method of the fine_tuning object
    mock_job = MagicMock()
    mock_job.status = together_status
    mock_together_client.fine_tuning.retrieve.return_value = mock_job

    status = await together_finetune.status()
    assert status.status == expected_status

    # Check that the status was updated in the datamodel
    assert together_finetune.datamodel.latest_status == expected_status
    assert status.status == expected_status
    assert expected_message == status.message

    # Verify the fine_tuning.retrieve method was called
    mock_together_client.fine_tuning.retrieve.assert_called_once_with(
        id=together_finetune.datamodel.provider_id
    )


async def test_status_exception(together_finetune, mock_together_client, mock_api_key):
    # Mock the retrieve method to raise an exception
    mock_together_client.fine_tuning.retrieve.side_effect = Exception("API error")

    status = await together_finetune.status()
    assert status.status == FineTuneStatusType.unknown
    assert "Error retrieving fine-tuning job status: API error" == status.message


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
    together_finetune, mock_dataset, mock_task, mock_together_client, mock_api_key
):
    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_path = Path("mock_path.jsonl")
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock the files.upload response
    mock_file = MagicMock()
    mock_file.id = "file-123"
    mock_together_client.files.upload.return_value = mock_file

    with patch(
        "kiln_ai.adapters.fine_tune.together_finetune.DatasetFormatter",
        return_value=mock_formatter,
    ):
        result = await together_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
        )

        # Check the formatter was created with correct parameters
        assert mock_formatter.dump_to_file.call_count == 1

        # Check the file was uploaded
        mock_together_client.files.upload.assert_called_once_with(
            file=mock_path,
            purpose=together.types.files.FilePurpose.FineTune,
            check=True,
        )

        # Check the result is the file ID
        assert result == "file-123"


async def test_generate_and_upload_jsonl_error(
    together_finetune, mock_dataset, mock_task, mock_together_client, mock_api_key
):
    # Mock the formatter
    mock_formatter = MagicMock(spec=DatasetFormatter)
    mock_path = Path("mock_path.jsonl")
    mock_formatter.dump_to_file.return_value = mock_path

    # Mock the files.upload to raise an exception
    mock_together_client.files.upload.side_effect = Exception("Upload failed")

    with (
        patch(
            "kiln_ai.adapters.fine_tune.together_finetune.DatasetFormatter",
            return_value=mock_formatter,
        ),
        pytest.raises(ValueError, match="Failed to upload dataset: Upload failed"),
    ):
        await together_finetune.generate_and_upload_jsonl(
            mock_dataset, "train", mock_task, DatasetFormat.OPENAI_CHAT_JSONL
        )


@pytest.mark.parametrize(
    "output_schema,expected_mode,expected_format,validation_file",
    [
        (
            '{"type": "object", "properties": {"key": {"type": "string"}}}',
            StructuredOutputMode.json_custom_instructions,
            DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL,
            True,
        ),
        (None, None, DatasetFormat.OPENAI_CHAT_JSONL, False),
    ],
)
async def test_start_success(
    together_finetune,
    mock_dataset,
    mock_task,
    mock_together_client,
    mock_api_key,
    output_schema,
    expected_mode,
    expected_format,
    validation_file,
):
    # Set output schema on task
    mock_task.output_json_schema = output_schema

    # Set parent task on finetune
    together_finetune.datamodel.parent = mock_task

    # Mock file ID from generate_and_upload_jsonl
    mock_file_id = "file-123"

    # Mock fine-tuning job response
    mock_job = MagicMock()
    mock_job.id = "job-123"
    mock_job.output_name = "model-123"
    mock_together_client.fine_tuning.create.return_value = mock_job

    with patch.object(
        together_finetune,
        "generate_and_upload_jsonl",
        AsyncMock(return_value=mock_file_id),
    ):
        if validation_file:
            together_finetune.datamodel.validation_split_name = "validation"

        await together_finetune._start(mock_dataset)

        # Check that generate_and_upload_jsonl was called with correct parameters
        first_call = together_finetune.generate_and_upload_jsonl.call_args_list[0].args
        assert first_call[0] == mock_dataset
        assert first_call[1] == together_finetune.datamodel.train_split_name
        assert first_call[2] == mock_task
        assert first_call[3] == expected_format
        if validation_file:
            second_call = together_finetune.generate_and_upload_jsonl.call_args_list[
                1
            ].args
            assert second_call[0] == mock_dataset
            assert second_call[1] == "validation"
            assert second_call[2] == mock_task
            assert second_call[3] == expected_format

        # Check that fine_tuning.create was called with correct parameters
        mock_together_client.fine_tuning.create.assert_called_once_with(
            training_file=mock_file_id,
            validation_file=mock_file_id if validation_file else "",
            model=together_finetune.datamodel.base_model_id,
            lora=True,
            suffix=f"kiln_ai_{together_finetune.datamodel.id}"[:40],
            wandb_api_key=Config.shared().wandb_api_key,
            wandb_project_name="Kiln_AI",
        )

        # Check that datamodel was updated correctly
        assert together_finetune.datamodel.provider_id == "job-123"
        assert together_finetune.datamodel.fine_tune_model_id == "model-123"
        assert together_finetune.datamodel.structured_output_mode == expected_mode


async def test_start_missing_task(together_finetune, mock_dataset, mock_api_key):
    # Don't set parent task
    together_finetune.datamodel.parent = None
    together_finetune.datamodel.save_to_file()

    with pytest.raises(ValueError, match="Task is required to start a fine-tune"):
        await together_finetune._start(mock_dataset)


async def test_deploy_always_succeeds(together_finetune, mock_api_key):
    # Together automatically deploys, so _deploy should always return True
    result = await together_finetune._deploy()
    assert result is True


def test_augment_system_message(mock_task):
    system_message = "You are a helpful assistant."

    # Plaintext == no change
    augmented_system_message = TogetherFinetune.augment_system_message(
        system_message, mock_task
    )
    assert augmented_system_message == "You are a helpful assistant."

    # Now with JSON == append JSON instructions
    mock_task.output_json_schema = (
        '{"type": "object", "properties": {"key": {"type": "string"}}}'
    )
    augmented_system_message = TogetherFinetune.augment_system_message(
        system_message, mock_task
    )
    assert (
        augmented_system_message
        == "You are a helpful assistant.\n\nReturn only JSON. Do not include any non JSON text.\n"
    )


@pytest.mark.parametrize(
    "parameter_name,input_value,expected_key,expected_value,should_exist",
    [
        # learning_rate tests
        ("learning_rate", 0.001, "learning_rate", 0.001, True),
        ("learning_rate", "not_a_float", "learning_rate", None, False),
        # epochs tests
        ("epochs", 5, "n_epochs", 5, True),
        ("epochs", "not_an_int", "n_epochs", None, False),
        # num_checkpoints tests
        ("num_checkpoints", 3, "n_checkpoints", 3, True),
        ("num_checkpoints", "not_an_int", "n_checkpoints", None, False),
        # batch_size tests
        ("batch_size", 32, "batch_size", 32, True),
        ("batch_size", "not_an_int", "batch_size", None, False),
        # min_lr_ratio tests
        ("min_lr_ratio", 0.1, "min_lr_ratio", 0.1, True),
        ("min_lr_ratio", "not_a_float", "min_lr_ratio", None, False),
        # warmup_ratio tests
        ("warmup_ratio", 0.2, "warmup_ratio", 0.2, True),
        ("warmup_ratio", "not_a_float", "warmup_ratio", None, False),
        # max_grad_norm tests
        ("max_grad_norm", 5.0, "max_grad_norm", 5.0, True),
        ("max_grad_norm", "not_a_float", "max_grad_norm", None, False),
        # weight_decay tests
        ("weight_decay", 0.01, "weight_decay", 0.01, True),
        ("weight_decay", "not_a_float", "weight_decay", None, False),
        # lora_rank tests
        ("lora_rank", 16, "lora_r", 16, True),
        ("lora_rank", "not_an_int", "lora_r", None, False),
        # lora_dropout tests
        ("lora_dropout", 0.1, "lora_dropout", 0.1, True),
        ("lora_dropout", "not_a_float", "lora_dropout", None, False),
        # lora_alpha tests
        ("lora_alpha", 32.0, "lora_alpha", 32.0, True),
        ("lora_alpha", "not_a_float", "lora_alpha", None, False),
    ],
)
def test_build_finetune_parameters(
    together_finetune,
    parameter_name,
    input_value,
    expected_key,
    expected_value,
    should_exist,
):
    """Test that _build_finetune_parameters correctly handles different parameters."""
    # Set the parameter
    together_finetune.datamodel.parameters = {parameter_name: input_value}
    together_finetune.datamodel.id = "test-display-name"

    # Call the method to build parameters
    result = together_finetune._build_finetune_parameters()

    # Check that required parameters are always present
    assert result["lora"] is True
    assert result["suffix"] == "kiln_ai_test-display-name"

    # Check the specific parameter we're testing
    if should_exist:
        assert expected_key in result
        assert result[expected_key] == expected_value
    else:
        assert expected_key not in result


@pytest.mark.parametrize(
    "parameters,expected_params",
    [
        # Test default values when parameters are empty
        (
            {},
            {
                "lora": True,
                "suffix": "kiln_ai_1234",
            },
        ),
        # Test multiple parameters together
        (
            {
                "epochs": 3,
                "learning_rate": 0.0005,
                "batch_size": 16,
                "num_checkpoints": 2,
                "min_lr_ratio": 0.1,
                "warmup_ratio": 0.2,
                "max_grad_norm": 2.0,
                "weight_decay": 0.01,
            },
            {
                "lora": True,
                "n_epochs": 3,
                "learning_rate": 0.0005,
                "batch_size": 16,
                "n_checkpoints": 2,
                "min_lr_ratio": 0.1,
                "warmup_ratio": 0.2,
                "max_grad_norm": 2.0,
                "weight_decay": 0.01,
                "suffix": "kiln_ai_1234",
            },
        ),
        # Test mix of valid and invalid parameters
        (
            {
                "epochs": "invalid",
                "learning_rate": 0.001,
                "batch_size": "invalid",
                "num_checkpoints": "invalid",
            },
            {
                "lora": True,
                "learning_rate": 0.001,
                "suffix": "kiln_ai_1234",
            },
        ),
    ],
)
def test_build_finetune_parameters_combinations(
    together_finetune, parameters, expected_params
):
    """Test combinations of parameters in _build_finetune_parameters."""
    together_finetune.datamodel.parameters = parameters
    together_finetune.datamodel.id = "1234"
    result = together_finetune._build_finetune_parameters()

    # Check that all expected keys are present with the correct values
    assert result == expected_params
