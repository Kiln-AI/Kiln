---
status: complete
---

# Phase 2: kiln_server docs and copilot chat content

## Overview

Phase 1 removed the Prompt Optimizer code from kiln_server. This phase removes it from the prose that still describes it: the `kiln-chat` copilot skill and task (so the hosted assistant no longer suggests, links to or calls the feature), and the agent convention docs (so coding agents aren't told about a package that no longer exists). It then runs the §1.5 final grep and the old-client acceptance test (§4). All changes are in the kiln_server repo; no runtime code changes except one stale docstring.

## Steps

1. **Delete copilot docs only about the feature** (under `static/kiln_projects/copilot_chat/skills/408910145779 - kiln-chat/references/`):
   - `knowledge/prompt_optimizer.md`
   - `docs/prompts/automatic-prompt-optimizer.md`
   - `knowledge/api_docs/prompt_optimization_api_list.md` and the 7 `knowledge/api_docs/*prompt_optimization_jobs*` / `*prompt_optimization_jobs_job_id*` docs.
2. **Edit `SKILL.md`** (kiln-chat): drop the Prompt Optimizer from the UI-only workflow list, the GEPA routing example, the "prompt optimization" cost lever (reword to prompt trimming), "Prompt Optimizer" from the Learn-about-Kiln feature list, and "prompt optimizer" from the deep-link note. Keep the "eager optimizer" persona wording, which is not about the feature.
3. **Sync `task.kiln`** (`tasks/291531180356 - kiln-chat/`): set `instruction` to the edited `SKILL.md` text (they are byte-identical today). Rewrite the JSON with the file's existing formatting so only `instruction` changes.
4. **Edit `skill.kiln`**: in `description`, drop ", and GEPA optimization" so the list ends at "RAG". No other field.
5. **Edit modes:** `modes/improve_task.md` (deep link, the improve-prompt routing row, the Optimize Quality summary, the Prompt Optimizer knowledge row) and `modes/learn_about_kiln.md` (GEPA in the App Help row, the Prompt Optimizer row).
6. **Edit knowledge files:** `app_help.md`, `experiment_batch.md`, `fine_tuning.md`, `freeform_help.md`, `local_private_on_prem.md`, `model_create_configs.md`, `model_work.md`, `optimize_performance.md`, `optimize_quality.md`, `prompt_audit.md`, `prompt_rewrite.md`, `specs_and_evals.md`. Remove each sentence, bullet, table row or link about GEPA, the Prompt Optimizer, or the `prompt_optimization_jobs` endpoints; smooth the surrounding text; when a list of levers loses an entry, leave the rest unchanged. No Harness Tuner mentions.
7. **Edit docs:** `docs/docs_index.md` (drop the `automatic-prompt-optimizer.md` row, reword the `prompts.md` description), `docs/prompts.md` (drop the automatic optimizer bullet and the "Try our automatic prompt optimizer" line, reword the description), `docs/optimizers.md` (reword "automatic optimizers"), `docs/fine-tuning/README.md` (drop the "consider the Automatic Prompt Optimizer" paragraph).
8. **Edit `api_docs/get_api_projects_project_id_tasks_task_id_agent_overview.md`:** remove the `prompt_optimization_jobs.total_count` row.
9. **Conventions skill docs** (`.agents/skills/kiln-server-conventions/`):
   - `SKILL.md`: drop `prompt_optimization` from the description and the `jobs_pipelines.md` path row; F22 bullet names only `kiln_pipelines`.
   - `references/jobs_pipelines.md`: retitle to jobs, pipelines and scripts; drop the `kiln_optimizers` package, the Optimizers gotcha section, its "where things go" row and its CLI startup row; rewrite the package-graph, key-bridge, registry-import and runner-startup bullets around `sample-job` and `data-guide-job`.
   - `references/api.md`: remove the dspy bullet; reword the paid-jobs bullet so it no longer cites `start_prompt_optimization_job` (no paid job exists today; keep the order rule for a future one); drop `start_prompt_optimization_job` from "older code to not extend" and the `kiln_optimizers` clause from the dependency-direction paragraph.
   - `scripts/gate_config.json`: remove the `prompt_optimization/kiln_optimizers/gepa/cli/**` env-access entry.
10. **`docs-sync/SKILL.md:27`:** remove the `kiln_optimizers.gepa.cli.args` (`prompt_optimization/`) dotted-path example.
11. **`api/kiln_fastapi_api/routes/jobs/data_guide_job.py`:** drop "unlike the prompt optimization job" from the module docstring (it spans a line break, so the grep misses it).
12. **Final checks:**
    - `git grep -n -i -E '(^|[^a-z])gepa|prompt.optimi|kiln_prompt_optimizer|Kiln Optimized'` under `static/` returns nothing.
    - `git grep -n -i -E '(^|[^a-z])gepa|dspy|prompt.optimi|kiln_optimizers'` returns only the sunset router and its test, `specs/`, `utils/generate_python_sdk.sh`, and the `test_kinde_integration.py` real-tenant feature code (Phase 1's allowed exception).
    - No remaining Markdown link in the kiln-chat skill points at a deleted file.
13. **Old-client acceptance test (§4):** run kiln_server from this branch locally and the pre-change Kiln studio server from a temporary worktree at `origin/main` (`058307fcc^`), pointed at the local kiln_server. Over HTTP, exercise the old studio endpoints for flows 1-5 (entitlement check, check_run_config / check_eval, start, a hand-made job with `latest_status: "running"` for detail/status/result, and the job list) and confirm each returns the sunset message or renders without error. Remove the worktree and stop the servers afterwards.

## Tests

- No new unit tests: this phase changes prose, JSON content and one docstring.
- Run the kiln_server automated checks (`checks.sh`: lint, format, ty, pytest across the workspace), including the task-model codegen `--check` (the `task.kiln` edit must not change generated types) and the conventions gate tests.
- The old-client acceptance run (step 13) verifies the sunset contract end to end.
