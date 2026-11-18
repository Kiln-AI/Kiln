---
status: complete
---

# Architecture: Remove GEPA / Prompt Optimization

Read with [functional_spec.md](functional_spec.md). Paths are relative to each repo root. Nothing new is added except the kiln_server sunset router. Everything else is deletion or a targeted edit.

## 1. kiln_server

### 1.1 Sunset router (new)

New file `api/kiln_fastapi_api/routes/jobs/prompt_optimization_sunset.py`:

```python
"""Prompt Optimizer (GEPA) was retired. Released desktop clients (v1.0.0-v1.2.1)
still call these endpoints, so they stay and answer 410 with a pointer to
Harness Tuner. Do not add logic here."""

from typing import NoReturn
from fastapi import APIRouter, HTTPException

PROMPT_OPTIMIZER_SUNSET_MESSAGE = (
    "Prompt Optimizer has been retired. Use Kiln Harness Tuner instead: it tunes "
    "your prompts, tools, skills and model. https://github.com/Kiln-AI/harness-tuner"
)

router = APIRouter(include_in_schema=False)

def _sunset() -> NoReturn:
    raise HTTPException(status_code=410, detail={"message": PROMPT_OPTIMIZER_SUNSET_MESSAGE})

@router.get("/prompt_optimization_job/check_model_supported")
async def check_model_supported_sunset() -> NoReturn: _sunset()

@router.post("/prompt_optimization_job/start")
async def start_sunset() -> NoReturn: _sunset()

@router.get("/prompt_optimization_job/{job_id}/result")
async def result_sunset(job_id: str) -> NoReturn: _sunset()

@router.get("/gepa-job/{job_id}/status")
async def status_sunset(job_id: str) -> NoReturn: _sunset()
```

- **No parameters except the path's `job_id`.** FastAPI then never parses the query or the multipart body, so no request can fail validation with a 422. The upload body is never read; Starlette and uvicorn discard it when the response is sent.
- **`include_in_schema=False`** keeps all four out of `openapi.json`, so the next generated client doesn't have them.
- **The error body** is built by the existing `utils/error_handler.py`, which copies `detail["message"]` into the body's `message` field. That is the field old clients read in `check_response_error`.
- **Route order matters.** In `routes/jobs/__init__.py`, include `prompt_optimization_sunset.router` **before** `status_router`. Otherwise `GET /gepa-job/{id}/status` matches the generic `/{job_type}/{job_id}/status`, and its `JobType` path enum turns it into a 422.
- **Auth needs no work.** The jobs router is mounted under `api_router` (`routes/auth.py:75`), so the stubs get the same auth as before.

### 1.2 Deletions

| Path | Notes |
|---|---|
| `prompt_optimization/` | whole workspace member |
| `api/kiln_fastapi_api/routes/jobs/prompt_optimization_job.py` + test | the real routes; replaced by the sunset router |
| `jobs/kiln_server_jobs/utils/prompt_optimization_job.py` + test | |
| `gcloud/jobs/{prod,staging}/gepa-job.yml` | |
| `static/kiln_projects/copilot_chat/skills/408910145779 - kiln-chat/references/knowledge/prompt_optimizer.md` | |
| `.../references/docs/prompts/automatic-prompt-optimizer.md` | |
| `.../references/knowledge/api_docs/prompt_optimization_api_list.md` and the 7 `*prompt_optimization_jobs*` api docs | |

### 1.3 Edits

**Packaging, config and runtime:**
- **Root `pyproject.toml`:** remove the `kiln-prompt-optimization` dependency, the workspace member, the `[tool.uv.sources]` entry, `prompt_optimization` from the ty `extra-paths`, and `kiln_prompt_optimization` from the isort first-party list. Run `uv lock`.
  - `dspy` and its transitive dependencies leave the lock.
  - `tenacity` and `google-cloud-storage` stay, because `pipelines`, `api` and `jobs` declare them.
  - Check the lock diff: only packages that came in through dspy should go.
