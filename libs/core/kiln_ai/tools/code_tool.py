"""PythonCodeTool — parent-side runtime for user-authored code tools.

Phase 1 provides identity + definition only (enough for registry resolution).
Full execution (run, spawn, IPC, nested calls) is added in phase 2.
"""

from kiln_ai.datamodel.code_tool import CodeTool
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.task import Task
from kiln_ai.datamodel.tool_id import ToolId, build_code_tool_id
from kiln_ai.tools.base_tool import (
    KilnToolInterface,
    ToolCallContext,
    ToolCallDefinition,
    ToolCallResult,
)


class PythonCodeTool(KilnToolInterface):
    """Wraps a :class:`CodeTool` artifact as a :class:`KilnToolInterface`.

    Phase 1 stub: ``run()`` raises ``NotImplementedError``; identity and
    definition methods are fully functional so the registry can resolve
    code-tool IDs and the adapter can build tool-call definitions.
    """

    def __init__(
        self,
        code_tool: CodeTool,
        project: Project,
        task: Task | None = None,
    ):
        self._code_tool = code_tool
        self._project = project
        self._task = task

    async def id(self) -> ToolId:
        return build_code_tool_id(self._code_tool.id)

    async def name(self) -> str:
        return self._code_tool.tool_function_name

    async def description(self) -> str:
        return self._code_tool.tool_description

    async def toolcall_definition(self) -> ToolCallDefinition:
        return {
            "type": "function",
            "function": {
                "name": self._code_tool.tool_function_name,
                "description": self._code_tool.tool_description,
                "parameters": self._code_tool.parameters_schema,
            },
        }

    async def run(
        self, context: ToolCallContext | None = None, **kwargs
    ) -> ToolCallResult:
        raise NotImplementedError(
            "PythonCodeTool.run() is not yet implemented (phase 2)."
        )
