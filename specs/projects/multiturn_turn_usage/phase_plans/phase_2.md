---
status: draft
---

# Phase 2: Non-streaming adapter wiring + `cumulative_usage` computation

## Overview

Phase 1 added the data fields. Phase 2 wires the non-streaming `LiteLlmAdapter`
to populate per-message `usage` for each LLM call (mirroring how
`message_latency` is captured today), and computes `TaskRun.cumulative_usage`
from the full trace at run-finalization time in `BaseAdapter.generate_run`.

No streaming changes — `AdapterStream` and `_run_stream` paths are Phase 3.

The four data-flow additions, all parallel to the existing `message_latency`
plumbing:

1. `ModelTurnResult.message_usage: dict[int, Usage] | None` — new optional
   field, default `None`. Built in `_run_model_turn` next to `message_latency`.
2. `LiteLlmAdapter._run_model_turn` captures `call_usage` per LLM call and
   stores it at the same message index as `message_latency`. Returns it on
   every `ModelTurnResult` construction site (normal completion, task_response
   tool path, tool-call interruption).
3. `LiteLlmAdapter._run` aggregates per-turn `message_usage` into a run-level
   dict and passes it through `all_messages_to_trace` for both the
   tool-call-interruption return and the normal completion return.
4. `litellm_message_to_trace_message` and `all_messages_to_trace` accept an
   optional `usage` / `message_usage` argument and attach it to assistant
   messages. Non-LiteLLM dict messages pass through untouched (preserving any
   `usage` already attached, e.g. from a seeded prior trace).

`BaseAdapter.generate_run` computes `cumulative_usage = Usage.from_trace(trace)`
and assigns it to the new `TaskRun`. This is the single point where the full
trace (seeded prior + new turns) gets summed; `MultiturnFormatter` and other
seeding paths need no changes — the prior trace's per-message `usage` flows
through unchanged.

## Steps

1. **`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`**

   - Add `message_usage: dict[int, Usage] | None = None` to `ModelTurnResult`.
   - In `_run_model_turn`:
     - Add local `message_usage: dict[int, Usage] = {}` next to `message_latency`.
     - Replace the existing `usage += self.usage_from_response(model_response)`
       with capture of `call_usage`:
       ```python
       call_usage = self.usage_from_response(model_response)
       usage += call_usage
       ```
     - After the existing `message_latency[len(messages) - 1] = call_latency_ms`
       line, add `message_usage[len(messages) - 1] = call_usage`.
     - Pass `message_usage=message_usage` to all three `ModelTurnResult(...)`
       construction sites: tool-call interruption return (line ~182), normal
       tool-call task_response return (line ~204), normal content return
       (line ~220).
   - In `_run`:
     - Add local `message_usage: dict[int, Usage] = {}` next to the existing
       `message_latency: dict[int, int] = {}`.
     - After the existing `if turn_result.message_latency: message_latency.update(...)`
       block, add the parallel block:
       ```python
       if turn_result.message_usage:
           message_usage.update(turn_result.message_usage)
       ```
     - Pass `message_usage=message_usage` to both `all_messages_to_trace` calls
       (tool-call interruption path and final completion path).
   - In `litellm_message_to_trace_message`:
     - Add `usage: Usage | None = None` keyword argument.
     - After the `latency_ms` attachment block, add:
       ```python
       if usage is not None:
           message["usage"] = usage
       ```
   - In `all_messages_to_trace`:
     - Add `message_usage: dict[int, Usage] | None = None` keyword argument.
     - In the LiteLLMMessage branch, look up
       `usage = message_usage.get(i) if message_usage else None` and pass it
       to `litellm_message_to_trace_message`.

2. **`libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`**

   - In `generate_run`, after constructing the `TaskRun(...)` and before
     returning it, compute and attach `cumulative_usage`. Simplest:
     ```python
     run = TaskRun(...)
     run.cumulative_usage = Usage.from_trace(trace)
     return run
     ```
     Trace is already an argument to `generate_run`, so no additional plumbing.
     `Usage.from_trace` handles `trace=None` → returns empty `Usage()`. Note
     this means `cumulative_usage` is set to `Usage()` (not `None`) for runs
     produced through this path, even when `trace` is `None`. Pre-existing
     records on disk that never went through this code path remain `None` —
     that's the intended distinction between "post-change" and "pre-change"
     records.

## Tests

### `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter.py`

- `test_litellm_message_to_trace_message_attaches_usage` — call with explicit
  `usage=Usage(input_tokens=5, ...)`; assert returned message dict has
  `usage` matching.
- `test_litellm_message_to_trace_message_omits_usage_when_none` — call without
  `usage` arg (or with `None`); assert `"usage"` key is absent.
- `test_all_messages_to_trace_attaches_per_message_usage` — pass a list of
  LiteLLM messages plus a `message_usage` dict mapping indices to distinct
  `Usage` instances. Assert each emitted dict has the matching `usage`.
- `test_all_messages_to_trace_passes_through_dict_messages_with_usage` — input
  contains a non-LiteLLM dict assistant message that already carries a
  `usage` field (e.g. seeded prior trace); assert it survives unchanged.
- `test_run_populates_per_message_usage_and_running_total` — mock
  `acompletion_checking_response` to return two distinct `Usage` payloads
  across a tool-call loop; assert each assistant message in `run_output.trace`
  has its own `usage` and that `usage` (the running total) equals the sum.
- `test_run_with_prior_trace_preserves_seeded_per_message_usage` — extend the
  existing `test_run_with_prior_trace_uses_multiturn_formatter` scenario with
  a seeded assistant message that has `usage`; mock the model call to also
  return `usage`; assert the seeded message still has its original `usage`
  and the new assistant message has its own.

### `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_tools.py`

- (Optional, if straightforward) Extend an existing tool-call mocked test to
  assert per-message `usage` is populated on each assistant message in the
  resulting trace.

### `libs/core/kiln_ai/adapters/model_adapters/test_saving_adapter_results.py`

- `test_generate_run_sets_cumulative_usage_from_trace` — call `generate_run`
  with a trace whose assistant messages carry `usage`; assert
  `task_run.cumulative_usage` equals the sum.
- `test_generate_run_sets_empty_cumulative_usage_when_trace_is_none` — call
  `generate_run` without a trace; assert `task_run.cumulative_usage` is
  `Usage()` (all-None fields), not `None`.
- `test_generate_run_fresh_run_cumulative_equals_usage` — fresh run path:
  `usage` matches `Usage.from_trace(trace)`; assert
  `task_run.cumulative_usage == task_run.usage`.
- `test_generate_run_seeded_run_cumulative_includes_prior_trace_usage` — pass
  a `trace` containing seeded assistant messages with `usage` plus a new
  assistant message with `usage`. Pass `usage=` (the new-turn total) that
  excludes the seeded portion. Assert
  `task_run.cumulative_usage > task_run.usage` and the values are correct.
