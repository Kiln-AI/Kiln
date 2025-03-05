from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from kiln_ai.adapters.fine_tune.base_finetune import FineTuneParameter, FineTuneStatus
from kiln_ai.adapters.fine_tune.dataset_formatter import DatasetFormat, DatasetFormatter
from kiln_ai.adapters.fine_tune.finetune_registry import finetune_registry
from kiln_ai.adapters.ml_model_list import (
    ModelProviderName,
    built_in_models,
)
from kiln_ai.adapters.prompt_builders import (
    chain_of_thought_prompt,
    prompt_builder_from_id,
)
from kiln_ai.adapters.provider_tools import (
    provider_enabled,
    provider_name_from_id,
)
from kiln_ai.datamodel import (
    DatasetSplit,
    Finetune,
    FinetuneDataStrategy,
    FineTuneStatusType,
    Task,
)
from kiln_ai.datamodel.dataset_filters import (
    DatasetFilterId,
)
from kiln_ai.datamodel.dataset_split import (
    AllSplitDefinition,
    Train60Test20Val20SplitDefinition,
    Train80Test10Val10SplitDefinition,
    Train80Test20SplitDefinition,
)
from kiln_ai.utils.name_generator import generate_memorable_name
from kiln_server.task_api import task_from_id
from pydantic import BaseModel


class FinetuneProviderModel(BaseModel):
    """Finetune provider model: a model a provider supports for fine-tuning"""

    name: str
    id: str


class FinetuneProvider(BaseModel):
    """Finetune provider: list of models a provider supports for fine-tuning"""

    name: str
    id: str
    enabled: bool
    models: list[FinetuneProviderModel]


class DatasetSplitType(Enum):
    """Dataset split types used in the API. Any split type can be created in code."""

    TRAIN_TEST = "train_test"
    TRAIN_TEST_VAL = "train_test_val"
    TRAIN_TEST_VAL_80 = "train_test_val_80"
    ALL = "all"


api_split_types = {
    DatasetSplitType.TRAIN_TEST: Train80Test20SplitDefinition,
    DatasetSplitType.TRAIN_TEST_VAL: Train60Test20Val20SplitDefinition,
    DatasetSplitType.TRAIN_TEST_VAL_80: Train80Test10Val10SplitDefinition,
    DatasetSplitType.ALL: AllSplitDefinition,
}


class CreateDatasetSplitRequest(BaseModel):
    """Request to create a dataset split"""

    dataset_split_type: DatasetSplitType
    filter_id: DatasetFilterId
    name: str | None = None
    description: str | None = None


class CreateFinetuneRequest(BaseModel):
    """Request to create a finetune"""

    name: str | None = None
    description: str | None = None
    dataset_id: str
    train_split_name: str
    validation_split_name: str | None = None
    parameters: dict[str, str | int | float | bool]
    provider: str
    base_model_id: str
    system_message_generator: str | None = None
    custom_system_message: str | None = None
    custom_thinking_instructions: str | None = None
    data_strategy: FinetuneDataStrategy


class FinetuneWithStatus(BaseModel):
    """Finetune with status"""

    finetune: Finetune
    status: FineTuneStatus


class UpdateFinetuneRequest(BaseModel):
    """Request to update a finetune"""

    name: str
    description: str | None = None


def finetune_from_id(project_id: str, task_id: str, finetune_id: str) -> Finetune:
    task = task_from_id(project_id, task_id)
    finetune = Finetune.from_id_and_parent_path(finetune_id, task.path)
    if finetune is None:
        raise HTTPException(
            status_code=404,
            detail=f"Finetune with ID '{finetune_id}' not found",
        )
    return finetune


