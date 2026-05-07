---
status: complete
---

# Architecture: Multiturn Turn-Level Usage Tracking

## Scope decision: single architecture doc

Small data-layer change. Touches ~5 files in `libs/core`. No separate component designs; everything fits here.

## Data Model

### Module location: `libs/core/kiln_ai/datamodel/usage.py`

`Usage` was originally defined in `libs/core/kiln_ai/datamodel/task_run.py`. To reference it from `libs/core/kiln_ai/utils/open_ai_types.py` (which `task_run.py` already imports from) without creating a cycle, the model lives in `libs/core/kiln_ai/datamodel/usage.py`. Re-exports from `task_run.py` and `kiln_ai.datamodel.__init__.py` preserve all external import paths.

Cycle check: `usage.py` has no Kiln imports; both `open_ai_types.py` and `task_run.py` import from it. No cycle.

### `MessageUsage` (base) + `Usage` (subclass with latency)

`usage.py` defines two classes:

- `MessageUsage(BaseModel)` — five aggregatable fields: `input_tokens`, `output_tokens`, `total_tokens`, `cached_tokens`, `cost`. `__add__(self, other: MessageUsage) -> MessageUsage` sums them with the existing None-graceful pattern.
- `Usage(MessageUsage)` — adds `total_llm_latency_ms`. Its `__add__(self, other: MessageUsage | Usage) -> Usage` sums the five base fields and, when `other` is also a `Usage`, sums `total_llm_latency_ms` too. When `other` is a plain `MessageUsage`, `self`'s latency is carried through unchanged. Always returns a `Usage` so chained `usage += per_message_usage` keeps the latency on the accumulator.

Why split: per-message records and full-trace sums (`cumulative_usage`) cannot meaningfully carry a single "total LLM latency" — each message already has its own `latency_ms`, and summing latencies across turns or seeded prior traces mixes values that were never simultaneously in flight. Only the in-flight per-run accumulator (`TaskRun.usage`) has a meaningful aggregate latency.

Re-exports:

- `from kiln_ai.datamodel.task_run import MessageUsage as MessageUsage` (and the existing `Usage as Usage`).
- `from kiln_ai.datamodel.task_run import MessageUsage, TaskRun, Usage` in `kiln_ai.datamodel.__init__`, with `"MessageUsage"` added to `__all__`.

### `MessageUsage.from_trace`

```python
@staticmethod
def from_trace(trace: list[ChatCompletionMessageParam] | None) -> "MessageUsage":
    """Sum per-message usage across all assistant messages in a trace.
    Returns MessageUsage() (all-None fields) when trace is None or no messages have usage.
    Skips non-assistant messages and messages without a `usage` field."""
```

Implementation: iterate `trace`, for each message where `role == "assistant"` and `usage` is present and non-None, accumulate via `MessageUsage.__add__`. Accepts both `MessageUsage` instances (including the `Usage` subclass) and plain dicts (post-JSON-roundtrip), validating dicts via `MessageUsage.model_validate` before summing.

`MessageUsage()` (all `None`) is returned for empty/missing-data cases. Always returns a `MessageUsage` instance — never `None`. Callers distinguish "this run was created post-change" from "pre-change" by checking the field on `TaskRun` (which IS `None` for old records).

### Per-message `usage` field on assistant messages

`libs/core/kiln_ai/utils/open_ai_types.py`:

- Import `MessageUsage` from `kiln_ai.datamodel.usage`.
- Add to `ChatCompletionAssistantMessageParamWrapper`:
  ```python
  usage: Optional[MessageUsage]
  """Token usage and cost for the LLM call that produced this assistant message.
  Set per-call (not per logical turn). Stripped before sending to providers via KILN_ONLY_MESSAGE_FIELDS.
  Per-call latency lives on the message's `latency_ms` field — MessageUsage intentionally does not carry latency."""
  ```
- Add `"usage"` to `KILN_ONLY_MESSAGE_FIELDS`. `sanitize_messages_for_provider` already handles strip-by-key — no changes there.

Since the wrapper is a `TypedDict`, the field is structurally optional. Pydantic serializes nested `MessageUsage` objects fine when the trace is part of `TaskRun` (Pydantic walks TypedDict values).

The per-message field is `MessageUsage` (no latency). The canonical per-call latency stays on the message's own `latency_ms` field. No duplication.

### `TaskRun.cumulative_usage`

`libs/core/kiln_ai/datamodel/task_run.py`:

```python
cumulative_usage: MessageUsage | None = Field(
    default=None,
    description=(
        "Sum of per-message token usage and cost across the entire trace, "
        "including any seeded prior trace. None on records created before "
        "this field existed. For a fresh (non-seeded) run, the token / "
        "cost fields equal those of `usage`."
    ),
)
```

