import json

import httpx
from kiln_ai.adapters.model_adapters.stream_events import AiSdkStreamEvent
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from pydantic import TypeAdapter

CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
MAX_TOOL_ROUNDS = 1000

SSE_TYPE_TOOL_CALLS_PENDING = "tool-calls-pending"
SSE_TYPE_TOOL_EXEC_START = "kiln-tool-execution-start"
SSE_TYPE_TOOL_EXEC_END = "kiln-tool-execution-end"
SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED = "auto-mode-consent-required"
# Revision R1: a burst settled but the conversation auto-mode flag stays on. This
# is distinct from auto-mode-off (which is published only on explicit disable).
SSE_TYPE_AUTO_MODE_IDLE = "auto-mode-idle"
# Emitted between retry attempts after a transient upstream failure (by BOTH the
# interactive chat stream and the auto runner — they share the retry helper), so
# the UI can show "retrying N/M…" instead of a hard error. Carries
# {attempt, max_attempts, status_code?, run_id?}.
SSE_TYPE_CHAT_RETRY = "kiln-chat-retry"
# Phase 9: an on-subscribe snapshot of the run's CURRENT liveness so a
# re-attaching client immediately reflects working-vs-idle (instead of looking
# idle until the next event happens to arrive). Carries {flag_on, working}.
SSE_TYPE_AUTO_MODE_STATE = "auto-mode-state"

DENIED_TOOL_OUTPUT = json.dumps(
    {"error": "The user did not accept the toolcall"}, ensure_ascii=False
)
# Returned instead of dispatching call_kiln_api when the conversation's spend
# budget is exhausted. Reads as a normal tool error so the model relays it and
# stops triggering operations; only the user can extend the budget (the
# budget-set endpoint is DENY_AGENT).
BUDGET_EXCEEDED_TOOL_OUTPUT = json.dumps(
    {
        "error": "The conversation's spend budget is exhausted. This operation was "
        "not run. Do not retry. Tell the user they can extend the budget from the "
        "budget control in the chat UI if they want you to continue."
    },
    ensure_ascii=False,
)
CALL_KILN_API_TOOL_NAME = "call_kiln_api"
FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    CALL_KILN_API_TOOL_NAME: KilnBuiltInToolId.CALL_KILN_API,
    "add": KilnBuiltInToolId.ADD_NUMBERS,
    "subtract": KilnBuiltInToolId.SUBTRACT_NUMBERS,
    "multiply": KilnBuiltInToolId.MULTIPLY_NUMBERS,
    "divide": KilnBuiltInToolId.DIVIDE_NUMBERS,
}

KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)

TOOL_EXECUTOR_SERVER = "server"
