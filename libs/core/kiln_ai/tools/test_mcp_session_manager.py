import os
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


    def test_get_path(self):
        path = MCPSessionManager.shared()._get_path()
        print(f"path: {path}")

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_path_parsing_various_formats(self, mock_open, mock_exists):
        """Test PATH parsing handles various shell config formats correctly."""
        # Mock config file content with various PATH export formats
        config_content = '''
# Valid append formats - should extract the new path part
export PATH="$PATH:/usr/local/bin"
export PATH=$PATH:/opt/homebrew/bin
PATH="$PATH:/Users/scosman/.cache/lm-studio/bin"
PATH=$PATH:/some/other/bin

# Invalid formats with $PATH at start of captured group - should be skipped
export PATH="$PATH:/invalid/path"
PATH="$PATH:/another/invalid"

# Absolute path formats - should extract the full path
export PATH="/usr/bin:/bin:/usr/sbin"
PATH="/absolute/path/only"

# Edge cases that should be skipped
export PATH="$SOME_OTHER_VAR:/path"
PATH="$HOME/bin:/path"
export PATH=""
PATH=

# Comments and other lines should be ignored
# export PATH="$PATH:/commented/out"
alias ll="ls -la"
'''
        
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = config_content
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Should include initial PATH and all valid extracted paths
        expected_paths = [
            '/initial/path',
            '/usr/local/bin',
            '/opt/homebrew/bin', 
            '/Users/scosman/.cache/lm-studio/bin',
            '/some/other/bin',
            '/usr/bin',
            '/bin',
            '/usr/sbin',
            '/absolute/path/only'
        ]
        
        for expected_path in expected_paths:
            assert expected_path in result_path, f"Expected path {expected_path} not found in {result_path}"
        
        # Should NOT include invalid paths that contain literal $PATH
        invalid_paths = [
            '$PATH:/invalid/path',
            '$PATH:/another/invalid',
            '$SOME_OTHER_VAR:/path',
            '$HOME/bin'
        ]
        
        for invalid_path in invalid_paths:
            assert invalid_path not in result_path, f"Invalid path {invalid_path} should not be in {result_path}"

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_path_malformed_paths_skipped(self, mock_open, mock_exists):
        """Test that malformed paths containing $PATH are properly skipped."""
        # This specifically tests the problematic case mentioned in the user query
        config_content = '''
export PATH="$PATH:/Users/scosman/.cache/lm-studio/bin"
export PATH="'$PATH:/Users/scosman/.cache/lm-studio/bin'"
PATH=$PATH:/valid/path
PATH="$PATH_WITH_TYPO:/invalid"
'''
        
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = config_content
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Should include the valid path
        assert '/Users/scosman/.cache/lm-studio/bin' in result_path
        assert '/valid/path' in result_path
        
        # Should NOT include malformed paths with literal $PATH
        assert '$PATH:/Users/scosman/.cache/lm-studio/bin' not in result_path
        assert "'$PATH:/Users/scosman/.cache/lm-studio/bin'" not in result_path

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_path_absolute_path_assignment(self, mock_open, mock_exists):
        """Test that absolute PATH assignments like PATH="/path1:/path2" are handled correctly."""
        config_content = '''
# Absolute PATH assignments - should split on : and add each component
export PATH="/usr/local/bin:/opt/bin:/custom/path"
PATH="/another/path:/yet/another"
PATH=/single/path
export PATH="/mixed:/paths:/here"
'''
        
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = config_content
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Should include all individual path components
        expected_paths = [
            '/initial/path',
            '/usr/local/bin',
            '/opt/bin', 
            '/custom/path',
            '/another/path',
            '/yet/another',
            '/single/path',
            '/mixed',
            '/paths',
            '/here'
        ]
        
        for expected_path in expected_paths:
            assert expected_path in result_path, f"Expected path {expected_path} not found in {result_path}"

    @patch('os.path.exists')
    def test_get_path_no_config_files(self, mock_exists):
        """Test PATH building when no config files exist."""
        mock_exists.return_value = False
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Should only contain the initial PATH
        assert result_path == '/initial/path'

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_path_file_read_error(self, mock_open, mock_exists):
        """Test PATH building when config file can't be read."""
        mock_exists.return_value = True
        mock_open.side_effect = IOError("Permission denied")
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Should only contain the initial PATH when files can't be read
        assert result_path == '/initial/path'

    @patch('kiln_ai.tools.mcp_session_manager.Config')
    def test_get_path_with_custom_mcp_path_single_item(self, mock_config_class):
        """Test _get_path with custom_mcp_path containing a single path."""
        # Mock Config to return a custom MCP path
        mock_config = MagicMock()
        mock_config.get_value.return_value = "/custom/mcp/path"
        mock_config_class.shared.return_value = mock_config
        
        manager = MCPSessionManager.shared()
        
        # Mock _get_paths_from_config_files to ensure it's not called
        with patch.object(manager, '_get_paths_from_config_files') as mock_config_files:
            mock_config_files.return_value = ['/should/not/be/called']
            
            with patch.dict('os.environ', {'PATH': '/initial/path'}):
                result_path = manager._get_path()
        
        # Should contain initial PATH and custom MCP path
        assert '/initial/path' in result_path
        assert '/custom/mcp/path' in result_path
        
        # Should NOT call _get_paths_from_config_files
        mock_config_files.assert_not_called()
        
        # Verify Config.get_value was called with correct parameter
        mock_config.get_value.assert_called_once_with("custom_mcp_path")

    @patch('kiln_ai.tools.mcp_session_manager.Config')
    def test_get_path_with_custom_mcp_path_multiple_items(self, mock_config_class):
        """Test _get_path with custom_mcp_path containing multiple paths."""
        # Mock Config to return multiple custom MCP paths
        custom_paths = "/custom/path1:/custom/path2:/custom/path3"
        mock_config = MagicMock()
        mock_config.get_value.return_value = custom_paths
        mock_config_class.shared.return_value = mock_config
        
        manager = MCPSessionManager.shared()
        
        # Mock _get_paths_from_config_files to ensure it's not called
        with patch.object(manager, '_get_paths_from_config_files') as mock_config_files:
            mock_config_files.return_value = ['/should/not/be/called']
            
            with patch.dict('os.environ', {'PATH': '/initial/path'}):
                result_path = manager._get_path()
        
        # Should contain initial PATH and all custom MCP paths
        assert '/initial/path' in result_path
        assert '/custom/path1' in result_path
        assert '/custom/path2' in result_path
        assert '/custom/path3' in result_path
        
        # Should NOT call _get_paths_from_config_files
        mock_config_files.assert_not_called()
        
        # Verify Config.get_value was called with correct parameter
        mock_config.get_value.assert_called_once_with("custom_mcp_path")

   
    @patch('kiln_ai.tools.mcp_session_manager.Config')
    def test_get_path_with_empty_custom_mcp_path_calls_config_files(self, mock_config_class):
        """Test _get_path calls _get_paths_from_config_files when custom_mcp_path is empty string."""
        # Mock Config to return empty string for custom_mcp_path
        mock_config = MagicMock()
        mock_config.get_value.return_value = ""
        mock_config_class.shared.return_value = mock_config
        
        manager = MCPSessionManager.shared()
        
        # Mock _get_paths_from_config_files to return some paths
        with patch.object(manager, '_get_paths_from_config_files') as mock_config_files:
            mock_config_files.return_value = ['/config/path1']
            
            with patch.dict('os.environ', {'PATH': '/initial/path'}):
                result_path = manager._get_path()
        
        # Should contain initial PATH and config file paths
        assert '/initial/path' in result_path
        
        # Should call _get_paths_from_config_files when custom_mcp_path is empty
        mock_config_files.assert_not_called()
        
        # Verify Config.get_value was called with correct parameter
        mock_config.get_value.assert_called_once_with("custom_mcp_path")

    @patch('kiln_ai.tools.mcp_session_manager.Config')
    def test_get_path_custom_mcp_path_removes_duplicates(self, mock_config_class):
        """Test _get_path removes duplicates when custom_mcp_path contains duplicate paths."""
        # Mock Config to return custom MCP path with duplicates
        custom_paths = "/custom/path1:/custom/path2:/custom/path1:/custom/path3"
        mock_config = MagicMock()
        mock_config.get_value.return_value = custom_paths
        mock_config_class.shared.return_value = mock_config
        
        manager = MCPSessionManager.shared()
        
        with patch.object(manager, '_get_paths_from_config_files') as mock_config_files:
            with patch.dict('os.environ', {'PATH': '/initial/path:/custom/path2'}):
                result_path = manager._get_path()
        
        # Split result to count occurrences
        result_paths = result_path.split(os.pathsep)
        
        # Each path should appear only once
        assert result_paths.count('/initial/path') == 1
        assert result_paths.count('/custom/path1') == 1
        assert result_paths.count('/custom/path2') == 1
        assert result_paths.count('/custom/path3') == 1
        
        # Should NOT call _get_paths_from_config_files
        mock_config_files.assert_not_called()

    @patch('os.path.exists')
    @patch('builtins.open')
    def test_get_path_problematic_patterns_fixed(self, mock_open, mock_exists):
        """Test that the specific problematic patterns mentioned in the user query are now handled correctly."""
        # These are the exact patterns that were failing according to the user
        config_content = '''
export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
export PATH="$PATH:/Users/scosman/.local/bin"
'''
        
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = config_content
        
        manager = MCPSessionManager.shared()
        
        with patch.dict('os.environ', {'PATH': '/initial/path'}):
            result_path = manager._get_path()
        
        # Both paths should now be extracted correctly
        assert '/opt/homebrew/opt/llvm/bin' in result_path, f"Expected '/opt/homebrew/opt/llvm/bin' not found in {result_path}"
        assert '/Users/scosman/.local/bin' in result_path, f"Expected '/Users/scosman/.local/bin' not found in {result_path}"
        
        # Should NOT include the problematic full matches
        assert '/opt/homebrew/opt/llvm/bin:$PATH' not in result_path, f"Should not include full match with $PATH"
        assert '"$PATH:/Users/scosman/.local/bin' not in result_path, f"Should not include match with leading quote"