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
