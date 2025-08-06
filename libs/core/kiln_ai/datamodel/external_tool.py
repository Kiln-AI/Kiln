from typing import Literal

from pydantic import Field, model_validator

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
)


class ExternalTool(KilnParentedModel):
    """
    Configuration for communicating with a external MCP (Model Context Protocol) Server for LLM tool calls. External tools can be remote or local.

    This model stores the necessary configuration to connect to and authenticate with
    external MCP servers that provide tools for LLM interactions.
    """

    name: FilenameString = Field(description="The name of the external tool.")
    type: Literal["remote_mcp"] = Field(
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

    @model_validator(mode="after")
    def validate_remote_mcp_config(self) -> "ExternalTool":
        """Validate that remote_mcp type has server_url configured."""
        if self.type == "remote_mcp" and not self.server_url:
            raise ValueError("server_url must be set when type is 'remote_mcp'")
        return self
