from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class Usage(BaseModel):
    """Token usage and cost information for a task run."""

    input_tokens: int | None = Field(
        default=None,
        description="The number of input tokens used in the task run.",
        ge=0,
    )
    output_tokens: int | None = Field(
        default=None,
        description="The number of output tokens used in the task run.",
        ge=0,
    )
    total_tokens: int | None = Field(
        default=None,
        description="The total number of tokens used in the task run.",
        ge=0,
    )
    cost: float | None = Field(
        default=None,
        description="The cost of the task run in US dollars, saved at runtime (prices can change over time).",
        ge=0,
    )
    cached_tokens: int | None = Field(
        default=None,
        description="Number of tokens served from prompt cache. None if not reported.",
        ge=0,
    )
    total_llm_latency_ms: int | None = Field(
        default=None,
        description="Total time spent waiting on LLM API calls in milliseconds. Sum of per-call latencies, excludes tool execution time.",
        ge=0,
    )

    def __add__(self, other: "Usage") -> "Usage":
        """Add two Usage objects together, handling None values gracefully.

        None + None = None
        None + value = value
        value + None = value
        value1 + value2 = value1 + value2
        """
        if not isinstance(other, Usage):
            raise TypeError(f"Cannot add Usage with {type(other).__name__}")

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

        return Usage(
            input_tokens=_add_optional_int(self.input_tokens, other.input_tokens),
            output_tokens=_add_optional_int(self.output_tokens, other.output_tokens),
            total_tokens=_add_optional_int(self.total_tokens, other.total_tokens),
            cost=_add_optional_float(self.cost, other.cost),
            cached_tokens=_add_optional_int(self.cached_tokens, other.cached_tokens),
            total_llm_latency_ms=_add_optional_int(
                self.total_llm_latency_ms, other.total_llm_latency_ms
            ),
        )

    @staticmethod
    def from_trace(
        trace: "list[ChatCompletionMessageParam] | None",
    ) -> "Usage":
        """Sum per-message usage across all assistant messages in a trace.

        Returns Usage() (all fields None) when trace is None/empty or no
        assistant message has a `usage` field. Skips non-assistant messages
        and messages where `usage` is missing or None. Always returns a
        Usage instance — never None.

        Accepts per-message `usage` values that are either Usage instances
        or plain dicts (e.g. from JSON round-trips); dicts are validated to
        Usage before summing.
        """
        total = Usage()
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
            if isinstance(raw_usage, Usage):
                total = total + raw_usage
            elif isinstance(raw_usage, dict):
                total = total + Usage.model_validate(raw_usage)
        return total
