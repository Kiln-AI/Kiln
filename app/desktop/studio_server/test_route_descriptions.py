import re

import pytest
from kiln_server.utils.agent_checks import MCP_POLICY_KEY

from app.desktop.desktop_server import make_app

# The API reference generator keeps this many characters of a description in a
# catalogue row, where an agent picks the endpoint to call.
CATALOGUE_DESCRIPTION_LIMIT = 100

_SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)\.(?=\s|$)")


def first_sentence(description: str) -> str:
    first_paragraph = re.split(r"\n\s*\n", description.strip(), maxsplit=1)[0]
    text = " ".join(first_paragraph.split())
    end = _SENTENCE_END.search(text)
    return text[: end.end()] if end else text


def operations_for_agents(spec: dict) -> dict[str, dict]:
    """Every operation of an OpenAPI document that is not blocked over MCP,
    keyed by "METHOD /path"."""
    return {
        f"{method.upper()} {path}": operation
        for path, path_item in spec["paths"].items()
        for method, operation in path_item.items()
        if operation.get(MCP_POLICY_KEY, {}).get("permission") != "deny"
    }


@pytest.fixture(scope="module")
def operations() -> dict[str, dict]:
    # Only the OpenAPI document is read; the lifespan is never entered.
    return operations_for_agents(make_app().openapi())


def test_every_unblocked_route_has_a_description(operations):
    missing = sorted(
        name
        for name, operation in operations.items()
        if not operation.get("description", "").strip()
    )
    assert missing == []


def test_every_description_starts_with_a_short_sentence(operations):
    too_long = sorted(
        name
        for name, operation in operations.items()
        if len(first_sentence(operation.get("description", "")))
        > CATALOGUE_DESCRIPTION_LIMIT
    )
    assert too_long == []


def test_blocked_routes_are_not_checked():
    spec = {
        "paths": {
            "/api/open": {"get": {"description": "Open."}},
            "/api/blocked": {
                "get": {MCP_POLICY_KEY: {"permission": "deny"}},
                "post": {MCP_POLICY_KEY: {"permission": "allow"}},
            },
        }
    }
    assert set(operations_for_agents(spec)) == {"GET /api/open", "POST /api/blocked"}


@pytest.mark.parametrize(
    "description, expected",
    [
        ("List the projects.", "List the projects."),
        ("List the projects. Then more.", "List the projects."),
        ("Get one\nproject.\n\nDetails.", "Get one project."),
        ("A heading paragraph\n\nwith no full stop.", "A heading paragraph"),
        (
            "Get a status (e.g. running, failed). More.",
            "Get a status (e.g. running, failed).",
        ),
        ("Ends at id::x.y without a space", "Ends at id::x.y without a space"),
    ],
)
def test_first_sentence(description, expected):
    assert first_sentence(description) == expected
