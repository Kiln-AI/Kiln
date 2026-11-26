---
status: complete
---

# Functional Spec: Remove GEPA / Prompt Optimization

Remove the GEPA-based Prompt Optimizer from kiln_server, Kiln, and the docs site. Released desktop clients (v1.0.0 to v1.2.1) still ship the feature. They must keep working without crashing, and anyone who tries the feature is told to use [Harness Tuner](https://github.com/Kiln-AI/harness-tuner).

No optimization jobs are in flight, so there's no running or unfinished job to migrate or protect.

## 1. Sunset contract for older clients (kiln_server)

### 1.1 Endpoints kept as stubs

These four endpoints stay registered, but they do nothing except return the sunset error:

| Method | Path (under `/v1/jobs`) | Old client caller |
|---|---|---|
| GET | `/prompt_optimization_job/check_model_supported` | `check_run_config` and `check_eval` on the create-job page |
| POST | `/prompt_optimization_job/start` | Start job |
| GET | `/prompt_optimization_job/{job_id}/result` | Job detail page, and artifact creation after a succeeded status |
| GET | `/gepa-job/{job_id}/status` | Job list refresh and job detail page |

Every stub behaves as follows:

- **Response:** `410 Gone`, with a JSON body whose `message` field holds the sunset message (section 1.2). The body goes through the existing error handler, so it also carries the usual `trace_id`.
- **Auth:** the same as the other `/v1/jobs` routes. An unauthenticated call still gets the normal `401`.
- **Validation:** none. Any query parameters, path values or multipart fields, including a missing or empty `project_zip`, return the same `410`. A stub never returns `422`.
- **No side effects:** no entitlement check, no Kinde usage recorded, no upload to GCS, no Cloud Run execution.
- **Not in the OpenAPI schema,** so the client regenerated for new Kiln builds doesn't include them.
- **No GEPA code:** the stubs import nothing from GEPA or prompt optimization.

### 1.2 Sunset message

The exact text, defined in one place:

> Prompt Optimizer has been retired. Use Kiln Harness Tuner instead: it tunes your prompts, tools, skills and model. https://github.com/Kiln-AI/harness-tuner

### 1.3 What old clients see

These were verified against the code of released clients:

- The generated client has `raise_on_unexpected_status=False`, so a `410` doesn't raise inside the client. `check_response_error` turns it into `HTTPException(410, message)`. This is the same path the existing `403` "plan does not include" error takes.
- **Create-job page:** checking the run config or an eval shows the sunset message in the validation area. Starting a job shows the message as the job-creation error.
- **Job list:** status refresh already swallows per-job errors. The list still renders from local `.kiln` files, with the last stored status.
- **Job detail page:** the status and result calls show the sunset message as an error. The page doesn't crash.
- **Entitlement check:** `GET /v1/check_entitlements?feature_codes=prompt-optimization` keeps working unchanged, since the route already accepts any code.

No old-client flow may crash, hang, or show a raw 404, 422 or 500 for these endpoints.

### 1.4 Acceptance test for old clients

Run current Kiln `main` before the removal, which behaves like v1.2.1, against a local kiln_server with the stubs. Walk through each flow:

1. Open the prompt optimization page.
2. Open the create-job page and pick a run config and an eval.
3. Start a job.
4. Open an existing job's detail page. Use a hand-made `prompt_optimization_job.kiln` with a non-final status.
5. Load the job list.

Each flow either shows the sunset message or renders without errors.

## 2. kiln_server removal

**Removed:**
- **The package and job code:**
  - the `prompt_optimization/` workspace member (GEPA optimizer, DSPy adapter, metric, cache, CLI and tests)
  - the jobs route and its util
  - the `gepa-job` job type and its registry entry
- **Dependencies and config:**
  - `dspy`, and any other dependency used only by that package. Check each one before dropping it from the lock.
  - the root `pyproject.toml` entries: dependency, workspace member, source, ty path, isort section
  - the `Dockerfile` lines
  - `.gitignore` `.dspy_cache`
  - `.vscode` settings
  - the `GEPA_OPTIMIZER_TYPE` / `DSPY_CACHEDIR` env handling
  - the README section on pinning the `kiln-ai` revision in two places
- **Cloud Run:** the `gcloud/jobs/{prod,staging}/gepa-job.yml` files.

**Generalized, not removed:**
- **The billing helpers stay:** `org_has_entitlement`, `record_usage_for_org` and `check_entitlements`.
- **`FeatureCode`** stops being `Literal["prompt-optimization"]` and becomes a generic feature-code type.
- **Tests** that use `prompt-optimization` as their example code switch to a neutral example code.

**Generic job tests:** the runner tests that use `gepa-job` as their example job switch to a job type that still exists. The generic runner, base job and status route stay.

**Agent and convention docs:** `.agents/skills/kiln-server-conventions` (`SKILL.md`, `references/jobs_pipelines.md`, `references/api.md`) and its `gate_config.json` drop the GEPA / prompt optimization content.

**Copilot chat content:** `static/kiln_projects/copilot_chat/`, the `kiln-chat` skill and task.
- **Deleted:** the docs only about this feature, `prompt_optimizer.md`, `automatic-prompt-optimizer.md`, `prompt_optimization_api_list.md`, and the 7 prompt optimization API docs.
- **Edited:** every other doc that mentions the feature (`SKILL.md`, `skill.kiln`, `task.kiln`, the modes, docs and knowledge files, and the `agent_overview` API doc). The copilot must no longer suggest it, link to it, or describe its API.
- **Harness Tuner:** don't add it as a replacement suggestion in this project.

**Not changed:** the Kinde configuration (the feature code, plans and metering), and the data-guide and sample jobs.

## 3. Infra cleanup (after the kiln_server deploy)

This is a manual checklist, run once the stubs are live in production:

1. Delete the Cloud Run Job `gepa-job` in staging and prod.
2. Delete the GEPA job artifacts in the GCS job bucket (the uploaded `project.zip` files and result JSON for `gepa-job` executions), in staging and prod.

Both steps are destructive. Show the exact resources and wait for an explicit go-ahead before deleting anything. If the gcloud credentials here can't do it, write down the exact commands for a human to run.

## 4. Kiln removal

**Removed:**
- **Studio API:** all 7 studio routes for prompt optimization jobs, and their registration in `desktop_server.py`.
- **Datamodel:** the `PromptOptimizationJob` model, the `Task.prompt_optimization_jobs` relationship, the accessor and the export.
- **Agent overview:** the `prompt_optimization_jobs` block in the agent overview, both the API response field and its builder.
- **Generated client:** regenerated from the updated kiln_server. This drops the 3 job endpoints, their models, `CheckModelSupportedResponse` and `JobType.GEPA_JOB`.
- **Agent policy:** the 7 annotation files in `libs/server` and the "Prompt Optimization" OpenAPI tag.
- **Web UI:**
  - the `/prompt_optimization/**` routes. Old URLs fall through to the app's normal 404.
  - the "Optimizer Jobs" button and the "Automatically Optimize Your Prompt" banner on the prompts page
  - the "Automatic Optimization" category in the prompt generator picker, and the redirect it triggers
  - `checkPromptOptimizationAccess`, while the generic `checkEntitlements` stays
  - the type aliases
- **Schemas:** both `api_schema.d.ts` files are regenerated.
- **Tests:** the unit and e2e tests that cover the removed code. The multipart boundary regression test keeps covering multipart uploads through another endpoint, or is removed if no multipart upload to kiln_server remains.
- **README:** the "Auto-Optimize" bullet and its links.

**Existing user data keeps working:**
- Prompts with `generator_id="kiln_prompt_optimizer"` still load. They still show as "Kiln Optimized" everywhere a prompt type label is shown: the prompt type label, the agent overview, eval results, the eval worker's generator label, and the prompt type selector or details. "Kiln Optimized" is no longer offered as an option when creating a prompt.
- Existing `prompt_optimization_jobs/` folders under tasks are never loaded, and never deleted or changed. A task with that folder loads with no error or warning.
- Provenance notes that mention a prompt optimization job are free text and stay as they are.

**Wording:**
- Comments and docstrings that refer to prompt optimization are updated. This includes the `eval_api` train-split comment and the docstring that points at a removed function.
- In the Optimize hub, "automatic optimizers" wording that refers to this feature is removed or reworded.
- Historical specs under `specs/projects/` stay as they are.

**Not changed:** the Optimize hub (`/optimize`), the evals `train` split, `train_set_filter_id`, the generic `/api/check_entitlements`, and `package_project`, which the CLI still uses.

## 5. Docs site ([Kiln-AI/docs](https://github.com/Kiln-AI/docs))

- **The `automatic-prompt-optimizer` page:** add a clear deprecation notice at the top saying the Prompt Optimizer is retired and pointing to Harness Tuner. Keep the page so existing links still resolve.
- **Pages that present it as a current feature,** such as the optimizers overview, the navigation and other links: mark it as deprecated in each place, without removing the links.
- Ship this as a separate PR in the docs repo.

## 6. Delivery and order

| # | Repo | Change | Depends on |
|---|---|---|---|
| 1 | kiln_server | Stubs, removal, copilot docs (one PR) | none |
| 2 | Kiln | Removal, client regenerated from #1's schema (one PR) | #1 merged, for client generation |
| 3 | docs | Deprecation notice (one PR) | none |
| 4 | Infra | Cloud Run and GCS cleanup | #1 deployed to prod |

When #1 deploys, the feature stops working for every client, whichever Kiln version it runs. That's intended. #2 can ship in any later Kiln release.

## 7. Constraints

- No old client may crash because of this change (section 1.3).
- Each repo's automated checks (lint, types, tests) pass after the removal.
- No GEPA, DSPy or prompt optimization code stays in either repo, except:
  - the sunset stubs and message
  - the `kiln_prompt_optimizer` → "Kiln Optimized" display label
  - historical specs
