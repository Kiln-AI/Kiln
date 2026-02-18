from enum import Enum
from typing import List

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.prompt_id import PromptId
from kiln_ai.datamodel.tool_id import ToolId


class RunConfigKind(str, Enum):
    kiln_agent = "kiln_agent"
    mcp = "mcp"


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


class RunConfigProperties(BaseModel):
    """
    A configuration for running a task.

    This includes everything needed to run a task, except the input and task ID. Running the same RunConfig with the same input should make identical calls to the model (output may vary as models are non-deterministic).
    """

    kind: RunConfigKind = Field(
        default=RunConfigKind.kiln_agent,
        description="The type of run config (kiln_agent or mcp).",
    )
    mcp_tool: MCPToolReference | None = Field(
        default=None,
        description="MCP tool reference used when kind is mcp.",
    )
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

    @model_validator(mode="before")
    def apply_mcp_defaults(cls, data: dict) -> dict:
        if not isinstance(data, dict):
            return data

        # set the defaults
        kind = data.get("kind")
        if kind in (RunConfigKind.mcp, RunConfigKind.mcp.value):
            data.setdefault("model_name", "mcp_tool")
            data.setdefault("model_provider_name", ModelProviderName.mcp_provider)
            data.setdefault("prompt_id", "simple_prompt_builder")
            data.setdefault("structured_output_mode", StructuredOutputMode.default)
            data.setdefault("top_p", 1.0)
            data.setdefault("temperature", 1.0)

        return data

    @model_validator(mode="after")
    def validate_mcp(self) -> Self:
        if self.kind != RunConfigKind.mcp:
            return self

        if self.mcp_tool is None:
            raise ValueError("mcp_tool is required when kind is mcp")

        if self.model_name != "mcp_tool":
            raise ValueError("model_name must be 'mcp_tool' when kind is mcp")
        if self.model_provider_name != ModelProviderName.mcp_provider:
            raise ValueError(
                "model_provider_name must be 'mcp_provider' when kind is mcp"
            )
        if self.prompt_id != "simple_prompt_builder":
            raise ValueError(
                "prompt_id must be 'simple_prompt_builder' when kind is mcp"
            )
        if self.structured_output_mode != StructuredOutputMode.default:
            raise ValueError("structured_output_mode must be default when kind is mcp")
        if self.top_p != 1.0:
            raise ValueError("top_p must be 1.0 when kind is mcp")
        if self.temperature != 1.0:
            raise ValueError("temperature must be 1.0 when kind is mcp")
        if self.tools_config is not None:
            raise ValueError("tools_config must not be set when kind is mcp")

        return self

    @model_validator(mode="after")
    def validate_kiln_agent(self) -> Self:
        if self.kind != RunConfigKind.kiln_agent:
            return self

        if self.mcp_tool is not None:
            raise ValueError("mcp_tool must not be set when kind is kiln_agent")

        return self

    @model_validator(mode="after")
    def validate_sampling(self) -> Self:
        if not (0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1")

        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

        return self
