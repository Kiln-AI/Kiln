import re

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from kiln_mcp_server.api_tool.route_index import RouteIndex
from kiln_server.utils.agent_checks import MCP_POLICY_KEY, is_mcp_denied

from app.desktop.desktop_server import make_app

# The endpoints that agents may not call over Kiln's MCP server. Adding or
# removing a row is a policy change: the Kiln skill tells agents what to do
# instead for each blocked capability, so it must agree with this list.
EXPECTED_MCP_BLOCKED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/git_sync/oauth/status/{state}"),
        ("POST", "/api/git_sync/oauth/start"),
        ("GET", "/api/git_sync/oauth/callback"),
        ("GET", "/api/git_sync/oauth/authorize"),
        ("POST", "/api/git_sync/test_access"),
        ("POST", "/api/git_sync/list_branches"),
        ("POST", "/api/git_sync/clone"),
        ("POST", "/api/git_sync/test_write_access"),
        ("POST", "/api/git_sync/scan_projects"),
        ("POST", "/api/git_sync/rename_clone"),
        ("POST", "/api/git_sync/save_config"),
        ("GET", "/api/git_sync/config/{project_id}"),
        ("PATCH", "/api/git_sync/config/{project_id}"),
        ("DELETE", "/api/git_sync/config/{project_id}"),
        ("GET", "/api/select_kiln_file"),
        ("POST", "/api/chat"),
        ("POST", "/api/chat/execute-tools"),
        ("GET", "/api/jobs/events"),
        ("POST", "/api/provider/create_kiln_copilot_api_key"),
        ("POST", "/api/settings"),
        ("POST", "/api/open_logs"),
        ("POST", "/api/open_project_folder/{project_id}"),
        (
            "POST",
            "/api/projects/{project_id}/documents/{document_id}/open_enclosing_folder",
        ),
        ("POST", "/api/projects/{project_id}/skills/{skill_id}/open_enclosing_folder"),
        ("GET", "/api/projects/{project_id}/documents/{document_id}/download"),
        ("POST", "/api/provider/connect_api_key"),
        ("POST", "/api/provider/disconnect_api_key"),
        ("POST", "/api/provider/openai_compatible"),
        ("DELETE", "/api/provider/openai_compatible"),
    }
)

# Endpoints next to blocked ones, or close to the block rules, that agents may
# call.
EXPECTED_MCP_ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/api/projects/{project_id}/add_code_trust"),
    ("POST", "/api/projects/{project_id}/add_code_trust"),
    ("POST", "/api/projects/{project_id}/connect_local_mcp"),
    ("PATCH", "/api/projects/{project_id}/edit_local_mcp/{tool_server_id}"),
    ("GET", "/api/settings"),
    ("GET", "/api/settings/{item_id}"),
    ("GET", "/api/jobs/{id}"),
    ("POST", "/api/provider/ollama/connect"),
    ("DELETE", "/api/delete_project/{project_id}"),
    ("GET", "/api/download_dataset_jsonl"),
    (
        "GET",
        "/api/projects/{project_id}/documents/{document_id}/download_extraction/{extraction_id}",
    ),
    ("GET", "/api/chat/sessions"),
    ("POST", "/api/projects/{project_id}/tasks/{task_id}/data_gen_guide"),
)


@pytest.fixture(scope="module")
def app() -> FastAPI:
    # Only the routes and the OpenAPI document are read; the lifespan is never
    # entered, so one app can serve the whole module.
    return make_app()


@pytest.fixture(scope="module")
def route_index(app: FastAPI) -> RouteIndex:
    return RouteIndex.from_app(app)


def _concrete_path(template: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", template)


def _operations(app: FastAPI) -> dict[tuple[str, str], dict]:
    return {
        (method.upper(), path): operation
        for path, path_item in app.openapi()["paths"].items()
        for method, operation in path_item.items()
    }


def test_blocked_routes_match_the_block_list(app):
    blocked = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and is_mcp_denied(route.openapi_extra)
        for method in route.methods
    }
    assert blocked == EXPECTED_MCP_BLOCKED


@pytest.mark.parametrize("method, template", sorted(EXPECTED_MCP_BLOCKED))
def test_each_blocked_route_is_reachable_by_its_template(route_index, method, template):
    match = route_index.match(method, _concrete_path(template))
    assert match.kind == "found"
    assert match.entry is not None
    assert match.entry.path == template
    assert match.entry.mcp_blocked


@pytest.mark.parametrize("method, template", sorted(EXPECTED_MCP_BLOCKED))
def test_each_blocked_route_is_tagged_in_openapi(app, method, template):
    operation = _operations(app)[(method, template)]
    assert operation[MCP_POLICY_KEY] == {"permission": "deny"}


@pytest.mark.parametrize("method, template", EXPECTED_MCP_ALLOWED)
def test_routes_kept_open(route_index, method, template):
    match = route_index.match(method, _concrete_path(template))
    assert match.kind == "found"
    assert match.entry is not None
    assert match.entry.path == template
    assert not match.entry.mcp_blocked


def test_agent_policies_are_unchanged_by_the_block(app):
    operations = _operations(app)
    agent_policies = {
        row: operations[row]["x-agent-policy"] for row in EXPECTED_MCP_BLOCKED
    }
    assert agent_policies.pop(("GET", "/api/jobs/events")) == {
        "permission": "allow",
        "requires_approval": False,
    }
    open_logs = agent_policies.pop(("POST", "/api/open_logs"))
    assert open_logs["permission"] == "allow"
    assert open_logs["requires_approval"] is True
    assert all(
        policy == {"permission": "deny", "requires_approval": False}
        for policy in agent_policies.values()
    )