- **`Dockerfile`:** remove the `COPY prompt_optimization/pyproject.toml` line (`:29`) and the `uv pip install ./prompt_optimization` line (`:44`).
- **`.gitignore`:** remove `**/.dspy_cache/`.
- **`.vscode/settings.json`:** remove the `prompt_optimization` path entries (`:19`, `:22`).
- **`README.md`:** remove the section that explains pinning `kiln-ai` in two places (`:44-61`). Keep the single remaining pin instruction.
- **Jobs code and conftest:**
  - `jobs/kiln_server_jobs/job_types.py`: remove `GEPA_JOB`.
  - `job_registry.py`: remove the import and the registry entry.
  - `jobs/conftest.py`: remove the GEPA env-var comment.
- **`jobs/kiln_server_jobs/test_runner.py:124-234`:** replace `gepa-job` with `sample-job`. The test logic is generic and must not change otherwise.
- **`api/kiln_fastapi_api/auth/kinde_client.py:168`:** change to `type FeatureCode = str` and add a comment that codes are defined in Kinde.
  - The `org_has_entitlement`, `record_usage_for_org` and `record_feat_usage_for_user` signatures stay.
  - In `test_kinde_client.py`, `test_kinde_integration.py` and `routes/test_auth.py`, replace `"prompt-optimization"` with `"example-feature"`.
  - Exception: if `test_kinde_integration.py` hits a real Kinde tenant that needs a code that really exists, keep that one value and add a comment.
- **`api/kiln_fastapi_api/auth/examples.md`:** change the example feature code to `example-feature`.

**Agent and convention docs:**
- `.agents/skills/kiln-server-conventions/SKILL.md` (`:24`, `:60`): remove the prompt optimization mentions.
- `references/jobs_pipelines.md`: rewrite the GEPA-heavy section (`:1-65`) around the remaining jobs (`sample-job`, `data-guide-job`).
- `references/api.md`: remove the mentions at `:24`, `:52` and `:78`.
- `scripts/gate_config.json:28`: remove the `prompt_optimization` entry.

**Copilot chat skill** (`static/kiln_projects/copilot_chat/`):
- **`skill.kiln`:** in the `description`, drop "and GEPA optimization". Change no other field.
- **`task.kiln`** (`tasks/291531180356 - kiln-chat/`): edit the instruction text only.
- **Prose files:** edit `SKILL.md` and the files under `modes/`, `references/docs/` and `references/knowledge/` listed in the functional spec.
  - Remove each sentence, bullet or link about GEPA, the Prompt Optimizer, "Kiln Optimized" as something to create, or the `prompt_optimization_jobs` endpoints. Smooth the text around each removal.
  - Don't add Harness Tuner.
  - When a list of optimization levers loses an entry, leave the remaining entries as they are.
- **`api_docs/get_api_projects_project_id_tasks_task_id_agent_overview.md`:** remove the `prompt_optimization_jobs` field.
- **`KilnApiDocVerifier`** derives doc filenames from endpoint paths. Removing the docs means the hosted chat can no longer call the studio prompt optimization endpoints on old clients, which is intended.
  - Search tests for a hard-coded list of api_docs or an index (`docs_index.md`) and update it.
- **Final check:** `git grep -n -i -E '(^|[^a-z])gepa|prompt.optimi|kiln_prompt_optimizer|Kiln Optimized'` under `static/` returns nothing.

### 1.4 Tests (kiln_server)

New file `api/kiln_fastapi_api/routes/jobs/test_prompt_optimization_sunset.py`, using the authenticated test client fixture the existing route tests use:

1. Each of the 4 routes returns `410`, and `json()["message"] == PROMPT_OPTIMIZER_SUNSET_MESSAGE`. Parametrize over the 4 routes.
2. `start` with no body, with a full multipart body (`task_id`, `target_run_config_id`, `eval_ids`, `project_zip`), and with an empty `project_zip` returns 410 every time and never 422.
3. `check_model_supported` with and without `model_name` / `model_provider_name` returns 410.
4. **Route order:** `GET /v1/jobs/gepa-job/abc/status` returns 410. `GET /v1/jobs/sample-job/<id>/status` still reaches the generic handler, so the response isn't 410; mock the job class as the existing status tests do.
5. Unauthenticated requests to a stub get the same status as other unauthenticated `/v1/jobs` routes (401).
6. **OpenAPI:** `app.openapi()` has no path containing `prompt_optimization` or `gepa`, and the `JobType` schema enum has no `gepa-job`.

The kiln_server automated checks must pass (lint, ty, pytest across the workspace).

### 1.5 Final check (kiln_server)

`git grep -n -i -E '(^|[^a-z])gepa|dspy|prompt.optimi|kiln_optimizers'` shows only these:
- the sunset router and its test
- historical `specs/`
- the generic multipart and binary workarounds in `utils/generate_python_sdk.sh`, which stay because they apply to any future upload route

## 2. Infra cleanup (after the kiln_server prod deploy)

It runs from this machine. Local `gcloud` is currently broken (it runs on Python 3.8), so first set `CLOUDSDK_PYTHON` to a Python 3.9-3.14 and check `gcloud auth list` and the configured project. If the right account and permissions aren't there, write the commands below into the PR description for a human to run, and stop.

For each environment (staging, prod):

1. `gcloud run jobs describe gepa-job --region us-central1`: confirm it exists. `gcloud run jobs executions list --job gepa-job` must show nothing running.
2. **GCS:** jobs are stored at `gs://<bucket>/jobs_data/<uuid>/`, and each one has a `job_details.json` with a `job_type` field. List every `jobs_data/*/job_details.json`, keep only the ones with `job_type == "gepa-job"`, and collect their `<uuid>` prefixes. Show the count, total size and a sample to the user.
3. **Wait for an explicit go-ahead,** then:
   - `gcloud run jobs delete gepa-job --region us-central1`
   - `gcloud storage rm -r gs://<bucket>/jobs_data/<uuid>/` for each collected prefix. Never touch prefixes of other job types.

## 3. Kiln

### 3.1 Deletions

| Path |
|---|
| `app/desktop/studio_server/prompt_optimization_job_api.py`, `test_prompt_optimization_job_api.py` |
| `app/desktop/studio_server/test_multipart_boundary.py` (see 3.4) |
| `libs/core/kiln_ai/datamodel/prompt_optimization_job.py`, `test_prompt_optimization_job.py` |
| `libs/server/kiln_server/utils/agent_checks/annotations/`: the 7 prompt optimization job annotation JSON files |
| `app/web_ui/src/routes/(app)/prompt_optimization/` (whole folder, including `pro_auth/`) |
| `app/web_ui/api_schema.d.ts`: an untracked-by-tooling duplicate. Nothing imports it, and no script writes it; the generator writes `src/lib/api_schema.d.ts`. |

### 3.2 Edits (Python)

- **`app/desktop/desktop_server.py`:** remove the import (`:45-46`) and `connect_prompt_optimization_job_api(app)` (`:161`).
- **`app/desktop/studio_server/agent_api.py`:**
  - remove `AgentOverviewPromptOptimizationJobs` (`:188-189`) and the `prompt_optimization_jobs` field on the overview model (`:215`)
  - remove `_prompt_optimization_jobs_block` (`:534-537`) and its call (`:593`)
  - in `test_agent_api.py`, remove the related fixtures and assertions (`:13`, `:44`, `:604-622`, `:676`)
- **`app/desktop/studio_server/eval_api.py`:** fix the docstring at `:1770-1771` so it no longer points at `reject_unusable_train_splits`. Reword the comment at `:2184` so the train split doesn't mention prompt optimization: it's the split agents may optimize against. Don't change any logic.
- **`libs/core/kiln_ai/datamodel/task.py`:** remove the import (`:30`), the `"prompt_optimization_jobs"` entry in `parent_of` (`:137`) and the `prompt_optimization_jobs()` accessor (`:295-298`).
  - Remove the export in `datamodel/__init__.py` (`:47`, `:94`).
  - In `test_task.py`, remove the two relationship tests (`:453-505`) and add the legacy-folder test from 3.5.
