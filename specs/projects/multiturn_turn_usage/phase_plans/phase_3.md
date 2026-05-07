---
status: complete
---

# Phase 3: Streaming adapter wiring (`AdapterStream`)

## Overview

Phase 2 wired the non-streaming `LiteLlmAdapter` to populate per-message
`usage` for each LLM call and computed `TaskRun.cumulative_usage` in
`BaseAdapter.generate_run`. Phase 3 mirrors those non-streaming changes in
the streaming orchestrator (`AdapterStream`), so streaming runs persist the
same per-message usage data as non-streaming runs.

`AdapterStream` is the single orchestrator behind both
`invoke_openai_stream` and `invoke_ai_sdk_stream` — one set of changes
covers both stream variants.

The two data-flow additions (parallel to existing `_message_latency`
plumbing):

1. `AdapterStream._message_usage: dict[int, Usage]` — new private state,
   built up alongside `_message_latency` in `_stream_model_turn` after each
   completed LLM call.
2. `AdapterStream.__aiter__` passes `_message_usage` through to
   `LiteLlmAdapter.all_messages_to_trace` at finalization, so each assistant
   message in the resulting `RunOutput.trace` carries the per-call `usage`.

LiteLLM's streaming `usage` block is gated behind
`stream_options={"include_usage": True}`; without it, the final assembled
`ModelResponse` from `litellm.stream_chunk_builder` has no `usage` field and
`usage_from_response` returns an empty `Usage()`. We add this to streaming
calls only — non-streaming responses already include usage by default.

`generate_run` already calls `Usage.from_trace(trace)` on the resulting
TaskRun (Phase 2), so once the streaming trace carries per-message `usage`,
`cumulative_usage` is populated automatically for streaming runs too — no
additional change needed in `_finalize_stream`.

## Steps

1. **`libs/core/kiln_ai/adapters/model_adapters/adapter_stream.py`**

   - In `AdapterStream.__init__`, add new state next to `_message_latency`:
     ```python
     self._message_usage: dict[int, Usage] = {}
     ```
   - In `_stream_model_turn`, capture `call_usage` per call (mirroring
     non-streaming):
     ```python
     call_usage = self._adapter.usage_from_response(response)
     usage += call_usage
     usage.total_llm_latency_ms = (
         usage.total_llm_latency_ms or 0
     ) + call_latency_ms
     ```
     Replace the existing
     `usage += self._adapter.usage_from_response(response)` line with the
     two-line capture above.
   - Right after the existing
     `self._message_latency[len(self._messages) - 1] = call_latency_ms`,
     add:
     ```python
     self._message_usage[len(self._messages) - 1] = call_usage
     ```
   - In `__aiter__`, pass `message_usage=self._message_usage` to
     `all_messages_to_trace`:
     ```python
     trace = self._adapter.all_messages_to_trace(
         self._messages, self._message_latency, self._message_usage
     )
     ```

2. **Enable LiteLLM streaming usage**

   `litellm.acompletion(..., stream=True)` returns no usage block by
   default; `stream_options={"include_usage": True}` is required. Two
   options:

   a. Add it inside `StreamingCompletion.__init__` so callers don't need to
      know about it (one source of truth, applies to all streaming).
   b. Add it inside `LiteLlmAdapter.build_completion_kwargs` gated by some
      "is streaming" flag.

   Option (a) is simpler and there is no use case where streaming should
   skip usage. Pick (a). In
   `libs/core/kiln_ai/adapters/litellm_utils/litellm_streaming.py`:

   ```python
   def __init__(self, *args: Any, **kwargs: Any) -> None:
       kwargs = dict(kwargs)
       kwargs.pop("stream", None)
       # Streaming responses don't include usage by default.
       # Force include_usage=True so the final assembled ModelResponse
       # carries token counts (and downstream cost). Merge with any
       # caller-provided stream_options without clobbering other keys.
       caller_stream_options = kwargs.get("stream_options") or {}
       kwargs["stream_options"] = {**caller_stream_options, "include_usage": True}
       ...
   ```

   No other caller currently passes `stream_options`, so the merge is
   future-proofing rather than required functionality.

3. **No `_finalize_stream` change needed.** `BaseAdapter.generate_run`
   already calls `Usage.from_trace(trace)` (Phase 2), so populating
   per-message `usage` on the streaming trace causes `cumulative_usage` to
   be set automatically.

## Tests

### `libs/core/kiln_ai/adapters/model_adapters/test_adapter_stream.py`

- `test_per_message_usage_captured_for_simple_response` — single LLM call,
  `usage_from_response` returns `Usage(input_tokens=10, output_tokens=20,
  cost=0.1)`. After iteration, `all_messages_to_trace` is called with a
  `message_usage` dict whose only entry maps to that `Usage`. Assert
  `result.usage` equals that `Usage` (with `total_llm_latency_ms` set to
  the call latency).
- `test_per_message_usage_distinct_per_tool_call_loop` — tool-call loop
  with 2 LLM calls returning distinct `Usage` payloads. Assert each
  message gets its own per-message `Usage` (verified through
  `all_messages_to_trace`'s `message_usage` argument).
- `test_per_message_usage_on_tool_call_interruption` — `return_on_tool_call
  = True`. Assert the assistant message produced before interruption has
  its per-message usage recorded.
- `test_per_message_usage_independent_of_message_latency` — `usage_from_response`
  returns a `Usage` with all `None` fields (provider returned no usage).
  Assert the stored per-message entry exists (`Usage()` instance) and
  doesn't break finalization.

### `libs/core/kiln_ai/adapters/litellm_utils/test_litellm_streaming.py`

- `test_stream_options_include_usage_added_by_default` — call
  `StreamingCompletion(model=..., messages=...)`, assert `acompletion` was
  invoked with `stream_options={"include_usage": True}`.
- `test_stream_options_include_usage_merged_with_caller_options` — caller
  passes `stream_options={"some_other_flag": True}`. Assert resulting call
  has `stream_options == {"some_other_flag": True, "include_usage": True}`.
- `test_caller_provided_include_usage_false_is_overridden` — caller passes
  `stream_options={"include_usage": False}`. Assert the wrapper forces
  `include_usage=True` (deliberate behavior — we always want usage on
  streaming).
