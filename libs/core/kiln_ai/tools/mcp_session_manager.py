import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, NoReturn

import httpx
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.config import Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

logger = logging.getLogger(__name__)

MCP_SESSION_CACHE_KEY_DELIMITER = "::"


class KilnMCPError(RuntimeError):
    """Wraps MCP connection failures. Unwraps ExceptionGroup; attaches stderr."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class MCPSessionManager:
    """
    This class is a singleton that manages MCP sessions for remote MCP servers.
    """

    _shared_instance = None

    def __init__(self):
        self._shell_path = None
        # Session cache: key = "{server_id}::{session_id}" → (ClientSession, AsyncExitStack)
        self._session_cache: dict[str, tuple[ClientSession, AsyncExitStack]] = {}
        self._cache_lock = asyncio.Lock()

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
            case ToolServerType.kiln_task:
                raise ValueError("Kiln task tools are not available from an MCP server")
            case _:
                raise_exhaustive_enum_error(tool_server.type)

    async def get_or_create_session(
        self,
        tool_server: ExternalToolServer,
        session_id: str,
    ) -> ClientSession:
        """Get or create a cached MCP session for the given server and session ID.

        Args:
            tool_server: The external tool server configuration
            session_id: The session ID for this agent run

        Returns:
            A cached or newly created ClientSession

        Raises:
            ValueError: If the server configuration is invalid
            RuntimeError: If connection to the server fails
        """
        cache_key = build_mcp_session_cache_key(tool_server.id, session_id)

        async with self._cache_lock:
            if cache_key in self._session_cache:
                return self._session_cache[cache_key][0]

        # Create outside the lock to avoid holding it during slow I/O.
        # Race: two coroutines may both reach here for the same key.
        # The lock below ensures only one wins; the loser closes its stack.
        session, stack = await self._create_cached_session(tool_server)

        async with self._cache_lock:
            if cache_key in self._session_cache:
                # Another coroutine created it first — close ours and return theirs
                try:
                    await stack.aclose()
                except Exception:
                    logger.warning(
                        f"Error closing redundant MCP session stack for {cache_key}",
                        exc_info=True,
                    )
                return self._session_cache[cache_key][0]
            self._session_cache[cache_key] = (session, stack)
            return session

    async def cleanup_session(self, session_id: str) -> None:
        """Close all MCP sessions associated with a session ID.

        Called by the root agent's finally block when the agent run completes.

        Args:
            session_id: The session ID to clean up
        """
        to_cleanup: list[tuple[str, AsyncExitStack]] = []

        async with self._cache_lock:
            keys_to_remove = [
                key
                for key in self._session_cache
                if parse_mcp_session_cache_session_id(key) == session_id
            ]
            for key in keys_to_remove:
                _, exit_stack = self._session_cache.pop(key)
                to_cleanup.append((key, exit_stack))

        # Close outside the lock to avoid holding it during I/O
        for key, exit_stack in to_cleanup:
            try:
                await exit_stack.aclose()
            except Exception:
                logger.warning(f"Error closing MCP session {key}", exc_info=True)

    async def _create_cached_session(
        self,
        tool_server: ExternalToolServer,
    ) -> tuple[ClientSession, AsyncExitStack]:
        """Create a cached MCP session with AsyncExitStack for lifecycle management.

        The session remains alive until the AsyncExitStack is closed,
        allowing the session to be reused across multiple tool calls.

        Args:
            tool_server: The external tool server configuration

        Returns:
            A tuple of (ClientSession, AsyncExitStack)

        Raises:
            ValueError: If the server configuration is invalid
            RuntimeError: If connection to the server fails
        """
        stack = AsyncExitStack()

        try:
            match tool_server.type:
                case ToolServerType.remote_mcp:
                    return await self._create_cached_remote_session(
                        tool_server, stack
                    ), stack
                case ToolServerType.local_mcp:
                    return await self._create_cached_local_session(
                        tool_server, stack
                    ), stack
                case ToolServerType.kiln_task:
                    raise ValueError("Kiln task tools are not MCP servers")
                case _:
                    raise_exhaustive_enum_error(tool_server.type)
        except Exception:
            await stack.aclose()
            raise

    def _prepare_remote_params(
        self, tool_server: ExternalToolServer
    ) -> tuple[str, dict]:
        """Extract and prepare parameters for remote MCP connection.

        Args:
            tool_server: The external tool server configuration

        Returns:
            A tuple of (server_url, headers) with secrets merged

        Raises:
            ValueError: If the server URL is not configured
        """
        server_url = tool_server.properties.get("server_url")
        if not server_url:
            raise ValueError("server_url is required")

        headers = tool_server.properties.get("headers", {}).copy()
        secret_headers, _ = tool_server.retrieve_secrets()
        headers.update(secret_headers)

        return server_url, headers

    async def _create_cached_remote_session(
        self,
        tool_server: ExternalToolServer,
        stack: AsyncExitStack,
    ) -> ClientSession:
        """Create a cached remote MCP session using AsyncExitStack.

        The transport and session remain alive until the stack is closed.

        Args:
            tool_server: The external tool server configuration
            stack: The AsyncExitStack to manage the transport lifecycle

        Returns:
            An initialized ClientSession

        Raises:
            ValueError: If the server URL is not configured
            RuntimeError: If connection to the server fails
        """
        server_url, headers = self._prepare_remote_params(tool_server)

        try:
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamablehttp_client(server_url, headers=headers)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            return session
        except Exception as e:
            self._handle_remote_mcp_error(e)
            raise  # unreachable but needed for type checker

    def _prepare_local_params(
        self, tool_server: ExternalToolServer
    ) -> tuple[str, list[str], dict, str, StdioServerParameters]:
        """Extract and prepare parameters for local MCP connection.

        Args:
            tool_server: The external tool server configuration

        Returns:
            A tuple of (command, args, env_vars, cwd, server_params)

        Raises:
            ValueError: If the command is not provided or args is not a list
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

        env_vars = tool_server.properties.get("env_vars", {}).copy()
        secret_env_vars, _ = tool_server.retrieve_secrets()
        env_vars.update(secret_env_vars)

        if "PATH" not in env_vars:
            env_vars["PATH"] = self._get_path()

        cwd = os.path.join(Config.settings_dir(), "cache", "mcp_cache")
        os.makedirs(cwd, exist_ok=True)
        server_params = StdioServerParameters(
            command=command, args=args, env=env_vars, cwd=cwd
        )

        return command, args, env_vars, cwd, server_params

    async def _create_cached_local_session(
        self,
        tool_server: ExternalToolServer,
        stack: AsyncExitStack,
    ) -> ClientSession:
        """Create a cached local MCP session using AsyncExitStack.

        The subprocess, stderr capture, and session remain alive until the stack is closed.

        Args:
            tool_server: The external tool server configuration
            stack: The AsyncExitStack to manage the transport lifecycle

        Returns:
            An initialized ClientSession

        Raises:
            ValueError: If the command is not provided or args is not a list
            RuntimeError: If the subprocess fails to start or initialize
        """
        _command, _args, _env_vars, _cwd, server_params = self._prepare_local_params(
            tool_server
        )

        err_log = stack.enter_context(
            tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
        )

        try:
            read, write = await stack.enter_async_context(
                stdio_client(server_params, errlog=err_log)
            )
            session = await stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30))
            )
            await session.initialize()
            return session
        except Exception as e:
            err_log.seek(0)
            stderr_content = err_log.read()
            if stderr_content:
                logger.error(
                    f"MCP server '{tool_server.name}' stderr: {stderr_content}"
                )

            self._handle_local_mcp_error(e, stderr_content)
            raise  # unreachable but needed for type checker

    def _extract_first_exception(
        self, exception: Exception, target_type: type | tuple[type, ...]
    ) -> Exception | None:
        """
        Extract first relevant exception from ExceptionGroup or handle direct exceptions
        """
        # Check if the exception itself is of the target type
        if isinstance(exception, target_type):
            return exception

        # Handle ExceptionGroup
        if hasattr(exception, "exceptions"):
            exceptions_attr = getattr(exception, "exceptions", None)
            if exceptions_attr:
                for nested_exc in exceptions_attr:
                    result = self._extract_first_exception(nested_exc, target_type)
                    if result:
                        return result

        return None

    @asynccontextmanager
    async def _create_remote_mcp_session(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Create a session for a remote MCP server.
        """
        server_url, headers = self._prepare_remote_params(tool_server)

        try:
            async with streamablehttp_client(server_url, headers=headers) as (
                read_stream,
                write_stream,
                _,
            ):
                # Create a session using the client streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
        except Exception as e:
            self._handle_remote_mcp_error(e)
            raise  # unreachable but needed for type checker

    @asynccontextmanager
    async def _create_local_mcp_session(
        self,
        tool_server: ExternalToolServer,
    ) -> AsyncGenerator[ClientSession, None]:
        """
        Create a session for a local MCP server.
        """
        _command, _args, _env_vars, _cwd, server_params = self._prepare_local_params(
            tool_server
        )

        # Create temporary file to capture MCP server stderr
        # Use errors="replace" to handle non-UTF-8 bytes gracefully
        with tempfile.TemporaryFile(
            mode="w+", encoding="utf-8", errors="replace"
        ) as err_log:
            try:
                async with stdio_client(server_params, errlog=err_log) as (
                    read,
                    write,
                ):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=30)
                    ) as session:
                        await session.initialize()
                        yield session
            except Exception as e:
                err_log.seek(0)
                stderr_content = err_log.read()
                if stderr_content:
                    logger.error(
                        f"MCP server '{tool_server.name}' stderr output: {stderr_content}"
                    )
                self._handle_local_mcp_error(e, stderr_content)
                raise  # unreachable but needed for type checker

    def _handle_remote_mcp_error(self, e: Exception) -> NoReturn:
        """Shared error handling for remote MCP connection failures.

        Args:
            e: The exception to handle

        Raises:
            KilnMCPError: Always, with the raw library error message
        """
        for exc_type in (
            httpx.HTTPStatusError,
            ConnectionError,
            OSError,
            httpx.RequestError,
        ):
            found = self._extract_first_exception(e, exc_type)
            if found:
                raise KilnMCPError(str(found)) from e
        raise KilnMCPError(str(e)) from e

    def _handle_local_mcp_error(self, e: Exception, stderr: str) -> NoReturn:
        """Shared error handling for local MCP connection failures.

        Args:
            e: The exception to handle
            stderr: The stderr content from the MCP server

        Raises:
            KilnMCPError: Always, with the raw library error message
        """
        for exc_type in (FileNotFoundError, OSError, McpError):
            found = self._extract_first_exception(e, exc_type)
            if found:
                raise KilnMCPError(str(found), stderr=stderr) from e
        raise KilnMCPError(str(e), stderr=stderr) from e

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


def build_mcp_session_cache_key(server_id: str | None, session_id: str) -> str:
    return f"{server_id}{MCP_SESSION_CACHE_KEY_DELIMITER}{session_id}"


def parse_mcp_session_cache_session_id(cache_key: str) -> str:
    return cache_key.rsplit(MCP_SESSION_CACHE_KEY_DELIMITER, 1)[1]
