from uuid import uuid4

import httpx

from kiln_ai.adapters.fine_tune.base_finetune import (
    BaseFinetuneAdapter,
    FineTuneParameter,
    FineTuneStatus,
    FineTuneStatusType,
)
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.datamodel import DatasetSplit, Task
from kiln_ai.utils.config import Config


class FireworksFinetune(BaseFinetuneAdapter):
    """
    A fine-tuning adapter for Fireworks.
    """

    async def status(self) -> FineTuneStatus:
        status = await self._status()
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

    async def _status(self) -> FineTuneStatus:
        try:
            api_key = Config.shared().fireworks_api_key
            account_id = Config.shared().fireworks_account_id
            if not api_key or not account_id:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Fireworks API key or account ID not set",
                )
            fine_tuning_job_id = self.datamodel.provider_id
            if not fine_tuning_job_id:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Fine-tuning job ID not set. Can not retrieve status.",
                )
            # Fireworks uses path style IDs
            url = f"https://api.fireworks.ai/v1/{fine_tuning_job_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=15.0)

            if response.status_code != 200:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message=f"Error retrieving fine-tuning job status: [{response.status_code}] {response.text}",
                )
            data = response.json()

            if "state" not in data:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message="Invalid response from Fireworks (no state).",
                )

            state = data["state"]
            if state in ["FAILED", "DELETING"]:
                return FineTuneStatus(
                    status=FineTuneStatusType.failed,
                    message="Fine-tuning job failed",
                )
            elif state in ["CREATING", "PENDING", "RUNNING"]:
                return FineTuneStatus(
                    status=FineTuneStatusType.running,
                    message=f"Fine-tuning job is running [{state}]",
                )
            elif state == "COMPLETED":
                return FineTuneStatus(
                    status=FineTuneStatusType.completed,
                    message="Fine-tuning job completed",
                )
            else:
                return FineTuneStatus(
                    status=FineTuneStatusType.unknown,
                    message=f"Unknown fine-tuning job status [{state}]",
                )
        except Exception as e:
            return FineTuneStatus(
                status=FineTuneStatusType.unknown,
                message=f"Error retrieving fine-tuning job status: {e}",
            )

    async def _start(self, dataset: DatasetSplit) -> None:
        task = self.datamodel.parent_task()
        if not task:
            raise ValueError("Task is required to start a fine-tune")

        train_file_id = await self.generate_and_upload_jsonl(
            dataset, self.datamodel.train_split_name, task
        )

        api_key = Config.shared().fireworks_api_key
        account_id = Config.shared().fireworks_account_id
        if not api_key or not account_id:
            raise ValueError("Fireworks API key or account ID not set")

        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/fineTuningJobs"
        # Model ID != fine tune ID on Fireworks. Model is the result of the tune job.
        model_id = str(uuid4())
        # Limit the display name to 60 characters
        display_name = (
            f"Kiln AI fine-tuning [ID:{self.datamodel.id}][name:{self.datamodel.name}]"[
                :60
            ]
        )
        payload = {
            "modelId": model_id,
            "dataset": f"accounts/{account_id}/datasets/{train_file_id}",
            "displayName": display_name,
            "baseModel": self.datamodel.base_model_id,
            "conversation": {
                # TODO: check model and load the correct jinja template
                "jinjaTemplate": LLAMA_3_1_JINJA_TEMPLATE,
            },
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
        # Keep track of the expected model ID before it's deployed as a property. We move it to fine_tune_model_id after deployment.
        self.datamodel.properties["undeployed_model_id"] = (
            f"accounts/{account_id}/models/{model_id}"
        )
        if self.datamodel.path:
            self.datamodel.save_to_file()

    async def generate_and_upload_jsonl(
        self, dataset: DatasetSplit, split_name: str, task: Task
    ) -> str:
        formatter = DatasetFormatter(dataset, self.datamodel.system_message)
        # OpenAI compatible: https://docs.fireworks.ai/fine-tuning/fine-tuning-models#conversation
        # Note: Fireworks does not support tool calls (tested and failed on llama 3.1 70b)
        format = DatasetFormat.OPENAI_CHAT_JSONL
        path = formatter.dump_to_file(split_name, format)

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
        # Now we "deploy" the model using PEFT serverless.
        # A bit complicated: most fireworks deploys are server based.
        # However, a Lora can be serverless (PEFT).
        # By calling the deploy endpoint WITHOUT first creating a deployment ID, it will only deploy if it can be done serverless.
        # https://docs.fireworks.ai/models/deploying#deploying-to-serverless
        # This endpoint will return 400 if already deployed with code 9, so we consider that a success.

        api_key = Config.shared().fireworks_api_key
        account_id = Config.shared().fireworks_account_id
        if not api_key or not account_id:
            raise ValueError("Fireworks API key or account ID not set")

        model_id = self.datamodel.properties.get("undeployed_model_id")
        if not model_id or not isinstance(model_id, str):
            return False

        url = f"https://api.fireworks.ai/v1/accounts/{account_id}/deployedModels"
        # Limit the display name to 60 characters
        display_name = f"Kiln AI fine-tuned model [ID:{self.datamodel.id}][name:{self.datamodel.name}]"[
            :60
        ]
        payload = {
            "displayName": display_name,
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

        return False


LLAMA_3_1_JINJA_TEMPLATE = """
{%- set _mode = mode | default('generate', true) -%}
{%- set stop_token = '<|eot_id|>' -%}
{%- set message_roles = ['SYSTEM', 'USER', 'ASSISTANT'] -%}
{%- set ns = namespace(initial_system_message_handled=false, last_assistant_index_for_eos=-1, messages=messages) -%}
{%- for message in ns.messages -%}
    {%- if not message.get('role') -%}
        {{ raise_exception('Key [role] is missing. Original input: ' +  message|tojson) }}
    {%- endif -%}
    {%- if message['role'] | upper not in message_roles -%}
        {{ raise_exception('Invalid role ' + message['role']|tojson + '. Only ' + message_roles|tojson + ' are supported.') }}
    {%- endif -%}
    {%- if 'content' not in message  -%}
        {{ raise_exception('Key [content] is missing. Original input: ' +  message|tojson) }}
    {%- endif -%}
    {%- if loop.last and message['role'] | upper == 'ASSISTANT' -%}
        {%- set ns.last_assistant_index_for_eos = loop.index0 -%}
    {%- endif -%}
{%- endfor -%}
{%- if _mode == 'generate' -%}
    {{ bos_token }}
{%- endif -%}
{%- for message in ns.messages -%}
    {%- if message['role'] | upper == 'SYSTEM' and not ns.initial_system_message_handled -%}
        {%- set ns.initial_system_message_handled = true -%}
        {{ '<|start_header_id|>system<|end_header_id|>\n\n' + message['content'] + stop_token }}
    {%- elif message['role'] | upper != 'SYSTEM' -%}
        {%- if (message['role'] | upper == 'USER') != ((loop.index0 - (1 if ns.initial_system_message_handled else 0)) % 2 == 0) -%}
            {{ raise_exception('Conversation roles must alternate user/assistant/user/assistant/...') }}
        {%- endif -%}
        {%- if message['role'] | upper == 'USER' -%}
            {{ '<|start_header_id|>user<|end_header_id|>\n\n' + message['content'] + 
               ('' if 'tool_call_schema' not in message  else '\n\nRespond with  {"name": function name, "parameters": dictionary of argument name and its value}. Do not use variables.\n\n' + message['tool_call_schema']) 
            }}{{ stop_token }}
        {%- elif message['role'] | upper == 'ASSISTANT' and message['content'] is not none -%}
            {%- if _mode == 'train' -%}
                {{ '<|start_header_id|>assistant<|end_header_id|>\n\n' + unk_token + message['content'] + stop_token + unk_token }}
            {%- else -%}
                {{ '<|start_header_id|>assistant<|end_header_id|>\n\n' + message['content'] + (stop_token if loop.index0 != ns.last_assistant_index_for_eos else '') }}
            {%- endif -%}
        {%- elif message['role'] | upper == 'ASSISTANT' and 'tool_call_json' in message and message['tool_call_json'] is not none -%}
            {%- if _mode == 'train' -%}
                {{ '<|start_header_id|>assistant<|end_header_id|>\n\n' + unk_token + message['tool_call_json'] + stop_token + unk_token }}
            {%- else -%}
                {{ '<|start_header_id|>assistant<|end_header_id|>\n\n' + message['tool_call_json'] + (stop_token if loop.index0 != ns.last_assistant_index_for_eos else '') }}
            {%- endif -%}
        {%- endif -%}
    {%- endif -%}
{%- endfor -%}
{%- if _mode == 'generate' and ns.last_assistant_index_for_eos == -1 -%}
    {{ '<|start_header_id|>assistant<|end_header_id|>' }}
{%- endif -%}
"""
