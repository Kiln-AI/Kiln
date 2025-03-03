from typing import TYPE_CHECKING, Dict, Union

from pydantic import Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.basemodel import NAME_FIELD, KilnParentedModel
from kiln_ai.datamodel.datamodel_enums import (
    FinetuneDataStrategy,
    FineTuneStatusType,
    StructuredOutputMode,
)

if TYPE_CHECKING:
    from kiln_ai.datamodel.task import Task


class Finetune(KilnParentedModel):
    """
    The Kiln fine-tune datamodel.

    Initially holds a reference to a training job, with needed identifiers to update the status. When complete, contains the new model ID.
    """

    name: str = NAME_FIELD
    description: str | None = Field(
        default=None,
        description="A description of the fine-tune for you and your team. Not used in training.",
    )
    structured_output_mode: StructuredOutputMode | None = Field(
        default=None,
        description="The mode to use to train the model for structured output, if it was trained with structured output. Will determine how we call the tuned model, so we call with the matching mode.",
    )
    provider: str = Field(
        description="The provider to use for the fine-tune (e.g. 'openai')."
    )
    base_model_id: str = Field(
        description="The id of the base model to use for the fine-tune. This string relates to the provider's IDs for their own models, not Kiln IDs."
    )
    provider_id: str | None = Field(
        default=None,
        description="The ID of the fine-tune job on the provider's side. May not be the same as the fine_tune_model_id.",
    )
    fine_tune_model_id: str | None = Field(
        default=None,
        description="The ID of the fine-tuned model on the provider's side. May not be the same as the provider_id.",
    )
    dataset_split_id: str = Field(
        description="The ID of the dataset split to use for this fine-tune.",
    )
    train_split_name: str = Field(
        default="train",
        description="The name of the training split to use for this fine-tune.",
    )
    validation_split_name: str | None = Field(
        default=None,
        description="The name of the validation split to use for this fine-tune. Optional.",
    )
    parameters: dict[str, str | int | float | bool] = Field(
        default={},
        description="The parameters to use for this fine-tune. These are provider-specific.",
    )
    # These two fields are saved exactly used for training. Even if they map exactly to a custom prompt or generator, those can change, so we want to keep a record of the training prompt.
    system_message: str = Field(
        description="The system message to use for this fine-tune.",
    )
    thinking_instructions: str | None = Field(
        default=None,
        description="The thinking instructions to use for this fine-tune. Only used when data_strategy is final_and_intermediate.",
    )
    latest_status: FineTuneStatusType = Field(
        default=FineTuneStatusType.unknown,
        description="The latest known status of this fine-tune. Not updated in real time.",
    )
    properties: Dict[str, str | int | float] = Field(
        default={},
        description="Properties of the fine-tune. Different providers may use different properties.",
    )
    data_strategy: FinetuneDataStrategy = Field(
        default=FinetuneDataStrategy.final_only,
        description="The strategy to use for training the model. 'final_only' will only train on the final response. 'final_and_intermediate' will train on the final response and intermediate outputs (chain of thought or reasoning).",
    )

    # Workaround to return typed parent without importing Task
    def parent_task(self) -> Union["Task", None]:
        if self.parent is None or self.parent.__class__.__name__ != "Task":
            return None
        return self.parent  # type: ignore

    @model_validator(mode="after")
    def validate_thinking_instructions(self) -> Self:
        if (
            self.thinking_instructions is not None
            and self.data_strategy != FinetuneDataStrategy.final_and_intermediate
        ):
            raise ValueError(
                "Thinking instructions can only be used when data_strategy is final_and_intermediate"
            )
        if (
            self.thinking_instructions is None
            and self.data_strategy == FinetuneDataStrategy.final_and_intermediate
        ):
            raise ValueError(
                "Thinking instructions are required when data_strategy is final_and_intermediate"
            )
        return self
