import json
import logging
from dataclasses import dataclass, field
from typing import Any

from kiln_ai.adapters.model_adapters.stream_events import (
    AiSdkStreamEvent,
    FinishEvent,
    TextDeltaEvent,
    ToolInputAvailableEvent,
)
from pydantic import ValidationError

from app.desktop.studio_server.chat.constants import (
    KILN_SSE_CHAT_TRACE,
    _ai_sdk_stream_event_adapter,
)

logger = logging.getLogger(__name__)


def _try_parse_ai_sdk_event(data: dict[str, Any]) -> AiSdkStreamEvent | None:
    try:
        return _ai_sdk_stream_event_adapter.validate_python(data)
    except ValidationError:
        return None


@dataclass
class ParseResult:
    lines_to_forward: list[bytes] = field(default_factory=list)
    finish_tool_calls: bool = False
    tool_input_events: list[ToolInputAvailableEvent] = field(default_factory=list)
    text_delta: str = ""
    chat_trace_id: str | None = None


class EventParser:
    """Stateful SSE parser that accumulates a line buffer across chunks."""

    def __init__(self) -> None:
        self._line_buffer = bytearray()

    def parse(self, raw: bytes) -> ParseResult:
        self._line_buffer.extend(raw)

        parts = bytes(self._line_buffer).split(b"\n")
        self._line_buffer.clear()
        self._line_buffer.extend(parts[-1])
        complete_lines = parts[:-1]

        result = ParseResult(lines_to_forward=list(complete_lines))

        i = 0
        while i < len(result.lines_to_forward):
            line = result.lines_to_forward[i]
            if line.startswith(b"data: "):
                payload = line[6:].strip()
                if payload and payload != b"[DONE]":
                    self._process_payload(payload, result)
            i += 1

        return result

    def _process_payload(self, payload: bytes, result: ParseResult) -> None:
        try:
            event = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.debug("Failed to parse SSE payload as JSON: %s", payload[:120])
            return

        if not isinstance(event, dict):
            return

        event_type = event.get("type")

        if event_type == KILN_SSE_CHAT_TRACE:
            tid = event.get("trace_id")
            if isinstance(tid, str) and tid:
                result.chat_trace_id = tid
            return

        parsed = _try_parse_ai_sdk_event(event)
        if isinstance(parsed, FinishEvent):
            meta = parsed.messageMetadata
            if meta is not None and meta.finishReason == "tool-calls":
                result.finish_tool_calls = True
        elif isinstance(parsed, TextDeltaEvent):
            result.text_delta += parsed.delta
        elif isinstance(parsed, ToolInputAvailableEvent):
            result.tool_input_events.append(parsed)
