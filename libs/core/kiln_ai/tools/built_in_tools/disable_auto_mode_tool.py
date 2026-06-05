"""Disable Auto Mode Tool — a signal the model emits when the user asks to stop auto mode.

This tool is **client-visible** and **never executed in chat**: when the model calls it, the app
server intercepts it by name (``disable_auto_mode``), clears the conversation's auto-mode flag, ends
the run, and resolves the call so the backend continues interactively. The :meth:`run`
implementation here is a signal no-op — it exists only to keep the ``libs/core`` tool surface
complete and standalone (the external backend exposes this tool via its ``kiln-ai`` dependency, and
the library must be usable on its own). It must NOT be added to the app server's
``FUNCTION_NAME_TO_TOOL_ID`` — interception by name happens first and the tool is never meant to run.

Symmetric counterpart to :mod:`enable_auto_mode_tool`.
"""

import json
from typing import Any

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult

# The function name the model calls and the app server intercepts by. Kept as a
# module constant so the interception layer can import it instead of hardcoding
# the string.
DISABLE_AUTO_MODE_TOOL_NAME = "disable_auto_mode"


class DisableAutoModeTool(KilnTool):
    """Tool the model calls to disable auto mode when the user asks to stop it."""

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.DISABLE_AUTO_MODE,
            name=DISABLE_AUTO_MODE_TOOL_NAME,
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Disable auto mode so you stop running autonomously and return to asking the user for approval on each step.

Call this when the user signals they want auto mode to stop (e.g. "stop auto mode", "stop doing this automatically", "ask me before each step again"). Call it ALONE — do not request any other tool calls in the same turn.

After calling it you will receive {"status": "disabled"} and should continue interactively."""

    @staticmethod
    def _build_parameters_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional short, user-facing explanation of why auto mode is being turned off.",
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
        # library is usable standalone. The "disabled" status mirrors what the app
        # server resolves an intercepted disable call to.
        return ToolCallResult(
            output=json.dumps({"status": "disabled"}, ensure_ascii=False)
        )
