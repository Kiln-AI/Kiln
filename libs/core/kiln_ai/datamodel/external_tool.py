from enum import Enum

from pydantic import Field, model_validator

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
)
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class ToolType(str, Enum):
    """
    Enumeration of supported external tool types.
    """

    remote_mcp = "remote_mcp"


class ExternalTool(KilnParentedModel):
    """
    Configuration for communicating with a external MCP (Model Context Protocol) Server for LLM tool calls. External tools can be remote or local.

    This model stores the necessary configuration to connect to and authenticate with
    external MCP servers that provide tools for LLM interactions.
    """

    name: FilenameString = Field(description="The name of the external tool.")
    type: ToolType = Field(
        description="The type of external tool. Remote tools are hosted on a remote server",
    )
    description: str | None = Field(
        default=None,
        description="A description of the external tool for you and your team. Will not be used in prompts/training/validation.",
    )
    server_url: str = Field(
        description="The URL of the remote MCP server.",
        min_length=1,
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description="HTTP headers to use when calling the server_url.",
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ExternalTool":
        """Validate that each tool type has the required configuration."""
        match self.type:
            case ToolType.remote_mcp:
                if not self.server_url:
                    raise ValueError("server_url must be set when type is 'remote_mcp'")
                if not self.headers:
                    raise ValueError("headers must be set when type is 'remote_mcp'")
            case _:
                # Type checking will catch missing cases
                raise_exhaustive_enum_error(self.type)
        return self
