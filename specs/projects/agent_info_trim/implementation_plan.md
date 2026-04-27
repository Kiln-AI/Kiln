---
status: complete
---

# Implementation Plan: Agent Info Trim

Two phases. Phase 1 is foundational (shared helper + endpoint rename). Phase 2 lands the bigger `agent_overview` shape changes.

## Phases

- [x] Phase 1: Add `truncate_to_words_with_agent_sentinel` + `AGENT_TRUNCATION_SENTINEL` in `libs/core/kiln_ai/utils/formatting.py`; rename `/api/all_tasks` → `/api/task_summaries` in `task_api.py` (models, handler, tests) and adopt the sentinel helper there; drop `created_at` / `instruction_truncated` from `task_summaries`; regenerate TS schema.
- [x] Phase 2: Trim `agent_overview` in `agent_api.py` — update response models (drop `created_at`, `thinking_instruction*`, `instruction_truncated`), collapse `fine_tunes` / `prompt_optimization_jobs` to count-only containers, add `AgentOverviewPrompts` / modified `AgentOverviewRunConfigs` with truncation-list shape + `generators_from_task_instruction_count`, rewrite `_prompts_block` (real-pool + top-5) and `_run_configs_block` (starred-first selection) with shared `_top_n_by_recency` helper, use sentinel helper at 70 words, update tests, regenerate TS schema.
