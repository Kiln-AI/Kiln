from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from litellm.types.utils import ModelResponseStream


class AiSdkEventType(str, Enum):
    START = "start"
    FINISH = "finish"
    ERROR = "error"
    ABORT = "abort"

    TEXT_START = "text-start"
    TEXT_DELTA = "text-delta"
    TEXT_END = "text-end"

    REASONING_START = "reasoning-start"
    REASONING_DELTA = "reasoning-delta"
    REASONING_END = "reasoning-end"

    TOOL_INPUT_START = "tool-input-start"
    TOOL_INPUT_DELTA = "tool-input-delta"
    TOOL_INPUT_AVAILABLE = "tool-input-available"
    TOOL_INPUT_ERROR = "tool-input-error"

    TOOL_OUTPUT_AVAILABLE = "tool-output-available"
    TOOL_OUTPUT_ERROR = "tool-output-error"

    START_STEP = "start-step"
    FINISH_STEP = "finish-step"

    METADATA = "metadata"
    SOURCE_URL = "source-url"
    SOURCE_DOCUMENT = "source-document"
    FILE = "file"


@dataclass
class AiSdkStreamEvent:
    type: AiSdkEventType
    payload: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            **self.payload,
        }


class ToolCallEventType(str, Enum):
    INPUT_AVAILABLE = "input_available"
    OUTPUT_AVAILABLE = "output_available"
    OUTPUT_ERROR = "output_error"


@dataclass
class ToolCallEvent:
    event_type: ToolCallEventType
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] | None = None
    result: str | None = None
    error: str | None = None


AdapterStreamEvent = ModelResponseStream | ToolCallEvent


