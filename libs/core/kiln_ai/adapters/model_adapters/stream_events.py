from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal, Union

from litellm.types.utils import ModelResponseStream
from pydantic import BaseModel, ConfigDict, Discriminator


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


class UsageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promptTokens: int
    completionTokens: int
    totalTokens: int | None = None


class FinishMessageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finishReason: str | None = None
    usage: UsageInfo | None = None


class StartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start"] = "start"
    messageId: str


class FinishEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["finish"] = "finish"
    messageMetadata: FinishMessageMetadata | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class StartStepEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["start-step"] = "start-step"


class FinishStepEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["finish-step"] = "finish-step"


class TextStartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text-start"] = "text-start"
    id: str


class TextEndEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text-end"] = "text-end"
    id: str


class TextDeltaEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text-delta"] = "text-delta"
    id: str
    delta: str


class ReasoningStartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reasoning-start"] = "reasoning-start"
    id: str


class ReasoningEndEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reasoning-end"] = "reasoning-end"
    id: str


class ReasoningDeltaEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reasoning-delta"] = "reasoning-delta"
    id: str
    delta: str


class ToolInputStartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool-input-start"] = "tool-input-start"
    toolCallId: str
    toolName: str


class ToolInputDeltaEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool-input-delta"] = "tool-input-delta"
    toolCallId: str
    inputTextDelta: str


class ToolInputAvailableEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool-input-available"] = "tool-input-available"
    toolCallId: str
    toolName: str
    input: dict[str, Any]


class ToolOutputAvailableEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool-output-available"] = "tool-output-available"
    toolCallId: str
    output: str | None = None


class ToolOutputErrorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool-output-error"] = "tool-output-error"
    toolCallId: str
    errorText: str


AiSdkStreamEvent = Annotated[
    Union[
        StartEvent,
        FinishEvent,
        StartStepEvent,
        FinishStepEvent,
        TextStartEvent,
        TextEndEvent,
        TextDeltaEvent,
        ReasoningStartEvent,
        ReasoningEndEvent,
        ReasoningDeltaEvent,
        ToolInputStartEvent,
        ToolInputDeltaEvent,
        ToolInputAvailableEvent,
        ToolOutputAvailableEvent,
        ToolOutputErrorEvent,
    ],
    Discriminator("type"),
]


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
            if reasoning_content:
                if not self._reasoning_started:
                    self._reasoning_block_count += 1
                    self._reasoning_id = f"reasoning-{uuid.uuid4().hex[:12]}"
                    events.append(ReasoningStartEvent(id=self._reasoning_id))
                    self._reasoning_started = True
                events.append(
                    ReasoningDeltaEvent(id=self._reasoning_id, delta=reasoning_content)
                )

            if delta.content:
                if self._reasoning_started:
                    events.append(ReasoningEndEvent(id=self._reasoning_id))
                    self._reasoning_started = False

                if not self._text_started:
                    self._text_id = f"text-{uuid.uuid4().hex[:12]}"
                    events.append(TextStartEvent(id=self._text_id))
                    self._text_started = True
                events.append(TextDeltaEvent(id=self._text_id, delta=delta.content))

            if delta.tool_calls:
                if self._reasoning_started:
                    events.append(ReasoningEndEvent(id=self._reasoning_id))
                    self._reasoning_started = False

                if self._text_started:
                    events.append(TextEndEvent(id=self._text_id))
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
                            ToolInputStartEvent(
                                toolCallId=tc_state["id"],
                                toolName=tc_state["name"],
                            )
                        )
                        tc_state["started"] = True

                    if func and func.arguments and tc_state["id"]:
                        events.append(
                            ToolInputDeltaEvent(
                                toolCallId=tc_state["id"],
                                inputTextDelta=func.arguments,
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
                ToolInputAvailableEvent(
                    toolCallId=event.tool_call_id,
                    toolName=event.tool_name,
                    input=event.arguments or {},
                )
            )
        elif event.event_type == ToolCallEventType.OUTPUT_AVAILABLE:
            events.append(
                ToolOutputAvailableEvent(
                    toolCallId=event.tool_call_id,
                    output=event.result,
                )
            )
        elif event.event_type == ToolCallEventType.OUTPUT_ERROR:
            events.append(
                ToolOutputErrorEvent(
                    toolCallId=event.tool_call_id,
                    errorText=event.error or "Unknown error",
                )
            )

        return events

    def close_open_blocks(self) -> list[AiSdkStreamEvent]:
        """Close any open text/reasoning blocks. Call before FINISH_STEP."""
        events: list[AiSdkStreamEvent] = []

        if self._reasoning_started:
            events.append(ReasoningEndEvent(id=self._reasoning_id))
            self._reasoning_started = False

        if self._text_started:
            events.append(TextEndEvent(id=self._text_id))
            self._text_started = False

        return events

    def finalize(self) -> list[AiSdkStreamEvent]:
        """Emit the terminal FINISH event with usage/finish metadata. Call after FINISH_STEP."""
        events: list[AiSdkStreamEvent] = []

        finish_reason: str | None = None
        if self._finish_reason is not None:
            finish_reason = self._finish_reason.replace("_", "-")

        usage_info: UsageInfo | None = None
        if self._usage_data is not None:
            total = getattr(self._usage_data, "total_tokens", None)
            usage_info = UsageInfo(
                promptTokens=self._usage_data.prompt_tokens,
                completionTokens=self._usage_data.completion_tokens,
                totalTokens=total,
            )

        if finish_reason is not None or usage_info is not None:
            meta = FinishMessageMetadata(
                finishReason=finish_reason,
                usage=usage_info,
            )
            events.append(FinishEvent(messageMetadata=meta))
        else:
            events.append(FinishEvent())

        return events

    def reset_for_next_step(self) -> None:
        """Reset per-step state between LLM calls in a multi-step flow."""
        self._tool_calls_state = {}
        self._finish_reason = None
        self._text_started = False
        self._reasoning_started = False
        self._text_id = f"text-{uuid.uuid4().hex[:12]}"
        self._reasoning_id = f"reasoning-{uuid.uuid4().hex[:12]}"
