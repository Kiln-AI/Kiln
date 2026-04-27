---
status: complete
---

# Implementation Plan: Agent API Info

## Phases

- [x] Phase 1: Port `prompt_type_label` to Python + surface `type` on `ApiPrompt`; switch Svelte prompts page to consume server-computed `type` and delete TS `getPromptType`.
- [x] Phase 2: `all_tasks` endpoint + response models in `task_api.py`, with tests.
- [x] Phase 3: Extract `compute_score_summary(...)` out of `/score_summary` handler in `eval_api.py` (behavior-preserving refactor; existing tests lock in parity).
- [x] Phase 4: `eval_results_summary` endpoint + response models in `eval_api.py`, with tests (happy path, empty-filter eval, behavioral-equivalence with `/score_summary`, single-`task.runs()` perf assertion).
- [x] Phase 5: `agent_overview` endpoint in new `agent_api.py` — all response models, block helpers (`_truncate_to_words`, `_split_tool_and_skill_ids`, `_dataset_stats`, `_docs_stats`, per-section blocks, `_connected_providers_block`), route wiring via `connect_agent_api(app)`, and tests (helpers, per-block aggregators, happy path, empty task, truncation edges).
