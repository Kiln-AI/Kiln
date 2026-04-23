from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator

from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    Choices,
    ModelResponse,
)

from kiln_ai.adapters.chat import ChatCompletionMessageIncludingLiteLLM
from kiln_ai.adapters.chat.chat_formatter import ChatFormatter, ToolResponseMessage
from kiln_ai.adapters.litellm_utils.litellm_streaming import StreamingCompletion
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.stream_events import (
    AdapterStreamEvent,
    ToolCallEvent,
    ToolCallEventType,
)
from kiln_ai.adapters.run_output import RunOutput
from kiln_ai.datamodel import Usage

if TYPE_CHECKING:
    from kiln_ai.adapters.model_adapters.litellm_adapter import LiteLlmAdapter

MAX_CALLS_PER_TURN = 10
MAX_TOOL_CALLS_PER_TURN = 30

logger = logging.getLogger(__name__)


@dataclass
class AdapterStreamResult:
    run_output: RunOutput
    usage: Usage


class AdapterStream:
    """
    Orchestrates a full task execution as an async iterator,
    composing StreamingCompletion instances across chat turns and tool-call rounds.

    Yields ``ModelResponseStream`` chunks from each LLM call and
    ``ToolCallEvent`` instances between tool-call rounds.

    After iteration completes the ``result`` property provides the
    ``AdapterStreamResult`` with the final ``RunOutput`` and ``Usage``.
    """

    def __init__(
        self,
        adapter: LiteLlmAdapter,
        provider: KilnModelProvider,
        chat_formatter: ChatFormatter,
        initial_messages: list[ChatCompletionMessageIncludingLiteLLM],
        top_logprobs: int | None,
    ) -> None:
        self._adapter = adapter
        self._provider = provider
        self._chat_formatter = chat_formatter
        self._messages = initial_messages
        self._top_logprobs = top_logprobs
        self._result: AdapterStreamResult | None = None
        self._iterated = False

    @property
    def result(self) -> AdapterStreamResult:
        if not self._iterated:
            raise RuntimeError(
                "AdapterStream has not been iterated yet. "
                "Use 'async for event in stream:' before accessing .result"
            )
        if self._result is None:
            raise RuntimeError("AdapterStream completed without producing a result")
        return self._result

    async def __aiter__(self) -> AsyncIterator[AdapterStreamEvent]:
        self._result = None
        self._iterated = False

        usage = Usage()
        prior_output: str | None = None
        final_choice: Choices | None = None
        turns = 0

        while True:
            turns += 1
            if turns > MAX_CALLS_PER_TURN:
                raise RuntimeError(
                    f"Too many turns ({turns}). Stopping iteration to avoid using too many tokens."
                )

            turn = self._chat_formatter.next_turn(prior_output)
            if turn is None:
                break

            for message in turn.messages:
                if message.content is None:
                    raise ValueError("Empty message content isn't allowed")
                msg_dict: dict = {"role": message.role, "content": message.content}
                if isinstance(message, ToolResponseMessage):
                    msg_dict["tool_call_id"] = message.tool_call_id
                self._messages.append(msg_dict)  # type: ignore[arg-type]

            skip_response_format = not turn.final_call
            turn_top_logprobs = self._top_logprobs if turn.final_call else None

            interrupted = False
            async for event in self._stream_model_turn(
                skip_response_format, turn_top_logprobs
            ):
                if isinstance(event, _ModelTurnComplete):
                    usage += event.usage
                    prior_output = event.assistant_message
                    final_choice = event.model_choice
                    if event.interrupted_by_tool_calls:
                        interrupted = True
                else:
                    yield event

            if interrupted:
                break

            if not prior_output:
                raise RuntimeError("No assistant message/output returned from model")

        logprobs = self._adapter._extract_and_validate_logprobs(final_choice)

        intermediate_outputs = self._chat_formatter.intermediate_outputs()
        self._adapter._extract_reasoning_to_intermediate_outputs(
            final_choice, intermediate_outputs
        )

        if not isinstance(prior_output, str):
            raise RuntimeError(f"assistant message is not a string: {prior_output}")

        trace = self._adapter.all_messages_to_trace(self._messages)
        self._result = AdapterStreamResult(
            run_output=RunOutput(
                output=prior_output,
                intermediate_outputs=intermediate_outputs,
                output_logprobs=logprobs,
                trace=trace,
            ),
            usage=usage,
        )
        self._iterated = True

    async def _stream_model_turn(
        self,
        skip_response_format: bool,
        top_logprobs: int | None,
    ) -> AsyncIterator[AdapterStreamEvent | _ModelTurnComplete]:
        usage = Usage()
        tool_calls_count = 0

        while tool_calls_count < MAX_TOOL_CALLS_PER_TURN:
            completion_kwargs = await self._adapter.build_completion_kwargs(
                self._provider,
                copy.deepcopy(self._messages),
                top_logprobs,
                skip_response_format,
            )

            stream = StreamingCompletion(**completion_kwargs)
            start = time.monotonic()
            async for chunk in stream:
                yield chunk
            call_latency_ms = int((time.monotonic() - start) * 1000)

            response, response_choice = _validate_response(stream.response)
            usage += self._adapter.usage_from_response(response)
            usage.total_llm_latency_ms = (
                usage.total_llm_latency_ms or 0
            ) + call_latency_ms

            content = response_choice.message.content
            tool_calls = response_choice.message.tool_calls
            if not content and not tool_calls:
                raise ValueError(
                    "Model returned an assistant message, but no content or tool calls. This is not supported."
                )

            response_choice.message._latency_ms = call_latency_ms  # type: ignore[attr-defined]
            self._messages.append(response_choice.message)

            if tool_calls and len(tool_calls) > 0:
                # Check for return_on_tool_call BEFORE processing
                if self._adapter.base_adapter_config.return_on_tool_call:
                    real_tool_calls = [
                        tc for tc in tool_calls if tc.function.name != "task_response"
                    ]
                    if real_tool_calls:
                        # Yield INPUT_AVAILABLE events for each tool call
                        for tc in real_tool_calls:
                            try:
                                parsed_args = json.loads(tc.function.arguments)
                            except (json.JSONDecodeError, TypeError):
                                parsed_args = None
                            yield ToolCallEvent(
                                event_type=ToolCallEventType.INPUT_AVAILABLE,
                                tool_call_id=tc.id,
                                tool_name=tc.function.name or "unknown",
                                arguments=parsed_args,
                                error=(
                                    f"Failed to parse arguments: {tc.function.arguments}"
                                    if parsed_args is None
                                    else None
                                ),
                            )

                        yield _ModelTurnComplete(
                            assistant_message="",
                            model_choice=response_choice,
                            usage=usage,
                            interrupted_by_tool_calls=True,
                        )
                        return

                # Existing flow: handle tool calls internally
                async for event in self._handle_tool_calls(tool_calls):
                    yield event

                assistant_msg = self._extract_task_response(tool_calls)
                if assistant_msg is not None:
                    yield _ModelTurnComplete(
                        assistant_message=assistant_msg,
                        model_choice=response_choice,
                        usage=usage,
                    )
                    return

                tool_calls_count += 1
                continue

            if content:
                yield _ModelTurnComplete(
                    assistant_message=content,
                    model_choice=response_choice,
                    usage=usage,
                )
                return

            raise RuntimeError(
                "Model returned neither content nor tool calls. It must return at least one of these."
            )

        raise RuntimeError(
            f"Too many tool calls ({tool_calls_count}). Stopping iteration to avoid using too many tokens."
        )

    async def _handle_tool_calls(
        self,
        tool_calls: list[ChatCompletionMessageToolCall],
    ) -> AsyncIterator[AdapterStreamEvent]:
        real_tool_calls = [
            tc for tc in tool_calls if tc.function.name != "task_response"
        ]

        for tc in real_tool_calls:
            try:
                parsed_args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                parsed_args = None

            yield ToolCallEvent(
                event_type=ToolCallEventType.INPUT_AVAILABLE,
                tool_call_id=tc.id,
                tool_name=tc.function.name or "unknown",
                arguments=parsed_args,
                error=(
                    f"Failed to parse arguments: {tc.function.arguments}"
                    if parsed_args is None
                    else None
                ),
            )

        _, tool_msgs = await self._adapter.process_tool_calls(tool_calls)

        for tool_msg in tool_msgs:
            tc_id = tool_msg["tool_call_id"]
            tc_name = _find_tool_name(tool_calls, tc_id)
            content = tool_msg["content"]
            yield ToolCallEvent(
                event_type=ToolCallEventType.OUTPUT_AVAILABLE,
                tool_call_id=tc_id,
                tool_name=tc_name,
                result=str(content) if content is not None else None,
            )

        self._messages.extend(tool_msgs)

    @staticmethod
    def _extract_task_response(
        tool_calls: list[ChatCompletionMessageToolCall],
    ) -> str | None:
        for tc in tool_calls:
            if tc.function.name == "task_response":
                return tc.function.arguments
        return None


@dataclass
class _ModelTurnComplete:
    """Internal sentinel yielded when a model turn finishes."""

    assistant_message: str
    model_choice: Choices | None
    usage: Usage
    interrupted_by_tool_calls: bool = False


def _validate_response(
    response: Any,
) -> tuple[ModelResponse, Choices]:
    if (
        not isinstance(response, ModelResponse)
        or not response.choices
        or len(response.choices) == 0
        or not isinstance(response.choices[0], Choices)
    ):
        raise RuntimeError(
            f"Expected ModelResponse with Choices, got {type(response)}."
        )
    return response, response.choices[0]


def _find_tool_name(
    tool_calls: list[ChatCompletionMessageToolCall], tool_call_id: str
) -> str:
    for tc in tool_calls:
        if tc.id == tool_call_id:
            return tc.function.name or "unknown"
    return "unknown"
