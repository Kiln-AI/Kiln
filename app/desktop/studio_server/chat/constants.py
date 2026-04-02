import json

import httpx
from kiln_ai.adapters.model_adapters.stream_events import AiSdkStreamEvent
from kiln_ai.datamodel.tool_id import KilnBuiltInToolId
from pydantic import TypeAdapter

_CHAT_TIMEOUT = httpx.Timeout(timeout=300.0, connect=30.0)
_MAX_TOOL_ROUNDS = 25
_TOOL_APPROVAL_TIMEOUT_SEC = 600.0

SSE_TYPE_TOOL_APPROVAL_REQUIRED = "tool-approval-required"

_DENIED_TOOL_OUTPUT = json.dumps({"error": "The user did not accept the toolcall"})
_FUNCTION_NAME_TO_TOOL_ID: dict[str, str] = {
    "call_kiln_api": KilnBuiltInToolId.CALL_KILN_API,
}

KILN_SSE_CHAT_TRACE = "kiln_chat_trace"

_ai_sdk_stream_event_adapter = TypeAdapter(AiSdkStreamEvent)

_EXECUTOR_SERVER = "server"
