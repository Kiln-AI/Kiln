---
status: complete
---

# Architecture: Multiturn Turn-Level Usage Tracking

## Scope decision: single architecture doc

Small data-layer change. Touches ~5 files in `libs/core`. No separate component designs; everything fits here.

## Data Model

### Move `Usage` to its own module (prerequisite)

`Usage` currently lives in `libs/core/kiln_ai/datamodel/task_run.py`. We need to reference it from `libs/core/kiln_ai/utils/open_ai_types.py` (to type the new per-message field), and `task_run.py` already imports from `open_ai_types.py` — so a direct import would create a cycle.

Resolution: create a new module `libs/core/kiln_ai/datamodel/usage.py` containing the `Usage` class. Keep behaviour, fields, docstrings, and `__add__` exactly as today — pure file move.

- `task_run.py`: `from kiln_ai.datamodel.usage import Usage`
- `open_ai_types.py`: `from kiln_ai.datamodel.usage import Usage`
- Re-export `Usage` from `kiln_ai.datamodel.task_run` (`from kiln_ai.datamodel.usage import Usage as Usage`) so any external imports of `kiln_ai.datamodel.task_run.Usage` (or `kiln_ai.datamodel.Usage` via `__init__.py`) keep working. Verify the re-export path: check `libs/core/kiln_ai/datamodel/__init__.py` and `libs/core/kiln_ai/adapters/model_adapters/base_adapter.py` (which imports `Usage` from base_adapter for downstream callers).

Cycle check: `usage.py` has no Kiln imports; both `open_ai_types.py` and `task_run.py` import from it. No cycle.

### Extend `Usage` with `from_trace`

Add a static method:

```python
@staticmethod
def from_trace(trace: list[ChatCompletionMessageParam] | None) -> "Usage":
    """Sum per-message usage across all assistant messages in a trace.
    Returns Usage() (all-None fields) when trace is None or no messages have usage.
    Skips non-assistant messages and messages without a `usage` field."""
```

Implementation: iterate `trace`, for each message where `role == "assistant"` and `usage` key is present and non-None, accumulate via existing `Usage.__add__`.

`Usage()` (all `None`) is returned for empty/missing-data cases. Always returns a `Usage` instance — never `None`. Callers distinguish "this run was created post-change" from "pre-change" by checking the field on `TaskRun` (which IS `None` for old records).

### Per-message `usage` field on assistant messages

`libs/core/kiln_ai/utils/open_ai_types.py`:

- Import `Usage` from `kiln_ai.datamodel.usage`.
- Add to `ChatCompletionAssistantMessageParamWrapper`:
  ```python
  usage: Optional[Usage]
  """Token usage and cost for the LLM call that produced this assistant message.
  Set per-call (not per logical turn). Stripped before sending to providers via KILN_ONLY_MESSAGE_FIELDS."""
  ```
- Add `"usage"` to `KILN_ONLY_MESSAGE_FIELDS`. `sanitize_messages_for_provider` already handles strip-by-key — no changes there.

Since the wrapper is a `TypedDict`, the field is structurally optional. Pydantic serializes nested `Usage` objects fine when the trace is part of `TaskRun` (Pydantic walks TypedDict values).

`total_llm_latency_ms` on the per-message `Usage` is left `None`. Canonical per-call latency stays on the message's `latency_ms` field. No duplication.

### `TaskRun.cumulative_usage`

`libs/core/kiln_ai/datamodel/task_run.py`:

```python
cumulative_usage: Usage | None = Field(
    default=None,
    description="Sum of per-message usage across the entire trace, including any seeded prior trace. None on records created before this field existed. For a fresh (non-seeded) run, equals `usage`.",
)
```

`usage` field stays unchanged.

## Component Breakdown

### `LiteLlmAdapter._run_model_turn` (litellm_adapter.py:113-236)

Add per-call usage capture parallel to `message_latency`.

- Add local: `message_usage: dict[int, Usage] = {}`
- After line 151 (`usage += self.usage_from_response(model_response)`), capture the per-call usage:
  ```python
  call_usage = self.usage_from_response(model_response)
  usage += call_usage
  usage.total_llm_latency_ms = (usage.total_llm_latency_ms or 0) + call_latency_ms
  # ... existing message append ...
  message_latency[len(messages) - 1] = call_latency_ms
  message_usage[len(messages) - 1] = call_usage
  ```
- Add `message_usage` field to `ModelTurnResult` dataclass:
  ```python
  message_usage: dict[int, Usage] | None = None
  ```
- Return `message_usage=message_usage` in all three `ModelTurnResult(...)` construction sites in this method (lines 182, 204, 220).

### `LiteLlmAdapter._run` (litellm_adapter.py:238-330)

Aggregate `message_usage` across turns (parallel to existing `message_latency` aggregation at line 290).

- Add local: `message_usage: dict[int, Usage] = {}`
- After `if turn_result.message_latency: message_latency.update(turn_result.message_latency)`, add:
  ```python
  if turn_result.message_usage:
      message_usage.update(turn_result.message_usage)
  ```
