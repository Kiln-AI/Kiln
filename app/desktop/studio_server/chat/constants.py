import json

import httpx
from kiln_ai.adapters.model_adapters.stream_events import AiSdkStreamEvent
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from pydantic import TypeAdapter

CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
MAX_TOOL_ROUNDS = 100

SSE_TYPE_TOOL_CALLS_PENDING = "tool-calls-pending"
SSE_TYPE_TOOL_EXEC_START = "kiln-tool-execution-start"
SSE_TYPE_TOOL_EXEC_END = "kiln-tool-execution-end"
SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED = "auto-mode-consent-required"
# The model called ask_user_question: the app server intercepts it (never runs
# it), surfaces this event with the question + suggested answers, and pauses
# until the user answers via /api/chat/ask/answer.
SSE_TYPE_ASK_USER_QUESTION = "ask-user-question"
# Revision R1: a burst settled but the conversation auto-mode flag stays on. This
# is distinct from auto-mode-off (which is published only on explicit disable).
SSE_TYPE_AUTO_MODE_IDLE = "auto-mode-idle"
# Phase 9: an on-subscribe snapshot of the run's CURRENT liveness so a
# re-attaching client immediately reflects working-vs-idle (instead of looking
# idle until the next event happens to arrive). Carries {flag_on, working}.
SSE_TYPE_AUTO_MODE_STATE = "auto-mode-state"

DENIED_TOOL_OUTPUT = json.dumps(
    {"error": "The user did not accept the toolcall"}, ensure_ascii=False
)
FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API,
    "add": KilnBuiltInToolId.ADD_NUMBERS,
    "subtract": KilnBuiltInToolId.SUBTRACT_NUMBERS,
    "multiply": KilnBuiltInToolId.MULTIPLY_NUMBERS,
    "divide": KilnBuiltInToolId.DIVIDE_NUMBERS,
}

KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)

TOOL_EXECUTOR_SERVER = "server"
