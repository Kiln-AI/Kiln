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
# Emitted by the OLD interactive loop when the model calls enable_auto_mode
# (survives until phase 4 ports the interactive path; the runtime interceptor
# emits the same event via stream_session's formatter). The rest of the old
# auto lifecycle vocabulary (auto-mode-on/off/idle/state) died in phase 3,
# replaced by the unified conversation-state event (runtime/sse.py).
SSE_TYPE_AUTO_MODE_CONSENT_REQUIRED = "auto-mode-consent-required"
# Emitted between retry attempts after a transient upstream failure (by BOTH the
# interactive chat stream and the runtime engine — they share the retry helper),
# so the UI can show "retrying N/M…" instead of a hard error. Carries
# {attempt, max_attempts, status_code?, run_id?}.
SSE_TYPE_CHAT_RETRY = "kiln-chat-retry"

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
