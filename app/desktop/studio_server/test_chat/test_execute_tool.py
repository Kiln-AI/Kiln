import json

import pytest
from app.desktop.studio_server.chat import execute_tool


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_runs_multiply_builtin(self):
        assert (
            await execute_tool("kiln_tool::multiply_numbers", {"a": 2, "b": 8}) == "16"
        )

    @pytest.mark.asyncio
    async def test_runs_add_builtin(self):
        assert await execute_tool("kiln_tool::add_numbers", {"a": 1, "b": 2}) == "3"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_json_error(self):
        out = await execute_tool("nonexistent_tool_xyz", {})
        data = json.loads(out)
        assert "error" in data
        assert "nonexistent_tool_xyz" in data["error"]
