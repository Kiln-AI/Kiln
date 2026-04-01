---
status: draft
---

# Phase 4: Path Renames, HTTP Method Changes, and Frontend Updates

## Overview

Ship all breaking API changes together: singular→plural path standardization, run config path unification, repair/eval endpoint renames, GET→POST for 2 provider connects. Update all backend tests and frontend code to match.

## Steps

### Step 1: Task paths — singular → plural (3 endpoints)
- `libs/server/kiln_server/task_api.py`:
  - POST `/api/projects/{project_id}/task` → `/api/projects/{project_id}/tasks`
  - PATCH `/api/projects/{project_id}/task/{task_id}` → `/api/projects/{project_id}/tasks/{task_id}`
  - DELETE `/api/projects/{project_id}/task/{task_id}` → `/api/projects/{project_id}/tasks/{task_id}`

### Step 2: Prompt paths — `/task` → `/tasks` (3 endpoints)
- `libs/server/kiln_server/prompt_api.py`:
  - POST `/api/projects/{project_id}/task/{task_id}/prompt` → `/api/projects/{project_id}/tasks/{task_id}/prompts`
  - GET `/api/projects/{project_id}/task/{task_id}/prompts` → `/api/projects/{project_id}/tasks/{task_id}/prompts`
- `app/desktop/studio_server/prompt_api.py`:
  - GET `/api/projects/{project_id}/task/{task_id}/gen_prompt/{prompt_id}` → `/api/projects/{project_id}/tasks/{task_id}/gen_prompt/{prompt_id}`

### Step 3: Spec path — singular → plural (1 endpoint)
- `libs/server/kiln_server/spec_api.py`:
  - POST `/api/projects/{project_id}/tasks/{task_id}/spec` → `/api/projects/{project_id}/tasks/{task_id}/specs`

### Step 4: Eval paths — `/eval` → `/evals` (all eval endpoints + sub-paths)
- `app/desktop/studio_server/eval_api.py`:
  - GET `/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}` → `/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`
  - DELETE `/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}` → `/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`
  - PATCH `/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}` → `/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}`
  - GET `.../eval/{eval_id}/eval_configs` → `.../evals/{eval_id}/eval_configs`
  - GET `.../eval/{eval_id}/eval_config/{eval_config_id}` → `.../evals/{eval_id}/eval_config/{eval_config_id}`
  - POST `.../eval/{eval_id}/create_eval_config` → `.../evals/{eval_id}/create_eval_config`
  - GET `.../eval/{eval_id}/eval_config/{eval_config_id}/run_task_run_eval` → `.../evals/{eval_id}/eval_config/{eval_config_id}/run_comparison`
  - POST `.../eval/{eval_id}/set_current_eval_config/{eval_config_id}` → `.../evals/{eval_id}/set_current_eval_config/{eval_config_id}`
  - GET `.../eval/{eval_id}/run_eval_config_eval` → `.../evals/{eval_id}/run_calibration`
  - GET `.../eval/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results` → `.../evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results`
  - GET `.../eval/{eval_id}/progress` → `.../evals/{eval_id}/progress`
  - GET `.../eval/{eval_id}/eval_config/{eval_config_id}/score_summary` → `.../evals/{eval_id}/eval_config/{eval_config_id}/score_summary`
  - GET `.../eval/{eval_id}/eval_configs_score_summary` → `.../evals/{eval_id}/eval_configs_score_summary`
  - GET `.../run_config/{run_config_id}/eval_scores` → `.../run_configs/{run_config_id}/eval_scores`

### Step 5: Run config path unification (3 endpoints)
- `app/desktop/studio_server/eval_api.py`:
  - GET `.../run_configs/` → `.../run_configs` (remove trailing slash)
  - POST `.../task_run_config` → `.../run_configs`
  - PATCH `.../run_config/{run_config_id}` → `.../run_configs/{run_config_id}`
- `app/desktop/studio_server/run_config_api.py`:
  - POST `.../mcp_run_config` → `.../run_configs/mcp`

### Step 6: Repair endpoint path renames (2 endpoints)
- `app/desktop/studio_server/repair_api.py`:
  - POST `.../runs/{run_id}/run_repair` → `.../runs/{run_id}/generate_repair`
  - POST `.../runs/{run_id}/repair` → `.../runs/{run_id}/save_repair`

### Step 7: GET → POST for provider connect (2 endpoints)
- `app/desktop/studio_server/provider_api.py`:
  - GET `/api/provider/ollama/connect` → POST
  - GET `/api/provider/docker_model_runner/connect` → POST

### Step 8: Update backend tests
- `libs/server/kiln_server/test_task_api.py` — update all `/task/` references to `/tasks/`
- `libs/server/kiln_server/test_prompt_api.py` — update `/task/` references to `/tasks/`
- `libs/server/kiln_server/test_spec_api.py` — update `/spec` to `/specs`
- `app/desktop/studio_server/test_repair_api.py` — update repair paths
- `app/desktop/studio_server/test_eval_api.py` — update eval paths, run_config paths
- `app/desktop/studio_server/test_server.py` — update ollama connect from GET to POST
- `app/desktop/studio_server/test_provider_api.py` — update docker_model_runner connect from GET to POST
- `app/desktop/studio_server/test_run_config_api.py` — update mcp_run_config path

### Step 9: Update frontend TypeScript/Svelte
- `app/web_ui/src/lib/stores/run_configs_store.ts` — update `/run_configs/`, `/task_run_config`, `/task/{task_id}`, `/mcp_run_config`
- `app/web_ui/src/lib/stores/prompts_store.ts` — update `/task/{task_id}/prompts`
- `app/web_ui/src/lib/stores/evals_store.ts` — update eval paths
- All svelte files with hardcoded API paths (edit_task, connect_providers, spec_builder, compare, eval_configs, compare_run_configs, run_result, create_eval_config, spec page, eval page, output_repair_edit_form, run.svelte)

### Step 10: Regenerate api_schema.d.ts
- Run `generate_schema.sh` to regenerate the types file

### Step 11: Run lint, format, tests
- `ruff check --fix` and `ruff format` on all modified files
- `uv run pytest libs/server/tests/ app/desktop/studio_server/test_*.py -x --timeout=30`
- `npx svelte-check --threshold error` in `app/web_ui/`
