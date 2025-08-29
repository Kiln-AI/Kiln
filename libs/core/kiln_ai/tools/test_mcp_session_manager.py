import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.tools.mcp_session_manager import MCPSessionManager


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
            match="command must be a string for external tools of type 'local_mcp'",
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
            match="args must be a list for external tools of type 'local_mcp'",
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

    async def test_local_mcp_empty_args_error(self):
        """Test that empty args list raises ValueError for local MCP."""
        with pytest.raises(
            ValidationError,
            match="args is required for external tools of type 'local_mcp'",
        ):
            ExternalToolServer(
                name="empty_args_server",
                type=ToolServerType.local_mcp,
                description="Server with empty args",
                properties={
                    "command": "python",
                    "args": [],  # Empty args list
                    "env_vars": {},
                },
            )

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

        with pytest.raises(ValueError, match="command is required"):
            async with manager.mcp_client(tool_server):
                pass

    async def test_local_mcp_session_empty_args_runtime_error(self):
        """Test that empty args list raises ValueError during session creation."""
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
        tool_server.properties["args"] = []

        manager = MCPSessionManager.shared()

        with pytest.raises(ValueError, match="argument is required"):
            async with manager.mcp_client(tool_server):
                pass

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
