from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest
from kiln_ai.tools.base_tool import KilnToolInterface
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ListToolsRequest,
    TextContent,
)

from kiln_server.mcp import mcp
from kiln_server.mcp.runtime import create_fastmcp_server, run_transport
from kiln_server.mcp.tool_registry import prepare_tool_contexts
from kiln_server.mcp.tool_selection import ToolResolution, collect_project_tools


class FakeTool(KilnToolInterface):
    def __init__(self, tool_id: str, name: str = "search", description: str = "desc") -> None:
        self._tool_id = tool_id
        self._name = name
        self._description = description
        self.output_schema: dict[str, Any] | None = None
        self.received: list[dict[str, Any]] = []

    async def run(self, **kwargs) -> Any:
        self.received.append(kwargs)
        return kwargs.get("query", "")

    async def toolcall_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"}
                    },
                    "required": ["query"],
                },
            },
        }

    async def id(self) -> str:
        return self._tool_id

    async def name(self) -> str:
        return self._name

    async def description(self) -> str:
        return self._description


@dataclass
class FakeRagConfig:
    id: str
    tool_name: str
    tool_description: str
    is_archived: bool = False
    archived: bool | None = None


class FakeProject:
    def __init__(self, rag_configs: List[FakeRagConfig]) -> None:
        self._rag_configs = rag_configs
        self.name = "demo"

    def rag_configs(self, readonly: bool = False) -> List[FakeRagConfig]:
        assert readonly is True
        return self._rag_configs


def _make_tool_factory(tools: dict[str, FakeTool]):
    def factory(tool_id: str, rag_config: FakeRagConfig) -> FakeTool:
        tool = FakeTool(tool_id, name=rag_config.tool_name, description=rag_config.tool_description)
        tools[tool_id] = tool
        return tool

    return factory


class TestCollectProjectTools:
    def test_filters_archived_and_missing(self) -> None:
        configs = [
            FakeRagConfig(id="active", tool_name="active", tool_description="Active"),
            FakeRagConfig(id="archived", tool_name="archived", tool_description="Archived", is_archived=True),
        ]
        project = FakeProject(configs)
        created: dict[str, FakeTool] = {}

        resolutions = collect_project_tools(
            project,
            rag_tool_factory=_make_tool_factory(created),
        )

        assert [resolution.tool_id for resolution in resolutions] == ["kiln_tool::rag::active"]
        assert "kiln_tool::rag::active" in created
        assert "kiln_tool::rag::archived" not in created

    def test_respects_tool_id_filter_and_errors_on_missing(self) -> None:
        configs = [
            FakeRagConfig(id="one", tool_name="one", tool_description="One"),
            FakeRagConfig(id="two", tool_name="two", tool_description="Two"),
        ]
        project = FakeProject(configs)
        created: dict[str, FakeTool] = {}

        selected = collect_project_tools(
            project,
            ["kiln_tool::rag::two"],
            rag_tool_factory=_make_tool_factory(created),
        )
        assert [resolution.tool_id for resolution in selected] == ["kiln_tool::rag::two"]

        with pytest.raises(ValueError):
            collect_project_tools(
                project,
                ["kiln_tool::rag::missing"],
                rag_tool_factory=_make_tool_factory({}),
            )


@pytest.mark.asyncio
async def test_prepare_tool_contexts_uses_definition() -> None:
    tool = FakeTool("kiln_tool::rag::demo", name="demo_tool", description="Demo tool")
    resolutions = [ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)]

    contexts = await prepare_tool_contexts(resolutions)

    assert len(contexts) == 1
    context = contexts[0]
    assert context.definition.name == "demo_tool"
    assert context.definition.description == "Demo tool"
    assert context.definition.inputSchema["properties"]["query"]["type"] == "string"
    assert context.definition.outputSchema is None


@pytest.mark.asyncio
async def test_prepare_tool_contexts_includes_output_schema() -> None:
    tool = FakeTool("kiln_tool::rag::demo", name="demo_tool", description="Demo tool")
    tool.output_schema = {"type": "object", "properties": {"context": {"type": "string"}}, "required": ["context"]}
    resolutions = [ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)]

    contexts = await prepare_tool_contexts(resolutions)
    assert contexts[0].definition.outputSchema == tool.output_schema
    assert contexts[0].requires_structured_output is True