`usage` field stays `Usage | None` (unchanged) — it's the in-flight accumulator that meaningfully carries `total_llm_latency_ms`.

Pydantic narrows: assigning a `Usage` to the `MessageUsage`-typed `cumulative_usage` field auto-strips `total_llm_latency_ms` on the next round-trip. Loading a legacy JSON payload that includes a stale `cumulative_usage.total_llm_latency_ms` key is also safe — Pydantic's default `extra="ignore"` drops it.

## Component Breakdown

### `LiteLlmAdapter._run_model_turn` (litellm_adapter.py:113-236)

Add per-call usage capture parallel to `message_latency`.

- Add local: `message_usage: dict[int, MessageUsage] = {}`
- After line 151 (`usage += self.usage_from_response(model_response)`), capture the per-call usage:
  ```python
  call_usage = self.usage_from_response(model_response)  # returns MessageUsage
  usage += call_usage  # Usage.__add__ accepts MessageUsage, returns Usage
  usage.total_llm_latency_ms = (usage.total_llm_latency_ms or 0) + call_latency_ms
  # ... existing message append ...
  message_latency[len(messages) - 1] = call_latency_ms
  message_usage[len(messages) - 1] = call_usage
  ```
- Add `message_usage` field to `ModelTurnResult` dataclass:
  ```python
  message_usage: dict[int, MessageUsage] | None = None
  ```
- Return `message_usage=message_usage` in all three `ModelTurnResult(...)` construction sites in this method (lines 182, 204, 220).

### `LiteLlmAdapter._run` (litellm_adapter.py:238-330)

Aggregate `message_usage` across turns (parallel to existing `message_latency` aggregation at line 290).

- Add local: `message_usage: dict[int, MessageUsage] = {}`
- After `if turn_result.message_latency: message_latency.update(turn_result.message_latency)`, add:
  ```python
  if turn_result.message_usage:
      message_usage.update(turn_result.message_usage)
  ```
- Pass `message_usage` to both `all_messages_to_trace` calls (line 298 for tool-call interruption; line 322 for normal completion).

### `LiteLlmAdapter.usage_from_response`

Returns `MessageUsage` (was `Usage`). The function never set `total_llm_latency_ms`, so this is a pure type narrowing.

```python
def usage_from_response(self, response: ModelResponse) -> MessageUsage:
    ...
```

### `LiteLlmAdapter.litellm_message_to_trace_message` (litellm_adapter.py:877-927)

Accept optional `usage` and attach it.

