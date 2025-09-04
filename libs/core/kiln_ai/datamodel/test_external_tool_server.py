from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.config import MCP_SECRETS_KEY


# Test fixtures for common server configurations
@pytest.fixture
def remote_mcp_minimal():
    """Minimal valid remote MCP server configuration."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {},
        },
    )


@pytest.fixture
def remote_mcp_with_headers():
    """Remote MCP server with headers."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {
                "Authorization": "Bearer token",
                "Content-Type": "application/json",
            },
        },
    )


@pytest.fixture
def remote_mcp_with_secrets():
    """Remote MCP server with secret headers."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.remote_mcp,
        properties={
            "server_url": "https://example.com/mcp",
            "headers": {
                "Authorization": "Bearer secret_token",
                "Content-Type": "application/json",
            },
            "secret_header_keys": ["Authorization"],
        },
    )


@pytest.fixture
def local_mcp_minimal():
    """Minimal valid local MCP server configuration."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.local_mcp,
        properties={
            "command": "python",
            "args": ["-m", "my_server"],
            "env_vars": {},
        },
    )


@pytest.fixture
def local_mcp_with_env_vars():
    """Local MCP server with environment variables."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.local_mcp,
        properties={
            "command": "python",
            "args": ["-m", "my_server"],
            "env_vars": {
                "API_KEY": "secret_key",
                "PORT": "3000",
            },
        },
    )


@pytest.fixture
def local_mcp_with_secrets():
    """Local MCP server with secret environment variables."""
    return ExternalToolServer(
        name="test_server",
        type=ToolServerType.local_mcp,
        properties={
            "command": "python",
            "args": ["-m", "my_server"],
            "env_vars": {
                "API_KEY": "secret_key",
                "PORT": "3000",
            },
            "secret_env_var_keys": ["API_KEY"],
        },
    )


class TestExternalToolServerValidation:
    """Tests for ExternalToolServer model validation, including secret header keys."""

    def test_remote_mcp_valid_minimal(self, remote_mcp_minimal):
        """Test ExternalToolServer with minimal valid remote MCP configuration."""
        server = remote_mcp_minimal

        assert server.name == "test_server"
        assert server.type == ToolServerType.remote_mcp
        assert server.properties["server_url"] == "https://example.com/mcp"
        assert server.properties["headers"] == {}

    def test_remote_mcp_valid_with_headers(self, remote_mcp_with_headers):
        """Test ExternalToolServer with valid remote MCP configuration including headers."""
        server = remote_mcp_with_headers

        assert server.name == "test_server"
        assert len(server.properties["headers"]) == 2
        assert server.properties["headers"]["Authorization"] == "Bearer token"

    def test_remote_mcp_valid_with_secret_header_keys(self):
        """Test ExternalToolServer with valid secret header keys."""
        server = ExternalToolServer(
            name="secret_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer secret",
                    "X-API-Key": "api-key",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )

        assert server.name == "secret_server"
        assert server.properties["secret_header_keys"] == ["Authorization", "X-API-Key"]

    def test_remote_mcp_valid_with_empty_secret_header_keys(self):
        """Test ExternalToolServer with empty secret header keys list."""
        server = ExternalToolServer(
            name="no_secrets_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": [],
            },
        )

        assert server.properties["secret_header_keys"] == []

    def test_remote_mcp_missing_server_url(self):
        """Test ExternalToolServer rejects remote MCP without server_url."""
        with pytest.raises(ValidationError, match="server_url must be a string"):
            ExternalToolServer(
                name="missing_url_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "headers": {},
                },
            )

    def test_remote_mcp_invalid_server_url_type(self):
        """Test ExternalToolServer rejects non-string server_url."""
        with pytest.raises(
            ValidationError, match="server_url must be a string for external tools"
        ):
            ExternalToolServer(
                name="invalid_url_type_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": 12345,  # Invalid type
                    "headers": {},
                },
            )

    def test_remote_mcp_empty_server_url(self):
        """Test ExternalToolServer rejects empty server_url."""
        with pytest.raises(
            ValidationError,
            match="server_url is required to connect to a remote MCP server",
        ):
            ExternalToolServer(
                name="empty_url_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "",  # Empty string
                    "headers": {},
                },
            )

    def test_remote_mcp_missing_headers(self):
        """Test ExternalToolServer rejects remote MCP without headers."""
        with pytest.raises(
            ValidationError, match="headers must be set when type is 'remote_mcp'"
        ):
            ExternalToolServer(
                name="missing_headers_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "https://example.com/mcp",
                    # No headers
                },
            )

    def test_remote_mcp_invalid_headers_type(self):
        """Test ExternalToolServer rejects non-dict headers."""
        with pytest.raises(
            ValidationError, match="headers must be a dictionary for external tools"
        ):
            ExternalToolServer(
                name="invalid_headers_type_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "https://example.com/mcp",
                    "headers": "not a dict",  # Invalid type
                },
            )

    def test_remote_mcp_invalid_secret_header_keys_type(self):
        """Test ExternalToolServer rejects non-list secret_header_keys."""
        with pytest.raises(
            ValidationError,
            match="secret_header_keys must be a list for external tools",
        ):
            ExternalToolServer(
                name="invalid_secret_keys_type_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "https://example.com/mcp",
                    "headers": {},
                    "secret_header_keys": "not a list",  # Invalid type
                },
            )

    def test_remote_mcp_invalid_secret_header_keys_non_string_elements(self):
        """Test ExternalToolServer rejects secret_header_keys with non-string elements."""
        with pytest.raises(
            ValidationError,
            match="secret_header_keys must contain only strings",
        ):
            ExternalToolServer(
                name="invalid_secret_keys_elements_server",
                type=ToolServerType.remote_mcp,
                properties={
                    "server_url": "https://example.com/mcp",
                    "headers": {},
                    "secret_header_keys": [
                        "Authorization",
                        123,
                        "X-API-Key",
                    ],  # Invalid non-string element
                },
            )

    def test_local_mcp_valid_minimal(self, local_mcp_minimal):
        """Test ExternalToolServer with minimal valid local MCP configuration."""
        server = local_mcp_minimal

        assert server.name == "test_server"
        assert server.type == ToolServerType.local_mcp
        assert server.properties["command"] == "python"
        assert server.properties["args"] == ["-m", "my_server"]

    def test_local_mcp_valid_with_env_vars(self):
        """Test ExternalToolServer with valid local MCP configuration including env vars."""
        server = ExternalToolServer(
            name="local_server_with_env",
            type=ToolServerType.local_mcp,
            properties={
                "command": "node",
                "args": ["server.js"],
                "env_vars": {
                    "API_KEY": "secret123",
                    "PORT": "3000",
                },
            },
        )

        assert server.properties["env_vars"]["API_KEY"] == "secret123"
        assert server.properties["env_vars"]["PORT"] == "3000"

    def test_local_mcp_valid_with_secret_env_var_keys(self):
        """Test ExternalToolServer with valid secret environment variable keys."""
        server = ExternalToolServer(
            name="secret_local_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {
                    "API_KEY": "secret_key",
                    "DB_PASSWORD": "secret_password",
                    "PORT": "3000",
                },
                "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
            },
        )

        assert server.name == "secret_local_server"
        assert server.properties["secret_env_var_keys"] == ["API_KEY", "DB_PASSWORD"]

    def test_local_mcp_valid_with_empty_secret_env_var_keys(self):
        """Test ExternalToolServer with empty secret env var keys list."""
        server = ExternalToolServer(
            name="no_secrets_local_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"PORT": "3000"},
                "secret_env_var_keys": [],
            },
        )

        assert server.properties["secret_env_var_keys"] == []

    def test_local_mcp_missing_command(self):
        """Test ExternalToolServer rejects local MCP without command."""
        with pytest.raises(ValidationError, match="command must be a string"):
            ExternalToolServer(
                name="missing_command_server",
                type=ToolServerType.local_mcp,
                properties={
                    "args": [],
                    "env_vars": {},
                },
            )

    def test_local_mcp_invalid_command_type(self):
        """Test ExternalToolServer rejects non-string command."""
        with pytest.raises(ValidationError, match="command must be a string"):
            ExternalToolServer(
                name="invalid_command_type_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": 123,  # Invalid type
                    "args": [],
                    "env_vars": {},
                },
            )

    def test_local_mcp_empty_command(self):
        """Test ExternalToolServer rejects empty command."""
        with pytest.raises(
            ValidationError, match="command is required to start a local MCP server"
        ):
            ExternalToolServer(
                name="empty_command_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "",  # Empty string
                    "args": [],
                    "env_vars": {},
                },
            )

    def test_local_mcp_whitespace_only_command(self):
        """Test ExternalToolServer rejects whitespace-only command."""
        with pytest.raises(
            ValidationError, match="command is required to start a local MCP server"
        ):
            ExternalToolServer(
                name="whitespace_command_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "   ",  # Whitespace only
                    "args": [],
                    "env_vars": {},
                },
            )

    def test_local_mcp_missing_args(self):
        """Test ExternalToolServer rejects local MCP without args."""
        with pytest.raises(ValidationError, match="arguments must be a list"):
            ExternalToolServer(
                name="missing_args_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "python",
                    "env_vars": {},
                },
            )

    def test_local_mcp_invalid_args_type(self):
        """Test ExternalToolServer rejects non-list args."""
        with pytest.raises(ValidationError, match="arguments must be a list"):
            ExternalToolServer(
                name="invalid_args_type_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "python",
                    "args": "not a list",  # Invalid type
                    "env_vars": {},
                },
            )

    def test_local_mcp_invalid_env_vars_type(self):
        """Test ExternalToolServer rejects non-dict env_vars."""
        with pytest.raises(
            ValidationError, match="environment variables must be a dictionary"
        ):
            ExternalToolServer(
                name="invalid_env_vars_type_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "python",
                    "args": [],
                    "env_vars": "not a dict",  # Invalid type
                },
            )

    def test_local_mcp_empty_args_allowed(self):
        """Test ExternalToolServer allows empty args list."""
        server = ExternalToolServer(
            name="empty_args_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": [],  # Empty list should be allowed
                "env_vars": {},
            },
        )

        assert server.properties["args"] == []

    def test_local_mcp_missing_env_vars_defaults_to_empty_dict(self):
        """Test ExternalToolServer defaults env_vars to empty dict when missing."""
        server = ExternalToolServer(
            name="default_env_vars_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": [],
                # No env_vars - should default to {}
            },
        )

        # The validator should set it to {} when missing
        assert server.properties.get("env_vars", {}) == {}

    def test_local_mcp_invalid_secret_env_var_keys_type(self):
        """Test ExternalToolServer rejects non-list secret_env_var_keys."""
        with pytest.raises(
            ValidationError,
            match="secret_env_var_keys must be a list for external tools of type 'local_mcp'",
        ):
            ExternalToolServer(
                name="invalid_secret_env_keys_type_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "python",
                    "args": [],
                    "env_vars": {},
                    "secret_env_var_keys": "not a list",  # Invalid type
                },
            )

    def test_local_mcp_invalid_secret_env_var_keys_non_string_elements(self):
        """Test ExternalToolServer rejects secret_env_var_keys with non-string elements."""
        with pytest.raises(
            ValidationError,
            match="secret_env_var_keys must contain only strings",
        ):
            ExternalToolServer(
                name="invalid_secret_env_keys_elements_server",
                type=ToolServerType.local_mcp,
                properties={
                    "command": "python",
                    "args": [],
                    "env_vars": {},
                    "secret_env_var_keys": [
                        "API_KEY",
                        456,
                        "DB_PASSWORD",
                    ],  # Invalid non-string element
                },
            )

    def test_server_with_description(self):
        """Test ExternalToolServer with optional description."""
        server = ExternalToolServer(
            name="described_server",
            type=ToolServerType.remote_mcp,
            description="This is a test server for demonstrations",
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},
            },
        )

        assert server.description == "This is a test server for demonstrations"

    def test_server_without_description(self):
        """Test ExternalToolServer without description (should be None)."""
        server = ExternalToolServer(
            name="undescribed_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},
            },
        )

        assert server.description is None


class TestExternalToolServerSecretMethods:
    """Tests for ExternalToolServer secret management methods."""

    def test_get_secret_keys_remote_mcp_with_secrets(self, remote_mcp_with_secrets):
        """Test get_secret_keys returns correct keys for remote MCP servers."""
        server = remote_mcp_with_secrets

        secret_keys = server.get_secret_keys()
        assert secret_keys == ["Authorization"]

    def test_get_secret_keys_remote_mcp_no_secrets(self, remote_mcp_minimal):
        """Test get_secret_keys returns empty list when no secret keys defined."""
        server = remote_mcp_minimal

        secret_keys = server.get_secret_keys()
        assert secret_keys == []

    def test_get_secret_keys_local_mcp_with_secrets(self, local_mcp_with_secrets):
        """Test get_secret_keys returns correct keys for local MCP servers."""
        server = local_mcp_with_secrets

        secret_keys = server.get_secret_keys()
        assert secret_keys == ["API_KEY"]

    def test_get_secret_keys_local_mcp_no_secrets(self, local_mcp_minimal):
        """Test get_secret_keys returns empty list for local MCP with no secrets."""
        server = local_mcp_minimal

        secret_keys = server.get_secret_keys()
        assert secret_keys == []

    def test_config_secret_key_formats_correctly(self):
        """Test _config_secret_key generates the correct secret key pattern."""
        # Test with remote MCP server
        remote_server = ExternalToolServer(
            name="test_remote_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},
            },
        )
        remote_server.id = "remote_server_123"

        assert (
            remote_server._config_secret_key("Authorization")
            == "remote_server_123::Authorization"
        )
        assert (
            remote_server._config_secret_key("X-API-Key")
            == "remote_server_123::X-API-Key"
        )

        # Test with local MCP server
        local_server = ExternalToolServer(
            name="test_local_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "server"],
            },
        )
        local_server.id = "local_server_456"

        assert local_server._config_secret_key("API_KEY") == "local_server_456::API_KEY"
        assert (
            local_server._config_secret_key("SECRET_TOKEN")
            == "local_server_456::SECRET_TOKEN"
        )

    def test_config_secret_key_with_special_characters(self):
        """Test _config_secret_key handles key names with special characters."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},
            },
        )
        server.id = "test_server_789"

        # Test with key names containing special characters
        assert (
            server._config_secret_key("X-Custom-Header")
            == "test_server_789::X-Custom-Header"
        )
        assert server._config_secret_key("API_KEY_V2") == "test_server_789::API_KEY_V2"
        assert (
            server._config_secret_key("oauth.token") == "test_server_789::oauth.token"
        )

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_remote_mcp_with_secrets(self, mock_config_shared):
        """Test retrieve_secrets returns correct secret values for remote MCP."""
        # Mock config
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::Authorization": "Bearer secret_token",
            "test_id::X-API-Key": "api_key_value",
            "other_server::key": "other_value",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer placeholder",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "test_id"  # Set ID for secret lookup

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {
            "Authorization": "Bearer secret_token",
            "X-API-Key": "api_key_value",
        }
        assert missing_secrets == []

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_local_mcp_with_secrets(self, mock_config_shared):
        """Test retrieve_secrets returns correct secret values for local MCP."""
        # Mock config
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::API_KEY": "secret_api_key",
            "test_id::DB_PASSWORD": "secret_password",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"API_KEY": "placeholder", "PORT": "3000"},
                "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {
            "API_KEY": "secret_api_key",
            "DB_PASSWORD": "secret_password",
        }
        assert missing_secrets == []

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_no_mcp_secrets_in_config(self, mock_config_shared):
        """Test retrieve_secrets handles missing mcp_secrets in config."""
        # Mock config with no mcp_secrets
        mock_config = Mock()
        mock_config.get_value.return_value = None
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer placeholder"},
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {}
        assert missing_secrets == ["Authorization"]

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_no_matching_secrets(self, mock_config_shared):
        """Test retrieve_secrets returns empty dict when no matching secrets found."""
        # Mock config with secrets for different server
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "other_server::Authorization": "Bearer other_token",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer placeholder"},
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {}
        assert missing_secrets == ["Authorization"]

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_remote_mcp_all_present(
        self, mock_config_shared
    ):
        """Test retrieve_secrets returns empty missing_secrets list when all secrets are present for remote MCP."""
        # Mock config with all required secrets present
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::Authorization": "Bearer secret_token",
            "test_id::X-API-Key": "api_key_value",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer placeholder",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {
            "Authorization": "Bearer secret_token",
            "X-API-Key": "api_key_value",
        }
        assert missing_secrets == []

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_remote_mcp_some_missing(
        self, mock_config_shared
    ):
        """Test retrieve_secrets returns correct missing_secrets for remote MCP with partial secrets."""
        # Mock config with only one secret present
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::Authorization": "Bearer secret_token",
            # X-API-Key is missing
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer placeholder",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {"Authorization": "Bearer secret_token"}
        assert missing_secrets == ["X-API-Key"]

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_remote_mcp_empty_values(
        self, mock_config_shared
    ):
        """Test retrieve_secrets treats empty string values as missing for remote MCP."""
        # Mock config with empty string values
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::Authorization": "",  # Empty string should be treated as missing
            "test_id::X-API-Key": "valid_key",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer placeholder",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {"X-API-Key": "valid_key"}
        assert missing_secrets == ["Authorization"]

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_local_mcp_all_present(
        self, mock_config_shared
    ):
        """Test retrieve_secrets returns empty missing_secrets list when all secrets are present for local MCP."""
        # Mock config with all required secrets present
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::API_KEY": "secret_api_key",
            "test_id::DB_PASSWORD": "secret_password",
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"API_KEY": "placeholder", "PORT": "3000"},
                "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {
            "API_KEY": "secret_api_key",
            "DB_PASSWORD": "secret_password",
        }
        assert missing_secrets == []

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_local_mcp_some_missing(
        self, mock_config_shared
    ):
        """Test retrieve_secrets returns correct missing_secrets for local MCP with partial secrets."""
        # Mock config with only one secret present
        mock_config = Mock()
        mock_config.get_value.return_value = {
            "test_id::API_KEY": "secret_api_key",
            # DB_PASSWORD is missing
        }
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"API_KEY": "placeholder", "PORT": "3000"},
                "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {"API_KEY": "secret_api_key"}
        assert missing_secrets == ["DB_PASSWORD"]

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_retrieve_secrets_missing_secrets_no_secret_keys(self, mock_config_shared):
        """Test retrieve_secrets returns empty missing_secrets list when no secret keys are defined."""
        mock_config = Mock()
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                # No secret_header_keys defined
            },
        )
        server.id = "test_id"

        secrets, missing_secrets = server.retrieve_secrets()
        assert secrets == {}
        assert missing_secrets == []

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_save_secrets_remote_mcp(self, mock_config_shared):
        """Test save_secrets stores remote MCP secrets correctly."""
        # Mock config
        mock_config = Mock()
        mock_config.get_value.return_value = {}
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer secret_token",
                    "Content-Type": "application/json",
                },
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "test_id"

        server.save_secrets()

        # Verify config was updated with correct secret key pattern
        mock_config.update_settings.assert_called_once()
        call_args = mock_config.update_settings.call_args[0][0]
        assert MCP_SECRETS_KEY in call_args
        assert (
            call_args[MCP_SECRETS_KEY]["test_id::Authorization"]
            == "Bearer secret_token"
        )

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_save_secrets_local_mcp(self, mock_config_shared):
        """Test save_secrets stores local MCP secrets correctly."""
        # Mock config
        mock_config = Mock()
        mock_config.get_value.return_value = {}
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"API_KEY": "secret_key", "PORT": "3000"},
                "secret_env_var_keys": ["API_KEY"],
            },
        )
        server.id = "test_id"

        server.save_secrets()

        # Verify config was updated with correct secret key pattern
        mock_config.update_settings.assert_called_once()
        call_args = mock_config.update_settings.call_args[0][0]
        assert MCP_SECRETS_KEY in call_args
        assert call_args[MCP_SECRETS_KEY]["test_id::API_KEY"] == "secret_key"

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_save_secrets_no_secret_keys(self, mock_config_shared):
        """Test save_secrets does nothing when no secret keys defined."""
        mock_config = Mock()
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
            },
        )
        server.id = "test_id"

        server.save_secrets()

        # Should not call config update when no secrets to save
        mock_config.update_settings.assert_not_called()

    def test_save_secrets_none_id_raises_error(self):
        """Test save_secrets raises error when server ID is None."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer token"},
                "secret_header_keys": ["Authorization"],
            },
        )
        # Manually set ID to None to test the validation
        server.id = None

        with pytest.raises(
            ValueError, match="Server ID cannot be None when saving secrets"
        ):
            server.save_secrets()

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_delete_secrets(self, mock_config_shared):
        """Test delete_secrets removes all secrets for the server."""
        # Mock config with existing secrets
        mock_config = Mock()
        existing_secrets = {
            "test_id::Authorization": "Bearer token",
            "test_id::X-API-Key": "api_key",
            "other_server::key": "other_value",
        }
        mock_config.get_value.return_value = existing_secrets.copy()
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer placeholder"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "test_id"

        server.delete_secrets()

        # Verify config was updated with secrets removed
        mock_config.update_settings.assert_called_once()
        call_args = mock_config.update_settings.call_args[0][0]
        expected_secrets = {
            "other_server::key": "other_value"
        }  # Only other server's secrets should remain
        assert call_args[MCP_SECRETS_KEY] == expected_secrets

    @patch("kiln_ai.datamodel.external_tool_server.Config.shared")
    def test_delete_secrets_no_existing_secrets(self, mock_config_shared):
        """Test delete_secrets handles case when no secrets exist."""
        # Mock config with no existing secrets
        mock_config = Mock()
        mock_config.get_value.return_value = {}
        mock_config_shared.return_value = mock_config

        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer placeholder"},
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "test_id"

        server.delete_secrets()

        # Should still call update_settings to maintain consistency
        mock_config.update_settings.assert_called_once()
        call_args = mock_config.update_settings.call_args[0][0]
        assert call_args[MCP_SECRETS_KEY] == {}


class TestExternalToolServerSaveToFileOverride:
    """Tests for ExternalToolServer save_to_file method that strips secrets."""

    @patch("kiln_ai.datamodel.external_tool_server.ExternalToolServer.save_secrets")
    @patch.object(
        ExternalToolServer.__bases__[0], "save_to_file"
    )  # Mock parent save_to_file
    def test_save_to_file_strips_remote_mcp_secrets(
        self, mock_parent_save, mock_save_secrets
    ):
        """Test save_to_file strips secret headers from remote MCP properties."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer secret_token",
                    "Content-Type": "application/json",
                    "X-API-Key": "secret_key",
                },
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )

        server.save_to_file()

        # Verify secrets were stripped from headers
        expected_headers = {"Content-Type": "application/json"}
        assert server.properties["headers"] == expected_headers

        # Verify parent save_to_file was called
        mock_parent_save.assert_called_once()

    @patch("kiln_ai.datamodel.external_tool_server.ExternalToolServer.save_secrets")
    @patch.object(ExternalToolServer.__bases__[0], "save_to_file")
    def test_save_to_file_strips_local_mcp_secrets(
        self, mock_parent_save, mock_save_secrets
    ):
        """Test save_to_file strips secret env vars from local MCP properties."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {
                    "API_KEY": "secret_key",
                    "PORT": "3000",
                    "DB_PASSWORD": "secret_password",
                },
                "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
            },
        )

        server.save_to_file()

        # Verify secrets were stripped from env_vars
        expected_env_vars = {"PORT": "3000"}
        assert server.properties["env_vars"] == expected_env_vars

        # Verify parent save_to_file was called
        mock_parent_save.assert_called_once()

    @patch("kiln_ai.datamodel.external_tool_server.ExternalToolServer.save_secrets")
    @patch.object(ExternalToolServer.__bases__[0], "save_to_file")
    def test_save_to_file_no_secrets_to_strip(
        self, mock_parent_save, mock_save_secrets
    ):
        """Test save_to_file works correctly when no secrets need stripping."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
            },
        )

        original_headers = server.properties["headers"].copy()
        server.save_to_file()

        # Headers should remain unchanged
        assert server.properties["headers"] == original_headers

        # Verify parent save_to_file was called
        mock_parent_save.assert_called_once()

    @patch("kiln_ai.datamodel.external_tool_server.ExternalToolServer.save_secrets")
    @patch.object(ExternalToolServer.__bases__[0], "save_to_file")
    def test_save_to_file_handles_missing_headers_dict(
        self, mock_parent_save, mock_save_secrets
    ):
        """Test save_to_file handles case where headers dict is missing."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},  # Empty headers
                "secret_header_keys": ["Authorization"],
            },
        )

        server.save_to_file()

        # Should not raise error and headers should remain empty
        assert server.properties["headers"] == {}
        mock_parent_save.assert_called_once()

    @patch("kiln_ai.datamodel.external_tool_server.ExternalToolServer.save_secrets")
    @patch.object(ExternalToolServer.__bases__[0], "save_to_file")
    def test_save_to_file_handles_missing_env_vars_dict(
        self, mock_parent_save, mock_save_secrets
    ):
        """Test save_to_file handles case where env_vars dict is missing."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {},  # Empty env_vars
                "secret_env_var_keys": ["API_KEY"],
            },
        )

        server.save_to_file()

        # Should not raise error and env_vars should remain empty
        assert server.properties["env_vars"] == {}
        mock_parent_save.assert_called_once()


