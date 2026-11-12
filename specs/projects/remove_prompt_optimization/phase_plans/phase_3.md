---
status: complete
---

# Phase 3: Kiln backend removal

## Overview

Remove the Prompt Optimizer from the Kiln Python side: the studio API routes, the `PromptOptimizationJob` datamodel and its `Task` relationship, the agent overview block, the agent-policy annotations, the OpenAPI tag, and the three job endpoints in the generated kiln_server client (regenerated from the kiln_server branch with the sunset stubs). Fix the wording that refers to the feature. Existing user data keeps loading: `kiln_prompt_optimizer` prompts still show "Kiln Optimized", and a legacy `prompt_optimization_jobs/` folder under a task is ignored. Web UI changes and the `api_schema.d.ts` regeneration are Phase 4.

## Steps

1. **Delete** `app/desktop/studio_server/prompt_optimization_job_api.py` and its test, `libs/core/kiln_ai/datamodel/prompt_optimization_job.py` and its test, and the 7 `*prompt_optimization*` annotation JSON files under `libs/server/kiln_server/utils/agent_checks/annotations/`.
2. **`app/desktop/desktop_server.py`:** remove the `connect_prompt_optimization_job_api` import and call.
3. **`app/desktop/studio_server/agent_api.py`:** remove `AgentOverviewPromptOptimizationJobs`, the `prompt_optimization_jobs` field on `AgentOverview`, `_prompt_optimization_jobs_block` and its call. In `test_agent_api.py`, remove the import, the block tests and the endpoint assertion.
4. **`app/desktop/studio_server/eval_api.py`:** reword the `require_dataset_run_test_split_or_400` docstring so it doesn't cite `reject_unusable_train_splits`; reword the train-split comment in the update-eval handler ("the split agents may optimize against"). No logic change.
5. **`libs/core/kiln_ai/datamodel/task.py`:** remove the import, the `parent_of` entry and the `prompt_optimization_jobs()` accessor. Remove the export from `datamodel/__init__.py`.
6. **`libs/core/kiln_ai/datamodel/prompt_type.py`:** keep the `kiln_prompt_optimizer` label, with a comment that saved prompts still carry the id.
7. **`libs/server/kiln_server/server.py`:** remove the "Prompt Optimization" tag from `tags_metadata`.
8. **`app/desktop/studio_server/test_settings_api.py`:** replace the example feature code `prompt-optimization` with `example-feature` (the generic entitlement route accepts any code).
9. **Generated client (§3.3):** run kiln_server from its `leonard/remove-prompt-optimization` branch on `:8000`, run `utils/generate_python_sdk.sh`, copy `python_client/kiln_ai_server_client/` over `app/desktop/studio_server/api_client/kiln_ai_server_client/`, and revert any hunk outside the removal list (3 endpoint modules, 4 models, their `models/__init__.py` exports, `JobType.GEPA_JOB`). Stop the server and delete the generated `python_client/` afterwards if it wasn't there before.
10. **Multipart test (§3.4):** after regeneration, `git grep to_multipart app/desktop/studio_server/api_client`. If nothing remains, delete `test_multipart_boundary.py`; otherwise port it to the remaining endpoint.
11. **Annotation checks:** run the agent-policy annotation tests / `check_api_bindings` equivalent locally so the removed routes and annotation files agree.

## Tests

- `test_task.py::test_task_loads_with_unknown_legacy_child_folder`: a task with a saved prompt and run config plus a hand-written `prompt_optimization_jobs/123 - old/prompt_optimization_job.kiln` loads with `Task.load_from_file`, `prompts()` and `run_configs()` return the saved children, no warning or log record is emitted, and the legacy file is unchanged. Replaces the two relationship tests.
- `test_prompt_type.py` stays: `kiln_prompt_optimizer` still maps to "Kiln Optimized".
- `test_agent_api.py` endpoint test passes without the removed field.
- Full Python checks: `ruff check`, `ruff format --check`, `ty check`, pytest across the repo, and the conventions gate on the worktree.