```python
def litellm_message_to_trace_message(
    self,
    raw_message: LiteLLMMessage,
    latency_ms: int | None = None,
    usage: MessageUsage | None = None,
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
    message_usage: dict[int, MessageUsage] | None = None,
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

- Add to `__init__`: `self._message_usage: dict[int, MessageUsage] = {}`
- In `_stream_model_turn` (line 150-...):
  - Capture per-call usage right after `usage_from_response` (line 173):
    ```python
    call_usage = self._adapter.usage_from_response(response)  # MessageUsage
    usage += call_usage  # Usage.__add__ accepts MessageUsage
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
run.cumulative_usage = MessageUsage.from_trace(trace)
```

Or pass directly in the constructor if `trace` is available before construction. Either approach is fine; pick the simpler one.

This computes from the FULL trace (which already includes any seeded prior trace's messages with their original `usage`), so `cumulative_usage` is correct for both fresh and seeded runs without further special-casing. `MultiturnFormatter` doesn't need any changes.

### Sanitization

Existing `sanitize_messages_for_provider` strips `KILN_ONLY_MESSAGE_FIELDS` from dict messages. Adding `"usage"` to that frozenset is the entire change — sanitization continues to work on outbound provider calls. The provider never sees the `usage` field, so there's no risk of provider rejection.

For seeded multiturn runs, the prior trace's per-message `usage` is preserved on `TaskRun.trace` (read-side) but stripped before each LLM call (write-side). Same pattern as `latency_ms` today.

## Public Interfaces

| Module | New / Changed | Notes |
|---|---|---|
| `kiln_ai.datamodel.usage` | NEW module | Houses `MessageUsage` (base) + `Usage` (subclass). Re-exported from old paths. |
| `kiln_ai.datamodel.usage.MessageUsage` | NEW base class | Five aggregatable fields (no latency). |
| `kiln_ai.datamodel.usage.MessageUsage.from_trace(trace)` | NEW static method | Sums per-message usage. Returns `MessageUsage` (never None). |
| `kiln_ai.datamodel.usage.Usage` | Existing class, now subclass | Adds `total_llm_latency_ms`. `__add__` accepts `Usage \| MessageUsage`, returns `Usage`. |
| `kiln_ai.datamodel.task_run.TaskRun.cumulative_usage` | NEW field, optional | Typed `MessageUsage \| None`. Default `None`. |
| `kiln_ai.datamodel.MessageUsage` | NEW re-export | Mirrors the existing `Usage` re-export. |
| `kiln_ai.utils.open_ai_types.ChatCompletionAssistantMessageParamWrapper.usage` | NEW field, optional | Typed `Optional[MessageUsage]`. Per-LLM-call usage. |
| `kiln_ai.utils.open_ai_types.KILN_ONLY_MESSAGE_FIELDS` | Adds `"usage"` | Existing strip mechanism covers it. |
| `LiteLlmAdapter.usage_from_response` | Return type | Now `MessageUsage`. |
| `LiteLlmAdapter.litellm_message_to_trace_message` | Adds `usage=` kwarg | Optional `MessageUsage`, default `None`. |
| `LiteLlmAdapter.all_messages_to_trace` | Adds `message_usage=` kwarg | Optional `dict[int, MessageUsage]`, default `None`. |
| `ModelTurnResult.message_usage` | NEW field, optional | `dict[int, MessageUsage] \| None`. Default `None`. |
| `AdapterStream._message_usage` | NEW private state | `dict[int, MessageUsage]`. Mirrors `_message_latency`. |

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
| `usage_from_response` returns `MessageUsage()` (all None) | Stored as-is on the message. Sums correctly via `__add__`. |
| Provider returns no usage at all | `MessageUsage()` per-message; cumulative becomes `MessageUsage()` (all None) but the field is set. |
| Trace has tool/user/system messages only (no assistant) | `MessageUsage.from_trace` returns `MessageUsage()`. |
| Seeded prior trace messages have `usage` from prior runs | Trace-pass-through (the `else` branch in `all_messages_to_trace`) preserves them. `cumulative_usage` sums them in. |
| Seeded prior trace messages have NO `usage` (legacy) | Skipped silently; cumulative is best-effort. |
| Pre-split TaskRun JSON with `cumulative_usage.total_llm_latency_ms` | Pydantic's default `extra="ignore"` drops the unknown field on the narrowed `MessageUsage`. Loads cleanly. |
| Tool-call interruption (`return_on_tool_call`) returns mid-run | The interruption path at litellm_adapter.py:298 also calls `all_messages_to_trace`. Same change applies — pass `message_usage`. `cumulative_usage` will reflect what's been accumulated so far. |
| Streaming cancelled mid-stream | Per-message usage is only attached after a model call completes (`usage_from_response` runs after the stream iterator finishes per call). Partial calls don't contaminate. Same shape as `latency_ms` today. |
| `usage` field name collision with `usage` from OpenAI SDK | The OpenAI SDK uses `usage` at the response level, not at the message level. No collision. |

## Error Handling

No new error paths. All additions are optional fields that default safely. `MessageUsage.from_trace` swallows missing-key cases via `.get()`. Both `MessageUsage.__add__` and `Usage.__add__` handle `None` gracefully on every aggregatable field.

## Logging

No new logs. The existing `logger.warning` in `usage_from_response` for unexpected formats covers anomalies in incoming data.

## Testing Strategy

Tests live alongside source per repo convention. Add to:

### `libs/core/kiln_ai/datamodel/test_usage.py`

Tests for `MessageUsage.from_trace`:

- Empty trace (`None` and `[]`) → returns `MessageUsage()`.
- Trace with only system/user/tool messages (no assistant) → `MessageUsage()`.
- Single assistant with `usage` → equal to that usage.
- Multiple assistants with `usage` → sum.
- Mix of assistants with and without `usage` → sum of present ones.
- Assistant with `usage` having some `None` fields → `__add__` handles, sum is partial.
- Trace dict missing `usage` key entirely → skipped, no error.

Tests for the `MessageUsage` / `Usage` split:

- `MessageUsage + MessageUsage` returns `MessageUsage` (not `Usage`); no latency field.
- `Usage + Usage` sums `total_llm_latency_ms`.
- `Usage + MessageUsage` carries `self`'s `total_llm_latency_ms` through unchanged.
- `MessageUsage.__add__` rejects non-`MessageUsage` operands with `TypeError`.
- `issubclass(Usage, MessageUsage)`.
- `MessageUsage.model_validate({..., "total_llm_latency_ms": ...})` silently drops the legacy key.

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
