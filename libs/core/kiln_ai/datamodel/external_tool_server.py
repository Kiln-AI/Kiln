from enum import Enum
from typing import Any, Dict

from pydantic import Field, PrivateAttr, model_validator

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

    # Private variable to store unsaved secrets
    _unsaved_secrets: dict[str, str] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Process secrets after initialization (pydantic v2 hook)
        self._process_secrets_from_properties()

    def _process_secrets_from_properties(self) -> None:
        """
        Extract secrets from properties and move them to _unsaved_secrets.
        This removes secrets from the properties dict so they aren't saved to file.
        Clears existing _unsaved_secrets first to handle property updates correctly.
        """
        # Clear existing unsaved secrets since we're reprocessing
        self._unsaved_secrets.clear()

        secret_keys = self.get_secret_keys()

        if not secret_keys:
            return

        # Extract secret values from properties based on server type
        match self.type:
            case ToolServerType.remote_mcp:
                headers = self.properties.get("headers", {})
                for key_name in secret_keys:
                    if key_name in headers:
                        self._unsaved_secrets[key_name] = headers[key_name]
                        # Remove from headers immediately so they are not saved to file
                        del headers[key_name]

            case ToolServerType.local_mcp:
                env_vars = self.properties.get("env_vars", {})
                for key_name in secret_keys:
                    if key_name in env_vars:
                        self._unsaved_secrets[key_name] = env_vars[key_name]
                        # Remove from env_vars immediately so they are not saved to file
                        del env_vars[key_name]

            case _:
                raise_exhaustive_enum_error(self.type)

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Override __setattr__ to process secrets whenever properties are updated.
        """
        super().__setattr__(name, value)

        # Process secrets whenever properties are updated
        if name == "properties":
            self._process_secrets_from_properties()

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
                if secret_header_keys is not None:
                    if not isinstance(secret_header_keys, list):
                        raise ValueError(
                            "secret_header_keys must be a list for external tools of type 'remote_mcp'"
                        )
                    if not all(isinstance(k, str) for k in secret_header_keys):
                        raise ValueError("secret_header_keys must contain only strings")

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
                if secret_env_var_keys is not None:
                    if not isinstance(secret_env_var_keys, list):
                        raise ValueError(
                            "secret_env_var_keys must be a list for external tools of type 'local_mcp'"
                        )
                    if not all(isinstance(k, str) for k in secret_env_var_keys):
                        raise ValueError(
                            "secret_env_var_keys must contain only strings"
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

    def retrieve_secrets(self) -> tuple[dict[str, str], list[str]]:
        """
        Retrieve secrets from configuration system or in-memory storage.
        Automatically determines which secret keys to retrieve based on the server type.
        Config secrets take precedence over unsaved secrets.

        Returns:
            Tuple of (secrets_dict, missing_secrets_list) where:
            - secrets_dict: Dictionary mapping key names to their secret values
            - missing_secrets_list: List of secret key names that are missing values
        """
        secrets = {}
        missing_secrets = []
        secret_keys = self.get_secret_keys()

        if secret_keys and len(secret_keys) > 0:
            config = Config.shared()
            mcp_secrets = config.get_value(MCP_SECRETS_KEY)

            for key_name in secret_keys:
                secret_value = None

                # First check config secrets (persistent storage), key is mcp_server_id::key_name
                secret_key = self._config_secret_key(key_name)
                secret_value = mcp_secrets.get(secret_key) if mcp_secrets else None

                # Fall back to unsaved secrets (in-memory storage)
                if (
                    not secret_value
                    and hasattr(self, "_unsaved_secrets")
                    and key_name in self._unsaved_secrets
                ):
                    secret_value = self._unsaved_secrets[key_name]

                if secret_value:
                    secrets[key_name] = secret_value
                else:
                    missing_secrets.append(key_name)

        return secrets, missing_secrets

    def _save_secrets(self) -> None:
        """
        Save unsaved secrets to the configuration system.
        """
        secret_keys = self.get_secret_keys()

        # No secrets to save
        if not secret_keys:
            return

        if self.id is None:
            raise ValueError("Server ID cannot be None when saving secrets")

        # Check if secrets are already saved
        if not hasattr(self, "_unsaved_secrets") or not self._unsaved_secrets:
            return

        config = Config.shared()
        mcp_secrets: dict[str, str] = config.get_value(MCP_SECRETS_KEY) or {}

        # Store secrets with the pattern: mcp_server_id::key_name
        for key_name, secret_value in self._unsaved_secrets.items():
            secret_key = self._config_secret_key(key_name)
            mcp_secrets[secret_key] = secret_value

        config.update_settings({MCP_SECRETS_KEY: mcp_secrets})

        # Clear unsaved secrets after saving
        self._unsaved_secrets.clear()

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
        Override save_to_file to automatically save any unsaved secrets before saving to file.

        This ensures that secrets are always saved when the object is saved,
        preventing the issue where secrets could be lost if save_to_file is called
        without explicitly saving secrets first.
        """
        # Save any unsaved secrets first
        if hasattr(self, "_unsaved_secrets") and self._unsaved_secrets:
            self._save_secrets()

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
