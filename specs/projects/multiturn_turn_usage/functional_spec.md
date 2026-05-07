---
status: complete
---

# Functional Spec: Multiturn Turn-Level Usage Tracking

## Goal

Persist per-LLM-call token usage and cost on each assistant message in the TaskRun trace, mirroring how `latency_ms` is already stored. Preserve the existing `TaskRun.usage` semantics (this run's new-turn cost) and add a new `TaskRun.cumulative_usage` field representing the full-trace sum including any seeded prior trace.

## Non-Goals

- No UI changes. This project is purely data-layer: capture and persist. Any UI surfacing comes later.
- No backfill of existing TaskRun records on disk. Old runs keep their existing aggregate `usage`; per-message usage and `cumulative_usage` only appear on runs created after this change.

## Behavior

### Per-Message Usage (New)

A new optional Kiln-only field is added to the assistant message wrapper:

- `usage`: an optional `Usage` object describing the cost of producing **that single LLM call** (the call whose response materialized as this assistant message).

This mirrors the existing `latency_ms` field on assistant messages, which is already populated per-LLM-call. The `Usage` payload reuses the existing `Usage` model unchanged: `input_tokens`, `output_tokens`, `total_tokens`, `cached_tokens`, `cost`, `total_llm_latency_ms`.

`total_llm_latency_ms` on a per-message `Usage` is redundant with the message's own `latency_ms` and SHOULD be left `None` on the per-message record (or set equal to `latency_ms`); the canonical per-call latency stays on `latency_ms`. Implementation may choose either; pick one and apply consistently.

`usage` is added to `KILN_ONLY_MESSAGE_FIELDS` so existing sanitization logic strips it before sending messages back to the LLM provider.

### TaskRun.usage Semantics (Unchanged)

`TaskRun.usage` continues to mean **this run's contribution only** — the sum of usage across the new turns added by this run. Behavior for fresh (non-seeded) runs is identical to today. For seeded runs, `TaskRun.usage` excludes the seeded prior trace's usage.

Implementation continues to accumulate `usage` per turn inside `_run()` as it does today (`usage += turn_result.usage`).

### TaskRun.cumulative_usage (New)

A new optional field `cumulative_usage: Usage | None` is added to `TaskRun`. It represents the sum of per-message usage across the **entire final trace**, including any messages carried in from a seeded prior trace.

- For a fresh (non-seeded) run, `cumulative_usage` equals `usage`.
- For a seeded run, `cumulative_usage` = `usage` + sum of per-message usage on the seeded prior trace's messages.

Aggregation guidance: callers totalling cost across a chain of related TaskRuns should sum `usage` (not `cumulative_usage`) to avoid double-counting. To get the total cost of a conversation given only its latest TaskRun, read `cumulative_usage`.

If any seeded message has no `usage` (e.g., legacy or pre-change records), it contributes nothing (the existing `Usage.__add__` handles `None` gracefully). `cumulative_usage` is best-effort.

### Computation

Per-message usage is captured at the same point usage is extracted today: `usage_from_response()` in `litellm_adapter.py`. The mechanism mirrors `message_latency: dict[int, int]` — a parallel `message_usage: dict[int, Usage]` keyed by message index, attached to assistant messages by `all_messages_to_trace()`.

`cumulative_usage` is computed at run-finalization time as the sum of per-message usage across all assistant messages in the full final trace (seeded prior trace + new messages). User, system, and tool messages don't carry usage and are skipped.

`usage` is NOT recomputed; it remains the running per-turn accumulator's final value, as today.

### Streaming

Both streaming paths must populate per-message usage:

- **OpenAI streaming** (`invoke_openai_stream`): final-chunk usage from the LiteLLM stream is attached to the corresponding assistant message at finalization (`_finalize_stream`). Requires LiteLLM `stream_options={"include_usage": True}` (verify it's already set; add if not).
- **AI SDK streaming** (`invoke_ai_sdk_stream`): same — finalization writes the per-message usage onto the trace before persisting the TaskRun.

Tool-call-driven internal LLM calls within a single user-visible turn each get their own assistant message and their own per-message usage, identical to non-streaming.

### Seeding (MultiturnFormatter)

`MultiturnFormatter.initial_messages()` continues to return the prior trace verbatim. No transformation, stripping, or recomputation of usage on prior messages. If the prior trace has per-message usage from a previous run, it flows through into the new TaskRun's final trace and contributes to `TaskRun.cumulative_usage` (but not to `TaskRun.usage`).

The prior trace is not re-billed: those messages are not sent to the LLM again, so no new usage is incurred for them. `cumulative_usage` simply rolls up what's already on those messages.

## Edge Cases

| Case | Behavior |
|------|----------|
| Provider returns no usage on a response | Per-message `usage` is `None`. Cumulative sum simply skips it. |
| Seeded prior trace has messages with no `usage` (legacy / pre-change runs) | Same: those messages contribute nothing to `cumulative_usage`. Best-effort. |
| Seeded prior trace has `usage` on every message | All seeded usage flows into `cumulative_usage`. `usage` is unaffected. |
| Tool-call loop with N internal LLM calls in one turn | N assistant messages each with their own `usage`. Sum across them is the turn's cost. |
| LiteLLM `response_cost` missing | `Usage.cost` is `None` for that message. Token counts may still populate. |
| Streaming run is cancelled mid-stream | Per-message usage is populated only for completed assistant messages (same as `latency_ms` today). Partial-message usage is not synthesized. |
| Old TaskRun loaded from disk with no per-message usage | Loads fine. `TaskRun.usage` retains its previously-saved value; `TaskRun.cumulative_usage` is `None` (Pydantic default) — it is not synthesized on load. |

## Backwards Compatibility

- **Loading old TaskRun JSON**: New optional fields default to `None`; old files load unchanged.
- **`TaskRun.usage` semantics**: Unchanged. No behavior change for any existing consumer.
- **`TaskRun.cumulative_usage`**: `None` on old records. Consumers that need it should fall back to `TaskRun.usage` when `cumulative_usage` is `None` (or treat the absence as "unknown").
- **No migration / rewrite of existing TaskRun files.**
- **`KILN_ONLY_MESSAGE_FIELDS`**: gains `usage`. Existing sanitization that strips Kiln-only fields before sending to providers continues to work for the new field.

## Public API Surface (libs/core)

Per project memory: `libs/core` is a standalone library; the public API surface must be complete even if no in-repo code exercises it. The new fields — `usage` on the assistant message wrapper, `cumulative_usage` on `TaskRun` — are part of the public Pydantic schema and are documented in the model docstrings.

## Out of Scope

- UI changes (run viewer, chat pane) to display per-turn or cumulative usage.
- New REST API endpoints. Existing endpoints that already serialize TaskRun automatically pick up the new field.
- Backfill scripts.
- Aggregation across TaskRuns (e.g., per-task or per-project totals).
- Changes to how cost is computed (still LiteLLM's `response_cost`).
