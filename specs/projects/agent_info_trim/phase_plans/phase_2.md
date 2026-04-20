---
status: complete
---

# Phase 2: Trim agent_overview response

## Overview

Update the `agent_overview` endpoint in `agent_api.py` to drop low-signal fields (`created_at`, `thinking_instruction*`, `instruction_truncated`), collapse `fine_tunes`/`prompt_optimization_jobs` to count-only containers, introduce truncation-list shape for `prompts` (real-pool + top-5 + generator count) and `run_configs` (starred-first selection), and use the sentinel helper at 70 words for task.instruction.

## Steps

1. Update response models in `agent_api.py`:
   - Drop `created_at` from `AgentOverviewProject`, `AgentOverviewTask`, `AgentOverviewSearchTool`, `AgentOverviewSpec`, `AgentOverviewEval`, `AgentOverviewToolServer`, `AgentOverviewRunConfig`, `AgentOverviewSkill`
   - Drop `instruction_truncated`, `thinking_instruction`, `thinking_instruction_truncated` from `AgentOverviewTask`
   - Delete `AgentOverviewFineTune` and `AgentOverviewPromptOptimizationJob` models
   - Add `AgentOverviewFineTunes(total_count: int)` and `AgentOverviewPromptOptimizationJobs(total_count: int)`
   - Add `AgentOverviewPrompts(total, showing, generators_from_task_instruction_count, items)`
   - Add `total` and `showing` to `AgentOverviewRunConfigs`
   - Update `AgentOverview` root model field types

2. Add `_top_n_by_recency` private helper for shared selection logic

3. Rewrite `_prompts_block`:
   - Compute `generators_from_task_instruction_count = len(prompt_generators)`
   - Build real pool (persisted prompts + fine-tune virtuals + task_run_config virtuals) with `created_at` for sorting
   - Select top 5 by recency using `_top_n_by_recency`
   - Return `AgentOverviewPrompts` container

4. Rewrite `_run_configs_block`:
   - Split starred/unstarred, sort each by recency
   - If starred >= 5: return all starred; else pad from unstarred up to 5
   - Return `AgentOverviewRunConfigs` with `total` and `showing`

5. Replace `_fine_tunes_block` and `_prompt_optimization_jobs_block` with count-only versions

6. Update route handler:
   - Use `truncate_to_words_with_agent_sentinel(task.instruction, 70)`
   - Remove thinking_instruction handling
   - Remove `run_configs_by_id` (no longer needed)
   - Drop `created_at` from project/task construction

7. Update all helper functions to drop `created_at` from items

8. Update tests in `test_agent_api.py`

9. Regenerate TS schema

## Tests

- Test `_prompts_block` returns only real pool items (no generators), capped at 5, with correct `total`/`showing`/`generators_from_task_instruction_count`
- Test `_run_configs_block` starred-first selection with various cases (all starred, mixed, none starred)
- Test `_top_n_by_recency` selection and ordering
- Test endpoint drops `created_at`, `instruction_truncated`, `thinking_instruction*`
- Test `fine_tunes`/`prompt_optimization_jobs` return count-only shape
- Test instruction truncation at 70 words with sentinel
