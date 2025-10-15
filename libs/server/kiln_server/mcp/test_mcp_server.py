from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from kiln_ai.datamodel.external_tool_server import ToolServerType
from kiln_ai.tools.base_tool import KilnToolInterface, ToolCallResult
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    ListToolsRequest,
    TextContent,
)

from kiln_server.mcp import mcp
from kiln_server.mcp.mcp_server_tool_utils import prepare_tool_contexts
from kiln_server.mcp.runtime import create_fastmcp_server, run_transport
from kiln_server.mcp.tool_selection import ToolResolution, collect_project_tools


class FakeTool(KilnToolInterface):
    def __init__(
        self, tool_id: str, name: str = "search", description: str = "desc"
    ) -> None:
        self._tool_id = tool_id
        self._name = name
        self._description = description
        self.output_schema: dict[str, Any] | None = None
        self.received: list[dict[str, Any]] = []

    async def run(self, **kwargs) -> ToolCallResult:
        self.received.append(kwargs)
        return ToolCallResult(output=kwargs.get("query", ""))

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


class FakeRagConfig:
    def __init__(
        self,
        id: str,
        tool_name: str,
        tool_description: str,
        is_archived: bool = False,
        archived: bool | None = None,
    ):
        self.id = id
        self.tool_name = tool_name
        self.tool_description = tool_description
        self.is_archived = is_archived
        self.archived = archived


class TestCollectProjectTools:
    @patch("kiln_server.mcp.tool_selection.RagTool")
    def test_filters_archived_and_missing(self, mock_rag_tool_class) -> None:
        from unittest.mock import Mock

        # Create mock RAG configs
        active_config = Mock()
        active_config.id = "active"
        active_config.is_archived = False

        archived_config = Mock()
        archived_config.id = "archived"
        archived_config.is_archived = True

        # Create mock project
        project = Mock()
        project.rag_configs.return_value = [active_config, archived_config]
        project.external_tool_servers.return_value = []

        resolutions = collect_project_tools(project)

        assert [resolution.tool_id for resolution in resolutions] == [
            "kiln_tool::rag::active"
        ]
        # Verify RagTool was only called for the active config
        mock_rag_tool_class.assert_called_once_with(
            "kiln_tool::rag::active", active_config
        )

    @patch("kiln_server.mcp.tool_selection.RagTool")
    def test_respects_tool_id_filter_and_errors_on_missing(
        self, mock_rag_tool_class
    ) -> None:
        from unittest.mock import Mock

        # Create mock RAG configs
        config_one = Mock()
        config_one.id = "one"
        config_one.is_archived = False

        config_two = Mock()
        config_two.id = "two"
        config_two.is_archived = False

        # Create mock project
        project = Mock()
        project.rag_configs.return_value = [config_one, config_two]
        project.external_tool_servers.return_value = []

        selected = collect_project_tools(
            project,
            ["kiln_tool::rag::two"],
        )
        assert [resolution.tool_id for resolution in selected] == [
            "kiln_tool::rag::two"
        ]
        # Verify RagTool was only called for the selected config
        mock_rag_tool_class.assert_called_once_with("kiln_tool::rag::two", config_two)

        with pytest.raises(
            ValueError, match="Requested tool IDs were not found or are archived"
        ):
            collect_project_tools(
                project,
                ["kiln_tool::rag::missing"],
            )

    @patch("kiln_server.mcp.tool_selection.KilnTaskTool")
    def test_includes_kiln_task_tools(self, mock_kiln_task_tool_class) -> None:
        """Test that kiln task tools are included in the results."""
        from unittest.mock import Mock

        # Create mock task servers
        task_server = Mock()
        task_server.id = "task1"
        task_server.type = ToolServerType.kiln_task

        remote_server = Mock()
        remote_server.id = "task2"
        remote_server.type = ToolServerType.remote_mcp

        # Create mock project
        project = Mock()
        project.id = "test-project-id"
        project.rag_configs.return_value = []
        project.external_tool_servers.return_value = [task_server, remote_server]

        resolutions = collect_project_tools(project)

        assert [resolution.tool_id for resolution in resolutions] == [
            "kiln_task::task1"
        ]
        # Verify KilnTaskTool was called with correct parameters
        mock_kiln_task_tool_class.assert_called_once_with(
            "test-project-id", "kiln_task::task1", task_server
        )

    @patch("kiln_server.mcp.tool_selection.RagTool")
    @patch("kiln_server.mcp.tool_selection.KilnTaskTool")
    def test_combines_rag_and_task_tools(
        self, mock_kiln_task_tool_class, mock_rag_tool_class
    ) -> None:
        """Test that both RAG and task tools are included together."""
        from unittest.mock import Mock

        # Create mock RAG config
        rag_config = Mock()
        rag_config.id = "rag1"
        rag_config.is_archived = False

        # Create mock task server
        task_server = Mock()
        task_server.id = "task1"
        task_server.type = ToolServerType.kiln_task

        # Create mock project
        project = Mock()
        project.id = "test-project-id"
        project.rag_configs.return_value = [rag_config]
        project.external_tool_servers.return_value = [task_server]

        resolutions = collect_project_tools(project)

        tool_ids = [resolution.tool_id for resolution in resolutions]
        assert "kiln_tool::rag::rag1" in tool_ids
        assert "kiln_task::task1" in tool_ids
        assert len(tool_ids) == 2

    def test_requires_project_id_for_task_tools(self) -> None:
        """Test that task tools require a project ID."""
        from unittest.mock import Mock

        # Create mock task server
        task_server = Mock()
        task_server.id = "task1"
        task_server.type = ToolServerType.kiln_task

        # Create mock project with no ID
        project = Mock()
        project.id = None
        project.rag_configs.return_value = []
        project.external_tool_servers.return_value = [task_server]

        with pytest.raises(ValueError, match="Project ID is required"):
            collect_project_tools(project)


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
    tool.output_schema = {
        "type": "object",
        "properties": {"context": {"type": "string"}},
        "required": ["context"],
    }
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
async def test_create_server_errors_when_structured_output_missing() -> None:
    class BadDictTool(FakeTool):
        async def run(self, **kwargs: Any) -> Any:
            return "not a dict"

    tool = BadDictTool(
        "kiln_tool::rag::demo", name="demo_tool", description="Demo tool"
    )
    tool.output_schema = {"type": "object"}
    contexts = await prepare_tool_contexts(
        [ToolResolution(tool_id="kiln_tool::rag::demo", tool=tool)]
    )

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
