from typing import List

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.prompt_id import PromptId
from kiln_ai.datamodel.tool_id import ToolId


class ToolsRunConfig(BaseModel):
    """
    A config describing which tools are available to a task.
    """

    tools: List[ToolId] = Field(
        description="The IDs of the tools available to the task."
    )


class RunConfigProperties(BaseModel):
    """
    A configuration for running a task.

    This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).
    """

    model_name: str = Field(description="The model to use for this run config.")
    model_provider_name: ModelProviderName = Field(
        description="The provider to use for this run config."
    )
    prompt_id: PromptId = Field(
        description="The prompt to use for this run config. Defaults to building a simple prompt from the task if not provided.",
    )
    top_p: float = Field(
        default=1.0,
        description="The top-p value to use for this run config. Defaults to 1.0.",
    )
    temperature: float = Field(
        default=1.0,
        description="The temperature to use for this run config. Defaults to 1.0.",
    )
    structured_output_mode: StructuredOutputMode = Field(
        description="The structured output mode to use for this run config.",
    )
    tools_config: ToolsRunConfig | None = Field(
        default=None,
        description="The tools config to use for this run config, defining which tools are available to the model.",
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> Self:
        if not (0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1")

        elif self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

        return self
