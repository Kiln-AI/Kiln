"""Enable Auto Mode Tool — a signal the model emits to suggest the assistant run autonomously.

This tool is **client-visible** and **never executed in chat**: when the model calls it, the app
server intercepts it by name (``enable_auto_mode``), returns control to the user for consent, and
either starts an auto-run or resolves the call as declined. The :meth:`run` implementation here is a
signal no-op — it exists only to keep the ``libs/core`` tool surface complete and standalone (the
external backend exposes this tool via its ``kiln-ai`` dependency, and the library must be usable on
its own). It must NOT be added to the app server's ``FUNCTION_NAME_TO_TOOL_ID`` — interception by
name happens first and the tool is never meant to run.
"""

import json
from typing import Any

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult

# The function name the model calls and the app server intercepts by. Kept as a
# module constant so the interception layer can import it instead of hardcoding
# the string.
ENABLE_AUTO_MODE_TOOL_NAME = "enable_auto_mode"


class EnableAutoModeTool(KilnTool):
    """Tool the model calls to suggest enabling auto mode (autonomous tool execution)."""

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.ENABLE_AUTO_MODE,
            name=ENABLE_AUTO_MODE_TOOL_NAME,
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Suggest enabling auto mode so you can carry out a multi-step plan autonomously without pausing for approval on each tool call.

Call this when the user has signed off on a concrete, multi-step plan that you can execute with tools (e.g. running an eval, building a RAG index, or another tool/job-driven workflow). Call it ALONE — do not request any other tool calls in the same turn.

The user may accept or decline. On decline you will receive {"status": "declined"} and should continue interactively. On accept you will receive {"status": "enabled"} and should proceed to carry out the plan."""

    @staticmethod
    def _build_parameters_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional short, user-facing explanation of what you intend to do autonomously and why auto mode helps.",
                },
            },
        }

    async def run(  # type: ignore[override]
        self,
        context: ToolCallContext | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        # Signal no-op. In chat this is intercepted by name and never executed;
        # this body exists only so the libs/core tool surface is complete and the
        # library is usable standalone. The "enabled" status mirrors what the app
        # server's auto-run seed resolves an accepted enable call to.
        return ToolCallResult(
            output=json.dumps({"status": "enabled"}, ensure_ascii=False)
        )