class AiSdkStreamConverter:
    """Stateful converter from OpenAI streaming chunks to AI SDK events."""

    def __init__(self) -> None:
        self._text_started = False
        self._text_id = f"text-{uuid.uuid4().hex[:12]}"
        self._reasoning_started = False
        self._reasoning_id = f"reasoning-{uuid.uuid4().hex[:12]}"
        self._reasoning_block_count = 0
        self._tool_calls_state: dict[int, dict[str, Any]] = {}
        self._finish_reason: str | None = None
        self._usage_data: Any = None

    def convert_chunk(self, chunk: ModelResponseStream) -> list[AiSdkStreamEvent]:
        events: list[AiSdkStreamEvent] = []

        for choice in chunk.choices:
            if choice.finish_reason is not None:
                self._finish_reason = choice.finish_reason

            delta = choice.delta
            if delta is None:
                continue

            reasoning_content = getattr(delta, "reasoning_content", None)
            if reasoning_content is not None:
                if not self._reasoning_started:
                    self._reasoning_block_count += 1
                    self._reasoning_id = f"reasoning-{uuid.uuid4().hex[:12]}"
                    events.append(
                        AiSdkStreamEvent(
                            AiSdkEventType.REASONING_START,
                            {"id": self._reasoning_id},
                        )
                    )
                    self._reasoning_started = True
                events.append(
                    AiSdkStreamEvent(
                        AiSdkEventType.REASONING_DELTA,
                        {"id": self._reasoning_id, "delta": reasoning_content},
                    )
                )

            if delta.content:
                if self._reasoning_started:
                    events.append(
                        AiSdkStreamEvent(
                            AiSdkEventType.REASONING_END,
                            {"id": self._reasoning_id},
                        )
                    )
                    self._reasoning_started = False

                if not self._text_started:
                    self._text_id = f"text-{uuid.uuid4().hex[:12]}"
                    events.append(
                        AiSdkStreamEvent(
                            AiSdkEventType.TEXT_START,
                            {"id": self._text_id},
                        )
                    )
                    self._text_started = True
                events.append(
                    AiSdkStreamEvent(
                        AiSdkEventType.TEXT_DELTA,
                        {"id": self._text_id, "delta": delta.content},
                    )
                )

            if delta.tool_calls:
                if self._reasoning_started:
                    events.append(
                        AiSdkStreamEvent(
                            AiSdkEventType.REASONING_END,
                            {"id": self._reasoning_id},
                        )
                    )
                    self._reasoning_started = False

                if self._text_started:
                    events.append(
                        AiSdkStreamEvent(
                            AiSdkEventType.TEXT_END,
                            {"id": self._text_id},
                        )
                    )
                    self._text_started = False

                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    tc_state = self._tool_calls_state.setdefault(
                        idx,
                        {
                            "id": None,
                            "name": None,
                            "arguments": "",
                            "started": False,
                        },
                    )

                    if tc_delta.id is not None:
                        tc_state["id"] = tc_delta.id

                    func = getattr(tc_delta, "function", None)
                    if func is not None:
                        if func.name is not None:
                            tc_state["name"] = func.name
                        if func.arguments:
                            tc_state["arguments"] += func.arguments

                    if tc_state["id"] and tc_state["name"] and not tc_state["started"]:
                        events.append(
                            AiSdkStreamEvent(
                                AiSdkEventType.TOOL_INPUT_START,
                                {
                                    "toolCallId": tc_state["id"],
                                    "toolName": tc_state["name"],
                                },
                            )
                        )
                        tc_state["started"] = True

                    if func and func.arguments and tc_state["id"]:
                        events.append(
                            AiSdkStreamEvent(
                                AiSdkEventType.TOOL_INPUT_DELTA,
                                {
                                    "toolCallId": tc_state["id"],
                                    "inputTextDelta": func.arguments,
                                },
                            )
                        )

        if not chunk.choices:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                self._usage_data = usage

        return events

    def convert_tool_event(self, event: ToolCallEvent) -> list[AiSdkStreamEvent]:
        events: list[AiSdkStreamEvent] = []

        if event.event_type == ToolCallEventType.INPUT_AVAILABLE:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.TOOL_INPUT_AVAILABLE,
                    {
                        "toolCallId": event.tool_call_id,
                        "toolName": event.tool_name,
                        "input": event.arguments or {},
                    },
                )
            )
        elif event.event_type == ToolCallEventType.OUTPUT_AVAILABLE:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.TOOL_OUTPUT_AVAILABLE,
                    {
                        "toolCallId": event.tool_call_id,
                        "output": event.result,
                    },
                )
            )
        elif event.event_type == ToolCallEventType.OUTPUT_ERROR:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.TOOL_OUTPUT_ERROR,
                    {
                        "toolCallId": event.tool_call_id,
                        "errorText": event.error or "Unknown error",
                    },
                )
            )

        return events

    def finalize(self) -> list[AiSdkStreamEvent]:
        events: list[AiSdkStreamEvent] = []

        if self._reasoning_started:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.REASONING_END,
                    {"id": self._reasoning_id},
                )
            )
            self._reasoning_started = False

        if self._text_started:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.TEXT_END,
                    {"id": self._text_id},
                )
            )
            self._text_started = False

        finish_payload: dict[str, Any] = {}
        if self._finish_reason is not None:
            finish_payload["finishReason"] = self._finish_reason.replace("_", "-")

        if self._usage_data is not None:
            usage_payload: dict[str, Any] = {
                "promptTokens": self._usage_data.prompt_tokens,
                "completionTokens": self._usage_data.completion_tokens,
            }
            total = getattr(self._usage_data, "total_tokens", None)
            if total is not None:
                usage_payload["totalTokens"] = total
            finish_payload["usage"] = usage_payload

        if finish_payload:
            events.append(
                AiSdkStreamEvent(
                    AiSdkEventType.FINISH,
                    {"messageMetadata": finish_payload},
                )
            )
        else:
            events.append(AiSdkStreamEvent(AiSdkEventType.FINISH))

        return events

    def reset_for_next_step(self) -> None:
        """Reset per-step state between LLM calls in a multi-step flow."""
        self._tool_calls_state = {}
        self._finish_reason = None
