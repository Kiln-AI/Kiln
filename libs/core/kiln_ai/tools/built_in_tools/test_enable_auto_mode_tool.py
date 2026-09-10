import json

import pytest

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import ToolCallContext
from kiln_ai.tools.built_in_tools.enable_auto_mode_tool import (
    ENABLE_AUTO_MODE_TOOL_NAME,
    EnableAutoModeTool,
)


@pytest.fixture
def tool():
    return EnableAutoModeTool()


class TestEnableAutoModeToolMetadata:
    @pytest.mark.asyncio
    async def test_tool_metadata(self, tool):
        assert await tool.name() == "enable_auto_mode"
        assert ENABLE_AUTO_MODE_TOOL_NAME == "enable_auto_mode"
        assert await tool.id() == KilnBuiltInToolId.ENABLE_AUTO_MODE
        description = await tool.description()
        assert description
        assert "auto mode" in description.lower()

    @pytest.mark.asyncio
    async def test_toolcall_definition_schema(self, tool):
        definition = await tool.toolcall_definition()
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"] == "enable_auto_mode"
        params = function["parameters"]
        assert params["type"] == "object"
        # Single optional `reason: string` — no required params.
        assert params["properties"]["reason"]["type"] == "string"
        assert set(params["properties"].keys()) == {"reason"}
        assert params.get("required", []) == []


class TestEnableAutoModeToolRun:
    """run() is a signal no-op: in chat it is intercepted by name and never
    executed, but it must return a valid enabled signal to keep the libs/core
    tool surface complete and standalone."""

    @pytest.mark.asyncio
    async def test_run_returns_enabled_signal(self, tool):
        result = await tool.run()
        assert result.is_error is False
        assert json.loads(result.output) == {"status": "enabled"}

    @pytest.mark.asyncio
    async def test_run_with_reason_arg_is_noop(self, tool):
        # The optional reason is accepted and ignored by the no-op.
        result = await tool.run(reason="run the eval suite")
        assert json.loads(result.output) == {"status": "enabled"}

    @pytest.mark.asyncio
    async def test_run_with_positional_context(self, tool):
        # Mirrors LiteLlmAdapter.process_tool_calls: context passed positionally.
        result = await tool.run(ToolCallContext(allow_saving=False))
        assert json.loads(result.output) == {"status": "enabled"}

    @pytest.mark.asyncio
    async def test_run_without_context(self, tool):
        # Mirrors studio_server executor: tool.run(**args) with no context.
        result = await tool.run(**{})
        assert json.loads(result.output) == {"status": "enabled"}
