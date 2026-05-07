---
status: complete
---

# Implementation Plan: Multiturn Turn-Level Usage Tracking

## Phases

- [x] Phase 1: Extract `Usage` to its own module + re-exports. Pure refactor; no behavior change. Adds `Usage.from_trace` static helper. Adds `cumulative_usage` field to `TaskRun` (defaults to `None`). Adds `usage` to `ChatCompletionAssistantMessageParamWrapper` and `KILN_ONLY_MESSAGE_FIELDS`.
- [x] Phase 2: Capture per-message usage in the non-streaming adapter (`LiteLlmAdapter._run_model_turn`, `_run`, `litellm_message_to_trace_message`, `all_messages_to_trace`, `ModelTurnResult`). Compute `cumulative_usage` in `BaseAdapter.generate_run`. Tests for `Usage.from_trace`, sanitization, non-streaming round-trip, fresh vs seeded TaskRun behavior.
- [ ] Phase 3: Capture per-message usage in the streaming adapter (`AdapterStream`). Verify/enable LiteLLM `stream_options={"include_usage": True}` if needed. Streaming tests covering both stream variants and tool-call interruption.
