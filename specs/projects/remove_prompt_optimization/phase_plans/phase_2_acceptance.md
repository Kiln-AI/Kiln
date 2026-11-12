# Phase 2: old-client acceptance results

Old-client acceptance test from architecture §4 / functional spec §1.4, run before the kiln_server PR.

## Setup

- **kiln_server:** branch `leonard/remove-prompt-optimization` (sunset stubs), run locally on `127.0.0.1:8765`.
- **Kiln:** a temporary worktree at `058307fcc^` (= `origin/main` before this project, which behaves like v1.2.1). Its studio server ran on `127.0.0.1:8767` with `KILN_SERVER_BASE_URL=http://127.0.0.1:8765` and a test `KILN_COPILOT_API_KEY`. `HOME` was isolated, so no real Kiln settings or projects were used.
- **Fixture project:** a task with a Kiln Agent run config (`gpt_4o_mini` / openai), and an eval with a train split and an LLM-judge config set as current. It also has a hand-written `prompt_optimization_jobs/111111111111 - handmade/prompt_optimization_job.kiln` with `latest_status: "running"`.
- The studio endpoints were exercised over HTTP with curl. No browser was used.

## Results

| Flow | Studio call | Result |
|---|---|---|
| 1. Open the prompt optimization page | `GET /api/check_entitlements?feature_codes=prompt-optimization` | 200, `{"prompt-optimization": true}` |
| 1, 5. Job list with status refresh | `GET .../prompt_optimization_jobs?update_status=true` | 200. The job is listed with its stored status `running`. The 410 from the status refresh is swallowed and logged, as designed. |
| 2. Create-job page: check run config | `GET .../prompt_optimization_jobs/check_run_config` | 410, sunset message |
| 2. Create-job page: check eval | `GET .../prompt_optimization_jobs/check_eval` | 410, sunset message |
| 3. Start a job | `POST .../prompt_optimization_jobs/start` | 410, sunset message. No job file was created. |
| 4. Job detail (non-final job) | `GET .../prompt_optimization_jobs/{id}` | 200, the cached job. The refresh error is swallowed. |
| 4. Job status | `GET /api/prompt_optimization_jobs/{job_id}/status` | 410, sunset message |
| 4. Job result | `GET /api/prompt_optimization_jobs/{job_id}/result` | 410, sunset message |
| 5. Job list, no refresh | `GET .../prompt_optimization_jobs` | 200, the job is listed |

The sunset message as received by the old client:

> Prompt Optimizer has been retired. Use Kiln Harness Tuner instead: it tunes your prompts, tools, skills and model. https://github.com/Kiln-AI/harness-tuner

kiln_server's access log shows every stub call answered `410 Gone`:
- `check_model_supported`, twice
- `start`
- `prompt_optimization_job/{id}/result`
- `gepa-job/{id}/status`, three times

The last one shows the generic status route doesn't shadow `gepa-job`. No call returned 404, 422 or 500.

## What was stubbed

There was no real Copilot API key, so kiln_server ran through a local launcher script that patched `KindeClient` methods:
- `verify_api_key` accepts any key.
- `get_user`, `get_organization` and `get_entitlements` return an org entitled to `prompt-optimization`.
- `org_has_entitlement`, `record_usage_for_org`, `record_feat_usage_for_user` and `post_meter_usage_request` raise if called. None was called, so the stubs record no usage.

## Not verified

- **Real API-key auth against Kinde, and the 401 path.** These are covered by the unit tests in `test_prompt_optimization_sunset.py` and `routes/test_auth.py`.
- **The old Svelte UI rendering these responses.** No browser walkthrough or screenshots were taken. The UI shows `detail` from the studio's `HTTPException`, the same path the existing 403 "plan does not include" error takes.
