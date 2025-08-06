from pydantic import Field

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
)


class ExternalTool(KilnParentedModel):
    """
    Configuration for communicating with a remote MCP (Model Context Protocol) Server for LLM tool calls.

    This model stores the necessary configuration to connect to and authenticate with
    external MCP servers that provide tools for LLM interactions.
    """

    name: FilenameString = Field(description="The name of the external tool.")
    description: str | None = Field(
        default=None,
        description="A description of the external tool for you and your team. Will not be used in prompts/training/validation.",
    )
    server_url: str = Field(
        description="The URL of the remote MCP server.",
        min_length=1,
    )
    api_key: str = Field(
        description="API key for authenticating with the MCP server.",
        min_length=1,
    )
