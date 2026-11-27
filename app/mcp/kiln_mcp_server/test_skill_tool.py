import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult, TextContent, Tool
from starlette.testclient import TestClient

from kiln_mcp_server.conftest import MCP_HEADERS, jsonrpc, sse_message, write_tree
from kiln_mcp_server.skill_files import E_ABS, SkillIndex, build_index
from kiln_mcp_server.skill_tool import SKILL_TOOL_NAME, register_skill_tool
from kiln_mcp_server.texts import PATH_DESCRIPTION, SKILL_TOOL_DESCRIPTION

SKILL_MD = "---\nname: kiln\ndescription: Test.\n---\n\n# Kiln\n\nApp: http://localhost:8757/settings\n"
RAG_MD = "---\nname: rag\n---\nRAG at http://localhost:8757/docs\n"


@pytest.fixture
def index(tmp_path) -> SkillIndex:
    return build_index(
        write_tree(
            tmp_path / "skill",
            {"SKILL.md": SKILL_MD, "references/knowledge/rag.md": RAG_MD},
        )
    )


def make_mcp(
    index: SkillIndex,
    host: str = "127.0.0.1",
    port: int = 8757,
    ui_origin: str | None = None,
) -> FastMCP:
    mcp = FastMCP(
        name="kiln",
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )
    register_skill_tool(
        mcp, bound_host=host, bound_port=port, ui_origin=ui_origin, index=index
    )
    return mcp


@pytest.fixture
def mcp(index) -> FastMCP:
    return make_mcp(index)


# The client session's task group must be entered and left in one task, so
# each helper opens its own session instead of sharing one through a fixture.
async def list_tool(mcp: FastMCP) -> Tool:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        (tool,) = (await client.list_tools()).tools
    return tool


async def call(mcp: FastMCP, arguments: dict) -> CallToolResult:
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        return await client.call_tool(SKILL_TOOL_NAME, arguments)


async def call_text(mcp: FastMCP, arguments: dict) -> tuple[str, bool]:
    result = await call(mcp, arguments)
    assert len(result.content) == 1
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text, result.isError


async def test_schema_has_only_optional_path(mcp):
    tool = await list_tool(mcp)
    assert tool.name == SKILL_TOOL_NAME
    assert tool.description == SKILL_TOOL_DESCRIPTION
    assert tool.inputSchema == {
        "type": "object",
        "title": "kiln_skillArguments",
        "properties": {
            "path": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "description": PATH_DESCRIPTION,
                "title": "Path",
            }
        },
    }
    assert tool.outputSchema is None


async def test_a_ui_on_another_address_adds_one_note_to_the_description(index):
    tool = await list_tool(make_mcp(index, ui_origin="http://localhost:5173"))
    assert tool.description == (
        SKILL_TOOL_DESCRIPTION
        + "\n\nNote: the Kiln UI is running at http://localhost:5173, not "
        "http://localhost:8757; use that address in any UI link you give the user."
    )


@pytest.mark.parametrize("ui_origin", [None, "http://localhost:8757"])
async def test_a_ui_on_the_app_address_leaves_the_description_alone(index, ui_origin):
    tool = await list_tool(make_mcp(index, ui_origin=ui_origin))
    assert tool.description == SKILL_TOOL_DESCRIPTION


async def test_the_ui_note_names_the_bound_app_address(index):
    tool = await list_tool(
        make_mcp(index, host="0.0.0.0", port=9000, ui_origin="http://localhost:5174")
    )
    assert tool.description is not None
    assert tool.description.endswith(
        "Note: the Kiln UI is running at http://localhost:5174, not "
        "http://localhost:9000; use that address in any UI link you give the user."
    )


async def test_meta_always_load_and_annotations(mcp):
    tool = await list_tool(mcp)
    assert tool.meta == {"anthropic/alwaysLoad": True}
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.openWorldHint is False


async def test_no_args_returns_skill_md_without_front_matter(mcp):
    assert await call_text(mcp, {}) == (
        "# Kiln\n\nApp: http://localhost:8757/settings\n",
        False,
    )


async def test_path_returns_file_text(mcp):
    assert await call_text(mcp, {"path": "references/knowledge/rag.md"}) == (
        RAG_MD,
        False,
    )


async def test_resource_alias(mcp):
    assert await call_text(mcp, {"resource": "references/knowledge/rag.md"}) == (
        RAG_MD,
        False,
    )


async def test_stray_name_skill_id_ignored(mcp):
    text, is_error = await call_text(mcp, {"name": "kiln", "skill": "x", "id": 3})
    assert not is_error
    assert text.startswith("# Kiln")


async def test_error_is_iserror_without_sdk_prefix(mcp):
    assert await call_text(mcp, {"path": "/etc/passwd"}) == (
        E_ABS.format(raw="/etc/passwd"),
        True,
    )


async def test_no_structured_content(mcp):
    result = await call(mcp, {})
    assert result.structuredContent is None


async def test_wrong_type_is_an_error(mcp):
    text, is_error = await call_text(mcp, {"path": 5})
    assert is_error
    assert "validation error" in text


async def test_non_default_origin_is_replaced(index):
    text, _ = await call_text(make_mcp(index, port=9000), {})
    assert text == "# Kiln\n\nApp: http://localhost:9000/settings\n"


def test_host_header_is_not_used(index):
    mcp = make_mcp(index, host="kiln.lan", port=8800)
    with TestClient(
        mcp.streamable_http_app(), base_url="http://example.test:1234"
    ) as client:
        response = client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json=jsonrpc("tools/call", {"name": SKILL_TOOL_NAME, "arguments": {}}),
        )
    assert response.status_code == 200
    text = sse_message(response.text)["result"]["content"][0]["text"]
    assert text == "# Kiln\n\nApp: http://kiln.lan:8800/settings\n"


def test_description_is_100_to_150_words_and_front_loaded():
    assert 100 <= len(SKILL_TOOL_DESCRIPTION.split()) <= 150
    trigger_rule = "that is a request to call this tool."
    assert SKILL_TOOL_DESCRIPTION.index(trigger_rule) + len(trigger_rule) <= 500
