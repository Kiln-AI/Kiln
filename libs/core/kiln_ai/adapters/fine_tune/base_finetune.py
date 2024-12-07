from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.datamodel import DatasetSplit, FineTuneStatusType
from kiln_ai.datamodel import Finetune as FinetuneModel
from kiln_ai.utils.name_generator import generate_memorable_name


class FineTuneStatus(BaseModel):
    """
    The status of a fine-tune, including a user friendly message.
    """

    status: FineTuneStatusType
    message: str | None = None


class FineTuneParameter(BaseModel):
    """
    A parameter for a fine-tune. Hyperparameters, etc.
    """

    name: str
    type: Literal["string", "int", "float", "bool"]
    description: str
    optional: bool = True


TYPE_MAP = {
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
}


class BaseFinetuneAdapter(ABC):
    """
    A base class for fine-tuning adapters.
    """

    def __init__(
        self,
        datamodel: FinetuneModel,
    ):
        self.datamodel = datamodel

    @classmethod
    async def create_and_start(
        cls,
        dataset: DatasetSplit,
        provider_id: str,
        provider_base_model_id: str,
        train_split_name: str,
        system_message: str,
        parameters: dict[str, str | int | float | bool] = {},
        name: str | None = None,
        description: str | None = None,
        validation_split_name: str | None = None,
    ) -> tuple["BaseFinetuneAdapter", FinetuneModel]:
        """
        Create and start a fine-tune.
        """

        cls.check_valid_provider_model(provider_id, provider_base_model_id)

        if not dataset.id:
            raise ValueError("Dataset must have an id")

        if train_split_name not in dataset.split_contents:
            raise ValueError(f"Train split {train_split_name} not found in dataset")

        if (
            validation_split_name
            and validation_split_name not in dataset.split_contents
        ):
            raise ValueError(
                f"Validation split {validation_split_name} not found in dataset"
            )

        # Default name if not provided
        if name is None:
            name = generate_memorable_name()

        cls.validate_parameters(parameters)
        parent_task = dataset.parent_task()
        if parent_task is None or not parent_task.path:
            raise ValueError("Dataset must have a parent task with a path")

        datamodel = FinetuneModel(
            name=name,
            description=description,
            provider=provider_id,
            base_model_id=provider_base_model_id,
            dataset_split_id=dataset.id,
            train_split_name=train_split_name,
            validation_split_name=validation_split_name,
            parameters=parameters,
            system_message=system_message,
            parent=parent_task,
        )

        adapter = cls(datamodel)
        await adapter._start(dataset)

        datamodel.save_to_file()

        return adapter, datamodel

    @abstractmethod
    async def _start(self, dataset: DatasetSplit) -> None:
        """
        Start the fine-tune.
        """
        pass

    @abstractmethod
    async def status(self) -> FineTuneStatus:
        """
        Get the status of the fine-tune.
        """
        pass

    @classmethod
    def available_parameters(cls) -> list[FineTuneParameter]:
        """
        Returns a list of parameters that can be provided for this fine-tune. Includes hyperparameters, etc.
        """
        return []

    @classmethod
    def validate_parameters(
        cls, parameters: dict[str, str | int | float | bool]
    ) -> None:
        """
        Validate the parameters for this fine-tune.
        """
        # Check required parameters and parameter types
        available_parameters = cls.available_parameters()
        for parameter in available_parameters:
            if not parameter.optional and parameter.name not in parameters:
                raise ValueError(f"Parameter {parameter.name} is required")
            elif parameter.name in parameters:
                # check parameter is correct type
                expected_type = TYPE_MAP[parameter.type]
                value = parameters[parameter.name]

                # Strict type checking for numeric types
                if expected_type is float and not isinstance(value, float):
                    raise ValueError(
                        f"Parameter {parameter.name} must be a float, got {type(value)}"
                    )
                elif expected_type is int and not isinstance(value, int):
                    raise ValueError(
                        f"Parameter {parameter.name} must be an integer, got {type(value)}"
                    )
                elif not isinstance(value, expected_type):
                    raise ValueError(
                        f"Parameter {parameter.name} must be type {expected_type}, got {type(value)}"
                    )

        allowed_parameters = [p.name for p in available_parameters]
        for parameter_key in parameters:
            if parameter_key not in allowed_parameters:
                raise ValueError(f"Parameter {parameter_key} is not available")

    @classmethod
    def check_valid_provider_model(
        cls, provider_id: str, provider_base_model_id: str
    ) -> None:
        """
        Check if the provider and base model are valid.
        """
        for model in built_in_models:
            for provider in model.providers:
                if (
                    provider.name == provider_id
                    and provider.provider_finetune_id == provider_base_model_id
                ):
                    return
        raise ValueError(
            f"Provider {provider_id} with base model {provider_base_model_id} is not available"
        )