- **`libs/core/kiln_ai/datamodel/prompt_type.py`:** keep `"kiln_prompt_optimizer": "Kiln Optimized"`, with a comment that the generator is retired but saved prompts still carry the id. `test_prompt_type.py` stays.
- **`libs/server/kiln_server/server.py:96-99`:** remove the "Prompt Optimization" OpenAPI tag.
- **Agent policy annotations:** if a test or generator checks that every studio route has an annotation, or the reverse (look for tests next to `agent_checks/annotations`), it must pass with the files and routes removed together.

### 3.3 Generated kiln_server client

The target is the current `app/desktop/studio_server/api_client/kiln_ai_server_client/` **minus**:
- `api/jobs/start_prompt_optimization_job_…_post.py`, `get_prompt_optimization_job_result_…_get.py` and `check_prompt_optimization_model_supported_…_get.py`
- `models/body_start_prompt_optimization_job_…_post.py`, `prompt_optimization_job_output.py`, `prompt_optimization_job_result_response.py` and `check_model_supported_response.py`
- their exports in `models/__init__.py`, and in `api/jobs/__init__.py` if it has any
- `JobType.GEPA_JOB` in `models/job_type.py`

The procedure is to regenerate, then trim the drift:
1. Run kiln_server from the PR #1 branch locally on `:8000`.
2. Run `utils/generate_python_sdk.sh`.
3. Copy `python_client/kiln_ai_server_client/` over the Kiln copy.
4. kiln_server `main` may have unrelated schema changes the Kiln client doesn't have yet. If `git diff` shows changes beyond the removal list above, revert those hunks so the commit contains **only** the removal.
5. If regeneration isn't possible, delete the same files and lines by hand. The result must be identical.

### 3.4 Multipart boundary test

`test_multipart_boundary.py` guards the generated client's multipart encoding, through the prompt optimization start body. After 3.3, no multipart (`to_multipart`) endpoint remains in the client, so delete the test.

The generator patch it protects (`utils/generate_python_sdk.sh` in kiln_server) stays, ready for any future upload route.

Check with `git grep -n to_multipart app/desktop/studio_server/api_client` after regeneration. If something still uses multipart, port the test to that endpoint instead of deleting it.

### 3.5 Legacy on-disk data

Once `prompt_optimization_jobs` is out of `Task.parent_of`, nothing enumerates `<task>/prompt_optimization_jobs/`, so the folder is ignored and never deleted.

New test in `test_task.py`:
1. Save a task.
2. Create `<task_dir>/prompt_optimization_jobs/123 - old/prompt_optimization_job.kiln` with representative JSON (`model_type: "prompt_optimization_job"`).
3. Reload the task with `Task.load_from_file`.
4. Assert it loads, its `prompts()` and `run_configs()` work, and the folder is still there.

### 3.6 Web UI edits

- **`src/lib/prompt_generators.ts`:** remove the "Automatic Optimization" category (`:16-30`). `prompt_type_selector.svelte` and the generator picker read this array, so the option disappears from both.
  - Existing prompts keep "Kiln Optimized", because labels come from the server (`prompt_type.py` via the API).
  - The generator-requirements map in the selector doesn't need the entry.
