from contextlib import asynccontextmanager
from typing import AsyncGenerator
import os
import re

from kiln_ai.utils.config import Config
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

import logging

logger = logging.getLogger(__name__)


class MCPSessionManager:
    """
    This class is a singleton that manages MCP sessions for remote MCP servers.
    """

    _shared_instance = None

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

        headers = tool_server.properties.get("headers", {})

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

        env_vars = tool_server.properties.get("env_vars", {})
        logger.error(f"os.environ: {os.environ['PATH']}")
        logger.error(f"self._get_path: {self._get_path()}")

        # Setup PATH, only if not explicitly set.
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
        
        # Load the environment PATH.
        initial_path = os.environ["PATH"]
        paths = initial_path.split(os.pathsep)
        
        try:
            # If the user sets a custom MCP path, use only this to extend path. This also functions as a way to disable the config file's paths.
            custom_mcp_path = Config.shared().get_value("custom_mcp_path")
            if custom_mcp_path is not None:
                paths.extend(custom_mcp_path.split(os.pathsep))
            else:
                config_paths = self._get_paths_from_config_files()
                paths.extend(config_paths)
        except Exception as e:
            logger.error(f"Error getting custom MCP PATH. You may not be able to find MCP server commands like 'npx': {e}")
            return os.environ["PATH"]

        # Remove duplicates while preserving order
        unique_paths = []
        seen = set()
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        # Join all paths with the system path separator
        return os.pathsep.join(unique_paths)
        
    def _get_paths_from_config_files(self) -> list[str]:
        """
        Builds a PATH environment variable, loading shell config files if they exist (like .bash_profile, .bashrc, .zshrc, etc.)
        """
        paths = []
        
        # Common shell configuration files that may modify PATH
        config_file_paths = [
            "~/.profile",      # POSIX-compliant profile, sourced by many shells
            "~/.bash_profile", # Bash login shell profile
            "~/.bashrc",       # Bash interactive shell config
            "~/.zshenv",       # Zsh environment (always sourced)
            "~/.zprofile",     # Zsh login shell profile
            "~/.zshrc",        # Zsh interactive shell config
        ]
        
        config_files = [os.path.expanduser(path) for path in config_file_paths]
        
        for config_file in config_files:
            if not os.path.exists(config_file):
                logger.error(f"Config file {config_file} does not exist")
            
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        content = f.read()

                    logger.error(f"content: {config_file}\n {content}")
                    
                    # Look for PATH exports in various formats:
                    # export PATH="$PATH:/new/path"  -> extract /new/path
                    # export PATH=$PATH:/new/path    -> extract /new/path
                    # export PATH="/new/path:$PATH"  -> extract /new/path
                    # PATH="$PATH:/new/path"         -> extract /new/path
                    # PATH=$PATH:/new/path           -> extract /new/path
                    # PATH="/new/path:$PATH"         -> extract /new/path
                    # export PATH="/absolute/path"   -> extract /absolute/path
                    # PATH="/absolute/path"          -> extract /absolute/path
                    
                    # Patterns that append to $PATH - extract only the new path part
                    append_patterns = [
                        # $PATH at the beginning: $PATH:/new/path
                        r'export\s+PATH\s*=\s*["\']?\$PATH:([^"\';\n]+?)["\']?(?:\s|$|;)',
                        r'PATH\s*=\s*["\']?\$PATH:([^"\';\n]+?)["\']?(?:\s|$|;)',
                        # $PATH at the end: /new/path:$PATH  
                        r'export\s+PATH\s*=\s*["\']?([^"\';\n]+?):\$PATH["\']?(?:\s|$|;)',
                        r'PATH\s*=\s*["\']?([^"\';\n]+?):\$PATH["\']?(?:\s|$|;)',
                    ]
                    
                    # Patterns that set absolute PATH - extract the full path
                    absolute_patterns = [
                        r'export\s+PATH\s*=\s*["\']?([^$][^"\';\n]*?)["\']?(?:\s|$|;)',
                        r'PATH\s*=\s*["\']?([^$][^"\';\n]*?)["\']?(?:\s|$|;)'
                    ]
                    
                    # Process append patterns first
                    for pattern in append_patterns:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            # Clean up the path (remove quotes, whitespace)
                            clean_path = match.strip().strip('"\'')
                            # Skip paths that still contain $PATH or other variables (malformed)
                            if (clean_path and 
                                '$PATH' not in clean_path and 
                                not clean_path.startswith('$')):
                                paths.append(clean_path)
                    
                    # Process absolute patterns
                    for pattern in absolute_patterns:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            # Clean up the path (remove quotes, whitespace)
                            clean_path = match.strip().strip('"\'')
                            # Skip paths that contain $PATH (should be handled by append patterns)
                            # Also skip if it looks like a variable expansion we can't handle
                            if (clean_path and 
                                '$PATH' not in clean_path and 
                                not clean_path.startswith('$')):
                                # For absolute paths, split on : and add each component
                                path_components = clean_path.split(':')
                                for component in path_components:
                                    component = component.strip()
                                    if (component and 
                                        not component.startswith('$')):
                                        paths.append(component)
                                
                except (IOError, OSError):
                    # Skip files that can't be read
                    logger.error(f"Config file {config_file} exists but cannot be read")
                    continue

        # Filter to only include paths that actually exist
        existing_paths = []
        seen = set()
        for path in paths:
            if path not in seen and os.path.exists(path):
                existing_paths.append(path)
                seen.add(path)
        
        logger.error(f"paths: {existing_paths}")
        return existing_paths


