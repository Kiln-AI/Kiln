from __future__ import annotations

import inspect
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from litellm.types.utils import ModelResponseStream

AISDK_DONE = "[DONE]"


def _ensure_async(
    fn: Callable[[Any], Awaitable[None]] | Callable[[Any], None],
) -> Callable[[Any], Awaitable[None]]:
    async def wrapper(x: Any) -> None:
        result = fn(x)
        if inspect.iscoroutine(result):
            await result

    return wrapper


class LiteLLMTransportAdapter(ABC):
    @abstractmethod
    async def on_chunk(self, chunk: ModelResponseStream) -> None:
        pass

    async def on_step_start(self) -> None:
        pass

    async def on_step_finish(self) -> None:
        pass


class OpenAIStreamTransport(LiteLLMTransportAdapter):
    def __init__(
        self,
        on_part: Callable[[ModelResponseStream], Awaitable[None]]
        | Callable[[ModelResponseStream], None]
        | None = None,
    ) -> None:
        self._on_part = _ensure_async(on_part) if on_part else None
        self.parts: list[ModelResponseStream] = []

    async def on_chunk(self, chunk: ModelResponseStream) -> None:
        self.parts.append(chunk)
        if self._on_part is not None:
            await self._on_part(chunk)


class AISDKStreamTransport(LiteLLMTransportAdapter):
    def __init__(
        self,
        on_part: Callable[[dict[str, Any] | str], Awaitable[None]]
        | Callable[[dict[str, Any] | str], None]
        | None = None,
    ) -> None:
        self._on_part = _ensure_async(on_part) if on_part else None
        self.parts: list[dict[str, Any] | str] = []
        self._message_id: str | None = None
        self._text_block_id: str | None = None
        self._reasoning_block_id: str | None = None
        self._tool_call_accumulator: dict[int, dict[str, Any]] = {}
        self._tool_call_start_emitted: set[int] = set()

    async def _emit(self, part: dict[str, Any] | str) -> None:
        self.parts.append(part)
        if self._on_part is not None:
            await self._on_part(part)

    async def _finish_text_block(self) -> None:
        if self._text_block_id is not None:
            await self._emit({"type": "text-end", "id": self._text_block_id})
            self._text_block_id = None

    async def _finish_reasoning_block(self) -> None:
        if self._reasoning_block_id is not None:
            await self._emit({"type": "reasoning-end", "id": self._reasoning_block_id})
            self._reasoning_block_id = None

    async def on_step_start(self) -> None:
        if self._message_id is None:
            self._message_id = uuid.uuid4().hex
            await self._emit({"type": "start", "messageId": self._message_id})
        await self._emit({"type": "start-step"})

    async def on_step_finish(self) -> None:
        await self._emit({"type": "finish-step"})

    async def on_chunk(self, chunk: ModelResponseStream) -> None:
        if not chunk.choices:
            return
        choice = chunk.choices[0]
        if choice.finish_reason is not None:
            await self._finish_text_block()
            await self._finish_reasoning_block()
            await self._emit({"type": "finish"})
            await self._emit(AISDK_DONE)
            return
        delta = choice.delta
        if delta is None:
            return
        if delta.tool_calls is not None:
            await self._finish_text_block()
            await self._finish_reasoning_block()
            await self._process_tool_calls(delta.tool_calls)
        elif getattr(delta, "reasoning_content", None) is not None:
            text = getattr(delta, "reasoning_content", None)
            if text is not None:
                await self._finish_text_block()
                await self._process_reasoning_delta(text)
        elif delta.content is not None:
            await self._finish_reasoning_block()
            await self._process_text_delta(delta.content)

    async def _process_text_delta(self, delta: str) -> None:
        if self._text_block_id is None:
            self._text_block_id = uuid.uuid4().hex
            await self._emit({"type": "text-start", "id": self._text_block_id})
        await self._emit(
            {"type": "text-delta", "id": self._text_block_id, "delta": delta}
        )

    async def _process_reasoning_delta(self, delta: str) -> None:
        if self._reasoning_block_id is None:
            self._reasoning_block_id = uuid.uuid4().hex
            await self._emit(
                {"type": "reasoning-start", "id": self._reasoning_block_id}
            )
        await self._emit(
            {
                "type": "reasoning-delta",
                "id": self._reasoning_block_id,
                "delta": delta,
            }
        )

    async def _process_tool_calls(self, tool_calls: list[Any]) -> None:
        for tc in tool_calls:
            index = getattr(tc, "index", None)
            if index is None:
                continue
            if index not in self._tool_call_accumulator:
                self._tool_call_accumulator[index] = {
                    "id": None,
                    "name": None,
                    "arguments": "",
                }
            acc = self._tool_call_accumulator[index]
            if getattr(tc, "id", None) is not None:
                acc["id"] = tc.id
            func = getattr(tc, "function", None)
            if func is not None:
                if getattr(func, "name", None) is not None:
                    acc["name"] = func.name
                if getattr(func, "arguments", None) is not None:
                    acc["arguments"] += func.arguments
            if index not in self._tool_call_start_emitted:
                self._tool_call_start_emitted.add(index)
                tool_call_id = acc["id"] or f"call_{index}"
                tool_name = acc["name"] or ""
                await self._emit(
                    {
                        "type": "tool-input-start",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                    }
                )
            args_delta = getattr(func, "arguments", None) if func else None
            if args_delta is not None:
                await self._emit(
                    {
                        "type": "tool-input-delta",
                        "toolCallId": acc["id"] or f"call_{index}",
                        "inputTextDelta": args_delta,
                    }
                )
            try:
                parsed = json.loads(acc["arguments"])
                tool_call_id = acc["id"] or f"call_{index}"
                tool_name = acc["name"] or ""
                await self._emit(
                    {
                        "type": "tool-input-available",
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "input": parsed,
                    }
                )
                del self._tool_call_accumulator[index]
                self._tool_call_start_emitted.discard(index)
            except json.JSONDecodeError:
                pass
