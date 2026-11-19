---
status: complete
---

# Phase 1: kiln_server sunset router and GEPA removal

## Overview

Replace the real prompt optimization job routes in kiln_server with a sunset router that answers `410 Gone` with a pointer to Harness Tuner, so released desktop clients keep working without crashing. Then delete the `prompt_optimization` workspace member, the job route and util, the `gepa-job` job type and its Cloud Run config, and every packaging, Docker and config entry that served them. `FeatureCode` becomes a generic string type, and tests that used `prompt-optimization` or `gepa-job` as example values switch to neutral or still-existing values. All code changes are in the kiln_server repo. The copilot chat content and the conventions skill docs are Phase 2.

## Steps

1. **Sunset router.** Add `api/kiln_fastapi_api/routes/jobs/prompt_optimization_sunset.py` as in architecture §1.1:
   - `PROMPT_OPTIMIZER_SUNSET_MESSAGE` constant with the exact text from functional spec §1.2.
   - `router = APIRouter(include_in_schema=False)`.
   - `_sunset() -> NoReturn` raising `HTTPException(410, detail={"message": PROMPT_OPTIMIZER_SUNSET_MESSAGE})`.
   - Four handlers with no parameters except the path `job_id`: `GET /prompt_optimization_job/check_model_supported`, `POST /prompt_optimization_job/start`, `GET /prompt_optimization_job/{job_id}/result`, `GET /gepa-job/{job_id}/status`.
2. **Router wiring.** In `routes/jobs/__init__.py`, drop the `prompt_optimization_job` import and include, and include `prompt_optimization_sunset.router` before `status_router`.
3. **Deletions:**
   - `prompt_optimization/` (whole workspace member).
   - `api/kiln_fastapi_api/routes/jobs/prompt_optimization_job.py` and `test_prompt_optimization_job.py`.
   - `jobs/kiln_server_jobs/utils/prompt_optimization_job.py` and `test_prompt_optimization_job.py`.
   - `gcloud/jobs/prod/gepa-job.yml`, `gcloud/jobs/staging/gepa-job.yml`.
4. **Job type and registry.** Remove `JobType.GEPA_JOB` from `jobs/kiln_server_jobs/job_types.py`, and the `PromptOptimizationJob` import and entry from `job_registry.py`. Reword the `jobs/conftest.py` env-var comment so it is not about prompt optimization.
5. **Runner tests.** In `jobs/kiln_server_jobs/test_runner.py`, replace `gepa-job` / `JobType.GEPA_JOB` / `FailingGepaJob` with `data-guide-job` / `JobType.DATA_GUIDE_JOB` / `FailingDataGuideJob`. `sample-job` can't be used: the runner sends no Slack ping for sample jobs, which `test_sample_job_failure_sends_no_ping` asserts, so the failure-ping tests need another job type that still exists. No other test logic changes.
6. **Packaging and config:**
   - Root `pyproject.toml`: remove the `kiln-prompt-optimization` dependency, the `prompt_optimization` workspace member, the `[tool.uv.sources]` entry, `prompt_optimization` from ty `extra-paths`, and `kiln_prompt_optimization` from isort `known-first-party`.
   - Run `uv lock` and review the diff: only `kiln-prompt-optimization`, `dspy` and packages that came in only through it may leave; shared packages must not change version unexpectedly.
   - `Dockerfile`: remove `COPY prompt_optimization/pyproject.toml …` and `RUN uv pip install --compile-bytecode ./prompt_optimization`.
   - `.gitignore`: remove `**/.dspy_cache/`.
   - `.vscode/settings.json`: remove `"prompt_optimization"` from both `extraPaths` lists.
   - `README.md`: replace the "Managing the Kiln AI Library Dependency" section's two-file instructions with the single root `pyproject.toml` pin (edit `rev` in the root `pyproject.toml`, then `uv sync`).
   - Check for `GEPA_OPTIMIZER_TYPE` / `DSPY_CACHEDIR` handling outside the deleted package and remove any found.
7. **FeatureCode.** In `api/kiln_fastapi_api/auth/kinde_client.py`, change to `type FeatureCode = str` with a one-line comment that feature codes are defined in Kinde; remove `Literal` from imports if unused. Change the `get_entitlements` docstring example from `"prompt-optimization"` to `"example-feature"`.
8. **Kinde tests and docs:**
   - `test_kinde_client.py`, `routes/test_auth.py`: replace `"prompt-optimization"` with `"example-feature"`, and the `feature_name` values `"Prompt Optimize"` / `"Prompt Optimization"` with `"Example Feature"`.
   - `test_kinde_integration.py`: it runs against a real Kinde tenant (`--runpaid`) whose plans define `prompt-optimization`, and the Kinde config is not changing, so keep that value and make the comment say why.
   - `api/kiln_fastapi_api/auth/examples.md`: change the example feature code and names to `example-feature` / "Example Feature".

## Tests

New file `api/kiln_fastapi_api/routes/jobs/test_prompt_optimization_sunset.py`, using the full app (`kiln_fastapi_api.main.app`) with the API-key auth dependency overridden, as the existing route tests do:

- `test_sunset_routes_return_410_with_message` (parametrized over the 4 routes): status 410, `json()["message"] == PROMPT_OPTIMIZER_SUNSET_MESSAGE`.
- `test_start_never_validates_body` (parametrized: no body; full multipart body with `task_id`, `target_run_config_id`, `eval_ids`, `project_zip`; empty `project_zip`): always 410, never 422.
- `test_check_model_supported_ignores_query` (with and without `model_name` / `model_provider_name`): 410.
- `test_gepa_status_is_not_shadowed_by_generic_status_route`: `GET /v1/jobs/gepa-job/abc/status` is 410.
- `test_other_job_status_still_reaches_generic_handler`: `GET /v1/jobs/sample-job/<id>/status` with the job class mocked returns 200, not 410.
- `test_sunset_routes_require_auth` (parametrized over the 4 routes, no auth override): 401, the same as other `/v1/jobs` routes.
- `test_sunset_routes_not_in_openapi`: no path in `app.openapi()` contains `prompt_optimization` or `gepa`, and the `JobType` schema enum has no `gepa-job`.

Existing tests updated: runner tests (`data-guide-job`), Kinde client and auth route tests (`example-feature`). The full kiln_server check suite (`checks.sh`: ruff, ruff format, ty, task models, pytest) passes.
