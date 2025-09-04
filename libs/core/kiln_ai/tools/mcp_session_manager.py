import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

logger = logging.getLogger(__name__)


class MCPSessionManager:
    """
    This class is a singleton that manages MCP sessions for remote MCP servers.
    """

    _shared_instance = None

    def __init__(self):
        self._shell_path = None

    @classmethod
    def shared(cls):
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @asynccontextmanager
    async def mcp_client(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[
        ClientSession,
        None,
    ]:
        match tool_server.type:
            case ToolServerType.remote_mcp:
                async with self._create_remote_mcp_session(tool_server) as session:
                    yield session
            case ToolServerType.local_mcp:
                async with self._create_local_mcp_session(tool_server) as session:
                    yield session
            case _:
                raise_exhaustive_enum_error(tool_server.type)

    @asynccontextmanager
    async def _create_remote_mcp_session(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Create a session for a remote MCP server.
        """
        # Make sure the server_url is set
        server_url = tool_server.properties.get("server_url")
        if not server_url:
            raise ValueError("server_url is required")

        # Make a copy of the headers to avoid modifying the original object
        headers = tool_server.properties.get("headers", {}).copy()

        # Retrieve secret headers from configuration and merge with regular headers
        secret_headers, _ = tool_server.retrieve_secrets()
        headers.update(secret_headers)

        async with streamablehttp_client(server_url, headers=headers) as (
            read_stream,
            write_stream,
            _,
        ):
            # Create a session using the client streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    @asynccontextmanager
    async def _create_local_mcp_session(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Create a session for a local MCP server.
        """
        command = tool_server.properties.get("command")
        if not command:
            raise ValueError(
                "Attempted to start local MCP server, but no command was provided"
            )

        args = tool_server.properties.get("args", [])
        if not isinstance(args, list):
            raise ValueError(
                "Attempted to start local MCP server, but args is not a list of strings"
            )

        # Make a copy of the env_vars to avoid modifying the original object
        env_vars = tool_server.properties.get("env_vars", {}).copy()

        # Retrieve secret environment variables from configuration and merge with regular env_vars
        secret_env_vars, _ = tool_server.retrieve_secrets()
        env_vars.update(secret_env_vars)

        # Set PATH, only if not explicitly set during MCP tool setup
        if "PATH" not in env_vars:
            env_vars["PATH"] = self._get_path()

        # Set the server parameters
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env_vars,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    def _get_path(self) -> str:
        """
        Builds a PATH environment variable. From environment, Kiln Config, and loading rc files.
        """

        # If the user sets a custom MCP path, use only it. This also functions as a way to disable the shell path loading.
        custom_mcp_path = Config.shared().get_value("custom_mcp_path")
        if custom_mcp_path is not None:
            return custom_mcp_path
        else:
            return self.get_shell_path()

    def get_shell_path(self) -> str:
        # Windows has a global PATH, so we don't need to source rc files
        if sys.platform in ("win32", "Windows"):
            return os.environ.get("PATH", "")

        # Cache
        if self._shell_path is not None:
            return self._shell_path

        # Attempt to get shell PATH from preferred shell, which will source rc files, run scripts like `brew shellenv`, etc.
        shell_path = None
        try:
            shell = os.environ.get("SHELL", "/bin/bash")
            # Use -l (login) flag to source ~/.profile, ~/.bash_profile, ~/.zprofile, etc.
            result = subprocess.run(
                [shell, "-l", "-c", "echo $PATH"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                shell_path = result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception) as e:
            logger.error(f"Shell path exception details: {e}")

        # Fallback to environment PATH
        if shell_path is None:
            logger.error(
                "Error getting shell PATH. You may not be able to find MCP server commands like 'npx'. You can set a custom MCP path in the Kiln config file. See docs for details."
            )
            shell_path = os.environ.get("PATH", "")

        self._shell_path = shell_path
        return shell_path

    def clear_shell_path_cache(self):
        """Clear the cached shell path. Typically used when adding a new tool, which might have just been installed."""
        self._shell_path = None
