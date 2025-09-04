from enum import Enum
from typing import Any, Dict

from pydantic import Field, model_validator

from kiln_ai.datamodel.basemodel import (
    FilenameString,
    KilnParentedModel,
)
from kiln_ai.utils.config import MCP_SECRETS_KEY, Config
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
                        "server_url is required to connect to a remote MCP server"
                    )

                headers = self.properties.get("headers", None)
                if headers is None:
                    raise ValueError("headers must be set when type is 'remote_mcp'")
                if not isinstance(headers, dict):
                    raise ValueError(
                        "headers must be a dictionary for external tools of type 'remote_mcp'"
                    )

                secret_header_keys = self.properties.get("secret_header_keys", None)
                # Secret header keys are optional, but if they are set, they must be a list of strings
                if secret_header_keys is not None and not isinstance(
                    secret_header_keys, list
                ):
                    raise ValueError(
                        "secret_header_keys must be a list for external tools of type 'remote_mcp'"
                    )

            case ToolServerType.local_mcp:
                command = self.properties.get("command", None)
                if not isinstance(command, str):
                    raise ValueError(
                        "command must be a string to start a local MCP server"
                    )
                if not command.strip():
                    raise ValueError("command is required to start a local MCP server")

                args = self.properties.get("args", None)
                if not isinstance(args, list):
                    raise ValueError(
                        "arguments must be a list to start a local MCP server"
                    )

                env_vars = self.properties.get("env_vars", {})
                if not isinstance(env_vars, dict):
                    raise ValueError(
                        "environment variables must be a dictionary for external tools of type 'local_mcp'"
                    )

                secret_env_var_keys = self.properties.get("secret_env_var_keys", None)
                # Secret env var keys are optional, but if they are set, they must be a list of strings
                if secret_env_var_keys is not None and not isinstance(
                    secret_env_var_keys, list
                ):
                    raise ValueError(
                        "secret_env_var_keys must be a list for external tools of type 'local_mcp'"
                    )

            case _:
                # Type checking will catch missing cases
                raise_exhaustive_enum_error(self.type)
        return self

    def get_secret_keys(self) -> list[str]:
        """
        Get the list of secret key names based on server type.

        Returns:
            List of secret key names (header names for remote, env var names for local)
        """
        match self.type:
            case ToolServerType.remote_mcp:
                return self.properties.get("secret_header_keys", [])
            case ToolServerType.local_mcp:
                return self.properties.get("secret_env_var_keys", [])
            case _:
                raise_exhaustive_enum_error(self.type)

    def retrieve_secrets(self) -> dict[str, str]:
        """
        Retrieve secrets from configuration using the pattern: mcp_server_id::key_name
        Automatically determines which secret keys to retrieve based on the server type.

        Returns:
            Dictionary mapping key names to their secret values
        """
        secrets = {}
        secret_keys = self.get_secret_keys()

        if secret_keys and len(secret_keys) > 0:
            config = Config.shared()
            mcp_secrets = config.get_value(MCP_SECRETS_KEY)

            # Look for secrets with the pattern: mcp_server_id::key_name
            if mcp_secrets:  # Only proceed if mcp_secrets is not None
                for key_name in secret_keys:
                    secret_value = mcp_secrets.get(self._config_secret_key(key_name))
                    if secret_value:
                        secrets[key_name] = secret_value

        return secrets

    def missing_secrets(self) -> list[str]:
        """
        Check if the tool server has missing secrets.

        Returns:
            List of secret key names that are missing values in Config
        """
        missing_secrets = []
        secret_keys = self.get_secret_keys()

        if secret_keys and len(secret_keys) > 0:
            config = Config.shared()
            mcp_secrets = config.get_value(MCP_SECRETS_KEY)

            for key_name in secret_keys:
                secret_key = self._config_secret_key(key_name)
                # Check if the secret is missing or empty
                if not mcp_secrets or not mcp_secrets.get(secret_key):
                    missing_secrets.append(key_name)

        return missing_secrets

    def save_secrets(self) -> None:
        """
        Save secrets to the configuration system.
        Extracts secret values from properties based on server type.
        """
        secret_keys = self.get_secret_keys()

        if not secret_keys:
            return

        if self.id is None:
            raise ValueError("Server ID cannot be None when saving secrets")

        # Extract secret values from properties based on server type
        match self.type:
            case ToolServerType.remote_mcp:
                secret_values = self.properties.get("headers", {})
            case ToolServerType.local_mcp:
                secret_values = self.properties.get("env_vars", {})
            case _:
                raise_exhaustive_enum_error(self.type)

        config = Config.shared()
        mcp_secrets = config.get_value(MCP_SECRETS_KEY) or dict[str, str]()

        # Store secrets with the pattern: mcp_server_id::key_name
        for key_name in secret_keys:
            if key_name in secret_values:
                secret_key = self._config_secret_key(key_name)
                mcp_secrets[secret_key] = secret_values[key_name]

        config.update_settings({MCP_SECRETS_KEY: mcp_secrets})

    def delete_secrets(self) -> None:
        """
        Delete all secrets for this tool server from the configuration system.
        """
        secret_keys = self.get_secret_keys()

        config = Config.shared()
        mcp_secrets = config.get_value(MCP_SECRETS_KEY) or dict[str, str]()

        # Remove secrets with the pattern: mcp_server_id::key_name
        for key_name in secret_keys:
            secret_key = self._config_secret_key(key_name)
            if secret_key in mcp_secrets:
                del mcp_secrets[secret_key]

        # Always call update_settings to maintain consistency with the old behavior
        config.update_settings({MCP_SECRETS_KEY: mcp_secrets})

    def save_to_file(self) -> None:
        """
        Override save_to_file to automatically strip secrets from properties before saving.

        This ensures that sensitive data is never persisted to disk in the properties,
        while still being accessible via retrieve_secrets() for runtime use.

        This method also permanently strips secrets from the in-memory object to ensure
        consistent behavior between saved and in-memory representations.
        """
        # Strip secrets based on server type
        match self.type:
            case ToolServerType.remote_mcp:
                secret_keys = self.properties.get("secret_header_keys", [])
                if secret_keys and "headers" in self.properties:
                    # Remove secret headers from the headers dict
                    non_secret_headers = {
                        key: value
                        for key, value in self.properties["headers"].items()
                        if key not in secret_keys
                    }
                    self.properties["headers"] = non_secret_headers

            case ToolServerType.local_mcp:
                secret_keys = self.properties.get("secret_env_var_keys", [])
                if secret_keys and "env_vars" in self.properties:
                    # Remove secret env vars from the env_vars dict
                    non_secret_env_vars = {
                        key: value
                        for key, value in self.properties["env_vars"].items()
                        if key not in secret_keys
                    }
                    self.properties["env_vars"] = non_secret_env_vars

            case _:
                raise_exhaustive_enum_error(self.type)

        # Call the parent save_to_file method
        super().save_to_file()

    #  Internal helpers

    def _config_secret_key(self, key_name: str) -> str:
        """
        Generate the secret key pattern for storing/retrieving secrets.

        Args:
            key_name: The name of the secret key

        Returns:
            The formatted secret key: "{server_id}::{key_name}"
        """
        return f"{self.id}::{key_name}"
