import logging
import os
import secrets
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import AsyncGenerator
from urllib.parse import urlencode, urljoin

import httpx
from mcp import StdioServerParameters
from mcp.client.auth import (
    OAuthClientProvider,
    OAuthFlowError,
    OAuthTokenError,
    PKCEParameters,
    TokenStorage,
)
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)
from mcp.shared.exceptions import McpError
from pydantic import AnyUrl, TypeAdapter

from kiln_ai.datamodel.external_tool_server import ExternalToolServer, ToolServerType
from kiln_ai.utils.config import REMOTE_MCP_OAUTH_TOKENS_KEY, Config
from kiln_ai.utils.exhaustive_error import raise_exhaustive_enum_error

logger = logging.getLogger(__name__)

LOCAL_MCP_ERROR_INSTRUCTION = "Please verify your command, arguments, and environment variables, and consult the server's documentation for the correct setup."


class RemoteMCPOAuthTokensMissing(RuntimeError):
    """Raised when an OAuth-enabled MCP server is missing stored tokens."""


class RemoteMCPOAuthRedirectRequired(RuntimeError):
    """Raised when the OAuth flow requires a browser redirect."""

    def __init__(self, redirect_url: str):
        self.redirect_url = redirect_url
        super().__init__(f"OAuth redirect required: {redirect_url}")


@dataclass
class PendingOAuthState:
    """State required to complete an OAuth authorization code flow."""

    tool_server_id: str
    project_id: str
    token_url: str
    code_verifier: str
    state: str
    client_info: OAuthClientInformationFull
    redirect_uri: str
    include_resource: bool
    resource: str | None
    scope: str | None


class ConfigBackedOAuthTokenStorage(TokenStorage):
    """Token storage backed by the Kiln configuration system."""

    def __init__(self, server_id: str, force_new_flow: bool = False):
        self._config = Config.shared()
        self._server_id = server_id
        self._force_new_flow = force_new_flow

    def _load_entry(self) -> dict | None:
        store = self._config.get_value(REMOTE_MCP_OAUTH_TOKENS_KEY) or {}
        entry = store.get(self._server_id)
        return entry if isinstance(entry, dict) else None

    async def get_tokens(self) -> OAuthToken | None:
        entry = self._load_entry()
        if not entry:
            return None
        if self._force_new_flow:
            return None
        token_data = entry.get("tokens")
        if not token_data:
            return None
        try:
            return OAuthToken.model_validate(token_data)
        except Exception:
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        store = self._config.get_value(REMOTE_MCP_OAUTH_TOKENS_KEY) or {}
        entry = self._load_entry() or {}
        entry["tokens"] = tokens.model_dump(mode="json")
        store[self._server_id] = entry
        self._config.update_settings({REMOTE_MCP_OAUTH_TOKENS_KEY: store})

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        entry = self._load_entry()
        if not entry:
            return None
        client_info = entry.get("client_info")
        if not client_info:
            return None
        try:
            return OAuthClientInformationFull.model_validate(client_info)
        except Exception:
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        store = self._config.get_value(REMOTE_MCP_OAUTH_TOKENS_KEY) or {}
        entry = self._load_entry() or {}
        entry["client_info"] = client_info.model_dump(mode="json")
        store[self._server_id] = entry
        self._config.update_settings({REMOTE_MCP_OAUTH_TOKENS_KEY: store})


