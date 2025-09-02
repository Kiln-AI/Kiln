import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType


class TestExternalToolServerValidation:
    """Tests for ExternalToolServer model validation, including secret header keys."""

    def test_remote_mcp_valid_minimal(self):
        """Test ExternalToolServer with minimal valid remote MCP configuration."""
        server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://example.com/mcp",
                "headers": {},
            },
        )

        assert server.name == "test_server"
        assert server.type == ToolServerType.remote_mcp
        assert server.properties["server_url"] == "https://example.com/mcp"
        assert server.properties["headers"] == {}

    def test_remote_mcp_valid_with_headers(self):
        """Test ExternalToolServer with valid remote MCP configuration including headers."""
        server = ExternalToolServer(
            name="test_server_with_headers",
            type=ToolServerType.remote_mcp,
            properties={
                "server_url": "https://api.example.com/mcp",
                "headers": {
                    "Authorization": "Bearer token123",
                    "Content-Type": "application/json",
                },
            },
        )

        assert server.name == "test_server_with_headers"
        assert len(server.properties["headers"]) == 2
        assert server.properties["headers"]["Authorization"] == "Bearer token123"

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

    def test_local_mcp_valid_minimal(self):
        """Test ExternalToolServer with minimal valid local MCP configuration."""
        server = ExternalToolServer(
            name="local_server",
            type=ToolServerType.local_mcp,
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {},
            },
        )

        assert server.name == "local_server"
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
