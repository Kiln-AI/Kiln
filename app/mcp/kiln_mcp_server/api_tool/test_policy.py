import re

import pytest
from starlette.requests import Request

from kiln_mcp_server.api_tool.messages import blocked_endpoint
from kiln_mcp_server.api_tool.policy import (
    ALLOWED,
    OPEN_SCOPE,
    ApiCall,
    ConnectionPolicy,
    PolicyDecision,
)
from kiln_mcp_server.api_tool.route_index import RouteEntry


def entry(blocked: bool) -> RouteEntry:
    return RouteEntry(
        path="/api/things/{thing_id}",
        methods=frozenset({"GET"}),
        regex=re.compile("^/api/things/(?P<thing_id>[^/]+)$"),
        mcp_blocked=blocked,
    )


def api_call(blocked: bool) -> ApiCall:
    return ApiCall(
        method="GET",
        url_path="/api/things/7",
        route=entry(blocked),
        path_params={"thing_id": "7"},
        query_params=None,
        body=None,
    )


def test_a_blocked_route_is_refused_with_the_block_text():
    decision = ConnectionPolicy().check(api_call(blocked=True), OPEN_SCOPE)
    assert decision == PolicyDecision(
        False, blocked_endpoint("GET", "/api/things/{thing_id}")
    )
    assert decision.message == (
        "The endpoint GET /api/things/{thing_id} is not available to agents over "
        "MCP. Do not retry it and do not look for another way to call it. If the "
        "user needs this, ask them to do it in the Kiln app."
    )


def test_an_allowed_route_is_allowed():
    assert ConnectionPolicy().check(api_call(blocked=False), OPEN_SCOPE) is ALLOWED


@pytest.mark.parametrize(
    "request_",
    [None, Request({"type": "http", "method": "POST", "path": "/mcp", "headers": []})],
)
def test_every_connection_is_open(request_):
    assert ConnectionPolicy().scope_for_request(request_) is OPEN_SCOPE
