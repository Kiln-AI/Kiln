"""Token usage / cost / latency model.

Lives in its own module so ``kiln_ai.utils.open_ai_types`` can import it
for the per-message ``usage`` field on assistant trace messages without
creating a circular dependency on ``kiln_ai.datamodel.task_run`` (which
itself imports from ``open_ai_types``).
"""

from pydantic import BaseModel, Field


def record_per_call_usage_and_latency(
    call_usage: "Usage",
    call_latency_ms: int,
    turn_usage: "Usage",
    message_index: int,
    message_latency: dict[int, int],
    message_usage: dict[int, "Usage"],
) -> "Usage":
    """Aggregate one inference's usage + latency onto the turn total and
    record the per-message entries on the trace.

    Returns the new turn-level ``Usage`` (since ``Usage + Usage`` produces
    a fresh object — caller reassigns). Stamps ``total_llm_latency_ms``
    on the per-call ``Usage`` AFTER the aggregation so latency travels
    with usage on the trace without double-counting it on the turn total.

    Shared by ``_run_model_turn`` (litellm_adapter.py) and
    ``_stream_model_turn`` (adapter_stream.py).
    """
    new_turn_usage = turn_usage + call_usage
    new_turn_usage.total_llm_latency_ms = (
        new_turn_usage.total_llm_latency_ms or 0
    ) + call_latency_ms
    call_usage.total_llm_latency_ms = call_latency_ms
    message_latency[message_index] = call_latency_ms
    message_usage[message_index] = call_usage
    return new_turn_usage


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
