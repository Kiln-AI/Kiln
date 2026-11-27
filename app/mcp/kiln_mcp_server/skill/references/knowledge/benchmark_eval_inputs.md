---
name: benchmark_eval_inputs
description: |
  EvalInput-backed benchmark evals: on-disk eval input datasets with reference data, generate-then-score eval runs (including synthetic-user multi-turn drives), and the recipe for benchmarking a candidate run config. Load when: an eval's test split is EvalInput-backed, someone mentions eval inputs / benchmark datasets / reference data, or you need to score a new run config on a benchmark task.
---
# Knowledge: EvalInput Benchmark Evals

Most evals score **stored** dataset runs (their `test` split is `task_run`-backed). A second kind of eval carries its **own input dataset** — EvalInputs — and **generates** a fresh response per (eval input × run config) at eval time, then scores it against per-item reference data. These are benchmark evals: run one against a candidate run config and you get an apples-to-apples score without any stored runs existing first.

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

| Endpoint | Load |
|----------|------|
| Eval Inputs — API catalog (list, create, update, delete) | `references/knowledge/api_docs/eval_inputs_api_list.md` |
| Evals API catalog | `references/knowledge/api_docs/evals_api_list.md` |
| GET evals list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET eval progress (dataset_size = matching EvalInputs) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md` |
| GET per-eval-config score summary | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md` |
| GET eval run results (per-item drill-down) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md` |

## Recognizing a benchmark eval

`GET /api/projects/{project_id}/tasks/{task_id}/evals` — an eval carries a **`splits`** map (`test` / `train` / `val`), and a **benchmark eval** is one whose `test` split is EvalInput-backed: **`splits["test"].source == "eval_input"`** (a stored-dataset eval has `source == "task_run"` instead). (On older servers the signal was the now-deprecated `eval_input_filter_id` / `eval_set_filter_id` fields — always null on current builds; read `splits` instead.) `GET /evals/{eid}/progress` → `dataset_size` counts the matching EvalInputs.

## EvalInputs: the dataset rows

EvalInputs live on disk under the task (`eval_inputs/<id>/eval_input.kiln`). The Eval Inputs endpoints list, create, update and delete them (`references/knowledge/api_docs/eval_inputs_api_list.md`); an update changes the tags and the reference data only, never `data`. Never create EvalInputs yourself: they are eval data (`references/knowledge/create_eval.md`). Never change the `data` or the `reference` of an EvalInput that an eval uses, even to fix it: the items of an eval only grow, so that it keeps catching regressions. The fix for wrong reference data is a new eval: a copy of the old eval's items with the corrected reference data, which the user makes in the app. The old eval is archived only when the user agrees (`references/improving_agents/playbooks/dealing-with-a-wrong-eval.md`). Change a benchmark's dataset in any other way only when the user asks for it. Each row has:

- `data` — what to run, one of two types:

| Type | Fields | At eval time the runner… |
|------|--------|--------------------------|
| `single_turn` | `user_message: {text}` | runs the task once with that message against the run config |
| `multi_turn_synthetic` | `first_message: {text}`, `synthetic_user_info: {persona, goal, behavior_guidance?, turns?, su_model_name?, su_model_provider?}` | drives a **live multi-turn conversation**: a synthetic user (playing `persona`, pursuing `goal`) talks to the run config for up to `turns` turns (default 5); the SU model defaults to the target run config's own model |

- `reference` — optional flat dict of ground truth for scoring (see reference_data below)
- `tags` — filtering labels; the eval's `test` split filter selects the rows carrying its tag

## Generation is shared across evals

Driven conversations are keyed by (eval input, run config): the produced leaf run is tagged `sei_<eval_input_id>` (plus `synthetic_eval_drive_<eval_id>`) and stamped with the run config id. Any later eval scoring the same pair **reuses the stored conversation instead of re-driving it** — so running a second benchmark eval over the same dataset and run config only pays for judging, not generation. Eval jobs are also idempotent per item: re-triggering a job skips already-scored items and sweeps only the failures.

## reference_data: how ground truth reaches the scorer

The EvalInput's `reference` dict flows into scoring as `reference_data`:

- **Code evals** receive it as the `reference_data` parameter of their `score()` function (the full `score()` contract and the judge-type menu live in `references/knowledge/judge_types.md`).
- **LLM judges** see it in the Jinja prompt template as `reference_data.*` — e.g. `{{ reference_data.expected_answer }}` or `{% for c in reference_data.llm_judge_criteria_blocking %}`.

House conventions: flat dict, snake_case, `expected_*` keys for ground truth (`expected_answer`, `expected_tool_name`, …), `llm_judge_criteria_*` lists for per-item judge criteria. A scorer referencing a missing reference key skips that item gracefully (`skipped_reason` on the result row) rather than erroring.

Only the EvalInput lane delivers `reference_data` — evals over stored TaskRuns (test split `source == "task_run"`) get `reference_data: null`.

**Your job here is running benchmarks and reading scores.** For creating an eval, follow `references/knowledge/create_eval.md`; a judge is `references/knowledge/judge_types.md`.

## The recipe: benchmark a candidate run config

To answer "how does model/prompt X do on this benchmark?":

1. **Create the candidate run config** (or find its `rcid`) — `references/knowledge/model_create_configs.md`.
2. **Enumerate the benchmark evals** — `GET /evals`, keep those whose splits are EvalInput-backed (`splits[<split>].source == "eval_input"` for each split the eval has); note each eval's default judge `current_config_id` (a benchmark task often has several, e.g. one code eval + one judge per bucket).
3. **Measure and compare** the candidate against the baseline (in a chat with a user, as `references/client_guidance/chat/running_an_experiment_from_chat.md` says): on the train split first, then the confirmation on val. Run each eval as a job, one per eval × run config × split (`references/knowledge/specs_and_evals.md`, "Running an eval"). A benchmark eval with only a test split gets its train and val splits first (`references/knowledge/train_val_test.md`). Benchmark runs can be sizeable — each `multi_turn_synthetic` item drives up to `turns` conversation turns (SU model call + full agent invocation per turn, tools included) **per run config**, plus a scoring call per eval × item — estimate the cost before a large run (`references/knowledge/experiment_costing.md`).
4. **Pair per item** on `eval_input_id` in the results call (below), and report per the response-assembly rules in `references/knowledge/eval_scores.md` (deep links, coverage, significance).

The `run_comparison` / `run_calibration` endpoints behind the app's Run button are event streams for the app; use the eval job instead.

## Reading scores: use score_summary, not the batch summary

`score_summary` and `eval_results_summary` read the test split, for a report of where the benchmark stands; an experiment reads train and val with the results call (`references/knowledge/train_val_test.md`).

- `GET .../evals/{eid}/eval_config/{ecid}/score_summary` **fully supports benchmark evals** — scores are keyed by run config and mean per score key, completion measured against the EvalInput count.
- `GET .../eval_results_summary` (the batch scorecard endpoint) includes EvalInput-backed evals (`dataset_size` counts matching EvalInputs). If it returns empty `evals_by_id` on a benchmark task you are on an older server — fall back to looping `score_summary` over the benchmark evals' default configs.
- `GET .../results` rows for this lane carry `eval_input_id` (with `dataset_id: null`) plus the item's `reference_data` — join per-item scores across run configs on `eval_input_id` (e.g. for paired significance tests per `references/knowledge/eval_scores.md`). Rows with `skipped_reason` set were not scored — surface them, don't average them.

## UI Deep Links

| Action | Link |
|--------|------|
| Benchmark eval detail / results (usually spec-less → legacy) | `http://localhost:8757/specs/{project_id}/{task_id}/legacy/{eval_id}` |
| Candidate run config | `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid}` |
| A driven conversation leaf (tagged `sei_<eval_input_id>`) | `http://localhost:8757/dataset/{project_id}/{task_id}/{run_id}/run` |

## See also

When and why, in the knowledge: `references/improving_agents/playbooks/dealing-with-a-noisy-eval.md`, `references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md`, `references/improving_agents/playbooks/spending-the-budget.md`.
