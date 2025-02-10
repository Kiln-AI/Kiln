import time

import openai
from openai.types.fine_tuning import FineTuningJob

from kiln_ai.adapters.fine_tune.base_finetune import (
    BaseFinetuneAdapter,
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.datamodel import DatasetSplit, StructuredOutputMode, Task
from kiln_ai.utils.config import Config

oai_client = openai.AsyncOpenAI(
    api_key=Config.shared().open_ai_api_key or "",
)


class OpenAIFinetune(BaseFinetuneAdapter):
    """
    A fine-tuning adapter for OpenAI.
    """

    async def status(self) -> FineTuneStatus:
        """
        Get the status of the fine-tune.
        """

        # Update the datamodel with the latest status if it has changed
        status = await self._status()
        if status.status != self.datamodel.latest_status:
            self.datamodel.latest_status = status.status
            if self.datamodel.path:
                self.datamodel.save_to_file()
        return status

    async def _status(self) -> FineTuneStatus:
        if not self.datamodel or not self.datamodel.provider_id:
            return FineTuneStatus(
                status=FineTuneStatusType.pending,
                message="This fine-tune has not been started or has not been assigned a provider ID.",
            )

        try:
            # Will raise an error if the job is not found, or for other issues
            response = await oai_client.fine_tuning.jobs.retrieve(
                self.datamodel.provider_id
            )

            # If the fine-tuned model has been updated, update the datamodel
            try:
                if (
                    self.datamodel.fine_tune_model_id != response.fine_tuned_model
                    or self.datamodel.base_model_id != response.model
                ):
                    self.datamodel.fine_tune_model_id = response.fine_tuned_model
                    self.datamodel.base_model_id = response.model
                    self.datamodel.save_to_file()
            except Exception:
                # Don't let this error crash the status call
                pass

        except openai.APIConnectionError:
            return FineTuneStatus(
                status=FineTuneStatusType.unknown, message="Server connection error"
            )
        except openai.RateLimitError:
            return FineTuneStatus(
                status=FineTuneStatusType.unknown,
                message="Rate limit exceeded. Could not fetch fine-tune status.",
            )
        except openai.APIStatusError as e:
            if e.status_code == 404:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Job with this ID not found. It may have been deleted.",
                )
            return FineTuneStatus(
                status=FineTuneStatusType.unknown,
                message=f"Unknown error: [{str(e)}]",
            )

        if not response or not isinstance(response, FineTuningJob):
            return FineTuneStatus(
                status=FineTuneStatusType.unknown,
                message="Invalid response from OpenAI",
            )
        if response.error and response.error.code:
            return FineTuneStatus(
                status=FineTuneStatusType.failed,
                message=f"{response.error.message} [Code: {response.error.code}]",
            )
        status = response.status
        if status == "failed":
            return FineTuneStatus(
                status=FineTuneStatusType.failed,
                message="Job failed - unknown reason",
            )
        if status == "cancelled":
            return FineTuneStatus(
                status=FineTuneStatusType.failed, message="Job cancelled"
            )
        if status in ["validating_files", "running", "queued"]:
            time_to_finish_msg: str | None = None
            if response.estimated_finish is not None:
                time_to_finish_msg = f"Estimated finish time: {int(response.estimated_finish - time.time())} seconds."
            return FineTuneStatus(
                status=FineTuneStatusType.running,
                message=f"Fine tune job is running [{status}]. {time_to_finish_msg or ''}",
            )
        if status == "succeeded":
            return FineTuneStatus(
                status=FineTuneStatusType.completed, message="Training job completed"
            )
        return FineTuneStatus(
            status=FineTuneStatusType.unknown,
            message=f"Unknown status: [{status}]",
        )

    async def _start(self, dataset: DatasetSplit) -> None:
        task = self.datamodel.parent_task()
        if not task:
            raise ValueError("Task is required to start a fine-tune")

        # Use chat format for unstructured output, and JSON for formatted output (was previously function calls)
        format = DatasetFormat.OPENAI_CHAT_JSONL
        if task.output_json_schema:
            format = DatasetFormat.OPENAI_CHAT_JSON_SCHEMA_JSONL
            self.datamodel.structured_output_mode = StructuredOutputMode.json_schema
        train_file_id = await self.generate_and_upload_jsonl(
            dataset, self.datamodel.train_split_name, task, format
        )
        validation_file_id = None
        if self.datamodel.validation_split_name:
            validation_file_id = await self.generate_and_upload_jsonl(
                dataset, self.datamodel.validation_split_name, task, format
            )

        # Filter to hyperparameters which are set via the hyperparameters field (some like seed are set via the API)
        hyperparameters = {
            k: v
            for k, v in self.datamodel.parameters.items()
            if k in ["n_epochs", "learning_rate_multiplier", "batch_size"]
        }

        ft = await oai_client.fine_tuning.jobs.create(
            training_file=train_file_id,
            model=self.datamodel.base_model_id,
            validation_file=validation_file_id,
            seed=self.datamodel.parameters.get("seed"),  # type: ignore
            hyperparameters=hyperparameters,  # type: ignore
            suffix=f"kiln_ai.{self.datamodel.id}",
        )
        self.datamodel.provider_id = ft.id
        self.datamodel.fine_tune_model_id = ft.fine_tuned_model
        # Model can get more specific after fine-tune call (gpt-4o-mini to gpt-4o-mini-2024-07-18) so we update it in the datamodel
        self.datamodel.base_model_id = ft.model

        return None

    async def generate_and_upload_jsonl(
        self, dataset: DatasetSplit, split_name: str, task: Task, format: DatasetFormat
    ) -> str:
        formatter = DatasetFormatter(
            dataset, self.datamodel.system_message, self.datamodel.thinking_instructions
        )
        path = formatter.dump_to_file(split_name, format, self.datamodel.data_strategy)

        response = await oai_client.files.create(
            file=open(path, "rb"),
            purpose="fine-tune",
        )
        id = response.id
        if not id:
            raise ValueError("Failed to upload file to OpenAI")
        return id

    @classmethod
    def available_parameters(cls) -> list[FineTuneParameter]:
        return [
            FineTuneParameter(
                name="batch_size",
                type="int",
                description="Number of examples in each batch. A larger batch size means that model parameters are updated less frequently, but with lower variance. Defaults to 'auto'",
            ),
            FineTuneParameter(
                name="learning_rate_multiplier",
                type="float",
                description="Scaling factor for the learning rate. A smaller learning rate may be useful to avoid overfitting. Defaults to 'auto'",
                optional=True,
            ),
            FineTuneParameter(
                name="n_epochs",
                type="int",
                description="The number of epochs to train the model for. An epoch refers to one full cycle through the training dataset. Defaults to 'auto'",
                optional=True,
            ),
            FineTuneParameter(
                name="seed",
                type="int",
                description="The seed controls the reproducibility of the job. Passing in the same seed and job parameters should produce the same results, but may differ in rare cases. If a seed is not specified, one will be generated for you.",
                optional=True,
            ),
        ]