- Pass `message_usage` to both `all_messages_to_trace` calls (line 298 for tool-call interruption; line 322 for normal completion).

### `LiteLlmAdapter.litellm_message_to_trace_message` (litellm_adapter.py:877-927)

Accept optional `usage` and attach it.

```python
def litellm_message_to_trace_message(
    self,
    raw_message: LiteLLMMessage,
    latency_ms: int | None = None,
    usage: Usage | None = None,
) -> ChatCompletionAssistantMessageParamWrapper:
    ...
    if latency_ms is not None:
        message["latency_ms"] = latency_ms
    if usage is not None:
        message["usage"] = usage
    ...
```

### `LiteLlmAdapter.all_messages_to_trace` (litellm_adapter.py:929-944)

Accept and thread per-message usage.

```python
def all_messages_to_trace(
    self,
    messages: list[ChatCompletionMessageIncludingLiteLLM],
    message_latency: dict[int, int] | None = None,
    message_usage: dict[int, Usage] | None = None,
) -> list[ChatCompletionMessageParam]:
    trace: list[ChatCompletionMessageParam] = []
    for i, message in enumerate(messages):
        if isinstance(message, LiteLLMMessage):
            latency_ms = message_latency.get(i) if message_latency else None
            usage = message_usage.get(i) if message_usage else None
            trace.append(self.litellm_message_to_trace_message(message, latency_ms, usage))
        else:
            trace.append(message)
    return trace
```

Note: messages already passed through as dicts (the `else` branch) include any `usage` already attached to them — e.g., from a seeded prior trace. No transformation needed.

### `AdapterStream` (adapter_stream.py)

Mirror the non-streaming changes for both stream variants (OpenAI + AI SDK use the same `AdapterStream` orchestrator).

- Add to `__init__`: `self._message_usage: dict[int, Usage] = {}`
- In `_stream_model_turn` (line 150-...):
  - Capture per-call usage right after `usage_from_response` (line 173):
    ```python
    call_usage = self._adapter.usage_from_response(response)
    usage += call_usage
    ...
    self._messages.append(response_choice.message)
    self._message_latency[len(self._messages) - 1] = call_latency_ms
    self._message_usage[len(self._messages) - 1] = call_usage
    ```
- In `__aiter__` (line 136-138), pass `message_usage` to `all_messages_to_trace`:
  ```python
  trace = self._adapter.all_messages_to_trace(
      self._messages, self._message_latency, self._message_usage
  )
  ```

### `BaseAdapter.generate_run` (base_adapter.py:626-...)

Compute `cumulative_usage` from the trace and set it on the new `TaskRun`.

After constructing the `TaskRun(...)` (search for where `usage=usage` is passed — likely in the `TaskRun(...)` call near the end of `generate_run`), set:

```python
run.cumulative_usage = Usage.from_trace(trace)
```

Or pass directly in the constructor if `trace` is available before construction. Either approach is fine; pick the simpler one.

