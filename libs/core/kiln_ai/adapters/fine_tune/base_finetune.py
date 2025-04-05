from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from kiln_ai.adapters.ml_model_list import built_in_models
from kiln_ai.datamodel import (
    DatasetSplit,
    FinetuneDataStrategy,
    FineTuneStatusType,
    Task,
)
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
        thinking_instructions: str | None,
        data_strategy: FinetuneDataStrategy,
        parameters: dict[str, str | int | float | bool] = {},
        name: str | None = None,
        description: str | None = None,
        validation_split_name: str | None = None,
    ) -> tuple["BaseFinetuneAdapter", FinetuneModel]:
        """
        Create and start a fine-tune.
        """

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
            system_message=cls.augment_system_message(system_message, parent_task),
            thinking_instructions=thinking_instructions,
            parent=parent_task,
            data_strategy=data_strategy,
        )

        adapter = cls(datamodel)
        await adapter._start(dataset)

        datamodel.save_to_file()

        return adapter, datamodel

    @classmethod
    def augment_system_message(cls, system_message: str, task: Task) -> str:
        """
        Augment the system message with additional instructions, such as JSON instructions.
        """

        # Base implementation does nothing, can be overridden by subclasses
        return system_message

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
