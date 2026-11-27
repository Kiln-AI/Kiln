from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from kiln_server.utils.agent_checks import ALLOW_AGENT, with_mcp_deny
from starlette.routing import Match

from kiln_mcp_server.api_tool.route_index import RouteIndex, RouteMatch


@pytest.fixture
def index(api_app) -> RouteIndex:
    return RouteIndex.from_app(api_app)


def test_found_with_path_params(index):
    match = index.match("PATCH", "/api/items/42")
    assert match.kind == "found"
    assert match.entry is not None
    assert match.entry.path == "/api/items/{item_id}"
    assert match.entry.methods == frozenset({"PATCH"})
    assert match.path_params == {"item_id": "42"}


def test_unknown(index):
    assert index.match("GET", "/api/nope") == RouteMatch(kind="unknown")


def test_wrong_method_lists_the_methods_of_the_path(index):
    assert index.match("DELETE", "/api/items/1") == RouteMatch(
        kind="wrong_method", path_methods=("GET", "PATCH")
    )


def test_the_static_route_wins_over_the_parameter_route(index):
    match = index.match("GET", "/api/things/special")
    assert match.entry is not None
    assert match.entry.path == "/api/things/special"
    assert match.path_params == {}


def test_a_block_on_one_route_of_a_pair_does_not_block_the_other(index):
    special = index.match("GET", "/api/things/special").entry
    other = index.match("GET", "/api/things/other").entry
    assert special is not None and special.mcp_blocked is True
    assert other is not None and other.mcp_blocked is False
    assert other.path == "/api/things/{thing_id}"


def test_a_block_on_the_parameter_route_does_not_block_the_static_one():
    app = FastAPI()
    app.get("/api/jobs/events", openapi_extra=ALLOW_AGENT)(lambda: None)
    app.get("/api/jobs/{job_id}", openapi_extra=with_mcp_deny(ALLOW_AGENT))(
        lambda job_id: None
    )
    index = RouteIndex.from_app(app)
    events = index.match("GET", "/api/jobs/events").entry
    job = index.match("GET", "/api/jobs/7").entry
    assert events is not None and events.mcp_blocked is False
    assert job is not None and job.mcp_blocked is True


@pytest.mark.parametrize("url_path", ["/api/things/specia%6C", "/api/things%2Fspecial"])
def test_escapes_match_the_route_the_server_runs(index, url_path):
    match = index.match("GET", url_path)
    assert match.entry is not None
    assert match.entry.path == "/api/things/special"
    assert match.entry.mcp_blocked is True


def test_only_ping_and_api_routes_are_indexed(index):
    paths = {entry.path for entry in index.entries}
    assert "/ping" in paths
    assert all(path == "/ping" or path.startswith("/api/") for path in paths)
    assert index.match("GET", "/not_api").kind == "unknown"
    assert index.match("GET", "/static").kind == "unknown"
    assert index.match("GET", "/openapi.json").kind == "unknown"


def test_entries_keep_the_route_order(index, api_app):
    assert [entry.path for entry in index.entries] == [
        route.path
        for route in api_app.routes
        if isinstance(route, APIRoute) and route.path != "/not_api"
    ]


SAMPLES = [
    ("GET", "/ping"),
    ("POST", "/ping"),
    ("GET", "/api/items/1"),
    ("PATCH", "/api/items/1"),
    ("POST", "/api/items/1"),
    ("GET", "/api/items/1/sub"),
    ("GET", "/api/items"),
    ("GET", "/api/things/special"),
    ("DELETE", "/api/things/special"),
    ("GET", "/api/things/x"),
    ("GET", "/api/things/specia%6C"),
    ("GET", "/api/things%2Fx"),
    ("POST", "/api/secrets"),
    ("GET", "/api/secrets"),
    ("GET", "/api/text"),
    ("POST", "/api/stream"),
    ("GET", "/api/stream"),
    ("GET", "/api/slow"),
    ("GET", "/api/missing"),
    ("GET", "/api/unknown/deep/path"),
]


def _starlette_walk(app, method: str, url_path: str) -> tuple[str, str | None]:
    """The route Starlette's router picks: the first full match, else 405
    when some route matched the path only."""
    scope = {"type": "http", "method": method, "path": unquote(url_path)}
    partial = False
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path == "/not_api":
            continue
        result, _ = route.matches(scope)
        if result == Match.FULL:
            return "found", route.path
        partial = partial or result == Match.PARTIAL
    return ("wrong_method", None) if partial else ("unknown", None)


@pytest.mark.parametrize("method, url_path", SAMPLES)
def test_matches_the_starlette_router(index, api_app, method, url_path):
    match = index.match(method, url_path)
    found_path = match.entry.path if match.entry else None
    assert (match.kind, found_path) == _starlette_walk(api_app, method, url_path)
