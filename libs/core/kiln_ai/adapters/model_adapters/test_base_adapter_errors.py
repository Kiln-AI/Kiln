"""Tests for BaseAdapter exception wrapping (KilnRunError).

Verifies that:
- Exceptions raised from `_run` escape as `KilnRunError`
- The partial trace is preserved across the exception boundary
- Already-wrapped KilnRunErrors pass through unmodified
- The original exception is accessible via `.original` and `__cause__`
- `format_error_message` is applied to the wrapped message
"""

from __future__ import annotations

from typing import Tuple
from unittest.mock import patch

import litellm
import pytest

from kiln_ai.adapters.errors import KilnRunError
from kiln_ai.adapters.ml_model_list import KilnModelProvider
from kiln_ai.adapters.model_adapters.base_adapter import BaseAdapter, RunOutput
from kiln_ai.datamodel import Task, Usage
from kiln_ai.datamodel.project import Project
from kiln_ai.datamodel.run_config import KilnAgentRunConfigProperties
from kiln_ai.utils.open_ai_types import ChatCompletionMessageParam


class _ControllableAdapter(BaseAdapter):
    """Minimal adapter whose `_run` behaviour is set per-test.

    - `pre_raise`: Exception to raise BEFORE touching `messages`. Produces empty trace.
    - `messages_to_add`: messages to extend into the caller's list, then raise `post_raise`.
    - `post_raise`: Exception to raise AFTER mutating `messages`.
    - `return_output`: If set, return this instead of raising.
    """

    def __init__(
        self,
        *args,
        pre_raise: Exception | None = None,
        messages_to_add: list[ChatCompletionMessageParam] | None = None,
        post_raise: Exception | None = None,
        return_output: Tuple[RunOutput, Usage | None] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._pre_raise = pre_raise
        self._messages_to_add = messages_to_add or []
        self._post_raise = post_raise
        self._return_output = return_output

    async def _run(
        self,
        input,
        messages: list[ChatCompletionMessageParam],
        prior_trace: list[ChatCompletionMessageParam] | None = None,
    ) -> Tuple[RunOutput, Usage | None]:
        if self._pre_raise is not None:
            raise self._pre_raise
        if self._messages_to_add:
            messages.extend(self._messages_to_add)
        if self._post_raise is not None:
            raise self._post_raise
        if self._return_output is not None:
            return self._return_output
        raise AssertionError("_ControllableAdapter configured with no behaviour")

    def adapter_name(self) -> str:
        return "controllable"


@pytest.fixture
def base_task():
    project = Project(name="p", description="d")
    return Task(name="t", instruction="i", parent=project)


@pytest.fixture
def run_config():
    return KilnAgentRunConfigProperties(
        model_name="test_model",
        model_provider_name="openai",
        prompt_id="simple_prompt_builder",
        structured_output_mode="json_schema",
    )


@pytest.fixture
def mock_provider_patch():
    """Patch `model_provider()` so adapter init/run don't try to look up a real provider."""
    with patch.object(
        BaseAdapter,
        "model_provider",
        return_value=KilnModelProvider(name="openai", formatter=None),
    ):
        yield


@pytest.fixture
def make_adapter(base_task, run_config, mock_provider_patch):
    def factory(**adapter_kwargs) -> _ControllableAdapter:
        return _ControllableAdapter(
            task=base_task,
            run_config=run_config,
            **adapter_kwargs,
        )

    return factory


async def test_raises_kiln_run_error_when_run_throws(make_adapter):
    adapter = make_adapter(post_raise=RuntimeError("Too many turns (11)."))
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert isinstance(ei.value.original, RuntimeError)
    assert ei.value.error_type == "RuntimeError"


async def test_partial_trace_populated_when_messages_extended(make_adapter):
    msgs: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
    ]
    adapter = make_adapter(
        messages_to_add=msgs,
        post_raise=RuntimeError("boom"),
    )
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert ei.value.partial_trace == msgs


async def test_partial_trace_none_when_failure_before_any_messages(make_adapter):
    adapter = make_adapter(pre_raise=RuntimeError("early fail"))
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert ei.value.partial_trace is None


async def test_existing_kiln_run_error_passes_through(make_adapter):
    original = RuntimeError("inner")
    pre_wrapped = KilnRunError(
        message="already wrapped",
        partial_trace=None,
        original=original,
    )
    adapter = make_adapter(pre_raise=pre_wrapped)
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    # Exact same instance — not re-wrapped.
    assert ei.value is pre_wrapped
    assert ei.value.original is original


async def test_cause_chain_preserved(make_adapter):
    inner = RuntimeError("inner")
    adapter = make_adapter(post_raise=inner)
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert ei.value.__cause__ is inner
    assert ei.value.original is inner


async def test_format_error_message_applied_for_known_exception(make_adapter):
    inner = RuntimeError("Too many turns (11). Stopping iteration...")
    adapter = make_adapter(post_raise=inner)
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert str(ei.value) == "The run exceeded the maximum number of turns."


async def test_format_error_message_applied_for_litellm_rate_limit(make_adapter):
    try:
        rate_limit = litellm.RateLimitError(
            message="upstream", model="m", llm_provider="openai"
        )
    except TypeError:
        rate_limit = litellm.RateLimitError("upstream")  # type: ignore[call-arg]
    adapter = make_adapter(post_raise=rate_limit)
    with pytest.raises(KilnRunError) as ei:
        await adapter._run_returning_run_output("hello")
    assert str(ei.value) == "Rate limit exceeded. Wait a moment and try again."
    assert ei.value.error_type == "RateLimitError"


async def test_messages_to_trace_failure_does_not_swallow_original_exception(
    make_adapter,
):
    """If `_messages_to_trace` itself throws in the except block, the
    original exception must still surface (with `partial_trace=None`).
    Regression test for CR feedback: trace-conversion errors used to mask
    the real failure (e.g., rate-limit errors).
    """
    msgs: list[ChatCompletionMessageParam] = [{"role": "user", "content": "u"}]
    try:
        rate_limit = litellm.RateLimitError(
            message="upstream", model="m", llm_provider="openai"
        )
    except TypeError:
        rate_limit = litellm.RateLimitError("upstream")  # type: ignore[call-arg]
    adapter = make_adapter(messages_to_add=msgs, post_raise=rate_limit)

    with patch.object(
        _ControllableAdapter,
        "_messages_to_trace",
        side_effect=ValueError("malformed assistant message"),
    ):
        with pytest.raises(KilnRunError) as ei:
            await adapter._run_returning_run_output("hello")

    # Original exception is preserved, trace conversion failure is absorbed.
    assert ei.value.original is rate_limit
    assert ei.value.error_type == "RateLimitError"
    assert ei.value.partial_trace is None
    assert str(ei.value) == "Rate limit exceeded. Wait a moment and try again."


async def test_messages_to_trace_hook_called(make_adapter):
    """Adapter subclasses can normalise the `messages` list before export."""
    msgs: list[ChatCompletionMessageParam] = [{"role": "user", "content": "u"}]
    adapter = make_adapter(
        messages_to_add=msgs,
        post_raise=RuntimeError("boom"),
    )
    converted = [{"role": "system", "content": "converted"}]

    with patch.object(
        _ControllableAdapter, "_messages_to_trace", return_value=converted
    ) as hook:
        with pytest.raises(KilnRunError) as ei:
            await adapter._run_returning_run_output("hello")
    hook.assert_called_once()
    assert ei.value.partial_trace == converted
