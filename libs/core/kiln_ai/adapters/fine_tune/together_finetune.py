from typing import Literal, Tuple

from together import Together
from together.types.files import FilePurpose
from together.types.finetune import FinetuneJobStatus as TogetherFinetuneJobStatus

from kiln_ai.adapters.fine_tune.base_finetune import (
    BaseFinetuneAdapter,
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.datamodel import DatasetSplit, StructuredOutputMode, Task
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.utils.config import Config

_pending_statuses = [
    TogetherFinetuneJobStatus.STATUS_PENDING,
    TogetherFinetuneJobStatus.STATUS_QUEUED,
]
_running_statuses = [
    TogetherFinetuneJobStatus.STATUS_RUNNING,
    TogetherFinetuneJobStatus.STATUS_COMPRESSING,
    TogetherFinetuneJobStatus.STATUS_UPLOADING,
]
_completed_statuses = [TogetherFinetuneJobStatus.STATUS_COMPLETED]
_failed_statuses = [
    TogetherFinetuneJobStatus.STATUS_CANCELLED,
    TogetherFinetuneJobStatus.STATUS_CANCEL_REQUESTED,
    TogetherFinetuneJobStatus.STATUS_ERROR,
    TogetherFinetuneJobStatus.STATUS_USER_ERROR,
]


class TogetherFinetune(BaseFinetuneAdapter):
    """
    A fine-tuning adapter for Together.ai.
    """

    def __init__(self, datamodel: FinetuneModel):
        super().__init__(datamodel)
        api_key = Config.shared().together_api_key
        if not api_key:
            raise ValueError("Together.ai API key not set")
        self.client = Together(api_key=api_key)

    async def status(self) -> FineTuneStatus:
        status, _ = await self._status()
        # update the datamodel if the status has changed
        if self.datamodel.latest_status != status.status:
            self.datamodel.latest_status = status.status
            if self.datamodel.path:
                self.datamodel.save_to_file()
        return status

    async def _status(self) -> Tuple[FineTuneStatus, str | None]:
        try:
            fine_tuning_job_id = self.datamodel.provider_id
            if not fine_tuning_job_id:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Fine-tuning job ID not set. Can not retrieve status.",
                ), None

            # retrieve the fine-tuning job
            together_finetune = self.client.fine_tuning.retrieve(id=fine_tuning_job_id)

            status = together_finetune.status
            if status in _pending_statuses:
                return FineTuneStatus(
                    status=FineTuneStatusType.pending,
                    message=f"Fine-tuning job is pending [{status}]",
                ), fine_tuning_job_id
            elif status in _running_statuses:
                return FineTuneStatus(
                    status=FineTuneStatusType.running,
                    message=f"Fine-tuning job is running [{status}]",
                ), fine_tuning_job_id
            elif status in _completed_statuses:
                return FineTuneStatus(
                    status=FineTuneStatusType.completed,
                    message="Fine-tuning job completed",
                ), fine_tuning_job_id
            elif status in _failed_statuses:
                return FineTuneStatus(
                    status=FineTuneStatusType.failed,
                    message=f"Fine-tuning job failed [{status}]",
                ), fine_tuning_job_id
            else:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message=f"Unknown fine-tuning job status [{status}]",
                ), fine_tuning_job_id
        except Exception as e:
            return FineTuneStatus(
                status=FineTuneStatusType.unknown,
                message=f"Error retrieving fine-tuning job status: {e}",
            ), None

    async def _start(self, dataset: DatasetSplit) -> None:
        task = self.datamodel.parent_task()
        if not task:
            raise ValueError("Task is required to start a fine-tune")

        format = DatasetFormat.OPENAI_CHAT_JSONL
        if task.output_json_schema:
            # This formatter will check it's valid JSON, and normalize the output (chat format just uses exact string).
            format = DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL
            # Together doesn't support JSON-mode for fine-tunes, so we use JSON instructions in the system message. However not our standard json_instructions mode.
            # Instead we augment the system message with custom JSON instructions for a fine-tune (see augment_system_message). A nice simple instructions.
            # Why: Fine-tunes tend to need less coaching to get JSON format correct, as they have seen examples. And they are often on smaller models that have trouble following longer/complex JSON-schema prompts so our default is a poor choice.
            # We save json_custom_instructions mode so it knows what to do at call time.
            self.datamodel.structured_output_mode = (
                StructuredOutputMode.json_custom_instructions
            )

        train_file_id = await self.generate_and_upload_jsonl(
            dataset, self.datamodel.train_split_name, task, format
        )

        # Their library defaults to "" and not None, so we follow that convention.
        validation_file_id = ""
        if self.datamodel.validation_split_name:
            validation_file_id = await self.generate_and_upload_jsonl(
                dataset, self.datamodel.validation_split_name, task, format
            )

        together_finetune = self.client.fine_tuning.create(
            training_file=train_file_id,
            validation_file=validation_file_id,
            model=self.datamodel.base_model_id,
            wandb_api_key=Config.shared().wandb_api_key,
            wandb_project_name="Kiln_AI" if Config.shared().wandb_api_key else None,
            **self._build_finetune_parameters(),
        )

        # 2 different IDs, output_name is the name of the model that results from the fine-tune job, the finetune_job_id is the ID of the fine-tune job
        self.datamodel.provider_id = together_finetune.id
        self.datamodel.fine_tune_model_id = together_finetune.output_name

        if self.datamodel.path:
            self.datamodel.save_to_file()

    def _build_finetune_parameters(self) -> dict:
        """
        Build the parameters dictionary for fine-tuning with Together.ai.
        Only includes parameters that exist in the datamodel and have valid types.

        Args:
            train_file_id: The ID of the uploaded training file
            display_name: The display name for the fine-tune job

        Returns:
            Dictionary of parameters to pass to Together's fine-tuning API
        """
        parameters = self.datamodel.parameters

        # Start with required parameters
        properties = {
            # Force LoRA for now. We only support serverless Loras at the moment. We can remove this later when we add support for full-finetunes.
            "lora": True,
            # Suffix must be truncated to 40 characters
            "suffix": f"kiln_ai_{self.datamodel.id}",
        }

        # Add optional parameters only if they exist and have correct types
        if "epochs" in parameters and isinstance(parameters["epochs"], int):
            properties["n_epochs"] = parameters["epochs"]

        if "learning_rate" in parameters and isinstance(
            parameters["learning_rate"], float
        ):
            properties["learning_rate"] = parameters["learning_rate"]

        if "batch_size" in parameters and isinstance(parameters["batch_size"], int):
            properties["batch_size"] = parameters["batch_size"]

        if "num_checkpoints" in parameters and isinstance(
            parameters["num_checkpoints"], int
        ):
            properties["n_checkpoints"] = parameters["num_checkpoints"]

        if "min_lr_ratio" in parameters and isinstance(
            parameters["min_lr_ratio"], float
        ):
            properties["min_lr_ratio"] = parameters["min_lr_ratio"]

        if "warmup_ratio" in parameters and isinstance(
            parameters["warmup_ratio"], float
        ):
            properties["warmup_ratio"] = parameters["warmup_ratio"]

        if "max_grad_norm" in parameters and isinstance(
            parameters["max_grad_norm"], float
        ):
            properties["max_grad_norm"] = parameters["max_grad_norm"]

        if "weight_decay" in parameters and isinstance(
            parameters["weight_decay"], float
        ):
            properties["weight_decay"] = parameters["weight_decay"]

        if "lora_rank" in parameters and isinstance(parameters["lora_rank"], int):
            properties["lora_r"] = parameters["lora_rank"]

        if "lora_dropout" in parameters and isinstance(
            parameters["lora_dropout"], float
        ):
            properties["lora_dropout"] = parameters["lora_dropout"]

        if "lora_alpha" in parameters and isinstance(parameters["lora_alpha"], float):
            properties["lora_alpha"] = parameters["lora_alpha"]

        return properties

    @classmethod
    def augment_system_message(cls, system_message: str, task: Task) -> str:
        """
        Augment the system message with custom JSON instructions for a fine-tune.

        This is a shorter version of the JSON instructions, as fine-tunes tend to need less coaching to get JSON format correct. Plus smaller models are often finetuned, and don't do well following our detailed JSON-schema instructions from json_instructions.

        Together doesn't support JSON-mode for fine-tunes, so this is needed where it isn't needed with other providers.
        """
        if task.output_json_schema:
            return (
                system_message
                + "\n\nReturn only JSON. Do not include any non JSON text.\n"
            )
        return system_message

    async def generate_and_upload_jsonl(
        self, dataset: DatasetSplit, split_name: str, task: Task, format: DatasetFormat
    ) -> str:
        formatter = DatasetFormatter(
            dataset=dataset,
            system_message=self.datamodel.system_message,
            thinking_instructions=self.datamodel.thinking_instructions,
        )
        path = formatter.dump_to_file(split_name, format, self.datamodel.data_strategy)

        try:
            together_file = self.client.files.upload(
                file=path,
                purpose=FilePurpose.FineTune,
                check=True,
            )
            return together_file.id
        except Exception as e:
            raise ValueError(f"Failed to upload dataset: {e}")

    @classmethod
    def available_parameters(cls) -> list[FineTuneParameter]:
        return [
            FineTuneParameter(
                name="epochs",
                description="Number of epochs to fine-tune for. Default: 1, Min: 1, Max: 20.",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="learning_rate",
                description="Learning rate to use for fine-tuning. Defaults to 0.00001",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="batch_size",
                description="Batch size used in training. Can be configured with a positive value less than 1024 and in power of 2. If not specified, defaults to the max supported value for this model. See together model pages for min/max values for each model.",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="num_checkpoints",
                description="Number of checkpoints to save during training. Defaults to 1.",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="min_lr_ratio",
                description="The ratio of the final learning rate to the peak learning rate. Default: 0.0, Min: 0.0, Max: 1.0.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="warmup_ratio",
                description="The percent of steps at the start of training to linearly increase the learning rate. Defaults to 0.0, Min: 0.0, Max: 1.0.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="max_grad_norm",
                description="Max gradient norm for gradient clipping. Set to 0 to disable. Defaults to 1.0, Min: 0.0.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="weight_decay",
                description="Weight decay. Defaults to 0.0.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="lora_rank",
                description="Rank of LoRA adapters. Default: 8, Min: 1, Max: 64",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="lora_dropout",
                description="Dropout rate for LoRA adapters. Default: 0.0, Min: 0.0, Max: 1.0.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="lora_alpha",
                description="Alpha value for LoRA adapter training. Default: 8. Min: 1. If a value less than 1 is given, it will default to lora_rank value to follow the recommendation of 1:1 scaling.",
                type="float",
                optional=True,
            ),
        ]

    async def _deploy(self) -> bool:
        # Together is awesome. Auto deploys!
        # If I add support for non-Lora serverless I'll have to modify this, but good for now.
        return True