class _KilnOAuthClientProvider(OAuthClientProvider):
    """OAuth client provider that surfaces redirect requirements to the caller."""

    def __init__(
        self,
        manager: "MCPSessionManager",
        tool_server: ExternalToolServer,
        server_url: str,
        client_metadata: OAuthClientMetadata,
        storage: ConfigBackedOAuthTokenStorage,
    ) -> None:
        self._manager = manager
        self._tool_server = tool_server
        self._project_id = manager._tool_server_project_id(tool_server)
        super().__init__(
            server_url=server_url,
            client_metadata=client_metadata,
            storage=storage,
            redirect_handler=self._noop_redirect,
            callback_handler=self._callback_handler,
        )

    async def _noop_redirect(
        self, _: str
    ) -> None:  # pragma: no cover - not expected to run
        return None

    async def _callback_handler(
        self,
    ) -> tuple[str, str | None]:  # pragma: no cover - handled upstream
        raise OAuthFlowError("OAuth callback handler invoked unexpectedly")

    def _get_token_url(self) -> str:
        if self.context.oauth_metadata and self.context.oauth_metadata.token_endpoint:
            return str(self.context.oauth_metadata.token_endpoint)
        auth_base_url = self.context.get_authorization_base_url(self.context.server_url)
        return urljoin(auth_base_url, "/token")

    async def _perform_authorization(self) -> tuple[str, str]:
        if self._tool_server.id is None:
            raise ValueError("Tool server must have an ID before starting OAuth flow")
        if self._project_id is None:
            raise ValueError(
                "Tool server must belong to a project before starting OAuth flow"
            )

        if (
            self.context.oauth_metadata
            and self.context.oauth_metadata.authorization_endpoint
        ):
            auth_endpoint = str(self.context.oauth_metadata.authorization_endpoint)
        else:
            auth_base_url = self.context.get_authorization_base_url(
                self.context.server_url
            )
            auth_endpoint = urljoin(auth_base_url, "/authorize")

        if not self.context.client_info:
            raise OAuthFlowError("No client info available for authorization")

        pkce_params = PKCEParameters.generate()
        state = secrets.token_urlsafe(32)

        auth_params = {
            "response_type": "code",
            "client_id": self.context.client_info.client_id,
            "redirect_uri": str(self.context.client_metadata.redirect_uris[0]),
            "state": state,
            "code_challenge": pkce_params.code_challenge,
            "code_challenge_method": "S256",
        }

        include_resource = self.context.should_include_resource_param(
            self.context.protocol_version
        )
        if include_resource:
            auth_params["resource"] = self.context.get_resource_url()

        if self.context.client_metadata.scope:
            auth_params["scope"] = self.context.client_metadata.scope

        authorization_url = f"{auth_endpoint}?{urlencode(auth_params)}"

        token_url = self._get_token_url()
        resource_value = self.context.get_resource_url() if include_resource else None

        pending_state = PendingOAuthState(
            tool_server_id=self._tool_server.id,
            project_id=self._project_id,
            token_url=token_url,
            code_verifier=pkce_params.code_verifier,
            state=state,
            client_info=self.context.client_info,
            redirect_uri=str(self.context.client_metadata.redirect_uris[0]),
            include_resource=include_resource,
            resource=resource_value,
            scope=self.context.client_metadata.scope,
        )

        await self.context.storage.set_client_info(self.context.client_info)
        self._manager._register_pending_oauth_state(state, pending_state)

        raise RemoteMCPOAuthRedirectRequired(authorization_url)


