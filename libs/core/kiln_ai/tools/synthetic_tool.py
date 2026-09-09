"""SyntheticToolProxy — a world's synthetic tool presented under the real tool's id.

The registry returns one of these in place of the real tool while a synthetic instance
is active. It answers ``id()`` with the *real* tool id and ``name()`` /
``toolcall_definition()`` with the synthetic tool's function name and schema (which the
world binding requires to match the real one), and delegates ``run()`` to the synthetic
tool's Python code in the sandbox. Traces, tool-call checks and fingerprints therefore
look exactly as they would against the real tool.
"""

from __future__ import annotations

from typing import Any

from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.synthetic_world import SyntheticTool
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import ToolId
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)
from kiln_ai.tools.code_tool import PythonCodeTool


class SyntheticToolProxy(KilnToolInterface):
    def __init__(
        self,
        real_tool_id: ToolId,
        synthetic_tool: SyntheticTool,
        project: Project,
        task: Task | None = None,
    ):
        self._real_tool_id = real_tool_id
        self._synthetic_tool = synthetic_tool
        self._impl = PythonCodeTool(synthetic_tool, project, task)

    @property
    def synthetic_tool(self) -> SyntheticTool:
        return self._synthetic_tool

    async def id(self) -> ToolId:
        return self._real_tool_id

    async def name(self) -> str:
        return await self._impl.name()

    async def description(self) -> str:
        return await self._impl.description()

    async def toolcall_definition(self) -> ToolCallDefinition:
        return await self._impl.toolcall_definition()

    async def run(
        self, context: ToolCallContext | None = None, **kwargs: Any
    ) -> ToolCallResult:
        return await self._impl.run(context, **kwargs)