def connect_fine_tune_api(app: FastAPI):
    @app.get("/api/projects/{project_id}/tasks/{task_id}/dataset_splits")
    async def dataset_splits(project_id: str, task_id: str) -> list[DatasetSplit]:
        task = task_from_id(project_id, task_id)
        return task.dataset_splits()

    @app.get("/api/projects/{project_id}/tasks/{task_id}/finetunes")
    async def finetunes(
        project_id: str, task_id: str, update_status: bool = False
    ) -> list[Finetune]:
        task = task_from_id(project_id, task_id)
        finetunes = task.finetunes()

        # Update the status of each finetune
        if update_status:
            for finetune in finetunes:
                # Skip "final" status states, as they are not updated
                if finetune.latest_status not in [
                    FineTuneStatusType.completed,
                    FineTuneStatusType.failed,
                ]:
                    provider_name = ModelProviderName[finetune.provider]
                    # fetching status updates the datamodel
                    ft_adapter = finetune_registry[provider_name](finetune)
                    await ft_adapter.status()

        return finetunes

    @app.get("/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}")
    async def finetune(
        project_id: str, task_id: str, finetune_id: str
    ) -> FinetuneWithStatus:
        finetune = finetune_from_id(project_id, task_id, finetune_id)
        if finetune.provider not in finetune_registry:
            raise HTTPException(
                status_code=400,
                detail=f"Fine tune provider '{finetune.provider}' not found",
            )
        finetune_adapter = finetune_registry[finetune.provider]
        status = await finetune_adapter(finetune).status()
        return FinetuneWithStatus(finetune=finetune, status=status)

    @app.patch("/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}")
    async def update_finetune(
        project_id: str,
        task_id: str,
        finetune_id: str,
        request: UpdateFinetuneRequest,
    ) -> Finetune:
        finetune = finetune_from_id(project_id, task_id, finetune_id)
        finetune.name = request.name
        finetune.description = request.description
        finetune.save_to_file()
        return finetune

    @app.get("/api/finetune_providers")
    async def finetune_providers() -> list[FinetuneProvider]:
        provider_models: dict[ModelProviderName, list[FinetuneProviderModel]] = {}

        # Collect models by provider
        for model in built_in_models:
            for provider in model.providers:
                if provider.provider_finetune_id:
                    if provider.name not in provider_models:
                        provider_models[provider.name] = []
                    provider_models[provider.name].append(
                        FinetuneProviderModel(
                            name=model.friendly_name, id=provider.provider_finetune_id
                        )
                    )

        # Create provider entries
        providers: list[FinetuneProvider] = []
        for provider_name, models in provider_models.items():
            providers.append(
                FinetuneProvider(
                    name=provider_name_from_id(provider_name),
                    id=provider_name,
                    enabled=await provider_enabled(provider_name),
                    models=models,
                )
            )

        return providers

    @app.get("/api/finetune/hyperparameters/{provider_id}")
    async def finetune_hyperparameters(
        provider_id: str,
    ) -> list[FineTuneParameter]:
        if provider_id not in finetune_registry:
            raise HTTPException(
                status_code=400, detail=f"Fine tune provider '{provider_id}' not found"
            )
        finetune_adapter_class = finetune_registry[provider_id]
        return finetune_adapter_class.available_parameters()

    @app.post("/api/projects/{project_id}/tasks/{task_id}/dataset_splits")
    async def create_dataset_split(
        project_id: str, task_id: str, request: CreateDatasetSplitRequest
    ) -> DatasetSplit:
        task = task_from_id(project_id, task_id)
        split_definitions = api_split_types[request.dataset_split_type]

        name = request.name
        if not name:
            name = generate_memorable_name()

        dataset_split = DatasetSplit.from_task(
            name,
            task,
            split_definitions,
            filter_id=request.filter_id,
            description=request.description,
        )
        dataset_split.save_to_file()
        return dataset_split

    @app.post("/api/projects/{project_id}/tasks/{task_id}/finetunes")
    async def create_finetune(
        project_id: str, task_id: str, request: CreateFinetuneRequest
    ) -> Finetune:
        task = task_from_id(project_id, task_id)
        if request.provider not in finetune_registry:
            raise HTTPException(
                status_code=400,
                detail=f"Fine tune provider '{request.provider}' not found",
            )
        finetune_adapter_class = finetune_registry[request.provider]

        dataset = DatasetSplit.from_id_and_parent_path(request.dataset_id, task.path)
        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset split with ID '{request.dataset_id}' not found",
            )

        if not request.system_message_generator and not request.custom_system_message:
            raise HTTPException(
                status_code=400,
                detail="System message generator or custom system message is required",
            )

        system_message = system_message_from_request(
            task, request.custom_system_message, request.system_message_generator
        )
        thinking_instructions = thinking_instructions_from_request(
            task, request.data_strategy, request.custom_thinking_instructions
        )

        _, finetune_model = await finetune_adapter_class.create_and_start(
            dataset=dataset,
            provider_id=request.provider,
            provider_base_model_id=request.base_model_id,
            train_split_name=request.train_split_name,
            system_message=system_message,
            thinking_instructions=thinking_instructions,
            parameters=request.parameters,
            name=request.name,
            description=request.description,
            validation_split_name=request.validation_split_name,
            data_strategy=request.data_strategy,
        )

        return finetune_model

    @app.get("/api/download_dataset_jsonl")
    async def download_dataset_jsonl(
        project_id: str,
        task_id: str,
        dataset_id: str,
        split_name: str,
        format_type: str,
        data_strategy: str,
        system_message_generator: str | None = None,
        custom_system_message: str | None = None,
        custom_thinking_instructions: str | None = None,
    ) -> StreamingResponse:
        if format_type not in [format.value for format in DatasetFormat]:
            raise HTTPException(
                status_code=400,
                detail=f"Dataset format '{format_type}' not found",
            )
        format_type_typed = DatasetFormat(format_type)
        if data_strategy not in [strategy.value for strategy in FinetuneDataStrategy]:
            raise HTTPException(
                status_code=400,
                detail=f"Data strategy '{data_strategy}' not found",
            )
        data_strategy_typed = FinetuneDataStrategy(data_strategy)

        task = task_from_id(project_id, task_id)
        dataset = DatasetSplit.from_id_and_parent_path(dataset_id, task.path)
        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset split with ID '{dataset_id}' not found",
            )
        if split_name not in dataset.split_contents:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset split with name '{split_name}' not found",
            )

        system_message = system_message_from_request(
            task, custom_system_message, system_message_generator
        )
        thinking_instructions = thinking_instructions_from_request(
            task, data_strategy_typed, custom_thinking_instructions
        )

        dataset_formatter = DatasetFormatter(
            dataset=dataset,
            system_message=system_message,
            thinking_instructions=thinking_instructions,
        )
        path = dataset_formatter.dump_to_file(
            split_name,
            format_type_typed,
            data_strategy_typed,
        )

        # set headers to force download in a browser
        headers = {
            "Content-Disposition": f'attachment; filename="{path.name}"',
            "Content-Type": "application/jsonl",
        }

        return StreamingResponse(open(path, "rb"), headers=headers)


def system_message_from_request(
    task: Task, custom_system_message: str | None, system_message_generator: str | None
) -> str:
    system_message = custom_system_message
    if (
        not system_message
        or len(system_message) == 0
        and system_message_generator is not None
    ):
        if system_message_generator is None:
            raise HTTPException(
                status_code=400,
                detail="System message generator is required when custom system message is not provided",
            )
        try:
            prompt_builder = prompt_builder_from_id(system_message_generator, task)
            system_message = prompt_builder.build_prompt(
                include_json_instructions=False
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error generating system message using generator: {system_message_generator}. Source error: {str(e)}",
            )
    if system_message is None or len(system_message) == 0:
        raise HTTPException(
            status_code=400,
            detail="System message is required",
        )

    return system_message


def thinking_instructions_from_request(
    task: Task,
    data_strategy: FinetuneDataStrategy,
    custom_thinking_instructions: str | None,
) -> str | None:
    if data_strategy != FinetuneDataStrategy.final_and_intermediate:
        # Not using COT/Thinking style
        return None

    if custom_thinking_instructions:
        # prefer custom instructions
        return custom_thinking_instructions

    # default for this task
    return chain_of_thought_prompt(task)
