---
status: complete
---

# Phase 4: Split `Usage` into `MessageUsage` (base) + `Usage`

## Overview

Phases 1–3 introduced per-message `usage` and `TaskRun.cumulative_usage`,
both currently typed as the single `Usage` model that carries
`total_llm_latency_ms`. That latency field is meaningful only for the
running per-run accumulator (`TaskRun.usage`) — it is redundant on a
per-message record (each assistant message already has its own
`latency_ms`) and meaningless when summed across a multi-turn /
seeded-prior trace (those latencies happened at different times and were
never simultaneously "in flight").

This phase splits the model: a new base class `MessageUsage` carries the
five aggregatable fields (tokens + cost) and is used everywhere a
per-message or a multi-message sum is recorded. `Usage` becomes a
subclass that adds `total_llm_latency_ms`, used only for the
`TaskRun.usage` running aggregator inside an adapter run. Re-exports
preserve external compatibility.

## Steps

1. **`libs/core/kiln_ai/datamodel/usage.py` — split into two classes.**

   - Replace the existing `Usage(BaseModel)` with
     `MessageUsage(BaseModel)` carrying the existing five aggregatable
     fields (`input_tokens`, `output_tokens`, `total_tokens`,
     `cached_tokens`, `cost`). Keep all field constraints and
     descriptions; touch up the class docstring to reflect "per-message
     or multi-message sum (no latency)".
   - Implement `MessageUsage.__add__(self, other: "MessageUsage") ->
     "MessageUsage"` that sums the five fields with the same
     None-graceful pattern. Preserve the existing `TypeError` behaviour
     for non-`MessageUsage` operands.
   - Move `from_trace` to `MessageUsage.from_trace(trace) ->
     "MessageUsage"`. Same logic, same docstring (adjusted to say
     "MessageUsage").
   - Define `Usage(MessageUsage)` adding only `total_llm_latency_ms`.
     Override `__add__(self, other: "MessageUsage | Usage") -> "Usage"`:
     - Sum the five base fields by delegating to
       `MessageUsage.__add__` (or by computing fresh).
     - If `other` is a `Usage`, sum `total_llm_latency_ms` too.
     - If `other` is a `MessageUsage` (not `Usage`), carry `self`'s
       `total_llm_latency_ms` through unchanged.
     - Always return a `Usage` (so chained `usage += msg_usage` keeps
       the latency on the accumulator).
   - Keep `from_trace` on `MessageUsage` only — `Usage` inherits it but
     callers should treat the result as `MessageUsage`. To keep typing
     honest, `Usage.from_trace` is fine to leave as inherited (returns
     a `MessageUsage`).

2. **`libs/core/kiln_ai/utils/open_ai_types.py` — switch field type.**

   - `from kiln_ai.datamodel.usage import MessageUsage, Usage` (Usage
     no longer needed here, but keep import path tidy — only import
     `MessageUsage`).
   - `ChatCompletionAssistantMessageParamWrapper.usage: Optional[MessageUsage]`.
   - Update field docstring: drop the line about
     `total_llm_latency_ms`; the new type can't carry it.

3. **`libs/core/kiln_ai/datamodel/task_run.py` — `cumulative_usage` typed
   as `MessageUsage | None`. `usage` stays `Usage | None`.**

   - Import both: `from kiln_ai.datamodel.usage import MessageUsage as
     MessageUsage, Usage as Usage`.
   - Update `cumulative_usage` field description to drop any mention of
     latency.

4. **`libs/core/kiln_ai/datamodel/__init__.py` — re-export
   `MessageUsage` alongside `Usage`.**

   - `from kiln_ai.datamodel.task_run import MessageUsage, TaskRun, Usage`
   - Add `"MessageUsage"` to `__all__`.

5. **`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`.**

   - `ModelTurnResult.message_usage: dict[int, MessageUsage] | None = None`.
   - `_run_model_turn`: `message_usage: dict[int, MessageUsage] = {}`.
     The `usage += self.usage_from_response(...)` line still works
     because `Usage.__add__` accepts a `MessageUsage`.
   - `_run`: `message_usage: dict[int, MessageUsage] = {}`.
   - `usage_from_response(self, response) -> MessageUsage`: return a
     `MessageUsage()` instance instead of `Usage()`. The function never
     touched `total_llm_latency_ms`, so this is a pure type narrowing.
   - `litellm_message_to_trace_message(..., usage: MessageUsage | None
     = None, ...)`.
   - `all_messages_to_trace(..., message_usage: dict[int, MessageUsage]
     | None = None, ...)`.

6. **`libs/core/kiln_ai/adapters/model_adapters/adapter_stream.py`.**

   - `from kiln_ai.datamodel import MessageUsage, Usage`.
   - `self._message_usage: dict[int, MessageUsage] = {}`.
   - `call_usage = self._adapter.usage_from_response(response)` is
     already typed `MessageUsage` after step 5; the
     `usage += call_usage; usage.total_llm_latency_ms = ...` lines keep
     working because `Usage.__add__` accepts `MessageUsage`.