class TestExternalToolServerExhaustiveEnumError:
    """Tests for ExternalToolServer exhaustive enum error coverage."""

    def test_validate_required_fields_exhaustive_enum_error(self, remote_mcp_minimal):
        """Test validate_required_fields raises exhaustive enum error for invalid type."""
        server = remote_mcp_minimal

        # Bypass Pydantic validation to set an invalid enum value
        object.__setattr__(server, "type", "invalid_type")

        # Call the underlying validator function directly
        validator_func = ExternalToolServer.__dict__["validate_required_fields"]
        with pytest.raises(ValueError, match="Unhandled enum value: invalid_type"):
            validator_func(server)

    def test_get_secret_keys_exhaustive_enum_error(self, remote_mcp_minimal):
        """Test get_secret_keys raises exhaustive enum error for invalid type."""
        server = remote_mcp_minimal

        # Bypass Pydantic validation to set an invalid enum value
        object.__setattr__(server, "type", "invalid_type")

        with pytest.raises(ValueError, match="Unhandled enum value: invalid_type"):
            server.get_secret_keys()

    def test_save_secrets_exhaustive_enum_error(self, remote_mcp_with_secrets):
        """Test save_secrets raises exhaustive enum error for invalid type."""
        server = remote_mcp_with_secrets
        server.id = "test_id"

        # Bypass Pydantic validation to set an invalid enum value
        object.__setattr__(server, "type", "invalid_type")

        with pytest.raises(ValueError, match="Unhandled enum value: invalid_type"):
            server.save_secrets()

    @patch.object(ExternalToolServer.__bases__[0], "save_to_file")
    def test_save_to_file_exhaustive_enum_error(
        self, mock_parent_save, remote_mcp_with_secrets
    ):
        """Test save_to_file raises exhaustive enum error for invalid type."""
        server = remote_mcp_with_secrets

        # Bypass Pydantic validation to set an invalid enum value
        object.__setattr__(server, "type", "invalid_type")

        with pytest.raises(ValueError, match="Unhandled enum value: invalid_type"):
            server.save_to_file()
