"""Tests for BaseAdapter exception wrapping (KilnRunError).

Verifies that:
- Exceptions raised from `_run` escape as `KilnRunError`
- The partial trace is preserved across the exception boundary
- Already-wrapped KilnRunErrors pass through unmodified
- The original exception is accessible via `.original` and `__cause__`
- `format_error_message` is applied to the wrapped message
- The streaming entry points wrap failures the same way
"""

from __future__ import annotations

from typing import Tuple
from unittest.mock import patch

import litellm
import pytest

from kiln_ai.adapters.errors import STUCK_LOOP_ERROR_PREFIX, KilnRunError
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
        trace_ref: list[ChatCompletionMessageParam],
        prior_trace: list[ChatCompletionMessageParam] | None = None,
    ) -> Tuple[RunOutput, Usage | None]:
        if self._pre_raise is not None:
            raise self._pre_raise
        if self._messages_to_add:
            trace_ref.extend(self._messages_to_add)
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


class _RaisingAdapterStream:
    """Stands in for `AdapterStream`: yields nothing, then raises `to_raise`."""

    def __init__(
        self,
        to_raise: Exception,
        trace: list[ChatCompletionMessageParam] | None = None,
    ) -> None:
        self._to_raise = to_raise
        self._trace = trace

    def partial_trace(self) -> list[ChatCompletionMessageParam] | None:
        return self._trace

    async def __aiter__(self):
        # An async generator needs a yield to be one; nothing is ever emitted.
        if False:
            yield None
        raise self._to_raise


async def _drain_openai_stream(adapter, adapter_stream):
    with patch.object(adapter, "_prepare_stream", return_value=adapter_stream):
        async for _chunk in adapter.invoke_openai_stream("hello"):
            pass


class TestStreamingErrorWrapping:
    """Streaming failures get the same mapped copy and partial trace as invoke."""

    async def test_context_window_error_surfaces_mapped_copy(self, make_adapter):
        adapter = make_adapter()
        context_window_error = litellm.ContextWindowExceededError(
            message="max tokens 128000 exceeded",
            model="m",
            llm_provider="openai",
        )

        with pytest.raises(KilnRunError) as ei:
            await _drain_openai_stream(
                adapter, _RaisingAdapterStream(context_window_error)
            )

        assert str(ei.value).startswith("The run exceeded the model's context window.")
        assert "max tokens 128000 exceeded" in str(ei.value)
        assert ei.value.original is context_window_error

    async def test_stuck_loop_error_surfaces_mapped_copy(self, make_adapter):
        adapter = make_adapter()
        stuck_error = RuntimeError(
            f"{STUCK_LOOP_ERROR_PREFIX}. It called lookup with the same arguments 5 "
            "times in a row and got the same error each time."
        )

        with pytest.raises(KilnRunError) as ei:
            await _drain_openai_stream(adapter, _RaisingAdapterStream(stuck_error))

        assert str(ei.value) == (
            "The run was stopped because the model kept repeating the same failing "
            "tool call after being warned. The run trace shows the repeated calls "
            "and the warning."
        )
        assert ei.value.error_type == "RuntimeError"

    async def test_partial_trace_carried_across_the_stream_boundary(self, make_adapter):
        adapter = make_adapter()
        trace: list[ChatCompletionMessageParam] = [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "partial"},
        ]

        with pytest.raises(KilnRunError) as ei:
            await _drain_openai_stream(
                adapter, _RaisingAdapterStream(RuntimeError("boom"), trace=trace)
            )

        assert ei.value.partial_trace == trace

    async def test_trace_conversion_failure_does_not_swallow_the_error(
        self, make_adapter
    ):
        adapter = make_adapter()
        adapter_stream = _RaisingAdapterStream(RuntimeError("boom"))
        with patch.object(
            _RaisingAdapterStream,
            "partial_trace",
            side_effect=ValueError("malformed assistant message"),
        ):
            with pytest.raises(KilnRunError) as ei:
                await _drain_openai_stream(adapter, adapter_stream)

        assert str(ei.value) == "boom"
        assert ei.value.partial_trace is None

    async def test_already_wrapped_error_passes_through(self, make_adapter):
        adapter = make_adapter()
        pre_wrapped = KilnRunError(
            message="already wrapped",
            partial_trace=None,
            original=RuntimeError("inner"),
        )

        with pytest.raises(KilnRunError) as ei:
            await _drain_openai_stream(adapter, _RaisingAdapterStream(pre_wrapped))

        assert ei.value is pre_wrapped

    async def test_ai_sdk_stream_wraps_errors_too(self, make_adapter):
        adapter = make_adapter()
        context_window_error = litellm.ContextWindowExceededError(
            message="max tokens 128000 exceeded",
            model="m",
            llm_provider="openai",
        )
        trace: list[ChatCompletionMessageParam] = [{"role": "user", "content": "u"}]

        with patch.object(
            adapter,
            "_prepare_stream",
            return_value=_RaisingAdapterStream(context_window_error, trace=trace),
        ):
            with pytest.raises(KilnRunError) as ei:
                async for _event in adapter.invoke_ai_sdk_stream("hello"):
                    pass

        assert str(ei.value).startswith("The run exceeded the model's context window.")
        assert ei.value.partial_trace == trace
