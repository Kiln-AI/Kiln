"""Disable Auto Mode Tool — a legacy signal the model can no longer use to end auto mode.

Auto mode turns off only by user action (the Stop button): the app server **refuses** a
``disable_auto_mode`` call with ``{"status": "not_available", ...}`` and never clears the flag. The
tool is no longer offered upstream; it exists so pre-upgrade conversations that resume with a
pending ``disable_auto_mode`` call (or an old server during rollout) still resolve the call cleanly
— with the same refusal — instead of erroring on an unknown tool. The :meth:`run` implementation
here is a signal no-op that mirrors that refusal — it exists only to keep the ``libs/core`` tool
surface complete and standalone (the external backend exposes this tool via its ``kiln-ai``
dependency, and the library must be usable on its own). It must NOT be added to the app server's
``FUNCTION_NAME_TO_TOOL_ID`` — interception by name happens first and the tool is never meant to run.

Counterpart to :mod:`enable_auto_mode_tool` (which remains a live, consent-gated signal).
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
    """Legacy tool whose calls are refused: auto mode is turned off only by the user."""

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.DISABLE_AUTO_MODE,
            name=DISABLE_AUTO_MODE_TOOL_NAME,
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Not available: auto mode can only be turned off by the user, via the Stop button.

Do not call this tool. If the user asks you to stop auto mode, direct them to the Stop button instead. A call to this tool is refused with {"status": "not_available"} and auto mode stays on."""

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
        # library is usable standalone. The refusal mirrors what the app server
        # resolves an intercepted (stale) disable call to: auto mode turns off
        # only by user action, never by the model.
        return ToolCallResult(
            output=json.dumps(
                {
                    "status": "not_available",
                    "message": "Auto mode can only be turned off by the user (Stop button).",
                },
                ensure_ascii=False,
            )
        )
