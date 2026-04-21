---
status: complete
---

# Phase 1: Sentinel Helper + task_summaries Rename

## Overview

Add the reusable `truncate_to_words_with_agent_sentinel` helper and `AGENT_TRUNCATION_SENTINEL` constant to `libs/core/kiln_ai/utils/formatting.py`. Rename `/api/all_tasks` to `/api/task_summaries` with updated models and handler. Drop `created_at` and `instruction_truncated` from the task_summaries response, adopting the sentinel helper instead. Regenerate the TS schema.

## Steps

1. Add `AGENT_TRUNCATION_SENTINEL` constant and `truncate_to_words_with_agent_sentinel(text, max_words)` to `libs/core/kiln_ai/utils/formatting.py`.

2. In `libs/server/kiln_server/task_api.py`:
   - Rename `AllTasksTask` -> `TaskSummary`, drop `instruction_truncated` and `created_at` fields.
   - Rename `AllTasksProject` -> `TaskSummariesProject`, drop `created_at` field.
   - Rename `AllTasksResponse` -> `TaskSummariesResponse`.
   - Rename route from `/api/all_tasks` to `/api/task_summaries`, function from `all_tasks` to `task_summaries`, summary to `"Task Summaries (agent-tuned)"`.
   - Add docstring per functional spec.
   - Switch import from `truncate_to_words` to `truncate_to_words_with_agent_sentinel`.
   - Replace `(text, bool)` tuple unpack with single call to `truncate_to_words_with_agent_sentinel(task.instruction, 100)`.

3. Update `libs/server/kiln_server/test_task_api.py`:
   - Retarget all `all_tasks` tests to `/api/task_summaries`.
   - Update assertions: remove `instruction_truncated` and `created_at` checks.
   - Add sentinel assertion for truncated instructions.
   - Add test confirming `/api/all_tasks` returns 404.

4. Add `libs/core/kiln_ai/utils/test_formatting.py` with tests for the new helper:
   - Under limit: no sentinel.
   - At limit: no sentinel.
   - Over limit: sentinel appended.
   - None input: returns None.
   - Empty string: returns empty string.
   - Trailing whitespace at cut point: no double spaces.
   - Constant value check.

5. Regenerate TS schema via `app/web_ui/src/lib/generate_schema.sh`.

## Tests

- `test_truncate_to_words_with_agent_sentinel_under_limit`: no sentinel appended
- `test_truncate_to_words_with_agent_sentinel_at_limit`: no sentinel appended
- `test_truncate_to_words_with_agent_sentinel_over_limit`: sentinel appended correctly
- `test_truncate_to_words_with_agent_sentinel_none`: returns None
- `test_truncate_to_words_with_agent_sentinel_empty`: returns empty string
- `test_truncate_to_words_with_agent_sentinel_trailing_whitespace`: no double spaces
- `test_agent_truncation_sentinel_value`: constant matches expected literal
- `test_task_summaries_happy_path`: renamed from all_tasks, drops created_at/instruction_truncated
- `test_task_summaries_truncation_over_limit`: sentinel present instead of bool+ellipsis
- `test_task_summaries_instruction_at_limit`: no sentinel
- `test_task_summaries_instruction_under_limit`: no sentinel
- `test_task_summaries_old_path_returns_404`: confirms /api/all_tasks is gone