@pytest.mark.asyncio
async def test_prepare_tool_contexts_rejects_duplicate_names() -> None:
    tool_one = FakeTool("kiln_tool::rag::one", name="dup", description="first")
    tool_two = FakeTool("kiln_tool::rag::two", name="dup", description="second")
    resolutions = [
        ToolResolution(tool_id="kiln_tool::rag::one", tool=tool_one),
        ToolResolution(tool_id="kiln_tool::rag::two", tool=tool_two),
    ]

    with pytest.raises(ValueError):
        await prepare_tool_contexts(resolutions)


@pytest.mark.asyncio
async def test_prepare_tool_contexts_rejects_missing_description() -> None:
    class NoDescriptionTool(FakeTool):
        async def description(self) -> str:
            return ""

    tool = NoDescriptionTool("kiln_tool::rag::demo", name="demo_tool", description="")
    resolutions = [ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)]

    with pytest.raises(ValueError):
        await prepare_tool_contexts(resolutions)


@pytest.mark.asyncio
async def test_create_server_invokes_tool_and_returns_text() -> None:
    tool = FakeTool("kiln_tool::rag::demo", name="demo_tool", description="Demo tool")
    resolutions = [ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)]
    contexts = await prepare_tool_contexts(resolutions)

    server = create_fastmcp_server(
        contexts,
        project_name="Demo Project",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        transport="stdio",
        mount_path=None,
    )

    list_handler = server._mcp_server.request_handlers[ListToolsRequest]
    list_result = await list_handler(ListToolsRequest(method="tools/list"))
    assert [tool.name for tool in list_result.root.tools] == ["demo_tool"]

    call_handler = server._mcp_server.request_handlers[CallToolRequest]
    call_request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="demo_tool", arguments={"query": "hello"}),
    )
    call_result = await call_handler(call_request)
    content = call_result.root.content
    assert len(content) == 1
    assert isinstance(content[0], TextContent)
    assert content[0].text == "hello"


@pytest.mark.asyncio
async def test_create_server_enforces_structured_output() -> None:
    class DictTool(FakeTool):
        async def run(self, **kwargs: Any) -> Any:
            return {"answer": 42}

    tool = DictTool("kiln_tool::rag::demo", name="demo_tool", description="Demo tool")
    tool.output_schema = {"type": "object", "properties": {"answer": {"type": "number"}}, "required": ["answer"]}
    contexts = await prepare_tool_contexts([ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)])

    server = create_fastmcp_server(
        contexts,
        project_name=None,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        transport="stdio",
        mount_path=None,
    )

    call_handler = server._mcp_server.request_handlers[CallToolRequest]
    call_request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="demo_tool", arguments={"query": "unused"}),
    )
    call_result = await call_handler(call_request)
    assert call_result.root.structuredContent == {"answer": 42}


@pytest.mark.asyncio
async def test_create_server_errors_when_structured_output_missing() -> None:
    class BadDictTool(FakeTool):
        async def run(self, **kwargs: Any) -> Any:
            return "not a dict"

    tool = BadDictTool("kiln_tool::rag::demo", name="demo_tool", description="Demo tool")
    tool.output_schema = {"type": "object"}
    contexts = await prepare_tool_contexts([ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)])

    server = create_fastmcp_server(
        contexts,
        project_name=None,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        transport="stdio",
        mount_path=None,
    )

    call_handler = server._mcp_server.request_handlers[CallToolRequest]
    call_request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="demo_tool", arguments={}),
    )

    call_result = await call_handler(call_request)
    assert call_result.root.isError is True


@pytest.mark.asyncio
async def test_run_transport_invokes_correct_method() -> None:
    class FakeServer:
        def __init__(self) -> None:
            self.run_stdio_async = AsyncMock()
            self.run_sse_async = AsyncMock()
            self.run_streamable_http_async = AsyncMock()

    server = FakeServer()

    await run_transport(server, "stdio", None)
    server.run_stdio_async.assert_awaited()

    await run_transport(server, "sse", "/sse")
    server.run_sse_async.assert_awaited_with("/sse")

    await run_transport(server, "streamable-http", None)
    server.run_streamable_http_async.assert_awaited()


class TestParseToolIds:
    def test_parse_tool_ids_handles_none(self) -> None:
        assert mcp._parse_tool_ids(None) is None
        assert mcp._parse_tool_ids(" ") is None

    def test_parse_tool_ids_splits_values(self) -> None:
        assert mcp._parse_tool_ids("a,b , c") == ["a", "b", "c"]