- **`routes/(app)/prompts/[project_id]/[task_id]/prompt_generators/+page.svelte:61-66`:** remove the `kiln_prompt_optimizer` redirect branch.
- **`routes/(app)/prompts/[project_id]/[task_id]/+page.svelte`:** remove the "Optimizer Jobs" action button (`:155-158`) and the "Automatically Optimize Your Prompt" banner (`:176-186`), with any imports, state or helpers that become unused.
- **`src/lib/utils/entitlement_utils.ts`:** remove `checkPromptOptimizationAccess` (`:29-40`) and keep `checkEntitlements`. If nothing else uses `checkEntitlements` afterwards, keep it anyway: it's the generic entitlement helper.
- **`src/lib/types.ts:195-198`:** remove the `PublicPromptOptimizationJobStatusResponse` and `PromptOptimizationJob` aliases.
- **`src/lib/ui/kiln_copilot/entitlement_required_card.svelte:22`:** if its docs link points at `automatic-prompt-optimizer`, and the card is used only by the deleted routes, delete the card. Otherwise point the link at the general Copilot docs.
- **`src/lib/ui/data_guide_progress_widget.svelte:66`:** reword the comment.
- **`routes/(app)/optimize/optimizers.ts:22`:** remove or reword the "automatic optimizers" wording. Make no other change to the Optimize hub.
- **`src/lib/api_schema.d.ts`:** regenerate with `src/lib/generate_schema.sh` **after** the Python changes. Then run `check_schema.sh`.
- **E2E:**
  - `tests/e2e/act/discover/prompts-management.spec.ts` (`:16`, `:23`, `:45`, `:107`, `:308-341`): drop the steps and assertions about "Kiln Optimized", the banner and "Optimizer Jobs".
  - Keep the picker test, and assert that "Kiln Optimized" is **not** listed.
  - `tests/e2e/mock_kiln_server/server.ts:5`: fix the comment.
- **`README.md`:** remove the "Auto-Optimize" bullet and links (`:30`, `:54`, `:117`).

### 3.7 Final check (Kiln)

`git grep -n -i -E '(^|[^a-z])gepa|prompt.optimi|PromptOptimization' -- ':!specs'` returns nothing. `git grep -n kiln_prompt_optimizer -- ':!specs'` returns only `prompt_type.py` and its test.

The Kiln automated checks must pass: the Python lint, types and tests, plus the web UI's lint, check and unit tests. Run the e2e `prompts-management` spec as well.

## 4. Old-client acceptance test (functional spec 1.4)

This is a manual test, run once before the kiln_server PR merges:

1. **kiln_server:** the PR #1 branch, run locally.
2. **Kiln:** the `main` checkout as it was before this project (in a separate worktree), with the desktop app pointed at the local kiln_server. Use the existing env override for the server URL, whatever the client uses, and a valid Copilot API key.
3. Walk through flows 1-5 of the functional spec (1.4). For flow 4, write a fake job file by hand: `prompt_optimization_job.kiln` with `latest_status: "running"`.
4. Record the result for each flow (screenshot or response) in the kiln_server PR description.

## 5. Docs repo (Kiln-AI/docs)

1. Clone it to `~/dev/kiln_ws_1/docs` and make a branch.
2. Find the `automatic-prompt-optimizer` page and every page that links to it or lists it as a feature (`git grep -n -i -E 'prompt.optimi|automatic-prompt-optimizer|gepa'`).
3. **On the page:** add the site's warning or callout component at the top: "Deprecated: the Prompt Optimizer has been retired. Use [Kiln Harness Tuner](https://github.com/Kiln-AI/harness-tuner), which tunes prompts, tools, skills and model together." Leave the rest of the page as it is.
4. **On listing pages:** mark the entry "(Deprecated)" and add the Harness Tuner pointer where it fits. Keep the links.
5. Use the repo's existing build or lint check, if it has one.

## 6. Error handling and logging

There's nothing new beyond the sunset router. The stubs log through the existing `HTTP_ERROR` warning path in the error handler, at warning level because 410 is below 500. That's enough to see the remaining traffic from old clients.

## 7. Risks

- **Route shadowing:** covered by test 1.4 #4.
- **Lockfile churn:** removing dspy may update shared transitive dependencies. Review the `uv.lock` diff, and pin anything that changes version unexpectedly.
- **Generated-client drift:** covered by the trimming rule in 3.3.
- **Copilot doc edits are hand edits to prose:** review the diff for sentences left broken or dangling.
