from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.config import MCP_SECRETS_KEY, Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error


class TestExternalToolServer:
    @pytest.fixture
    def mock_config(self):
        """Mock Config.shared() to avoid file system dependencies."""
        with patch.object(Config, "shared") as mock_shared:
            config_instance = Mock()
            config_instance.get_value.return_value = {}
            config_instance.update_settings = Mock()
            mock_shared.return_value = config_instance
            yield config_instance

    @pytest.fixture
    def remote_mcp_base_props(self) -> Dict[str, Any]:
        """Base properties for remote MCP server."""
        return {
            "server_url": "https://api.example.com/mcp",
            "headers": {"Content-Type": "application/json"},
        }

    @pytest.fixture
    def local_mcp_base_props(self) -> Dict[str, Any]:
        """Base properties for local MCP server."""
        return {
            "command": "python",
            "args": ["-m", "mcp_server"],
            "env_vars": {},
        }

    @pytest.mark.parametrize(
        "server_type, properties",
        [
            (
                ToolServerType.remote_mcp,
                {
                    "server_url": "https://api.example.com/mcp",
                    "headers": {"Authorization": "Bearer token123"},
                },
            ),
            (
                ToolServerType.local_mcp,
                {
                    "command": "python",
                    "args": ["-m", "server"],
                    "env_vars": {"API_KEY": "secret123"},
                },
            ),
        ],
    )
    def test_valid_server_creation(self, mock_config, server_type, properties):
        """Test creating valid servers of both types."""
        server = ExternalToolServer(
            name="test-server",
            type=server_type,
            description="Test server",
            properties=properties,
        )

        assert server.name == "test-server"
        assert server.type == server_type
        assert server.description == "Test server"
        assert server.properties == properties

    @pytest.mark.parametrize(
        "server_type, invalid_props, expected_error",
        [
            # Remote MCP validation errors
            (ToolServerType.remote_mcp, {}, "server_url must be a string"),
            (ToolServerType.remote_mcp, {"server_url": ""}, "server_url is required"),
            (
                ToolServerType.remote_mcp,
                {"server_url": 123},
                "server_url must be a string",
            ),
            (
                ToolServerType.remote_mcp,
                {"server_url": "http://test.com"},
                "headers must be set",
            ),
            (
                ToolServerType.remote_mcp,
                {"server_url": "http://test.com", "headers": "not-a-dict"},
                "headers must be a dictionary",
            ),
            (
                ToolServerType.remote_mcp,
                {
                    "server_url": "http://test.com",
                    "headers": {},
                    "secret_header_keys": "not-a-list",
                },
                "secret_header_keys must be a list",
            ),
            (
                ToolServerType.remote_mcp,
                {
                    "server_url": "http://test.com",
                    "headers": {},
                    "secret_header_keys": [123],
                },
                "secret_header_keys must contain only strings",
            ),
            # Local MCP validation errors
            (ToolServerType.local_mcp, {}, "command must be a string"),
            (ToolServerType.local_mcp, {"command": ""}, "command is required"),
            (ToolServerType.local_mcp, {"command": 123}, "command must be a string"),
            (
                ToolServerType.local_mcp,
                {"command": "python"},
                "arguments must be a list",
            ),
            (
                ToolServerType.local_mcp,
                {"command": "python", "args": "not-a-list"},
                "arguments must be a list",
            ),
            (
                ToolServerType.local_mcp,
                {"command": "python", "args": [], "env_vars": "not-a-dict"},
                "environment variables must be a dictionary",
            ),
            (
                ToolServerType.local_mcp,
                {
                    "command": "python",
                    "args": [],
                    "env_vars": {},
                    "secret_env_var_keys": "not-a-list",
                },
                "secret_env_var_keys must be a list",
            ),
            (
                ToolServerType.local_mcp,
                {
                    "command": "python",
                    "args": [],
                    "env_vars": {},
                    "secret_env_var_keys": [123],
                },
                "secret_env_var_keys must contain only strings",
            ),
        ],
    )
    def test_validation_errors(
        self, mock_config, server_type, invalid_props, expected_error
    ):
        """Test validation errors for invalid configurations."""
        with pytest.raises((ValueError, Exception)) as exc_info:
            ExternalToolServer(
                name="test-server", type=server_type, properties=invalid_props
            )
        # Check that the expected error message is in the exception string
        assert expected_error in str(exc_info.value)

    def test_get_secret_keys_remote_mcp(self, mock_config, remote_mcp_base_props):
        """Test get_secret_keys for remote MCP servers."""
        # No secret keys defined
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties=remote_mcp_base_props,
        )
        assert server.get_secret_keys() == []

        # With secret header keys
        props_with_secrets = {
            **remote_mcp_base_props,
            "secret_header_keys": ["Authorization", "X-API-Key"],
        }
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties=props_with_secrets,
        )
        assert server.get_secret_keys() == ["Authorization", "X-API-Key"]

    def test_get_secret_keys_local_mcp(self, mock_config, local_mcp_base_props):
        """Test get_secret_keys for local MCP servers."""
        # No secret keys defined
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.local_mcp,
            properties=local_mcp_base_props,
        )
        assert server.get_secret_keys() == []

        # With secret env var keys
        props_with_secrets = {
            **local_mcp_base_props,
            "secret_env_var_keys": ["API_KEY", "SECRET_TOKEN"],
        }
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.local_mcp,
            properties=props_with_secrets,
        )
        assert server.get_secret_keys() == ["API_KEY", "SECRET_TOKEN"]

    def test_secret_processing_remote_mcp_initialization(self, mock_config):
        """Test secret processing during remote MCP server initialization."""
        properties = {
            "server_url": "https://api.example.com/mcp",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer secret123",
                "X-API-Key": "api-key-456",
            },
            "secret_header_keys": ["Authorization", "X-API-Key"],
        }

        server = ExternalToolServer(
            name="test-server", type=ToolServerType.remote_mcp, properties=properties
        )

        # Secrets should be extracted to _unsaved_secrets
        assert server._unsaved_secrets == {
            "Authorization": "Bearer secret123",
            "X-API-Key": "api-key-456",
        }

        # Secrets should be removed from headers
        assert server.properties["headers"] == {"Content-Type": "application/json"}

    def test_secret_processing_local_mcp_initialization(self, mock_config):
        """Test secret processing during local MCP server initialization."""
        properties = {
            "command": "python",
            "args": ["-m", "server"],
            "env_vars": {
                "PATH": "/usr/bin",
                "API_KEY": "secret123",
                "DB_PASSWORD": "db-secret-456",
            },
            "secret_env_var_keys": ["API_KEY", "DB_PASSWORD"],
        }

        server = ExternalToolServer(
            name="test-server", type=ToolServerType.local_mcp, properties=properties
        )

        # Secrets should be extracted to _unsaved_secrets
        assert server._unsaved_secrets == {
            "API_KEY": "secret123",
            "DB_PASSWORD": "db-secret-456",
        }

        # Secrets should be removed from env_vars
        assert server.properties["env_vars"] == {"PATH": "/usr/bin"}

    def test_secret_processing_property_update_remote_mcp(
        self, mock_config, remote_mcp_base_props
    ):
        """Test secret processing when properties are updated via __setattr__ for remote MCP."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )

        # Clear any existing unsaved secrets
        server._unsaved_secrets.clear()

        # Update properties with secrets
        new_properties = {
            **remote_mcp_base_props,
            "headers": {
                **remote_mcp_base_props["headers"],
                "Authorization": "Bearer new-token",
            },
            "secret_header_keys": ["Authorization"],
        }

        server.properties = new_properties

        # Secret should be processed (extracted and removed from headers)
        assert server._unsaved_secrets == {"Authorization": "Bearer new-token"}
        assert "Authorization" not in server.properties["headers"]

    def test_secret_processing_clears_existing_secrets(
        self, mock_config, remote_mcp_base_props
    ):
        """Test that secret processing clears existing _unsaved_secrets."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )

        # Manually add some unsaved secrets
        server._unsaved_secrets = {"OldSecret": "old-value"}

        # Update properties - should clear old secrets
        new_properties = {
            **remote_mcp_base_props,
            "headers": {
                **remote_mcp_base_props["headers"],
                "Authorization": "Bearer new-token",
            },
            "secret_header_keys": ["Authorization"],
        }

        server.properties = new_properties

        # Only new secret should remain
        assert server._unsaved_secrets == {"Authorization": "Bearer new-token"}
        assert "OldSecret" not in server._unsaved_secrets

    def test_retrieve_secrets_from_config(self, mock_config, remote_mcp_base_props):
        """Test retrieving secrets from config storage."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "server-123"

        # Mock config to return saved secrets
        mock_config.get_value.return_value = {
            "server-123::Authorization": "Bearer config-token",
            "server-123::X-API-Key": "config-api-key",
            "other-server::Authorization": "other-token",
        }

        secrets, missing = server.retrieve_secrets()

        assert secrets == {
            "Authorization": "Bearer config-token",
            "X-API-Key": "config-api-key",
        }
        assert missing == []

    def test_retrieve_secrets_from_unsaved(self, mock_config, remote_mcp_base_props):
        """Test retrieving secrets from unsaved storage when not in config."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "server-123"
        server._unsaved_secrets = {
            "Authorization": "Bearer unsaved-token",
            "X-API-Key": "unsaved-api-key",
        }

        # Mock config to return empty
        mock_config.get_value.return_value = {}

        secrets, missing = server.retrieve_secrets()

        assert secrets == {
            "Authorization": "Bearer unsaved-token",
            "X-API-Key": "unsaved-api-key",
        }
        assert missing == []

    def test_retrieve_secrets_config_takes_precedence(
        self, mock_config, remote_mcp_base_props
    ):
        """Test that config secrets take precedence over unsaved secrets."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "server-123"
        server._unsaved_secrets = {"Authorization": "Bearer unsaved-token"}

        # Mock config to return saved secret
        mock_config.get_value.return_value = {
            "server-123::Authorization": "Bearer config-token"
        }

        secrets, missing = server.retrieve_secrets()

        assert secrets == {"Authorization": "Bearer config-token"}
        assert missing == []

    def test_retrieve_secrets_with_missing_values(
        self, mock_config, remote_mcp_base_props
    ):
        """Test retrieving secrets when some are missing."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization", "X-API-Key", "Missing-Key"],
            },
        )
        server.id = "server-123"

        # Mock config with only partial secrets
        mock_config.get_value.return_value = {
            "server-123::Authorization": "Bearer config-token"
        }

        secrets, missing = server.retrieve_secrets()

        assert secrets == {"Authorization": "Bearer config-token"}
        assert set(missing) == {"X-API-Key", "Missing-Key"}

    def test_retrieve_secrets_no_secret_keys(self, mock_config, remote_mcp_base_props):
        """Test retrieving secrets when no secret keys are defined."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties=remote_mcp_base_props,  # No secret_header_keys
        )

        secrets, missing = server.retrieve_secrets()

        assert secrets == {}
        assert missing == []

    def test_save_secrets(self, mock_config, remote_mcp_base_props):
        """Test saving unsaved secrets to config."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "server-123"
        server._unsaved_secrets = {
            "Authorization": "Bearer token",
            "X-API-Key": "api-key",
        }

        # Mock existing config secrets
        existing_secrets = {"other-server::key": "other-value"}
        mock_config.get_value.return_value = existing_secrets

        server._save_secrets()

        # Should update config with new secrets
        expected_secrets = {
            "other-server::key": "other-value",
            "server-123::Authorization": "Bearer token",
            "server-123::X-API-Key": "api-key",
        }
        mock_config.update_settings.assert_called_once_with(
            {MCP_SECRETS_KEY: expected_secrets}
        )

        # Should clear unsaved secrets
        assert server._unsaved_secrets == {}

    def test_save_secrets_no_id_error(self, mock_config, remote_mcp_base_props):
        """Test that saving secrets without ID raises error."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        # Manually set unsaved secrets to bypass the empty check
        server._unsaved_secrets = {"Authorization": "Bearer token"}
        # Explicitly set ID to None to test the error condition
        server.id = None

        with pytest.raises(
            ValueError, match="Server ID cannot be None when saving secrets"
        ):
            server._save_secrets()

    def test_save_secrets_with_no_unsaved_secrets(
        self, mock_config, remote_mcp_base_props
    ):
        """Test that saving secrets with no unsaved secrets does nothing."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "server-123"

        # No _unsaved_secrets set

        server._save_secrets()

        # Should not call update_settings
        mock_config.update_settings.assert_not_called()

    def test_delete_secrets(self, mock_config, remote_mcp_base_props):
        """Test deleting secrets from config."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        server.id = "server-123"

        # Mock existing config secrets
        existing_secrets = {
            "server-123::Authorization": "Bearer token",
            "server-123::X-API-Key": "api-key",
            "other-server::Authorization": "other-token",
        }
        mock_config.get_value.return_value = existing_secrets

        server.delete_secrets()

        # Should remove only this server's secrets
        expected_secrets = {"other-server::Authorization": "other-token"}
        mock_config.update_settings.assert_called_once_with(
            {MCP_SECRETS_KEY: expected_secrets}
        )

    def test_delete_secrets_with_no_existing_secrets(
        self, mock_config, remote_mcp_base_props
    ):
        """Test deleting secrets when none exist in config."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "server-123"

        # Mock empty config
        mock_config.get_value.return_value = {}

        server.delete_secrets()

        # Should still call update_settings with empty dict
        mock_config.update_settings.assert_called_once_with({MCP_SECRETS_KEY: {}})

    def test_save_to_file_saves_secrets_first(self, mock_config, remote_mcp_base_props):
        """Test that save_to_file automatically saves unsaved secrets first."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "server-123"
        server._unsaved_secrets = {"Authorization": "Bearer token"}

        mock_config.get_value.return_value = {}

        with patch(
            "kiln_ai.datamodel.basemodel.KilnParentedModel.save_to_file"
        ) as mock_parent_save:
            server.save_to_file()

            # Should save secrets first
            mock_config.update_settings.assert_called_once()
            assert server._unsaved_secrets == {}

            # Should call parent save_to_file
            mock_parent_save.assert_called_once()

    def test_save_to_file_no_unsaved_secrets(self, mock_config, remote_mcp_base_props):
        """Test save_to_file when no unsaved secrets exist."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties=remote_mcp_base_props,
        )

        with patch(
            "kiln_ai.datamodel.basemodel.KilnParentedModel.save_to_file"
        ) as mock_parent_save:
            server.save_to_file()

            # Should not save secrets
            mock_config.update_settings.assert_not_called()

            # Should still call parent save_to_file
            mock_parent_save.assert_called_once()

    def test_config_secret_key_format(self, mock_config, remote_mcp_base_props):
        """Test the _config_secret_key method formats keys correctly."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties=remote_mcp_base_props,
        )
        server.id = "server-123"

        assert server._config_secret_key("Authorization") == "server-123::Authorization"
        assert server._config_secret_key("X-API-Key") == "server-123::X-API-Key"

    def test_model_serialization_excludes_secrets(self, mock_config):
        """Test that model serialization excludes _unsaved_secrets private attribute and secrets from properties."""
        # Test all server types to ensure we update this test when new types are added
        for server_type in ToolServerType:
            match server_type:
                case ToolServerType.remote_mcp:
                    server = ExternalToolServer(
                        name="test-remote-server",
                        type=server_type,
                        properties={
                            "server_url": "https://api.example.com/mcp",
                            "headers": {"Authorization": "Bearer secret"},
                            "secret_header_keys": ["Authorization"],
                        },
                    )
                    data = server.model_dump()
                    assert "_unsaved_secrets" not in data
                    assert "Authorization" not in data["properties"]["headers"]

                case ToolServerType.local_mcp:
                    server = ExternalToolServer(
                        name="test-local-server",
                        type=server_type,
                        properties={
                            "command": "python",
                            "args": ["-m", "server"],
                            "env_vars": {"API_KEY": "secret"},
                            "secret_env_var_keys": ["API_KEY"],
                        },
                    )
                    data = server.model_dump()
                    assert "_unsaved_secrets" not in data
                    assert "API_KEY" not in data["properties"]["env_vars"]

                case _:
                    raise_exhaustive_enum_error(server_type)

    def test_empty_secret_keys_list(self, mock_config, remote_mcp_base_props):
        """Test behavior with empty secret_header_keys list."""
        properties = {**remote_mcp_base_props, "secret_header_keys": []}

        server = ExternalToolServer(
            name="test-server", type=ToolServerType.remote_mcp, properties=properties
        )

        assert server.get_secret_keys() == []
        secrets, missing = server.retrieve_secrets()
        assert secrets == {}
        assert missing == []

    def test_none_mcp_secrets_in_config(self, mock_config, remote_mcp_base_props):
        """Test behavior when MCP_SECRETS_KEY returns None from config."""
        server = ExternalToolServer(
            name="test-server",
            type=ToolServerType.remote_mcp,
            properties={
                **remote_mcp_base_props,
                "secret_header_keys": ["Authorization"],
            },
        )
        server.id = "server-123"

        # Mock config returning None for MCP_SECRETS_KEY
        mock_config.get_value.return_value = None

        secrets, missing = server.retrieve_secrets()

        assert secrets == {}
        assert missing == ["Authorization"]