7. **`libs/core/kiln_ai/adapters/model_adapters/base_adapter.py`.**

   - `cumulative_usage=MessageUsage.from_trace(trace)` (was
     `Usage.from_trace(trace)`). Import `MessageUsage` from
     `kiln_ai.datamodel`.

8. **Backward-compat re-exports.**

   - `kiln_ai.datamodel.task_run.Usage` already re-exported. Confirm
     `MessageUsage` is also re-exported from `task_run` (mirror the
     pattern: `from kiln_ai.datamodel.usage import MessageUsage as
     MessageUsage`).
   - `kiln_ai.adapters.model_adapters.base_adapter.Usage` already
     resolves through `from kiln_ai.datamodel import (..., Usage)`. No
     change needed there beyond pulling in `MessageUsage` for the call
     in `generate_run`.

## Tests

Add to `libs/core/kiln_ai/datamodel/test_usage.py`:

- `test_message_usage_add_returns_message_usage` — `MessageUsage + MessageUsage` is a `MessageUsage` (not `Usage`) and never carries
  latency.
- `test_message_usage_add_sums_five_fields` — token counts + cost sum
  with the existing None-graceful semantics.
- `test_message_usage_add_rejects_non_message_usage` — adding a
  non-`MessageUsage` raises `TypeError` with the existing message.
- `test_usage_plus_usage_sums_latency` — `Usage + Usage` returns a
  `Usage` whose `total_llm_latency_ms` is the sum of both operands.
- `test_usage_plus_message_usage_carries_latency_through` — `Usage +
  MessageUsage` returns a `Usage` whose `total_llm_latency_ms` equals
  `self.total_llm_latency_ms` (right-hand side has no latency to
  contribute).
- `test_message_usage_plus_usage_returns_message_usage_without_latency`
  — `MessageUsage + Usage` (left-hand side is the base class) returns a
  `MessageUsage` and discards latency. Documents that the only place
  latency is preserved is when `self` is a `Usage`.
- `test_usage_is_message_usage_subclass` — explicit
  `issubclass(Usage, MessageUsage)`.
- `test_message_usage_from_trace_returns_message_usage` — round-trip a
  small trace, confirm result is a `MessageUsage` (not `Usage`).

Add to `libs/core/kiln_ai/datamodel/test_example_models.py`:

- `test_task_run_per_message_usage_round_trip_has_no_latency_key` —
  build a `TaskRun` with an assistant message carrying a `MessageUsage`
  and a `cumulative_usage = MessageUsage(...)`, dump to JSON, assert
  neither serialized blob contains a `total_llm_latency_ms` key. The
  `TaskRun.usage` field (`Usage`) on the same record DOES contain the
  key.
- `test_task_run_loads_old_cumulative_usage_with_latency_key` — feed a
  payload where `cumulative_usage` includes
  `"total_llm_latency_ms": null` (legacy shape) and assert it loads
  cleanly into a `MessageUsage` without raising. Pydantic's default
  `extra="ignore"` drops the unknown key.

Update existing tests that referenced types now narrowed:

- `test_litellm_adapter.py::test_run_model_turn_records_per_message_usage`
  already asserts `recorded.total_llm_latency_ms is None`. Adapt: the
  recorded value is now a `MessageUsage` instance and has no such
  attribute. Replace the assertion with one of:
  - `assert not hasattr(recorded, "total_llm_latency_ms")`, OR
  - `assert isinstance(recorded, MessageUsage) and not isinstance(recorded, Usage)`.
  Pick the second — clearer intent.
- `test_litellm_adapter.py::test_run_attaches_per_message_usage_to_trace`
  has the same `attached.total_llm_latency_ms is None` assertion. Same
  treatment.
- Any other occurrence of `MessageUsage`-typed `usage` referencing
  `total_llm_latency_ms` (search after edits).

Existing tests that should keep passing without change:

- `test_usage.py::test_usage_re_exported_from_task_run` — still passes
  (re-export unchanged).
- `test_open_ai_types.py::test_sanitize_messages_strips_kiln_only_fields`
  — the assistant `usage` field now happens to be a `MessageUsage`
  instance, but `sanitize_messages_for_provider` works by key and
  doesn't care about the value type.

## Spec docs

After tests pass, update in place:

- `specs/projects/multiturn_turn_usage/functional_spec.md` — note the
  `Usage` / `MessageUsage` split; clarify `cumulative_usage` is
  `MessageUsage`; drop the "or set equal to `latency_ms`" wording about
  per-message `total_llm_latency_ms` (the field doesn't exist on the
  per-message type any more).
- `specs/projects/multiturn_turn_usage/architecture.md` — same
  clarifications: data-model section, `from_trace`/`usage_from_response`/
  `litellm_message_to_trace_message`/`all_messages_to_trace`/
  `generate_run` signatures.
- `specs/projects/multiturn_turn_usage/implementation_plan.md` — append
  a Phase 4 entry, marked complete after the commit.
