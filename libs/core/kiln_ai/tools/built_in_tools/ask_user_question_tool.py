"""Ask User Question Tool — a signal the model emits to ask the user a question with suggestions.

This tool is **client-visible** and **never executed in chat**: when the model calls it, the app
server intercepts it by name (``ask_user_question``), surfaces the question (and any suggested
answers) to the user, and resolves the call with the user's choice. The :meth:`run` implementation
here is a signal no-op — it exists only to keep the ``libs/core`` tool surface complete and
standalone (the external backend exposes this tool via its ``kiln-ai`` dependency, and the library
must be usable on its own). It must NOT be added to the app server's ``FUNCTION_NAME_TO_TOOL_ID`` —
interception by name happens first and the tool is never meant to run.

Mirrors the pattern in :mod:`enable_auto_mode_tool` / :mod:`disable_auto_mode_tool`.
"""

import json
from typing import Any

from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from kiln_ai.tools.base_tool import KilnTool, ToolCallContext, ToolCallResult

# The function name the model calls and the app server intercepts by. Kept as a
# module constant so the interception layer can import it instead of hardcoding
# the string.
ASK_USER_QUESTION_TOOL_NAME = "ask_user_question"


class AskUserQuestionTool(KilnTool):
    """Tool the model calls to ask the user a question with up to 5 suggested answers."""

    def __init__(self):
        super().__init__(
            tool_id=KilnBuiltInToolId.ASK_USER_QUESTION,
            name=ASK_USER_QUESTION_TOOL_NAME,
            description=self._build_description(),
            parameters_schema=self._build_parameters_schema(),
        )

    @staticmethod
    def _build_description() -> str:
        return """Ask the user a question to gather a decision or clarification you need to proceed.

Provide up to 5 concrete suggested answers. Each suggestion is a short main line (the answer the user can pick in one click) plus a 1-2 line explanation of what choosing it means. Make the suggestions specific and actionable, not vague.

The user will either pick one of your suggestions or choose to chat to refine. Call this tool ALONE — do not request any other tool calls in the same turn. After it resolves you will receive either the chosen answer text or a signal that the user wants to chat, at which point you should ask an open follow-up question to refine."""

    @staticmethod
    def _build_parameters_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user. Be clear and specific.",
                },
                "suggested_answers": {
                    "type": "array",
                    "maxItems": 5,
                    "description": "Up to 5 concrete suggested answers the user can pick from in one click.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The suggested answer — a short main line the user can pick.",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "A 1-2 line explanation of what choosing this answer means.",
                            },
                        },
                        "required": ["answer"],
                    },
                },
            },
            "required": ["question"],
        }

    async def run(  # type: ignore[override]
        self,
        context: ToolCallContext | None = None,
        **kwargs: Any,
    ) -> ToolCallResult:
        # Signal no-op. In chat this is intercepted by name and never executed;
        # this body exists only so the libs/core tool surface is complete and the
        # library is usable standalone. The "asked" status reflects that the
        # question was posed to the user (the app server resolves it with the
        # user's actual answer when intercepted).
        return ToolCallResult(
            output=json.dumps({"status": "asked"}, ensure_ascii=False)
        )
