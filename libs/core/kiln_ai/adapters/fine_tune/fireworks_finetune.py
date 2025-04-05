import logging
from typing import List, Tuple
from uuid import uuid4

import httpx

from kiln_ai.adapters.fine_tune.base_finetune import (
    BaseFinetuneAdapter,
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.datamodel import DatasetSplit, StructuredOutputMode, Task
from kiln_ai.utils.config import Config

logger = logging.getLogger(__name__)

# https://docs.fireworks.ai/fine-tuning/fine-tuning-models#supported-base-models-loras-on-serverless
serverless_models = [
    "accounts/fireworks/models/llama-v3p1-8b-instruct",
    "accounts/fireworks/models/llama-v3p1-70b-instruct",
]


class FireworksFinetune(BaseFinetuneAdapter):
    """
    A fine-tuning adapter for Fireworks.
    """

    async def status(self) -> FineTuneStatus:
        status, _ = await self._status()
        # update the datamodel if the status has changed
        if self.datamodel.latest_status != status.status:
            self.datamodel.latest_status = status.status
            if self.datamodel.path:
                self.datamodel.save_to_file()

        # Deploy every time we check status. This can help resolve issues, Fireworks will undeploy unused models after a time.
        if status.status == FineTuneStatusType.completed:
            deployed = await self._deploy()
            if not deployed:
                status.message = "Fine-tuning job completed but failed to deploy model."

        return status

    async def _status(self) -> Tuple[FineTuneStatus, str | None]:
        try:
            api_key = Config.shared().fireworks_api_key
            account_id = Config.shared().fireworks_account_id
            if not api_key or not account_id:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Fireworks API key or account ID not set",
                ), None
            fine_tuning_job_id = self.datamodel.provider_id
            if not fine_tuning_job_id:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Fine-tuning job ID not set. Can not retrieve status.",
                ), None
            # Fireworks uses path style IDs
            url = f"https://api.fireworks.ai/v1/{fine_tuning_job_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=15.0)

            if response.status_code != 200:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message=f"Error retrieving fine-tuning job status: [{response.status_code}] {response.text}",
                ), None
            data = response.json()
            model_id = data.get("outputModel")

            if "state" not in data:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Invalid response from Fireworks (no state).",
                ), model_id

            state = data["state"]
            if state in ["FAILED", "DELETING", "JOB_STATE_FAILED"]:
                return FineTuneStatus(
                    status=FineTuneStatusType.failed,
                    message="Fine-tuning job failed",
                ), model_id
            elif state in [
                "CREATING",
                "PENDING",
                "RUNNING",
                "JOB_STATE_VALIDATING",
                "JOB_STATE_RUNNING",
            ]:
                return FineTuneStatus(
                    status=FineTuneStatusType.running,
                    message=f"Fine-tuning job is running [{state}]",
                ), model_id
            elif state in ["COMPLETED", "JOB_STATE_COMPLETED"]:
                return FineTuneStatus(
                    status=FineTuneStatusType.completed,
                    message="Fine-tuning job completed",
                ), model_id
            else:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message=f"Unknown fine-tuning job status [{state}]",
                ), model_id
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
            # Fireworks doesn't support function calls or json schema, so we'll use json mode at call time
            self.datamodel.structured_output_mode = StructuredOutputMode.json_mode

        train_file_id = await self.generate_and_upload_jsonl(
            dataset, self.datamodel.train_split_name, task, format
        )

        api_key = Config.shared().fireworks_api_key
        account_id = Config.shared().fireworks_account_id
        if not api_key or not account_id:
            raise ValueError("Fireworks API key or account ID not set")

        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/supervisedFineTuningJobs"
        # Limit the display name to 60 characters
        display_name = (
            f"Kiln AI fine-tuning [ID:{self.datamodel.id}][name:{self.datamodel.name}]"[
                :60
            ]
        )
        payload: dict[str, str | dict[str, str | bool]] = {
            "dataset": f"accounts/{account_id}/datasets/{train_file_id}",
            "displayName": display_name,
            "baseModel": self.datamodel.base_model_id,
        }
        # Add W&B config if API key is set
        if Config.shared().wandb_api_key:
            payload["wandbConfig"] = {
                "enabled": True,
                "project": "Kiln_AI",
                "apiKey": Config.shared().wandb_api_key,
            }
        hyperparameters = self.create_payload_parameters(self.datamodel.parameters)
        payload.update(hyperparameters)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise ValueError(
                f"Failed to create fine-tuning job: [{response.status_code}] {response.text}"
            )
        data = response.json()
        if "name" not in data:
            raise ValueError(
                f"Failed to create fine-tuning job with valid name: [{response.status_code}] {response.text}"
            )

        # name is actually the ID of the fine-tune job,
        # model ID is the model that results from the fine-tune job
        job_id = data["name"]
        self.datamodel.provider_id = job_id

        # Fireworks has 2 different fine tuning endpoints, and depending which you use, the URLs change
        self.datamodel.properties["endpoint_version"] = "v2"

        if self.datamodel.path:
            self.datamodel.save_to_file()

    async def generate_and_upload_jsonl(
        self, dataset: DatasetSplit, split_name: str, task: Task, format: DatasetFormat
    ) -> str:
        formatter = DatasetFormatter(
            dataset=dataset,
            system_message=self.datamodel.system_message,
            thinking_instructions=self.datamodel.thinking_instructions,
        )
        path = formatter.dump_to_file(split_name, format, self.datamodel.data_strategy)

        # First call creates the dataset
        api_key = Config.shared().fireworks_api_key
        account_id = Config.shared().fireworks_account_id
        if not api_key or not account_id:
            raise ValueError("Fireworks API key or account ID not set")
        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/datasets"
        dataset_id = str(uuid4())
        payload = {
            "datasetId": dataset_id,
            "dataset": {
                "displayName": f"Kiln AI fine-tuning for dataset ID [{dataset.id}] split [{split_name}]",
                "userUploaded": {},
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            create_dataset_response = await client.post(
                url, json=payload, headers=headers
            )
        if create_dataset_response.status_code != 200:
            raise ValueError(
                f"Failed to create dataset: [{create_dataset_response.status_code}] {create_dataset_response.text}"
            )

        # Second call uploads the dataset
        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/datasets/{dataset_id}:upload"
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        async with httpx.AsyncClient() as client:
            with open(path, "rb") as f:
                files = {"file": f}
                upload_dataset_response = await client.post(
                    url,
                    headers=headers,
                    files=files,
                )
        if upload_dataset_response.status_code != 200:
            raise ValueError(
                f"Failed to upload dataset: [{upload_dataset_response.status_code}] {upload_dataset_response.text}"
            )

        # Third call checks it's "READY"
        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/datasets/{dataset_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise ValueError(
                f"Failed to check dataset status: [{response.status_code}] {response.text}"
            )
        data = response.json()
        if data["state"] != "READY":
            raise ValueError(f"Dataset is not ready [{data['state']}]")

        return dataset_id

    @classmethod
    def available_parameters(cls) -> list[FineTuneParameter]:
        return [
            FineTuneParameter(
                name="epochs",
                description="The number of epochs to fine-tune for. If not provided, defaults to a recommended value.",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="learning_rate",
                description="The learning rate to use for fine-tuning. If not provided, defaults to a recommended value.",
                type="float",
                optional=True,
            ),
            FineTuneParameter(
                name="batch_size",
                description="The batch size of dataset used in training can be configured with a positive integer less than 1024 and in power of 2. If not specified, a reasonable default value will be chosen.",
                type="int",
                optional=True,
            ),
            FineTuneParameter(
                name="lora_rank",
                description="LoRA rank refers to the dimensionality of trainable matrices in Low-Rank Adaptation fine-tuning, balancing model adaptability and computational efficiency in fine-tuning large language models. The LoRA rank used in training can be configured with a positive integer with a max value of 32. If not specified, a reasonable default value will be chosen.",
                type="int",
                optional=True,
            ),
        ]

    def create_payload_parameters(
        self, parameters: dict[str, str | int | float | bool]
    ) -> dict:
        payload = {
            "loraRank": parameters.get("lora_rank"),
            "epochs": parameters.get("epochs"),
            "learningRate": parameters.get("learning_rate"),
            "batchSize": parameters.get("batch_size"),
        }
        return {k: v for k, v in payload.items() if v is not None}

    async def _deploy(self) -> bool:
        if self.datamodel.base_model_id in serverless_models:
            return await self._deploy_serverless()
        else:
            return await self._check_or_deploy_server()

    def api_key_and_account_id(self) -> Tuple[str, str]:
        api_key = Config.shared().fireworks_api_key
        account_id = Config.shared().fireworks_account_id
        if not api_key or not account_id:
            raise ValueError("Fireworks API key or account ID not set")
        return api_key, account_id

    def deployment_display_name(self) -> str:
        # Limit the display name to 60 characters
        display_name = f"Kiln AI fine-tuned model [ID:{self.datamodel.id}][name:{self.datamodel.name}]"[
            :60
        ]
        return display_name

    async def model_id_checking_status(self) -> str | None:
        # Model ID != fine tune ID on Fireworks. Model is the result of the tune job. Call status to get it.
        status, model_id = await self._status()
        if status.status != FineTuneStatusType.completed:
            return None
        if not model_id or not isinstance(model_id, str):
            return None
        return model_id

    async def _deploy_serverless(self) -> bool:
        # Now we "deploy" the model using PEFT serverless.
        # A bit complicated: most fireworks deploys are server based.
        # However, a Lora can be serverless (PEFT).
        # By calling the deploy endpoint WITHOUT first creating a deployment ID, it will only deploy if it can be done serverless.
        # https://docs.fireworks.ai/models/deploying#deploying-to-serverless
        # This endpoint will return 400 if already deployed with code 9, so we consider that a success.

        api_key, account_id = self.api_key_and_account_id()

        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/deployedModels"
        model_id = await self.model_id_checking_status()
        if not model_id:
            logger.error(
                "Model ID not found - can't deploy model to Fireworks serverless"
            )
            return False

        payload = {
            "displayName": self.deployment_display_name(),
            "model": model_id,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        # Fresh deploy worked (200) or already deployed (code=9)
        if response.status_code == 200 or response.json().get("code") == 9:
            # Update the datamodel if the model ID has changed, which makes it available to use in the UI
            if self.datamodel.fine_tune_model_id != model_id:
                self.datamodel.fine_tune_model_id = model_id
                if self.datamodel.path:
                    self.datamodel.save_to_file()
            return True

        logger.error(
            f"Failed to deploy model to Fireworks serverless: [{response.status_code}] {response.text}"
        )
        return False

    async def _check_or_deploy_server(self) -> bool:
        """
        Check if the model is already deployed. If not, deploy it to a dedicated server.
        """

        # Check if the model is already deployed
        # If it's fine_tune_model_id is set, it might be deployed. However, Fireworks deletes them over time so we need to check.
        if self.datamodel.fine_tune_model_id:
            deployments = await self._fetch_all_deployments()
            for deployment in deployments:
                if deployment[
                    "baseModel"
                ] == self.datamodel.fine_tune_model_id and deployment["state"] in [
                    "READY",
                    "CREATING",
                ]:
                    return True

        # If the model is not deployed, deploy it
        return await self._deploy_server()

    async def _deploy_server(self) -> bool:
        # For models that are not serverless, we just need to deploy the model to a server.
        # We use a scale-to-zero on-demand deployment. If you stop using it, it
        # will scale to zero and charges will stop.
        model_id = await self.model_id_checking_status()
        if not model_id:
            logger.error("Model ID not found - can't deploy model to Fireworks server")
            return False

        api_key, account_id = self.api_key_and_account_id()
        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/deployments"

        payload = {
            "displayName": self.deployment_display_name(),
            "description": "Deployed by Kiln AI",
            # Allow scale to zero
            "minReplicaCount": 0,
            "autoscalingPolicy": {
                "scaleUpWindow": "30s",
                "scaleDownWindow": "300s",
                # Scale to zero after 5 minutes of inactivity - this is the minimum allowed
                "scaleToZeroWindow": "300s",
            },
            "baseModel": model_id,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            basemodel = response.json().get("baseModel")
            if basemodel is not None and isinstance(basemodel, str):
                self.datamodel.fine_tune_model_id = basemodel
                if self.datamodel.path:
                    self.datamodel.save_to_file()
                return True

        logger.error(
            f"Failed to deploy model to Fireworks server: [{response.status_code}] {response.text}"
        )
        return False

    async def _fetch_all_deployments(self) -> List[dict]:
        """
        Fetch all deployments for an account.
        """
        api_key, account_id = self.api_key_and_account_id()

        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/deployments"

        params = {
            # Note: filter param does not work for baseModel, which would have been ideal, and ideally would have been documented. Instead we'll fetch all and filter.
            # Max page size
            "pageSize": 200,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
        }

        deployments = []

        # Paginate through all deployments
        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(url, params=params, headers=headers)
                json = response.json()
                if "deployments" not in json or not isinstance(
                    json["deployments"], list
                ):
                    raise ValueError(
                        f"Invalid response from Fireworks. Expected list of deployments in 'deployments' key: [{response.status_code}] {response.text}"
                    )
                deployments.extend(json["deployments"])
                next_page_token = json.get("nextPageToken")
                if (
                    next_page_token
                    and isinstance(next_page_token, str)
                    and len(next_page_token) > 0
                ):
                    params = {
                        "pageSize": 200,
                        "pageToken": next_page_token,
                    }
                else:
                    break

        return deployments
