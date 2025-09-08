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

    # Note: Testing invalid tool server types is not possible because:
    # 1. The ToolServerType enum only has one value: remote_mcp
    # 2. Pydantic validation prevents creating objects with invalid types
    # 3. Pydantic prevents modifying the type field to invalid values after creation
    # The RuntimeError check in MCPSessionManager.mcp_client is defensive programming
    # that would only be triggered if new enum values are added without updating the match statement.

    @pytest.mark.parametrize(
        "exception,target_type,expected_result",
        [
            # Direct matches
            (ValueError("test"), ValueError, True),
            (ConnectionError("conn"), ConnectionError, True),
            (FileNotFoundError("file"), FileNotFoundError, True),
            # Non-matches
            (ValueError("test"), TypeError, False),
            (ConnectionError("conn"), ValueError, False),
            # Tuple targets - matches
            (ValueError("test"), (ValueError, TypeError), True),
            (ConnectionError("conn"), (ValueError, ConnectionError), True),
            # Tuple targets - non-matches
            (RuntimeError("test"), (ValueError, TypeError), False),
            # Inheritance - FileNotFoundError is subclass of OSError
            (FileNotFoundError("file"), OSError, True),
            (ConnectionError("conn"), OSError, True),
        ],
    )
    def test_extract_first_exception_direct_cases(
        self, exception, target_type, expected_result
    ):
        """Test _extract_first_exception with direct exception cases."""
        manager = MCPSessionManager()
        result = manager._extract_first_exception(exception, target_type)

        if expected_result:
            assert result is exception
        else:
            assert result is None

    def test_extract_first_exception_with_exceptions_attribute(self):
        """Test _extract_first_exception with object that has exceptions attribute."""
        manager = MCPSessionManager()

        # Create a mock exception-like object with exceptions attribute
        class MockExceptionGroup:
            def __init__(self, exceptions):
                self.exceptions = exceptions

        # Test finding target exception in exceptions list
        target_exception = ValueError("found")
        mock_group = MockExceptionGroup(
            [TypeError("other"), target_exception, RuntimeError("another")]
        )

        result = manager._extract_first_exception(mock_group, ValueError)
        assert result is target_exception

        # Test not finding target exception
        result = manager._extract_first_exception(mock_group, KeyError)
        assert result is None

    def test_extract_first_exception_nested_exceptions_attribute(self):
        """Test _extract_first_exception with nested objects having exceptions attribute."""
        manager = MCPSessionManager()

        class MockExceptionGroup:
            def __init__(self, exceptions):
                self.exceptions = exceptions

        # Create nested structure
        target_exception = FileNotFoundError("nested target")
        inner_group = MockExceptionGroup([target_exception, ValueError("inner other")])
        outer_group = MockExceptionGroup([TypeError("outer other"), inner_group])

        # Should find deeply nested exception
        result = manager._extract_first_exception(outer_group, FileNotFoundError)
        assert result is target_exception

        # Should find by parent class
        result = manager._extract_first_exception(outer_group, OSError)
        assert result is target_exception

        # Should not find non-existent exception
        result = manager._extract_first_exception(outer_group, KeyError)
        assert result is None

    def test_extract_first_exception_no_exceptions_attribute(self):
        """Test _extract_first_exception with object that has no exceptions attribute."""
        manager = MCPSessionManager()

        # Object without exceptions attribute should return None
        class MockObject:
            pass

        mock_obj = MockObject()
        result = manager._extract_first_exception(mock_obj, ValueError)
        assert result is None

    def test_extract_first_exception_none_exceptions_attribute(self):
        """Test _extract_first_exception with object that has None exceptions attribute."""
        manager = MCPSessionManager()

        class MockObject:
            exceptions = None

        mock_obj = MockObject()
        result = manager._extract_first_exception(mock_obj, ValueError)
        assert result is None

    def test_extract_first_exception_empty_exceptions_list(self):
        """Test _extract_first_exception with empty exceptions list."""
        manager = MCPSessionManager()

        class MockExceptionGroup:
            def __init__(self):
                self.exceptions = []

        mock_group = MockExceptionGroup()
        result = manager._extract_first_exception(mock_group, ValueError)
        assert result is None

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

    @pytest.mark.parametrize(
        "status_code,reason_phrase",
        [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
        ],
    )
    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_status_errors(
        self, mock_client, status_code, reason_phrase
    ):
        """Test remote MCP session handles various HTTP status errors with simplified message."""
        # Create HTTP error with specific status code
        response = MagicMock()
        response.status_code = status_code
        response.reason_phrase = reason_phrase
        http_error = httpx.HTTPStatusError(
            reason_phrase, request=MagicMock(), response=response
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

        # All HTTP errors should now use the simplified message format
        expected_pattern = f"The MCP server rejected the request. Status {status_code}. Response from server:\n{reason_phrase}"
        with pytest.raises(
            ValueError, match=expected_pattern.replace("(", r"\(").replace(")", r"\)")
        ):
            async with manager.mcp_client(tool_server):
                pass

    @pytest.mark.parametrize(
        "connection_error_type,error_message",
        [
            (ConnectionError, "Connection refused"),
            (OSError, "Network is unreachable"),
            (httpx.RequestError, "Request failed"),
            (httpx.ConnectError, "Connection error"),
        ],
    )
    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_connection_errors(
        self, mock_client, connection_error_type, error_message
    ):
        """Test remote MCP session handles various connection errors with simplified message."""
        # Create connection error
        if connection_error_type == httpx.RequestError:
            connection_error = connection_error_type(error_message, request=MagicMock())
        elif connection_error_type == httpx.ConnectError:
            connection_error = connection_error_type(error_message, request=MagicMock())
        else:
            connection_error = connection_error_type(error_message)

        # Mock client to raise the connection error
        mock_client.return_value.__aenter__.side_effect = connection_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # All connection errors should use the simplified message format
        with pytest.raises(RuntimeError, match="Unable to connect to MCP server"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_http_error_in_nested_exceptions(self, mock_client):
        """Test remote MCP session extracts HTTP error from nested exceptions."""
        # Create HTTP error nested in a mock exception group
        response = MagicMock()
        response.status_code = 401
        response.reason_phrase = "Unauthorized"
        http_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=response
        )

        class MockExceptionGroup(Exception):
            def __init__(self, exceptions):
                super().__init__("Mock exception group")
                self.exceptions = exceptions

        group_error = MockExceptionGroup([ValueError("other error"), http_error])

        # Mock client to raise the nested exception
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should extract the HTTP error from the nested structure
        with pytest.raises(
            ValueError, match="The MCP server rejected the request. Status 401"
        ):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_connection_error_in_nested_exceptions(self, mock_client):
        """Test remote MCP session extracts connection error from nested exceptions."""
        # Create connection error nested in mock exception group
        connection_error = ConnectionError("Connection timeout")

        class MockExceptionGroup(Exception):
            def __init__(self, exceptions):
                super().__init__("Mock exception group")
                self.exceptions = exceptions

        group_error = MockExceptionGroup([ValueError("other error"), connection_error])

        # Mock client to raise the nested exception
        mock_client.return_value.__aenter__.side_effect = group_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should extract the connection error from the nested structure
        with pytest.raises(RuntimeError, match="Unable to connect to MCP server"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.streamablehttp_client")
    async def test_remote_mcp_unknown_error_fallback(self, mock_client):
        """Test remote MCP session handles unknown errors with fallback message."""
        # Mock client to raise an unknown error type
        unknown_error = RuntimeError("Unexpected error")
        mock_client.return_value.__aenter__.side_effect = unknown_error

        tool_server = ExternalToolServer(
            name="test_server",
            type=ToolServerType.remote_mcp,
            description="Test server",
            properties={"server_url": "http://example.com/mcp", "headers": {}},
        )

        manager = MCPSessionManager.shared()

        # Should use the fallback error message
        with pytest.raises(RuntimeError, match="Failed to connect to the MCP Server"):
            async with manager.mcp_client(tool_server):
                pass

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

    @pytest.mark.parametrize(
        "error_type,error_message",
        [
            (McpError, "MCP initialization failed"),
            (FileNotFoundError, "Command 'nonexistent' not found"),
            (RuntimeError, "Unknown server error"),
            (ValueError, "Invalid arguments provided"),
        ],
    )
    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_various_errors_use_simplified_message(
        self, mock_client, error_type, error_message
    ):
        """Test local MCP session handles various errors with simplified message."""
        # Create the appropriate error
        if error_type == McpError:
            error_data = ErrorData(code=-1, message=error_message)
            test_error = McpError(error_data)
        else:
            test_error = error_type(error_message)

        # Mock client to raise the error
        mock_client.return_value.__aenter__.side_effect = test_error

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

        # All local errors should now use the simplified message format
        with pytest.raises(RuntimeError, match="MCP server failed to start"):
            async with manager.mcp_client(tool_server):
                pass

    @patch("kiln_ai.tools.mcp_session_manager.stdio_client")
    async def test_local_mcp_mcp_error_in_nested_exceptions(self, mock_client):
        """Test local MCP session extracts McpError from nested exceptions."""
        # Create McpError nested in mock exception group
        error_data = ErrorData(code=-1, message="Server startup failed")
        mcp_error = McpError(error_data)

        class MockExceptionGroup(Exception):
            def __init__(self, exceptions):
                super().__init__("Mock exception group")
                self.exceptions = exceptions

        group_error = MockExceptionGroup([ValueError("other error"), mcp_error])

        # Mock client to raise the nested exception
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

        # Should extract the McpError from the nested structure and use simplified message
        with pytest.raises(RuntimeError, match="MCP server failed to start"):
            async with manager.mcp_client(tool_server):
                pass

    def test_raise_local_mcp_error_method(self):
        """Test the _raise_local_mcp_error helper method."""
        manager = MCPSessionManager()

        # Test with different exception types
        test_exceptions = [
            ValueError("test value error"),
            FileNotFoundError("file not found"),
            RuntimeError("runtime error"),
            Exception("generic exception"),
        ]

        for original_error in test_exceptions:
            with pytest.raises(RuntimeError) as exc_info:
                manager._raise_local_mcp_error(original_error)

            # Check that the error message contains expected text
            assert "MCP server failed to start" in str(exc_info.value)
            assert (
                "Please verify your command, arguments, and environment variables"
                in str(exc_info.value)
            )
            assert str(original_error) in str(exc_info.value)

            # Check that the original exception is chained
            assert exc_info.value.__cause__ is original_error

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

        assert tools is not None
        assert len(tools.tools) > 0
        assert "firecrawl_scrape" in [tool.name for tool in tools.tools]
