import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData
from pydantic import ValidationError

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_session_manager import MCPSessionManager
from kiln_ai.utils.config import MCP_SECRETS_KEY

# Import ExceptionGroup with proper fallback for Python 3.10
try:
    from exceptiongroup import ExceptionGroup  # type: ignore[import-untyped]
except ImportError:
    # Python 3.11+ has ExceptionGroup in builtins
    pass


class TestMCPSessionManager:
    """Unit tests for MCPSessionManager."""

    def test_singleton_behavior(self):
        """Test that MCPSessionManager follows singleton pattern."""
        # Get two instances
        instance1 = MCPSessionManager.shared()
        instance2 = MCPSessionManager.shared()

        # They should be the same object
        assert instance1 is instance2
        assert id(instance1) == id(instance2)

    def test_singleton_reset_for_testing(self):
        """Test that we can reset the singleton for testing purposes."""
        # Get an instance
        instance1 = MCPSessionManager.shared()

        # Reset the singleton
        MCPSessionManager._shared_instance = None

        # Get a new instance
        instance2 = MCPSessionManager.shared()

        # They should be different objects
        assert instance1 is not instance2

    def test_extract_first_exception_direct_match(self):
        """Test _extract_first_exception with direct exception type match."""
        manager = MCPSessionManager()

        # Test with matching exception type
        error = ValueError("test error")
        result = manager._extract_first_exception(error, ValueError)
        assert result is error

        # Test with non-matching exception type
        result = manager._extract_first_exception(error, TypeError)
        assert result is None

    def test_extract_first_exception_tuple_types(self):
        """Test _extract_first_exception with tuple of exception types."""
        manager = MCPSessionManager()

        # Test with matching type in tuple
        error = ConnectionError("connection failed")
        result = manager._extract_first_exception(error, (ValueError, ConnectionError))
        assert result is error

        # Test with non-matching types in tuple
        result = manager._extract_first_exception(error, (TypeError, RuntimeError))
        assert result is None

    def test_extract_first_exception_with_exception_group(self):
        """Test _extract_first_exception with ExceptionGroup (Python 3.11+ or backport)."""
        manager = MCPSessionManager()

        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create nested exceptions
        inner_error = ValueError("inner error")
        other_error = TypeError("other error")
        group = ExceptionGroup("group error", [inner_error, other_error])

        # Test extracting matching exception from group
        result = manager._extract_first_exception(group, ValueError)
        assert result is inner_error

        # Test extracting non-matching exception from group
        result = manager._extract_first_exception(group, RuntimeError)
        assert result is None

    def test_extract_first_exception_nested_exception_groups(self):
        """Test _extract_first_exception with nested ExceptionGroups."""
        manager = MCPSessionManager()

        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create deeply nested exception structure
        target_error = FileNotFoundError("file not found")
        inner_group = ExceptionGroup("inner group", [target_error, ValueError("other")])
        outer_group = ExceptionGroup(
            "outer group", [TypeError("type error"), inner_group]
        )

        # Should find the deeply nested exception
        result = manager._extract_first_exception(outer_group, FileNotFoundError)
        assert result is target_error

        # Should not find non-existent exception type
        result = manager._extract_first_exception(outer_group, OSError)
        assert result is None

    # Note: Testing invalid tool server types is not possible because:
    # 1. The ToolServerType enum only has one value: remote_mcp
    # 2. Pydantic validation prevents creating objects with invalid types
    # 3. Pydantic prevents modifying the type field to invalid values after creation
    # The RuntimeError check in MCPSessionManager.mcp_client is defensive programming
    # that would only be triggered if new enum values are added without updating the match statement.

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_successful_session_creation(self, mock_client):
        """Test successful MCP session creation with mocked client."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Create a valid tool server
        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Authorization": "Bearer token123"},
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                # Verify session is returned
                assert session is mock_session_instance

                # Verify initialize was called
                mock_session_instance.initialize.assert_called_once()

        # Verify streamablehttp_client was called with correct parameters
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers={"Authorization": "Bearer token123"}
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_session_with_empty_headers(self, mock_client):
        """Test session creation when empty headers dict is provided."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Create a tool server with empty headers
        tool_server = ExternalToolServer(
            name="empty_headers_server",
            type=ToolServerType.remote_mcp,
            description="Server with empty headers",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {},  # Empty headers dict is required by pydantic
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify streamablehttp_client was called with empty headers dict
        mock_client.assert_called_once_with("http://example.com/mcp", headers={})

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_session_with_secret_headers(self, mock_config, mock_client):
        """Test session creation with secret headers retrieved from config."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Mock config with secret headers
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = {
            "test_server_id::Authorization": "Bearer secret-token-123",
            "test_server_id::X-API-Key": "api-key-456",
            "other_server::Token": "other-token",  # Should be ignored
        }
        mock_config.return_value = mock_config_instance

        # Create a tool server with secret header keys
        tool_server = ExternalToolServer(
            name="secret_headers_server",
            type=ToolServerType.remote_mcp,
            description="Server with secret headers",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        # Set the server ID to match our mock secrets
        tool_server.id = "test_server_id"

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify config was accessed for mcp_secrets
        mock_config_instance.get_value.assert_called_once_with(MCP_SECRETS_KEY)

        # Verify streamablehttp_client was called with merged headers
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret-token-123",
            "X-API-Key": "api-key-456",
        }
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers=expected_headers
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_session_with_partial_secret_headers(self, mock_config, mock_client):
        """Test session creation when only some secret headers are found in config."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Mock config with only one of the expected secret headers
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = {
            "test_server_id::Authorization": "Bearer found-token",
            # Missing test_server_id::X-API-Key
        }
        mock_config.return_value = mock_config_instance

        # Create a tool server expecting two secret headers
        tool_server = ExternalToolServer(
            name="partial_secret_server",
            type=ToolServerType.remote_mcp,
            description="Server with partial secret headers",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        tool_server.id = "test_server_id"

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify only the found secret header is merged
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer found-token",
            # X-API-Key should not be present since it wasn't found in config
        }
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers=expected_headers
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_session_with_no_secret_headers_config(
        self, mock_config, mock_client
    ):
        """Test session creation when config has no mcp_secrets."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Mock config with no mcp_secrets (returns None)
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = None
        mock_config.return_value = mock_config_instance

        # Create a tool server expecting secret headers
        tool_server = ExternalToolServer(
            name="no_secrets_config_server",
            type=ToolServerType.remote_mcp,
            description="Server with no secrets in config",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": ["Authorization"],
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify only the original headers are used
        expected_headers = {"Content-Type": "application/json"}
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers=expected_headers
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_session_with_empty_secret_header_keys(self, mock_client):
        """Test session creation with empty secret_header_keys list."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Create a tool server with empty secret header keys
        tool_server = ExternalToolServer(
            name="empty_secret_keys_server",
            type=ToolServerType.remote_mcp,
            description="Server with empty secret header keys",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": [],  # Empty list
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify only the original headers are used (no config access needed for empty list)
        expected_headers = {"Content-Type": "application/json"}
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers=expected_headers
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_session_with_missing_secret_header_keys_property(self, mock_client):
        """Test session creation when secret_header_keys property is missing."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Create a tool server without secret_header_keys property
        tool_server = ExternalToolServer(
            name="missing_secret_keys_server",
            type=ToolServerType.remote_mcp,
            description="Server without secret header keys property",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                # No secret_header_keys property
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify only the original headers are used (no config access needed when property missing)
        expected_headers = {"Content-Type": "application/json"}
        mock_client.assert_called_once_with(
            "http://example.com/mcp", headers=expected_headers
        )

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_secret_headers_do_not_modify_original_properties(
        self, mock_config, mock_client
    ):
        """Test that secret headers are not saved back to the original tool server properties."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Mock config with secret headers
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = {
            "test_server_id::Authorization": "Bearer secret-token-123",
            "test_server_id::X-API-Key": "api-key-456",
        }
        mock_config.return_value = mock_config_instance

        # Create a tool server with secret header keys
        tool_server = ExternalToolServer(
            name="bug_test_server",
            type=ToolServerType.remote_mcp,
            description="Server to test the secret headers bug",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": ["Authorization", "X-API-Key"],
            },
        )
        # Set the server ID to match our mock secrets
        tool_server.id = "test_server_id"

        # Store original headers for comparison
        original_headers = tool_server.properties["headers"].copy()

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            # Use the session multiple times to ensure the bug doesn't occur
            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

            # Check that original headers are unchanged after first use
            assert tool_server.properties["headers"] == original_headers
            assert "Authorization" not in tool_server.properties["headers"]
            assert "X-API-Key" not in tool_server.properties["headers"]

            # Use the session a second time to ensure the bug doesn't occur on subsequent uses
            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

            # Check that original headers are still unchanged after second use
            assert tool_server.properties["headers"] == original_headers
            assert "Authorization" not in tool_server.properties["headers"]
            assert "X-API-Key" not in tool_server.properties["headers"]

        # Verify streamablehttp_client was called with merged headers both times
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret-token-123",
            "X-API-Key": "api-key-456",
        }
        # Should have been called twice (once for each session)
        assert mock_client.call_count == 2
        for call in mock_client.call_args_list:
            assert call[0][0] == "http://example.com/mcp"
            assert call[1]["headers"] == expected_headers

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_400_error(self, mock_client):
        """Test remote MCP session handles HTTP 400 error with user-friendly message."""
        # Create HTTP 400 error
        response = MagicMock()
        response.status_code = 400
        http_error = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="The MCP server rejected the request"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_401_error(self, mock_client):
        """Test remote MCP session handles HTTP 401 error with user-friendly message."""
        # Create HTTP 401 error
        response = MagicMock()
        response.status_code = 401
        http_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="Authentication to the MCP server failed"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_403_error(self, mock_client):
        """Test remote MCP session handles HTTP 403 error with user-friendly message."""
        # Create HTTP 403 error
        response = MagicMock()
        response.status_code = 403
        http_error = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="Access to the MCP server is forbidden"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_404_error(self, mock_client):
        """Test remote MCP session handles HTTP 404 error with user-friendly message."""
        # Create HTTP 404 error
        response = MagicMock()
        response.status_code = 404
        http_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="MCP server not found"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_500_error(self, mock_client):
        """Test remote MCP session handles HTTP 500+ errors with user-friendly message."""
        # Create HTTP 500 error
        response = MagicMock()
        response.status_code = 500
        http_error = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError, match="The MCP server encountered an internal error"
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_502_error(self, mock_client):
        """Test remote MCP session handles HTTP 502 error (also 5xx) with user-friendly message."""
        # Create HTTP 502 error
        response = MagicMock()
        response.status_code = 502
        http_error = httpx.HTTPStatusError(
            "Bad Gateway", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError, match="The MCP server encountered an internal error"
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_other_error(self, mock_client):
        """Test remote MCP session handles other HTTP errors with generic message."""
        # Create HTTP 418 error (I'm a teapot - uncommon status code)
        response = MagicMock()
        response.status_code = 418
        http_error = httpx.HTTPStatusError(
            "I'm a teapot", request=MagicMock(), response=response
        )

        # Mock client to raise the HTTP error
        mock_client.return_value.__aenter__.side_effect = http_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="Failed to connect to the MCP server"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_error_in_exception_group(self, mock_client):
        """Test remote MCP session extracts HTTP error from ExceptionGroup."""
        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create HTTP error nested in ExceptionGroup
        response = MagicMock()
        response.status_code = 401
        http_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=response
        )
        group_error = ExceptionGroup(
            "Multiple errors", [ValueError("other error"), http_error]
        )

        # Mock client to raise the ExceptionGroup
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should extract the HTTP error from the group and handle it appropriately
        with pytest.raises(ValueError, match="Authentication to the MCP server failed"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_connection_error(self, mock_client):
        """Test remote MCP session handles ConnectionError with user-friendly message."""
        # Mock client to raise ConnectionError
        connection_error = ConnectionError("Connection refused")
        mock_client.return_value.__aenter__.side_effect = connection_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError,
            match="Unable to connect to MCP server due to: 'Connection refused'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_os_error(self, mock_client):
        """Test remote MCP session handles OSError with user-friendly message."""
        # Mock client to raise OSError
        os_error = OSError("Network is unreachable")
        mock_client.return_value.__aenter__.side_effect = os_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError,
            match="Unable to connect to MCP server due to: 'Network is unreachable'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_connection_error_in_exception_group(self, mock_client):
        """Test remote MCP session extracts connection error from ExceptionGroup."""
        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create connection error nested in ExceptionGroup
        connection_error = ConnectionError("Connection timeout")
        group_error = ExceptionGroup(
            "Multiple errors", [ValueError("other error"), connection_error]
        )

        # Mock client to raise the ExceptionGroup
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should extract the connection error from the group and handle it appropriately
        with pytest.raises(
            ValueError,
            match="Unable to connect to MCP server due to: 'Connection timeout'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_unknown_error_reraises(self, mock_client):
        """Test remote MCP session re-raises unknown errors."""
        # Mock client to raise an unknown error type
        unknown_error = RuntimeError("Unknown error")
        mock_client.return_value.__aenter__.side_effect = unknown_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should re-raise the original unknown error
        with pytest.raises(RuntimeError, match="Unknown error"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_demonstrates_bug_without_copy_fix(self, mock_config, mock_client):
        """
        Test that demonstrates the bug that would occur without the .copy() fix.
        This test simulates what would happen if we modified headers directly.
        """
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
            None,
        )

        # Mock config with secret headers
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = {
            "test_server_id::Authorization": "Bearer secret-token-123",
        }
        mock_config.return_value = mock_config_instance

        # Create a tool server with secret header keys
        tool_server = ExternalToolServer(
            name="bug_demo_server",
            type=ToolServerType.remote_mcp,
            description="Server to demonstrate the bug",
            properties={
                "server_url": "http://example.com/mcp",
                "headers": {"Content-Type": "application/json"},
                "secret_header_keys": ["Authorization"],
            },
        )
        tool_server.id = "test_server_id"

        # Store original headers for comparison
        original_headers = tool_server.properties["headers"].copy()

        # Simulate the buggy behavior by directly modifying the headers
        # (This is what would happen without the .copy() fix)
        buggy_headers = tool_server.properties.get("headers", {})  # No .copy()!

        # Simulate what the buggy code would do - directly modify the original headers
        secret_headers_keys = tool_server.properties.get("secret_header_keys", [])
        if secret_headers_keys:
            config = mock_config_instance
            mcp_secrets = config.get_value(MCP_SECRETS_KEY)
            if mcp_secrets:
                for header_name in secret_headers_keys:
                    header_value = mcp_secrets.get(f"{tool_server.id}::{header_name}")
                    if header_value:
                        buggy_headers[header_name] = header_value

        # Now the original properties would be contaminated with secrets!
        assert "Authorization" in tool_server.properties["headers"]
        assert (
            tool_server.properties["headers"]["Authorization"]
            == "Bearer secret-token-123"
        )

        # This demonstrates the security bug - secrets are now permanently stored
        # in the tool server properties and would be serialized/saved
        assert tool_server.properties["headers"] != original_headers

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_session_creation(self, mock_client):
        """Test successful local MCP session creation with mocked client."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
        )

        # Create a valid local tool server
        tool_server = ExternalToolServer(
            name="test_local_server",
            type=ToolServerType.local_mcp,
            description="Test local server",
            properties={
                "command": "python",
                "args": ["-m", "my_mcp_server"],
                "env_vars": {"API_KEY": "test123"},
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                # Verify session is returned
                assert session is mock_session_instance

                # Verify initialize was called
                mock_session_instance.initialize.assert_called_once()

        # Verify stdio_client was called with correct parameters
        call_args = mock_client.call_args[0][0]  # Get the StdioServerParameters
        assert call_args.command == "python"
        assert call_args.args == ["-m", "my_mcp_server"]
        # Verify that the original env vars are included plus PATH
        assert "API_KEY" in call_args.env
        assert call_args.env["API_KEY"] == "test123"
        assert "PATH" in call_args.env
        assert len(call_args.env["PATH"]) > 0

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_session_with_defaults(self, mock_client):
        """Test local MCP session creation with default env_vars."""
        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
        )

        # Create a tool server without env_vars (should default to {})
        tool_server = ExternalToolServer(
            name="test_local_server_defaults",
            type=ToolServerType.local_mcp,
            description="Test local server with defaults",
            properties={
                "command": "node",
                "args": ["server.js"],
                # No env_vars provided
            },
        )

        manager = MCPSessionManager.shared()

        with patch(
            "kiln_ai.tools.mcp_session_manager.ClientSession"
        ) as mock_session_class:
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                assert session is mock_session_instance

        # Verify stdio_client was called with PATH automatically added
        call_args = mock_client.call_args[0][0]
        # Should only contain PATH (no other env vars were provided)
        assert "PATH" in call_args.env
        assert len(call_args.env["PATH"]) > 0
        # Should not have any other env vars besides PATH
        assert len(call_args.env) == 1

    async def test_local_mcp_missing_command_error(self):
        """Test that missing command raises ValueError for local MCP."""
        with pytest.raises(
            ValidationError,
            match="command must be a string to start a local MCP server",
        ):
            ExternalToolServer(
                name="missing_command_server",
                type=ToolServerType.local_mcp,
                description="Server missing command",
                properties={
                    # No command provided
                    "args": ["arg1"],
                    "env_vars": {},
                },
            )

    async def test_local_mcp_missing_args_error(self):
        """Test that missing args raises ValueError for local MCP."""
        with pytest.raises(
            ValidationError,
            match="arguments must be a list to start a local MCP server",
        ):
            ExternalToolServer(
                name="missing_args_server",
                type=ToolServerType.local_mcp,
                description="Server missing args",
                properties={
                    "command": "python",
                    # No args provided
                    "env_vars": {},
                },
            )

    async def test_local_mcp_empty_args_allowed(self):
        """Test that empty args list is now allowed for local MCP."""
        # Should not raise any exception - empty args are now allowed
        tool_server = ExternalToolServer(
            name="empty_args_server",
            type=ToolServerType.local_mcp,
            description="Server with empty args",
            properties={
                "command": "python",
                "args": [],  # Empty args list should now be allowed
                "env_vars": {},
            },
        )

        assert tool_server.name == "empty_args_server"
        assert tool_server.type == ToolServerType.local_mcp
        assert tool_server.properties["args"] == []

    async def test_local_mcp_session_empty_command_runtime_error(self):
        """Test that empty command string raises ValueError during session creation."""
        # Create a valid tool server first
        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["arg1"],
                "env_vars": {},
            },
        )

        # Manually modify the properties after creation to bypass pydantic validation
        tool_server.properties["command"] = ""

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError,
            match="Attempted to start local MCP server, but no command was provided",
        ):
            async with manager.mcp_client(tool_server):
                pass

    async def test_local_mcp_session_invalid_args_type_runtime_error(self):
        """Test that non-list args raises ValueError during session creation."""
        # Create a valid tool server first
        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["arg1"],
                "env_vars": {},
            },
        )

        # Manually modify the properties after creation to bypass pydantic validation
        tool_server.properties["args"] = "not a list"

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError,
            match="Attempted to start local MCP server, but args is not a list of strings",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_local_mcp_session_with_secrets(self, mock_config, mock_client):
        """Test local MCP session creation with secret environment variables."""
        # Mock config to return different values based on the key
        mock_config_instance = MagicMock()

        def mock_get_value(key):
            if key == MCP_SECRETS_KEY:
                return {
                    "test_server_id::SECRET_API_KEY": "secret_value_123",
                    "test_server_id::ANOTHER_SECRET": "another_secret_value",
                }
            elif key == "custom_mcp_path":
                return None  # No custom path, will use shell path
            return None

        mock_config_instance.get_value.side_effect = mock_get_value
        mock_config.return_value = mock_config_instance

        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()

        # Configure the mock client context manager
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
        )

        # Create a tool server with secret env var keys
        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server with secrets",
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"PUBLIC_VAR": "public_value"},
                "secret_env_var_keys": ["SECRET_API_KEY", "ANOTHER_SECRET"],
            },
        )
        # Set the server ID to match our mock secrets
        tool_server.id = "test_server_id"

        manager = MCPSessionManager.shared()

        # Mock get_shell_path to return a simple PATH
        with (
            patch.object(manager, "get_shell_path", return_value="/usr/bin:/bin"),
            patch(
                "kiln_ai.tools.mcp_session_manager.ClientSession"
            ) as mock_session_class,
        ):
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server) as session:
                # Verify session is returned
                assert session is mock_session_instance

                # Verify initialize was called
                mock_session_instance.initialize.assert_called_once()

        # Verify config was accessed for mcp_secrets
        assert mock_config_instance.get_value.call_count == 2
        mock_config_instance.get_value.assert_any_call(MCP_SECRETS_KEY)
        mock_config_instance.get_value.assert_any_call("custom_mcp_path")

        # Verify stdio_client was called with correct parameters including secrets
        call_args = mock_client.call_args[0][0]  # Get the StdioServerParameters
        assert call_args.command == "python"
        assert call_args.args == ["-m", "my_server"]

        # Verify that both public and secret env vars are included
        assert "PUBLIC_VAR" in call_args.env
        assert call_args.env["PUBLIC_VAR"] == "public_value"
        assert "SECRET_API_KEY" in call_args.env
        assert call_args.env["SECRET_API_KEY"] == "secret_value_123"
        assert "ANOTHER_SECRET" in call_args.env
        assert call_args.env["ANOTHER_SECRET"] == "another_secret_value"
        assert "PATH" in call_args.env

        # Verify original properties were not modified (security check)
        original_env_vars = tool_server.properties.get("env_vars", {})
        assert "SECRET_API_KEY" not in original_env_vars
        assert "ANOTHER_SECRET" not in original_env_vars
        assert original_env_vars.get("PUBLIC_VAR") == "public_value"

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_file_not_found_error(self, mock_client):
        """Test local MCP session handles FileNotFoundError with user-friendly message."""
        # Mock client to raise FileNotFoundError
        file_not_found = FileNotFoundError("Command 'nonexistent' not found")
        mock_client.return_value.__aenter__.side_effect = file_not_found

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "nonexistent",
                "args": ["arg1"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="Command 'nonexistent' not found"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_file_not_found_in_exception_group(self, mock_client):
        """Test local MCP session extracts FileNotFoundError from ExceptionGroup."""
        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create FileNotFoundError nested in ExceptionGroup
        file_not_found = FileNotFoundError("Command 'missing' not found")
        group_error = ExceptionGroup(
            "Multiple errors", [ValueError("other error"), file_not_found]
        )

        # Mock client to raise the ExceptionGroup
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "missing",
                "args": ["arg1"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        # Should extract the FileNotFoundError from the group and handle it appropriately
        with pytest.raises(ValueError, match="Command 'missing' not found"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_mcp_error(self, mock_client):
        """Test local MCP session handles McpError with user-friendly message."""
        # Mock client to raise McpError
        error_data = ErrorData(code=-1, message="Failed to initialize MCP server")
        mcp_error = McpError(error_data)
        mock_client.return_value.__aenter__.side_effect = mcp_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["-m", "broken_server"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        with pytest.raises(
            ValueError,
            match="MCP server failed to start due to: 'Failed to initialize MCP server'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_mcp_error_with_whitespace(self, mock_client):
        """Test local MCP session handles McpError with whitespace in message."""
        # Mock client to raise McpError with leading/trailing whitespace
        error_data = ErrorData(
            code=-1, message="  \n  Server initialization failed  \t  "
        )
        mcp_error = McpError(error_data)
        mock_client.return_value.__aenter__.side_effect = mcp_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["-m", "broken_server"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        # Should strip whitespace from error message
        with pytest.raises(
            ValueError,
            match="MCP server failed to start due to: 'Server initialization failed'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_mcp_error_in_exception_group(self, mock_client):
        """Test local MCP session extracts McpError from ExceptionGroup."""
        # Only run this test if ExceptionGroup is available
        if "ExceptionGroup" not in globals():
            pytest.skip("ExceptionGroup not available in this Python version")

        # Create McpError nested in ExceptionGroup
        error_data = ErrorData(code=-1, message="Server startup failed")
        mcp_error = McpError(error_data)
        group_error = ExceptionGroup(
            "Multiple errors", [ValueError("other error"), mcp_error]
        )

        # Mock client to raise the ExceptionGroup
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["-m", "broken_server"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        # Should extract the McpError from the group and handle it appropriately
        with pytest.raises(
            ValueError,
            match="MCP server failed to start due to: 'Server startup failed'",
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_unknown_error_reraises(self, mock_client):
        """Test local MCP session re-raises unknown errors."""
        # Mock client to raise an unknown error type
        unknown_error = RuntimeError("Unknown local error")
        mock_client.return_value.__aenter__.side_effect = unknown_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.local_mcp,
            description="Test server",
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {},
            },
        )

        manager = MCPSessionManager.shared()

        # Should re-raise the original unknown error
        with pytest.raises(RuntimeError, match="Unknown local error"):
            async with manager.mcp_client(tool_server):
                pass

    def test_exception_group_import_compatibility(self):
        """Test that ExceptionGroup import works correctly across Python versions."""
        manager = MCPSessionManager()

        # Test that the import logic in the module works correctly
        # This verifies the try/except import block in the module
        import builtins
        import sys

        if sys.version_info >= (3, 11):
            # Python 3.11+ should have ExceptionGroup in builtins
            assert "ExceptionGroup" in dir(builtins)
        else:
            # Python 3.10 should either have the backport or skip ExceptionGroup tests
            # The actual availability depends on whether the exceptiongroup package is installed
            pass  # We handle this gracefully in individual tests with pytest.skip

        # Test that _extract_first_exception handles the case where ExceptionGroup might not exist
        # by testing with a regular exception (should work regardless of ExceptionGroup availability)
        error = ValueError("test error")
        result = manager._extract_first_exception(error, ValueError)
        assert result is error

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    @patch("kiln_ai.utils.config.Config.shared")
    async def test_local_mcp_session_with_no_secrets_config(
        self, mock_config, mock_client
    ):
        """Test local MCP session creation when config has no mcp_secrets."""
        # Mock config to return None for mcp_secrets
        mock_config_instance = MagicMock()

        def mock_get_value(key):
            if key == MCP_SECRETS_KEY:
                return None
            elif key == "custom_mcp_path":
                return None  # No custom path, will use shell path
            return None

        mock_config_instance.get_value.side_effect = mock_get_value
        mock_config.return_value = mock_config_instance

        # Mock the streams
        mock_read_stream = MagicMock()
        mock_write_stream = MagicMock()
        mock_client.return_value.__aenter__.return_value = (
            mock_read_stream,
            mock_write_stream,
        )

        # Create a tool server with secret env var keys but no secrets in config
        tool_server = ExternalToolServer(
            name="no_secrets_config_server",
            type=ToolServerType.local_mcp,
            description="Server with no secrets in config",
            properties={
                "command": "python",
                "args": ["-m", "my_server"],
                "env_vars": {"PUBLIC_VAR": "public_value"},
                "secret_env_var_keys": ["SECRET_API_KEY"],
            },
        )
        tool_server.id = "test_server_id"

        manager = MCPSessionManager.shared()

        # Mock get_shell_path to return a simple PATH
        with (
            patch.object(manager, "get_shell_path", return_value="/usr/bin:/bin"),
            patch(
                "kiln_ai.tools.mcp_session_manager.ClientSession"
            ) as mock_session_class,
        ):
            mock_session_instance = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = (
                mock_session_instance
            )

            async with manager.mcp_client(tool_server):
                pass  # Should not raise any errors

        # Verify stdio_client was called and only public vars are included
        call_args = mock_client.call_args[0][0]
        assert "PUBLIC_VAR" in call_args.env
        assert call_args.env["PUBLIC_VAR"] == "public_value"
        assert "SECRET_API_KEY" not in call_args.env  # Secret not found in config
        assert "PATH" in call_args.env

    @patch("kiln_ai.utils.config.Config.shared")
    def test_get_path_with_custom_mcp_path(self, mock_config):
        """Test _get_path() returns custom MCP path when configured."""
        # Setup mock config to return a custom path
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = "/custom/mcp/path"
        mock_config.return_value = mock_config_instance

        manager = MCPSessionManager()

        # Mock get_shell_path to ensure it's not called
        with patch.object(manager, "get_shell_path") as mock_get_shell_path:
            result = manager._get_path()

            assert result == "/custom/mcp/path"
            mock_config_instance.get_value.assert_called_once_with("custom_mcp_path")
            mock_get_shell_path.assert_not_called()

    @patch("kiln_ai.utils.config.Config.shared")
    def test_get_path_fallback_to_shell_path(self, mock_config):
        """Test _get_path() falls back to get_shell_path() when no custom path."""
        # Setup mock config to return None (no custom path)
        mock_config_instance = MagicMock()
        mock_config_instance.get_value.return_value = None
        mock_config.return_value = mock_config_instance

        manager = MCPSessionManager()

        with patch.object(
            manager, "get_shell_path", return_value="/shell/path"
        ) as mock_shell:
            result = manager._get_path()

            assert result == "/shell/path"
            mock_shell.assert_called_once()

    @patch("sys.platform", "win32")
    @patch.dict(os.environ, {"PATH": "/windows/path"})
    def test_get_shell_path_windows(self):
        """Test get_shell_path() on Windows platform."""
        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == "/windows/path"

    @patch("sys.platform", "Windows")
    @patch.dict(os.environ, {"PATH": "/windows/path2"})
    def test_get_shell_path_windows_alt_platform_name(self):
        """Test get_shell_path() on Windows with 'Windows' platform name."""
        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == "/windows/path2"

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_success(self, mock_run):
        """Test get_shell_path() successful shell execution on Unix."""
        # Mock successful subprocess execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/usr/local/bin:/usr/bin:/bin\n"
        mock_run.return_value = mock_result

        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == "/usr/local/bin:/usr/bin:/bin"
        mock_run.assert_called_once_with(
            ["/bin/bash", "-l", "-c", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=3,
        )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/zsh", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_with_custom_shell(self, mock_run):
        """Test get_shell_path() uses custom shell from environment."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/custom/shell/path\n"
        mock_run.return_value = mock_result

        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == "/custom/shell/path"
        mock_run.assert_called_once_with(
            ["/bin/zsh", "-l", "-c", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=3,
        )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"PATH": "/fallback/path"}, clear=True)
    @patch("subprocess.run")
    def test_get_shell_path_unix_default_shell(self, mock_run):
        """Test get_shell_path() uses default bash when SHELL not set."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/default/bash/path\n"
        mock_run.return_value = mock_result

        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == "/default/bash/path"
        mock_run.assert_called_once_with(
            ["/bin/bash", "-l", "-c", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=3,
        )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_subprocess_failure(self, mock_run):
        """Test get_shell_path() falls back to environment PATH on subprocess failure."""
        # Mock failed subprocess execution
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        manager = MCPSessionManager()

        with patch("kiln_ai.tools.mcp_session_manager.logger") as mock_logger:
            result = manager.get_shell_path()

            assert result == "/fallback/path"
            mock_logger.error.assert_called_once()
            assert "Error getting shell PATH" in mock_logger.error.call_args[0][0]

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_subprocess_timeout(self, mock_run):
        """Test get_shell_path() handles subprocess timeout."""
        # Mock subprocess timeout
        mock_run.side_effect = subprocess.TimeoutExpired(["bash"], 3)

        manager = MCPSessionManager()

        with patch("kiln_ai.tools.mcp_session_manager.logger") as mock_logger:
            result = manager.get_shell_path()

            assert result == "/fallback/path"
            mock_logger.error.assert_any_call(
                "Shell path exception details: Command '['bash']' timed out after 3 seconds"
            )
            mock_logger.error.assert_any_call(
                "Error getting shell PATH. You may not be able to find MCP server commands like 'npx'. You can set a custom MCP path in the Kiln config file. See docs for details."
            )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_subprocess_error(self, mock_run):
        """Test get_shell_path() handles subprocess errors."""
        # Mock subprocess error
        mock_run.side_effect = subprocess.SubprocessError("Command failed")

        manager = MCPSessionManager()

        with patch("kiln_ai.tools.mcp_session_manager.logger") as mock_logger:
            result = manager.get_shell_path()

            assert result == "/fallback/path"
            mock_logger.error.assert_any_call(
                "Shell path exception details: Command failed"
            )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/fallback/path"})
    @patch("subprocess.run")
    def test_get_shell_path_unix_general_exception(self, mock_run):
        """Test get_shell_path() handles general exceptions."""
        # Mock general exception
        mock_run.side_effect = RuntimeError("Unexpected error")

        manager = MCPSessionManager()

        with patch("kiln_ai.tools.mcp_session_manager.logger") as mock_logger:
            result = manager.get_shell_path()

            assert result == "/fallback/path"
            mock_logger.error.assert_any_call(
                "Shell path exception details: Unexpected error"
            )

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash"}, clear=True)
    @patch("subprocess.run")
    def test_get_shell_path_unix_no_fallback_path(self, mock_run):
        """Test get_shell_path() when no PATH environment variable exists."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")

        manager = MCPSessionManager()

        result = manager.get_shell_path()

        assert result == ""

    @patch("sys.platform", "linux")
    @patch.dict(os.environ, {"SHELL": "/bin/bash", "PATH": "/original/path"})
    @patch("subprocess.run")
    def test_get_shell_path_caching(self, mock_run):
        """Test get_shell_path() caches the result."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/cached/path\n"
        mock_run.return_value = mock_result

        manager = MCPSessionManager()

        # First call should execute subprocess
        result1 = manager.get_shell_path()
        assert result1 == "/cached/path"
        assert mock_run.call_count == 1

        # Second call should use cached value
        result2 = manager.get_shell_path()
        assert result2 == "/cached/path"
        assert mock_run.call_count == 1  # Should not have been called again


class TestMCPServerIntegration:
    """Integration tests for MCPServer using real services."""

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_list_tools_with_real_remote_mcp_server(self):
        """Test list_tools with a real MCP server if available."""
        external_tool_server = ExternalToolServer(
            name="postman_echo",
            type=ToolServerType.remote_mcp,
            description="Postman Echo MCP Server for testing",
            properties={
                "server_url": "https://postman-echo-mcp.fly.dev/",
                "headers": {},
            },
        )

        async with MCPSessionManager.shared().mcp_client(
            external_tool_server
        ) as session:
            tools = await session.list_tools()

        print("Test tools:", tools)

        assert tools is not None
        assert len(tools.tools) > 0
        assert "echo" in [tool.name for tool in tools.tools]

    @pytest.mark.skip(
        reason="Skipping integration test since it requires calling a real MCP server"
    )
    async def test_list_tools_with_real_local_mcp_server(self):
        """Test list_tools with a real local MCP server if available."""
        external_tool_server = ExternalToolServer(
            name="Firecrawl",
            type=ToolServerType.local_mcp,
            description="Firecrawl MCP Server for testing",
            properties={
                "command": "npx",
                "args": ["-y", "firecrawl-mcp"],
                "env_vars": {"FIRECRAWL_API_KEY": "REPLACE_WITH_YOUR_API_KEY"},
            },
        )

        async with MCPSessionManager.shared().mcp_client(
            external_tool_server
        ) as session:
            tools = await session.list_tools()

        print("Test tools:", tools)

        assert tools is not None
        assert len(tools.tools) > 0
        assert "firecrawl_scrape" in [tool.name for tool in tools.tools]
