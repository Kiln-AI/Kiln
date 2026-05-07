---
status: draft
---

# Phase 1: Extract `Usage` to its own module + datamodel/wrapper field additions

## Overview

Pure refactor + additive schema work — no behavior change. This phase moves `Usage` out of `task_run.py` so the message wrapper in `open_ai_types.py` can reference it without creating an import cycle, then adds the new optional fields the later phases will populate.

The four data-layer additions:

1. New module `kiln_ai.datamodel.usage` housing `Usage` (verbatim move) plus a new `Usage.from_trace` static helper that sums per-message usage across assistant messages in a trace.
2. `task_run.py` re-exports `Usage` from the new module so all existing imports of `kiln_ai.datamodel.task_run.Usage` (and the `kiln_ai.datamodel.Usage` re-export in `__init__.py`) keep working unchanged.
3. New optional `cumulative_usage: Usage | None` field on `TaskRun`, default `None`.
4. New optional `usage` key on `ChatCompletionAssistantMessageParamWrapper`, plus `"usage"` added to `KILN_ONLY_MESSAGE_FIELDS` so existing sanitization strips it before the trace is sent back to providers.

No adapter changes in this phase. Phase 2 wires the non-streaming adapter to populate `usage` per message and compute `cumulative_usage`. Phase 3 does streaming.

## Steps

1. Create `libs/core/kiln_ai/datamodel/usage.py` containing the `Usage` Pydantic model — moved verbatim from `task_run.py` (fields, docstrings, `__add__`). Add a new `from_trace` static method:

   ```python
   @staticmethod
   def from_trace(trace: list[ChatCompletionMessageParam] | None) -> "Usage":
       """Sum per-message usage across all assistant messages in a trace.

       Returns Usage() (all fields None) when trace is None/empty or no
       assistant message has a `usage` field. Skips non-assistant messages
       and messages where `usage` is missing or None."""
   ```

   Implementation: iterate the trace, accumulate via existing `Usage.__add__` only for entries where `role == "assistant"` and `usage` is present and non-None. The `usage` value on a dict TypedDict message could already be a `Usage` instance OR a plain dict (from JSON deserialization round-tripped via Pydantic) — handle both: if dict, validate to `Usage` first.

   Import note: `Usage.from_trace` needs `ChatCompletionMessageParam`. To avoid an import cycle (`open_ai_types` → `usage` → `open_ai_types`), import `ChatCompletionMessageParam` lazily inside `from_trace`, or guard with `TYPE_CHECKING`. Use the `TYPE_CHECKING` pattern; the runtime check on `role == "assistant"` plus dict `.get("usage")` doesn't need the type.

2. In `libs/core/kiln_ai/datamodel/task_run.py`:

   - Delete the in-file `Usage` class definition.
   - Add re-export at the top: `from kiln_ai.datamodel.usage import Usage as Usage` (the `as Usage` form preserves it on `__all__`-style introspection and silences ruff F401).
   - Add new field on `TaskRun`:

     ```python
     cumulative_usage: Usage | None = Field(
         default=None,
         description="Sum of per-message usage across the entire trace, including any seeded prior trace. None on records created before this field existed. For a fresh (non-seeded) run, equals `usage`.",
     )
     ```

   `kiln_ai.datamodel.__init__.py` already does `from kiln_ai.datamodel.task_run import TaskRun, Usage` — that keeps working because of the re-export.

3. In `libs/core/kiln_ai/utils/open_ai_types.py`:

   - Import `Usage` from `kiln_ai.datamodel.usage`. (No cycle because `usage.py` has no Kiln imports at runtime — the `ChatCompletionMessageParam` reference inside `from_trace` is `TYPE_CHECKING`-only.)
   - Add `usage: Optional[Usage]` to `ChatCompletionAssistantMessageParamWrapper`, with a docstring explaining per-LLM-call semantics and that it's stripped before sending to providers.
   - Add `"usage"` to `KILN_ONLY_MESSAGE_FIELDS`.

4. Verify the existing `test_open_ai_types.test_kiln_only_message_fields_set` test asserts the exact frozenset and update it to include `"usage"`.

## Tests

### `libs/core/kiln_ai/datamodel/test_usage.py` (new)

- `test_usage_re_exported_from_task_run` — `from kiln_ai.datamodel.task_run import Usage` and `from kiln_ai.datamodel.usage import Usage` resolve to the same class.
- `test_usage_re_exported_from_datamodel_init` — `from kiln_ai.datamodel import Usage` resolves to the same class.
- `test_from_trace_none_returns_empty_usage` — `Usage.from_trace(None)` returns a `Usage` with all None fields.
- `test_from_trace_empty_list_returns_empty_usage` — `Usage.from_trace([])` returns empty `Usage`.
- `test_from_trace_skips_non_assistant_messages` — trace with only system/user/tool messages → empty `Usage`.
- `test_from_trace_single_assistant_with_usage` — one assistant message with a populated `usage` → equal to that usage.
- `test_from_trace_multiple_assistants_sums_usage` — two assistant messages with distinct usages → sum.
- `test_from_trace_skips_assistants_without_usage` — mix of assistants with and without `usage` → sum of present ones; missing `usage` key contributes nothing.
- `test_from_trace_handles_assistant_with_usage_set_to_none` — `{"role": "assistant", "usage": None}` → skipped silently.
- `test_from_trace_accepts_usage_as_dict` — when `usage` is a dict (post-JSON round-trip), it's validated to `Usage` and summed.
- `test_from_trace_partial_none_fields_in_usage` — `Usage(input_tokens=10, cost=None)` + `Usage(input_tokens=None, cost=0.5)` sums to `(10, 0.5)`.
- `test_from_trace_returns_usage_instance_never_none` — even with empty input, returns `Usage` (never `None`).

### `libs/core/kiln_ai/datamodel/test_task_run.py` or `test_example_models.py`

- `test_task_run_default_cumulative_usage_is_none` — new `TaskRun` has `cumulative_usage is None`.
- `test_task_run_can_set_cumulative_usage` — accept a `Usage` instance.
- `test_task_run_loads_old_json_without_cumulative_usage` — JSON missing `cumulative_usage` deserializes successfully with the field as `None`.
- `test_task_run_round_trip_with_cumulative_usage` — set, serialize, deserialize, compare.

(These can live in `test_example_models.py` alongside the existing `test_usage_model_in_task_run`.)

### `libs/core/kiln_ai/utils/test_open_ai_types.py`

- Update `test_kiln_only_message_fields_set` to include `"usage"`.
- `test_sanitize_messages_strips_usage_field` — assistant message with a `usage` key has it removed by `sanitize_messages_for_provider`.
- `test_assistant_wrapper_accepts_usage_field` — instantiate the TypedDict with `usage` set to a `Usage` instance; assert it round-trips.
- `test_assistant_message_param_properties_match` — bump the kiln-only properties list to also remove `"usage"` from comparison.

### Sanitization integration

- A trace containing assistant + tool messages with `usage`/`latency_ms`/etc. round-trips through `sanitize_messages_for_provider` with all kiln-only fields stripped, including the new `usage` field.
