import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, PrivateAttr, model_validator
from typing_extensions import NotRequired, TypedDict

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


class LocalServerProperties(TypedDict, total=True):
    command: str
    args: NotRequired[list[str]]
    env_vars: NotRequired[dict[str, str]]
    secret_env_var_keys: NotRequired[list[str]]


class RemoteServerProperties(TypedDict, total=True):
    server_url: str
    headers: NotRequired[dict[str, str]]
    secret_header_keys: NotRequired[list[str]]


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

    properties: LocalServerProperties | RemoteServerProperties = Field(
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

    # Validation Helpers

    @classmethod
    def check_server_url(cls, server_url: str) -> None:
        """Validate Server URL"""
        if not isinstance(server_url, str):
            raise ValueError("Server URL must be a string")

        # Check for leading whitespace in URL
        if server_url != server_url.lstrip():
            raise ValueError("Server URL must not have leading whitespace")

        parsed_url = urlparse(server_url)
        if not parsed_url.netloc:
            raise ValueError("Server URL is not a valid URL")
        if parsed_url.scheme not in ["http", "https"]:
            raise ValueError("Server URL must start with http:// or https://")

    @classmethod
    def check_headers(cls, headers: dict) -> None:
        """Validate Headers"""
        if not isinstance(headers, dict):
            raise ValueError("headers must be a dictionary")

        for key, value in headers.items():
            if not key:
                raise ValueError("Header name is required")
            if not value:
                raise ValueError("Header value is required")

            # Reject invalid header names and CR/LF in names/values
            token_re = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
            if not token_re.match(key):
                raise ValueError(f'Invalid header name: "{key}"')
            if re.search(r"\r|\n", key) or re.search(r"\r|\n", value):
                raise ValueError(
                    "Header names/values must not contain invalid characters"
                )

    @classmethod
    def check_secret_keys(
        cls, secret_keys: list, key_type: str, tool_type: str
    ) -> None:
        """Validate Secret Keys (generic method for both header and env var keys)"""
        if not isinstance(secret_keys, list):
            raise ValueError(
                f"{key_type} must be a list for external tools of type '{tool_type}'"
            )
        if not all(isinstance(k, str) for k in secret_keys):
            raise ValueError(f"{key_type} must contain only strings")
        if not all(key for key in secret_keys):
            raise ValueError("Secret key is required")

    @classmethod
    def check_env_vars(cls, env_vars: dict) -> None:
        """Validate Environment Variables"""
        if not isinstance(env_vars, dict):
            raise ValueError("environment variables must be a dictionary")

        # Validate env_vars keys are in the correct format for Environment Variables
        # According to POSIX specification, environment variable names must:
        # - Start with a letter (a-z, A-Z) or underscore (_)
        # - Contain only ASCII letters, digits, and underscores
        for key, _ in env_vars.items():
            if not key or not (
                key[0].isascii() and (key[0].isalpha() or key[0] == "_")
            ):
                raise ValueError(
                    f"Invalid environment variable key: {key}. Must start with a letter or underscore."
                )

            if not all(c.isascii() and (c.isalnum() or c == "_") for c in key):
                raise ValueError(
                    f"Invalid environment variable key: {key}. Can only contain letters, digits, and underscores."
                )

    @model_validator(mode="before")
    def validate_required_fields(cls, data: dict) -> dict:
        """Validate that each tool type has the required configuration."""
        server_type = data.get("type")
        properties = data.get("properties", {})

        if not server_type:
            # pydantic will catch this but the not None check is needed to support `raise_exhaustive_enum_error`
            raise ValueError("Server type is required")

        match server_type:
            case ToolServerType.remote_mcp:
                server_url = properties.get("server_url", None)
                if server_url is None:
                    raise ValueError(
                        "Server URL is required to connect to a remote MCP server"
                    )
                ExternalToolServer.check_server_url(server_url)

            case ToolServerType.local_mcp:
                command = properties.get("command", None)
                if command is None:
                    raise ValueError("command is required to start a local MCP server")

                if not isinstance(command, str):
                    raise ValueError(
                        "command must be a string to start a local MCP server"
                    )

                # Reject empty/whitespace-only command strings
                if command.strip() == "":
                    raise ValueError("command must be a non-empty string")

                args = properties.get("args", None)
                if args is not None:
                    if not isinstance(args, list):
                        raise ValueError(
                            "arguments must be a list to start a local MCP server"
                        )

            case _:
                # Type checking will catch missing cases
                raise_exhaustive_enum_error(server_type)
        return data

    @model_validator(mode="before")
    def validate_headers_and_env_vars(cls, data: dict) -> dict:
        """
        Validate secrets, these needs to be validated before model initlization because secrets will be processed and stripped
        """
        type = data.get("type", None)
        if not type:
            raise ValueError("type is required")

        properties = data.get("properties", {})
        if properties is None:
            raise ValueError("properties is required")

        match type:
            case ToolServerType.remote_mcp:
                # Validate headers
                headers = properties.get("headers", None)
                if headers is not None:
                    ExternalToolServer.check_headers(headers)

                # Secret header keys are optional, validate if they are set
                secret_header_keys = properties.get("secret_header_keys", None)
                if secret_header_keys is not None:
                    ExternalToolServer.check_secret_keys(
                        secret_header_keys, "secret_header_keys", "remote_mcp"
                    )

            case ToolServerType.local_mcp:
                # Validate secret environment variable keys
                env_vars = properties.get("env_vars", {})
                if env_vars is not None:
                    ExternalToolServer.check_env_vars(env_vars)

                # Secret env var keys are optional, but if they are set, they must be a list of strings
                secret_env_var_keys = properties.get("secret_env_var_keys", None)
                if secret_env_var_keys is not None:
                    ExternalToolServer.check_secret_keys(
                        secret_env_var_keys, "secret_env_var_keys", "local_mcp"
                    )

            case _:
                raise_exhaustive_enum_error(type)

        return data

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
