"""The connection-policy seam: the one place that decides whether an API call
is allowed on an MCP connection."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from starlette.requests import Request

from kiln_mcp_server.api_tool.messages import blocked_endpoint
from kiln_mcp_server.api_tool.route_index import RouteEntry


@dataclass(frozen=True)
class ConnectionScope:
    kind: Literal["open"] = "open"


@dataclass(frozen=True)
class ApiCall:
    """One call as it will be sent: normalised method, concrete path, and the
    route the server will run for it."""

    method: str
    url_path: str
    route: RouteEntry
    path_params: Mapping[str, str]
    query_params: Mapping[str, str | list[str]] | None
    body: str | None


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    message: str | None = None


OPEN_SCOPE = ConnectionScope()
ALLOWED = PolicyDecision(True)


class ConnectionPolicy:
    def scope_for_request(self, request: Request | None) -> ConnectionScope:
        """The scope of the MCP connection that sent `request`. Every
        connection is open."""
        return OPEN_SCOPE

    def check(self, call: ApiCall, scope: ConnectionScope) -> PolicyDecision:
        if call.route.mcp_blocked:
            return PolicyDecision(False, blocked_endpoint(call.method, call.route.path))
        return ALLOWED