class MCPSessionManager:
    """
    This class is a singleton that manages MCP sessions for remote MCP servers.
    """

    _shared_instance = None

    def __init__(self):
        self._shell_path = None
        self._pending_oauth_states: dict[str, PendingOAuthState] = {}
        self._redirect_url_adapter = TypeAdapter(AnyUrl)

    @classmethod
    def shared(cls):
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @asynccontextmanager
    async def mcp_client(
        self,
        tool_server: ExternalToolServer,
        force_oauth: bool = False,
        oauth_callback_base_url: str | None = None,
    ) -> AsyncGenerator[
        ClientSession,
        None,
    ]:
        match tool_server.type:
            case ToolServerType.remote_mcp:
                async with self._create_remote_mcp_session(
                    tool_server,
                    force_oauth=force_oauth,
                    oauth_callback_base_url=oauth_callback_base_url,
                ) as session:
                    yield session
            case ToolServerType.local_mcp:
                async with self._create_local_mcp_session(tool_server) as session:
                    yield session
            case ToolServerType.kiln_task:
                raise ValueError("Kiln task tools are not available from an MCP server")
            case _:
                raise_exhaustive_enum_error(tool_server.type)

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
        *,
        force_oauth: bool = False,
        oauth_callback_base_url: str | None = None,
    ) -> AsyncGenerator[ClientSession, None]:
        """Create a session for a remote MCP server."""

        server_url = tool_server.properties.get("server_url")
        if not server_url:
            raise ValueError("server_url is required")

        if tool_server.id is None:
            raise ValueError("Tool server must have an ID before connecting")

        if (
            tool_server.properties.get("oauth_required")
            and not force_oauth
            and not self._has_oauth_tokens(tool_server.id)
        ):
            raise RemoteMCPOAuthTokensMissing(
                "OAuth tokens are required before connecting to this MCP server"
            )

        headers = tool_server.properties.get("headers", {}).copy()
        secret_headers, _ = tool_server.retrieve_secrets()
        headers.update(secret_headers)

        auth_provider = None
        try:
            if force_oauth or tool_server.properties.get("oauth_required"):
                auth_provider = self._build_oauth_client_provider(
                    tool_server,
                    server_url,
                    force_oauth,
                    oauth_callback_base_url,
                )
            elif self._has_oauth_tokens(tool_server.id):
                auth_provider = self._build_oauth_client_provider(
                    tool_server,
                    server_url,
                    False,
                    oauth_callback_base_url,
                )
        except RemoteMCPOAuthTokensMissing:
            raise

        try:
            async with streamablehttp_client(
                server_url, headers=headers, auth=auth_provider
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
        except RemoteMCPOAuthRedirectRequired:
            raise
        except RemoteMCPOAuthTokensMissing:
            raise
        except OAuthTokenError as exc:
            raise RuntimeError(f"OAuth token error: {exc}") from exc
        except OAuthFlowError as exc:
            raise RuntimeError(f"OAuth flow error: {exc}") from exc
        except Exception as e:
            # Re-raise the redirect exception if it exists in a ExceptionGroup
            redirect_exception = self._extract_first_exception(
                e, RemoteMCPOAuthRedirectRequired
            )
            if redirect_exception and isinstance(
                redirect_exception, RemoteMCPOAuthRedirectRequired
            ):
                raise redirect_exception

            http_error = self._extract_first_exception(e, httpx.HTTPStatusError)
            if http_error and isinstance(http_error, httpx.HTTPStatusError):
                raise ValueError(
                    "The MCP server rejected the request. "
                    f"Status {http_error.response.status_code}. "
                    f"Response from server:\n{http_error.response.reason_phrase}"
                )

            connection_error_types = (ConnectionError, OSError, httpx.RequestError)
            connection_error = self._extract_first_exception(e, connection_error_types)
            if connection_error and isinstance(
                connection_error, connection_error_types
            ):
                raise RuntimeError(
                    "Unable to connect to MCP server. Please verify the configurations are correct, "
                    "the server is running, and your network connection is working. "
                    f"Original error: {connection_error}"
                ) from e

            raise RuntimeError(
                "Failed to connect to the MCP Server. Check the server's docs for troubleshooting. "
                f"Original error: {e}"
            ) from e

    def _build_oauth_client_provider(
        self,
        tool_server: ExternalToolServer,
        server_url: str,
        force_oauth: bool,
        oauth_callback_base_url: str | None,
    ) -> _KilnOAuthClientProvider:
        storage = ConfigBackedOAuthTokenStorage(
            tool_server.id or "", force_new_flow=force_oauth
        )
        metadata = self._build_oauth_client_metadata(
            tool_server, storage, oauth_callback_base_url
        )
        return _KilnOAuthClientProvider(
            self,
            tool_server,
            server_url,
            metadata,
            storage,
        )

    def _build_oauth_client_metadata(
        self,
        tool_server: ExternalToolServer,
        storage: ConfigBackedOAuthTokenStorage,
        oauth_callback_base_url: str | None,
    ) -> OAuthClientMetadata:
        project_id = self._tool_server_project_id(tool_server)
        if not project_id:
            raise ValueError("Project ID is required for OAuth flow")
        if tool_server.id is None:
            raise ValueError("Tool server ID is required for OAuth flow")

        redirect_uri = self._resolve_redirect_uri(
            tool_server,
            storage,
            project_id,
            oauth_callback_base_url,
        )

        return OAuthClientMetadata(
            client_name=f"Kiln - {tool_server.name}",
            redirect_uris=[redirect_uri],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=None,
        )

    def _tool_server_project_id(self, tool_server: ExternalToolServer) -> str | None:
        parent = tool_server.parent
        if parent is None:
            return None
        return getattr(parent, "id", None)

    def _build_oauth_callback_url(
        self,
        callback_base_url: str,
        project_id: str,
        tool_server_id: str,
    ) -> str:
        base = callback_base_url.rstrip("/")
        return f"{base}/settings/manage_tools/{project_id}/tool_servers/{tool_server_id}/oauth"

    def _has_oauth_tokens(self, server_id: str | None) -> bool:
        if not server_id:
            return False
        store = Config.shared().get_value(REMOTE_MCP_OAUTH_TOKENS_KEY) or {}
        entry = store.get(server_id)
        if not isinstance(entry, dict):
            return False
        tokens = entry.get("tokens")
        return bool(tokens)

    def has_oauth_tokens(self, tool_server: ExternalToolServer) -> bool:
        return self._has_oauth_tokens(tool_server.id)

    def _get_stored_client_info(
        self, server_id: str | None
    ) -> OAuthClientInformationFull | None:
        if not server_id:
            return None
        store = Config.shared().get_value(REMOTE_MCP_OAUTH_TOKENS_KEY) or {}
        entry = store.get(server_id)
        if not isinstance(entry, dict):
            return None
        client_info = entry.get("client_info")
        if not client_info:
            return None
        try:
            return OAuthClientInformationFull.model_validate(client_info)
        except Exception:
            return None

    def _resolve_redirect_uri(
        self,
        tool_server: ExternalToolServer,
        storage: ConfigBackedOAuthTokenStorage,
        project_id: str,
        oauth_callback_base_url: str | None,
    ) -> AnyUrl:
        if tool_server.id is None:
            raise ValueError(
                "Tool server must have an ID before resolving redirect URI"
            )
        if oauth_callback_base_url:
            callback_url = self._build_oauth_callback_url(
                oauth_callback_base_url, project_id, tool_server.id
            )
            return self._redirect_url_adapter.validate_python(callback_url)

        stored_info = self._get_stored_client_info(tool_server.id)
        if stored_info and stored_info.redirect_uris:
            return stored_info.redirect_uris[0]

        if storage._force_new_flow:  # pragma: no cover - defensive guard
            raise ValueError(
                "OAuth callback base URL is required when forcing a new OAuth flow"
            )

        raise ValueError(
            "OAuth callback base URL is required for remote MCP servers without stored OAuth metadata"
        )

    def _register_pending_oauth_state(
        self, state: str, pending: PendingOAuthState
    ) -> None:
        for key, value in list(self._pending_oauth_states.items()):
            if value.tool_server_id == pending.tool_server_id:
                self._pending_oauth_states.pop(key, None)
        self._pending_oauth_states[state] = pending

    def _pop_pending_oauth_state(self, state: str) -> PendingOAuthState | None:
        return self._pending_oauth_states.pop(state, None)

    async def complete_remote_oauth(
        self,
        tool_server: ExternalToolServer,
        project_id: str,
        code: str,
        state: str,
    ) -> None:
        if tool_server.id is None:
            raise ValueError("Tool server must have an ID before completing OAuth flow")

        pending = self._pop_pending_oauth_state(state)
        if pending is None:
            raise ValueError("OAuth state is invalid or has expired")

        if pending.tool_server_id != tool_server.id:
            raise ValueError("OAuth state does not match the requested tool server")
        if pending.project_id != project_id:
            raise ValueError("OAuth state does not match the requested project")

        storage = ConfigBackedOAuthTokenStorage(tool_server.id)

        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending.redirect_uri,
            "client_id": pending.client_info.client_id,
            "code_verifier": pending.code_verifier,
        }

        if pending.include_resource and pending.resource:
            token_data["resource"] = pending.resource

        if pending.client_info.client_secret:
            token_data["client_secret"] = pending.client_info.client_secret

        async with httpx.AsyncClient() as client:
            response = await client.post(
                pending.token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            status_code = response.status_code
            response_text = response.text
            content = await response.aread()

        if status_code != 200:
            raise OAuthTokenError(
                f"Token exchange failed with status {status_code}: {response_text}"
            )

        token_response = OAuthToken.model_validate_json(content)

        if token_response.scope and pending.scope:
            requested_scopes = set(pending.scope.split())
            returned_scopes = set(token_response.scope.split())
            unauthorized_scopes = returned_scopes - requested_scopes
            if unauthorized_scopes:
                raise OAuthTokenError(
                    f"Server granted unauthorized scopes: {unauthorized_scopes}"
                )

        await storage.set_client_info(pending.client_info)
        await storage.set_tokens(token_response)

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
        cwd = os.path.join(Config.settings_dir(), "cache", "mcp_cache")
        os.makedirs(cwd, exist_ok=True)
        server_params = StdioServerParameters(
            command=command, args=args, env=env_vars, cwd=cwd
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
                # Read stderr content from temporary file for debugging
                err_log.seek(0)  # Read from the start of the file
                stderr_content = err_log.read()
                if stderr_content:
                    logger.error(
                        f"MCP server '{tool_server.name}' stderr output: {stderr_content}"
                    )

                # Check for MCP errors. Things like wrong arguments would fall here.
                mcp_error = self._extract_first_exception(e, McpError)
                if mcp_error and isinstance(mcp_error, McpError):
                    self._raise_local_mcp_error(mcp_error, stderr_content)

                # Re-raise the original error but with a friendlier message
                self._raise_local_mcp_error(e, stderr_content)

    def _raise_local_mcp_error(self, e: Exception, stderr: str):
        """
        Raise a RuntimeError with a friendlier message for local MCP errors.
        """
        error_msg = f"'{e}'"

        if stderr:
            error_msg += f"\nMCP server error: {stderr}"

        error_msg += f"\n{LOCAL_MCP_ERROR_INSTRUCTION}"

        raise RuntimeError(error_msg) from e

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