This computes from the FULL trace (which already includes any seeded prior trace's messages with their original `usage`), so `cumulative_usage` is correct for both fresh and seeded runs without further special-casing. `MultiturnFormatter` doesn't need any changes.

### Sanitization

Existing `sanitize_messages_for_provider` strips `KILN_ONLY_MESSAGE_FIELDS` from dict messages. Adding `"usage"` to that frozenset is the entire change — sanitization continues to work on outbound provider calls. The provider never sees the `usage` field, so there's no risk of provider rejection.

For seeded multiturn runs, the prior trace's per-message `usage` is preserved on `TaskRun.trace` (read-side) but stripped before each LLM call (write-side). Same pattern as `latency_ms` today.

## Public Interfaces

| Module | New / Changed | Notes |
|---|---|---|
| `kiln_ai.datamodel.usage` | NEW module | Houses `Usage`. Re-exported from old paths. |
| `kiln_ai.datamodel.usage.Usage.from_trace(trace)` | NEW static method | Sums per-message usage. Returns `Usage` (never None). |
| `kiln_ai.datamodel.task_run.TaskRun.cumulative_usage` | NEW field, optional | Default `None`. |
| `kiln_ai.utils.open_ai_types.ChatCompletionAssistantMessageParamWrapper.usage` | NEW field, optional | Per-LLM-call usage. |
| `kiln_ai.utils.open_ai_types.KILN_ONLY_MESSAGE_FIELDS` | Adds `"usage"` | Existing strip mechanism covers it. |
| `LiteLlmAdapter.litellm_message_to_trace_message` | Adds `usage=` kwarg | Optional, default `None`. |
| `LiteLlmAdapter.all_messages_to_trace` | Adds `message_usage=` kwarg | Optional, default `None`. |
| `ModelTurnResult.message_usage` | NEW field, optional | Default `None`. |
| `AdapterStream._message_usage` | NEW private state | Mirrors `_message_latency`. |

All changes are additive; no existing call sites break.

## Per-message vs aggregate accounting

The per-turn accumulator `usage` inside `_run` and `AdapterStream` (which becomes `TaskRun.usage`) is preserved exactly as today. We do NOT recompute `TaskRun.usage` from the trace. Reasons:

- Backwards compatibility: `TaskRun.usage` semantics unchanged.
- Correctness: the running accumulator includes `total_llm_latency_ms` aggregation that's slightly different from per-message `latency_ms` semantics; mixing approaches risks subtle drift.
- `cumulative_usage` is the single field that uses the trace as the source of truth.

The two paths produce different values only when a prior trace is provided — that's exactly the intended difference.

## Edge Cases

| Case | Handling |
|---|---|
| `usage_from_response` returns `Usage()` (all None) | Stored as-is on the message. Sums correctly via `__add__`. |
| Provider returns no usage at all | `Usage()` per-message; cumulative becomes `Usage()` (all None) but the field is set. |
| Trace has tool/user/system messages only (no assistant) | `Usage.from_trace` returns `Usage()`. |
| Seeded prior trace messages have `usage` from prior runs | Trace-pass-through (the `else` branch in `all_messages_to_trace`) preserves them. `cumulative_usage` sums them in. |
| Seeded prior trace messages have NO `usage` (legacy) | Skipped silently; cumulative is best-effort. |
| Tool-call interruption (`return_on_tool_call`) returns mid-run | The interruption path at litellm_adapter.py:298 also calls `all_messages_to_trace`. Same change applies — pass `message_usage`. `cumulative_usage` will reflect what's been accumulated so far. |
| Streaming cancelled mid-stream | Per-message usage is only attached after a model call completes (`usage_from_response` runs after the stream iterator finishes per call). Partial calls don't contaminate. Same shape as `latency_ms` today. |
| `Usage` field name collision with `usage` from OpenAI SDK | The OpenAI SDK uses `usage` at the response level, not at the message level. No collision. |

## Error Handling

No new error paths. All additions are optional fields that default safely. `Usage.from_trace` swallows missing-key cases via `.get()`. The existing `Usage.__add__` already handles `None` gracefully.

## Logging

No new logs. The existing `logger.warning` in `usage_from_response` for unexpected formats covers anomalies in incoming data.

## Testing Strategy

Tests live alongside source per repo convention. Add to:

### `libs/core/kiln_ai/datamodel/test_usage.py` (new)

Tests for `Usage.from_trace`:

- Empty trace (`None` and `[]`) → returns `Usage()`.
- Trace with only system/user/tool messages (no assistant) → `Usage()`.
- Single assistant with `usage` → equal to that usage.
- Multiple assistants with `usage` → sum.
- Mix of assistants with and without `usage` → sum of present ones.
- Assistant with `usage` having some `None` fields → `__add__` handles, sum is partial.
- Trace dict missing `usage` key entirely → skipped, no error.

### `libs/core/kiln_ai/utils/test_open_ai_types.py`

Add tests:

- `KILN_ONLY_MESSAGE_FIELDS` contains `"usage"`.
- `sanitize_messages_for_provider` strips `usage` from assistant messages.
- A round-trip through Pydantic serialization preserves `Usage` shape on a `TaskRun.trace` containing assistant messages with `usage`.

### `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter.py`

- Mock `usage_from_response` to return distinct `Usage` per call. After `_run`, assert each assistant message in `run_output.trace` has `usage` set to that call's value, and `usage` (the running total) equals the sum.
- Tool-call loop: assert one assistant message per LLM call, each with its own `usage`.
- `all_messages_to_trace` with a `message_usage` dict: assert per-message attachment.

### `libs/core/kiln_ai/adapters/model_adapters/test_litellm_adapter_streaming.py` (or test_adapter_stream.py)

- Mock streaming completion + usage. After stream exhaustion, assert per-message usage in `result.run_output.trace` and `result.usage` matches the sum.
- Streaming with tool-call interruption: per-message usage populated for completed calls.

### `libs/core/kiln_ai/adapters/model_adapters/test_base_adapter.py` (or wherever `generate_run` is tested)

- Fresh run: `TaskRun.usage == TaskRun.cumulative_usage`.
- Seeded run with prior trace containing assistant messages with `usage`: `TaskRun.cumulative_usage > TaskRun.usage` (cumulative includes seed; `usage` does not).
- Seeded run with prior trace messages WITHOUT `usage`: `TaskRun.cumulative_usage == TaskRun.usage` (no seeded usage to add).
- Loading old TaskRun JSON (no `cumulative_usage` in file): loads, field is `None`.

### Integration: round-trip persistence

- Create a TaskRun with per-message usage, save to file, reload. Assert per-message `usage` and `cumulative_usage` are preserved.

## Migration / Deployment

None. New fields are optional with `None` defaults. Existing files load unchanged.

## Out of Scope (recap from functional spec)

- UI surfacing of per-turn or cumulative usage.
- Aggregation across TaskRuns.
- Backfill scripts for existing on-disk records.
- Changes to LiteLLM cost computation.
