from typing import Annotated, Any, List, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.prompt_id import PromptId
from kiln_ai.datamodel.tool_id import ToolId


class MCPToolReference(BaseModel):
    tool_id: ToolId = Field(
        description="The MCP tool ID to call (mcp::local|remote::<server_id>::<tool_name>)."
    )
    tool_server_id: str | None = Field(
        default=None, description="The MCP tool server ID."
    )
    tool_name: str | None = Field(default=None, description="The MCP tool name.")
    input_schema: dict | None = Field(
        default=None, description="Snapshot of the MCP tool input schema."
    )
    output_schema: dict | None = Field(
        default=None, description="Snapshot of the MCP tool output schema."
    )


class ToolsRunConfig(BaseModel):
    """
    A config describing which tools are available to a task.
    """

    tools: List[ToolId] = Field(
        description="The IDs of the tools available to the task."
    )


class KilnAgentRunConfigProperties(BaseModel):
    """
    A configuration for running a task using a Kiln AI agent.

    This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).
    """

    type: Literal["kiln_agent"] = "kiln_agent"
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
    def validate_sampling(self) -> Self:
        if not (0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1")

        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

        return self


class McpRunConfigProperties(BaseModel):
    """
    A configuration for running a task via an MCP tool.
    """

    type: Literal["mcp"] = "mcp"
    tool_reference: MCPToolReference = Field(
        description="The MCP tool to use for this run config."
    )


def _get_run_config_type(data: Any) -> str:
    if isinstance(data, dict):
        return data.get("type", "kiln_agent")
    return getattr(data, "type", "kiln_agent")


RunConfigProperties = Annotated[
    Union[
        Annotated[KilnAgentRunConfigProperties, Tag("kiln_agent")],
        Annotated[McpRunConfigProperties, Tag("mcp")],
    ],
    Discriminator(_get_run_config_type),
]
