from typing import Annotated, Any, List, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from kiln_ai.datamodel.datamodel_enums import (
    ModelProviderName,
    StructuredOutputMode,
)
from kiln_ai.datamodel.input_transform import InputTransform
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


class OpenRouterRouting(BaseModel):
    """
    Choices a run config makes about which OpenRouter providers may serve its model calls.

    See https://openrouter.ai/docs/guides/routing/provider-selection
    """

    # An unknown key is a restriction this version can't enforce, or a misspelt one:
    # loading must fail, not drop it.
    model_config = ConfigDict(extra="forbid")

    zero_data_retention: bool = Field(
        default=False,
        description=(
            "When true, the call is sent with OpenRouter's `provider.zdr`, so OpenRouter "
            "routes it only to zero-data-retention endpoints and rejects it when none "
            "serves the model. A call that does not go through OpenRouter is refused. "
            "Endpoints OpenRouter labels Safety Retention stay eligible unless the "
            "OpenRouter account's privacy settings are set to ZDR only. Covers only "
            "this run config's own model calls: tools and sub-agent tasks that call "
            "models or services use their own settings."
        ),
    )
    sort: Literal["price", "throughput", "latency"] | None = Field(
        default=None,
        description=(
            "Sent as OpenRouter's `provider.sort`, in place of Kiln's default provider "
            "order. Not applied to models Kiln pins to specific providers, nor to calls "
            "that do not go through OpenRouter. If None, Kiln's default order is used."
        ),
    )


def require_openrouter_for_zero_data_retention(
    routing: OpenRouterRouting | None, provider_name: ModelProviderName
) -> None:
    """Refuse a model call that asks for zero data retention but would not go through OpenRouter.

    Raises:
        ValueError: zero data retention is requested and the provider is not OpenRouter.
    """
    if (
        routing is not None
        and routing.zero_data_retention
        and provider_name != ModelProviderName.openrouter
    ):
        raise ValueError(
            "This run config requires zero data retention "
            "(openrouter_routing.zero_data_retention), which Kiln can only enforce "
            f"on OpenRouter. The call to provider '{provider_name.value}' was not sent."
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
    thinking_level: str | None = Field(
        default=None,
        description="The thinking level to use for this run config. If None, defaults may apply.",
    )
    tools_config: ToolsRunConfig | None = Field(
        default=None,
        description="The tools config to use for this run config, defining which tools are available to the model.",
    )
    input_transform: InputTransform | None = Field(
        default=None,
        description=(
            "Optional transform applied to the task input at run time, producing "
            "the first user message sent to the model. Default None preserves "
            "the identity path."
        ),
    )
    openrouter_routing: OpenRouterRouting | None = Field(
        default=None,
        description=(
            "Provider routing choices for calls made through OpenRouter, such as "
            "zero data retention. If None, Kiln's default routing is used."
        ),
    )

    @field_validator("thinking_level")
    @classmethod
    def validate_thinking_level(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("thinking_level must be a non-empty string when provided")
        return normalized

    @model_validator(mode="after")
    def validate_sampling(self) -> Self:
        if not (0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1")

        if self.temperature < 0 or self.temperature > 2:
            raise ValueError("temperature must be between 0 and 2")

        return self

    @model_validator(mode="after")
    def validate_zero_data_retention_provider(self) -> Self:
        require_openrouter_for_zero_data_retention(
            self.openrouter_routing, self.model_provider_name
        )
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


def as_kiln_agent_run_config(
    run_config: RunConfigProperties,
) -> KilnAgentRunConfigProperties:
    """Centralize KilnAgentRunConfigProperties narrowing so callers don't repeat isinstance checks."""
    if not isinstance(run_config, KilnAgentRunConfigProperties):
        raise ValueError("Kiln agent run config is required for this operation")
    return run_config


def as_mcp_run_config(run_config: RunConfigProperties) -> McpRunConfigProperties:
    """Centralize McpRunConfigProperties narrowing so callers don't repeat isinstance checks."""
    if not isinstance(run_config, McpRunConfigProperties):
        raise ValueError("MCP run config is required for this operation")
    return run_config
