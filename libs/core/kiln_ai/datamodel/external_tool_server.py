from enum import Enum
from typing import Any, Dict

from pydantic import Field, model_validator

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
)
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class ToolServerType(str, Enum):
    """
    Enumeration of supported external tool server types.
    """

    remote_mcp = "remote_mcp"
    local_mcp = "local_mcp"


class ExternalToolServer(KilnParentedModel):
    """
    Configuration for communicating with a external MCP (Model Context Protocol) Server for LLM tool calls. External tool servers can be remote or local.

    This model stores the necessary configuration to connect to and authenticate with
    external MCP servers that provide tools for LLM interactions.
    """

    name: FilenameString = Field(description="The name of the external tool.")
    type: ToolServerType = Field(
        description="The type of external tool server. Remote tools are hosted on a remote server",
    )
    description: str | None = Field(
        default=None,
        description="A description of the external tool for you and your team. Will not be used in prompts/training/validation.",
    )
    properties: Dict[str, Any] = Field(
        default={},
        description="Configuration properties specific to the tool type.",
    )

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ExternalToolServer":
        """Validate that each tool type has the required configuration."""
        match self.type:
            case ToolServerType.remote_mcp:
                server_url = self.properties.get("server_url", None)
                if not isinstance(server_url, str):
                    raise ValueError(
                        "server_url must be a string for external tools of type 'remote_mcp'"
                    )
                if not server_url:
                    raise ValueError(
                        "server_url is required for external tools of type 'remote_mcp'"
                    )

                headers = self.properties.get("headers", None)
                if headers is None:
                    raise ValueError("headers must be set when type is 'remote_mcp'")
                if not isinstance(headers, dict):
                    raise ValueError(
                        "headers must be a dictionary for external tools of type 'remote_mcp'"
                    )
            case ToolServerType.local_mcp:
                command = self.properties.get("command", None)
                if not isinstance(command, str):
                    raise ValueError(
                        "command must be a string for external tools of type 'local_mcp'"
                    )
                if not command:
                    raise ValueError(
                        "command is required for external tools of type 'local_mcp'"
                    )

                args = self.properties.get("args", None)
                if not isinstance(args, list):
                    raise ValueError(
                        "args must be a list for external tools of type 'local_mcp'"
                    )
                if not args:
                    raise ValueError(
                        "args is required for external tools of type 'local_mcp'"
                    )

                env_vars = self.properties.get("env_vars", {})
                if not isinstance(env_vars, dict):
                    raise ValueError(
                        "env_vars must be a dictionary for external tools of type 'local_mcp'"
                    )
                # Set the default value if not provided
                if "env_vars" not in self.properties:
                    self.properties["env_vars"] = {}

            case _:
                # Type checking will catch missing cases
                raise_exhaustive_enum_error(self.type)
        return self
