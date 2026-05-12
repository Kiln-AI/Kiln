from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


def _add_optional_int(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a + b


def _add_optional_float(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a + b


class MessageUsage(BaseModel):
    """Token usage and cost for a single LLM call or a multi-message sum.

    Carries only the fields that are meaningfully aggregatable across
    messages: token counts and cost. Per-call latency lives on the
    individual message's ``latency_ms`` field; aggregating it across the
    full trace would mix latencies from different points in time, so
    ``MessageUsage`` does NOT carry ``total_llm_latency_ms``.

    The :class:`Usage` subclass adds ``total_llm_latency_ms`` for the
    in-flight per-run accumulator that tracks how long this run spent
    waiting on LLM calls.
    """

    input_tokens: int | None = Field(
        default=None,
        description="The number of input tokens used.",
        ge=0,
    )
    output_tokens: int | None = Field(
        default=None,
        description="The number of output tokens used.",
        ge=0,
    )
    total_tokens: int | None = Field(
        default=None,
        description="The total number of tokens used.",
        ge=0,
    )
    cost: float | None = Field(
        default=None,
        description="The cost in US dollars, saved at runtime (prices can change over time).",
        ge=0,
    )
    cached_tokens: int | None = Field(
        default=None,
        description="Number of tokens served from prompt cache. None if not reported.",
        ge=0,
    )

    def __add__(self, other: "MessageUsage") -> "MessageUsage":
        """Add two MessageUsage objects together, handling None values gracefully.

        None + None = None
        None + value = value
        value + None = value
        value1 + value2 = value1 + value2
        """
        if not isinstance(other, MessageUsage):
            raise TypeError(f"Cannot add MessageUsage with {type(other).__name__}")

        return MessageUsage(
            input_tokens=_add_optional_int(self.input_tokens, other.input_tokens),
            output_tokens=_add_optional_int(self.output_tokens, other.output_tokens),
            total_tokens=_add_optional_int(self.total_tokens, other.total_tokens),
            cost=_add_optional_float(self.cost, other.cost),
            cached_tokens=_add_optional_int(self.cached_tokens, other.cached_tokens),
        )

    @staticmethod
    def from_trace(
        trace: "list[ChatCompletionMessageParam] | None",
    ) -> "MessageUsage":
        """Sum per-message usage across all assistant messages in a trace.

        Returns MessageUsage() (all fields None) when trace is None/empty
        or no assistant message has a `usage` field. Skips non-assistant
        messages and messages where `usage` is missing or None. Always
        returns a MessageUsage instance — never None.

        Accepts per-message `usage` values that are either MessageUsage
        instances (including the Usage subclass) or plain dicts (e.g.
        from JSON round-trips); dicts are validated to MessageUsage
        before summing.
        """
        total: MessageUsage = MessageUsage()
        if not trace:
            return total

        for message in trace:
            if not isinstance(message, dict):
                continue
            if message.get("role") != "assistant":
                continue
            raw_usage = message.get("usage")
            if raw_usage is None:
                continue
            if isinstance(raw_usage, MessageUsage):
                total = total + raw_usage
            elif isinstance(raw_usage, dict):
                total = total + MessageUsage.model_validate(raw_usage)
        return total


class Usage(MessageUsage):
    """Token usage, cost, and aggregate LLM latency for a per-run accumulator.

    Extends :class:`MessageUsage` with ``total_llm_latency_ms``, which is
    only meaningful while a single run is in flight (its model calls run
    sequentially in real time). For per-message records and full-trace
    sums use :class:`MessageUsage` — those values would mix latencies
    from different points in time, so the field doesn't apply.
    """

    total_llm_latency_ms: int | None = Field(
        default=None,
        description="Total time spent waiting on LLM API calls in milliseconds. Sum of per-call latencies, excludes tool execution time.",
        ge=0,
    )

    def __add__(self, other: "MessageUsage | Usage") -> "Usage":
        """Add Usage to either Usage or MessageUsage.

        Token / cost fields sum the same way as :meth:`MessageUsage.__add__`.

        ``Usage + Usage`` sums both ``total_llm_latency_ms`` values
        (None-graceful). ``Usage + MessageUsage`` carries ``self``'s
        ``total_llm_latency_ms`` through unchanged — the right-hand side
        has no latency to contribute.

        Always returns a :class:`Usage` so chained ``usage += msg_usage``
        keeps the latency on the accumulator.
        """
        if not isinstance(other, MessageUsage):
            raise TypeError(f"Cannot add Usage with {type(other).__name__}")

        other_latency = other.total_llm_latency_ms if isinstance(other, Usage) else None

        return Usage(
            input_tokens=_add_optional_int(self.input_tokens, other.input_tokens),
            output_tokens=_add_optional_int(self.output_tokens, other.output_tokens),
            total_tokens=_add_optional_int(self.total_tokens, other.total_tokens),
            cost=_add_optional_float(self.cost, other.cost),
            cached_tokens=_add_optional_int(self.cached_tokens, other.cached_tokens),
            total_llm_latency_ms=_add_optional_int(
                self.total_llm_latency_ms, other_latency
            ),
        )
