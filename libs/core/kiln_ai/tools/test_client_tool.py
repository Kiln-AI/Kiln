import pytest

from kiln_ai.datamodel.tool_id import _check_tool_id, client_tool_name_from_id
from kiln_ai.tools.client_tool import (
    ClientToolCallRequired,
    ClientToolPlaceholder,
    client_tool_from_id,
)
from kiln_ai.tools.tool_registry import tool_from_id


class TestClientToolId:
    def test_valid_client_tool_id(self):
        assert (
            _check_tool_id("client_tool::read_task_run") == "client_tool::read_task_run"
        )

    def test_invalid_client_tool_id_no_name(self):
        with pytest.raises(ValueError, match="Invalid client tool ID"):
            _check_tool_id("client_tool::")

    def test_client_tool_name_from_id(self):
        assert client_tool_name_from_id("client_tool::read_task_run") == "read_task_run"

    def test_client_tool_name_from_id_invalid_prefix(self):
        with pytest.raises(ValueError, match="Invalid client tool ID"):
            client_tool_name_from_id("kiln_tool::add_numbers")


class TestClientToolPlaceholder:
    async def test_provides_schema(self):
        tool = client_tool_from_id("client_tool::read_task_run")
        definition = await tool.toolcall_definition()

        assert definition["type"] == "function"
        assert definition["function"]["name"] == "read_task_run"
        assert "path" in definition["function"]["parameters"]["properties"]

    async def test_run_raises_client_tool_call_required(self):
        tool = client_tool_from_id("client_tool::read_task_run")
        with pytest.raises(ClientToolCallRequired) as exc_info:
            await tool.run(path="/some/path.kiln")

        assert exc_info.value.tool_name == "read_task_run"
        assert exc_info.value.arguments["path"] == "/some/path.kiln"

    async def test_id(self):
        tool = client_tool_from_id("client_tool::read_task_run")
        assert await tool.id() == "client_tool::read_task_run"

    async def test_name(self):
        tool = client_tool_from_id("client_tool::read_task_run")
        assert await tool.name() == "read_task_run"


class TestClientToolFromId:
    def test_unknown_client_tool(self):
        with pytest.raises(ValueError, match="Unknown client tool"):
            client_tool_from_id("client_tool::nonexistent")

    def test_known_client_tool(self):
        tool = client_tool_from_id("client_tool::read_task_run")
        assert isinstance(tool, ClientToolPlaceholder)


class TestToolRegistryIntegration:
    def test_tool_from_id_resolves_client_tool(self):
        tool = tool_from_id("client_tool::read_task_run")
        assert isinstance(tool, ClientToolPlaceholder)


class TestClientToolCallRequired:
    def test_exception_attributes(self):
        exc = ClientToolCallRequired(
            tool_call_id="tc_123",
            tool_name="read_task_run",
            arguments={"path": "/test"},
        )
        assert exc.tool_call_id == "tc_123"
        assert exc.tool_name == "read_task_run"
        assert exc.arguments == {"path": "/test"}

    def test_tool_call_id_mutable(self):
        exc = ClientToolCallRequired(
            tool_call_id="",
            tool_name="read_task_run",
            arguments={},
        )
        exc.tool_call_id = "tc_updated"
        assert exc.tool_call_id == "tc_updated"
