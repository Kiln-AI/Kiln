---
name: eval_scores
description: |
  Eval score reading patterns, jq filters, scorecard building, comparison tables, and judge prompt access. Load when: you need to fetch eval scores, build comparison tables, check cost data, or investigate judge prompts.
---
# Knowledge: Reading Eval Scores & Building Scorecards

Read eval scores, build comparison tables, and understand the eval pipeline.

**Which split each call reads.** Most score calls of this file read an eval's **test** split, and take no `split` argument. They answer "how did my evals go?": report their numbers to the user as test scores. They never decide an improvement: to measure, compare or keep a run config, read train (and val, by metrics only) with the results call, as `references/knowledge/train_val_test.md` says, and follow `references/knowledge/run_an_experiment.md`.

| Call | Split it reads | For train or val |
|---|---|---|
| `eval_results_summary` (Approach 1) | test | the results call, with `split`, for each eval |
| `score_summary` of one eval config (Approach 2) | test | the results call, with `split` |
| `eval_scores` of one run config (Approach 3), with `mean_usage` | test | the results call, with `split`; its rows carry each item's usage |
| `eval_configs_score_summary` (judge calibration) | the eval's judge calibration items, not a split of the run configs | — |
| eval `progress` | `dataset_size` is the test split | `train_dataset_size`, `val_dataset_size` |
| The results call (the paired recipe) | the `split` you give; it is required | `query_params={"split": "train"}`; on val, summary numbers only |
| The Compare page and the spec pages | test | none; read train and val with the results call |

**When the eval itself looks wrong** — the playbook for each problem, before you change the eval or the judge:

- The judge fails right answers or passes wrong ones, or the eval does not measure the issue: [dealing with a wrong eval](references/improving_agents/playbooks/dealing-with-a-wrong-eval.md).
- The baseline passes almost every item: [dealing with a saturated eval](references/improving_agents/playbooks/dealing-with-a-saturated-eval.md).
- The baseline passes almost no item: [dealing with an eval near zero](references/improving_agents/playbooks/dealing-with-an-eval-near-zero.md).
- A score moves between repeats with no change: [dealing with a noisy eval](references/improving_agents/playbooks/dealing-with-a-noisy-eval.md).
- A train win is rejected on val: [dealing with train wins rejected at validation](references/improving_agents/playbooks/dealing-with-train-wins-rejected-at-val.md).

> **Before any eval scan:** confirm you have a specific project/task (or a short explicit list). "Summarize my evals" across an unknown number of projects is a scope-ambiguous request — ask once, then pull. A breadth-first scan across every project, task, and eval config will blow the session budget before producing output.

## Hard Requirements (response assembly)

Every scorecard or score comparison response MUST:

1. **Never emit placeholder link targets.** Links of the form `[Name](...)`, `[Name](run)`, `[Name]()`, or any empty/sentinel URL are forbidden. If the `rcid` isn't in hand, fetch it via `GET /run_configs` before writing the table — do not ship the table without real targets.
2. **Every ranked config row includes a `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid}` deep-link** built from the `id` field returned by the run_configs GET.
3. **One Compare link after the table** using `http://localhost:8757/specs/{project_id}/{task_id}/compare?columns=N&models={rcid1}%2C{rcid2}%2C...` where `N` is the number of run configs in the table — the `models=` query parameter MUST include **every** `rcid` in the table, URL-encoded and comma-joined. A bare `http://localhost:8757/specs/{project_id}/{task_id}/compare` without `models=` is incomplete. The Compare view renders **at most 6 run configs**; if the table has more, cap `models=` at the top 6 and mention the cap in the reply. The page shows test scores: say so, so that the user does not take them as the result of an experiment.
4. **Latency and cost columns** when the user's ask implies optimization — cost comes from `mean_usage` on `GET /run_configs/{rcid}/eval_scores` (test split), or for the split you measure, from each row's `task_run_usage` in the results call; latency from per-run metadata when available.
5. **Coverage and significance before verdict-language.** Every comparison row carries a **coverage column (n scored / n expected)** and a **significance column (paired CI or p-value from `POST /api/statistics`)** — the table cannot be rendered until the stats call has run, so run it *before* composing the reply, not after the user pushes back. Sides covering different or partial item sets get fixed (re-trigger the idempotent job) or flagged — never silently compared. "Better" / "regressed" / "clear" requires the paired result behind it — `compare_paired` (continuous) or `mcnemar_paired` (binary), **never the unpaired `compare_proportions`** when both configs scored the same items, and never mental CI arithmetic in place of the call; a within-noise delta is reported as *no significant difference*.
6. **A side with zero scored items has no row.** An all-items-errored config is an execution failure to name and diagnose (one cheap probe — same model on a different provider, or vice versa), never a comparison datapoint — no savings-at-matched-accuracy claim may rest on it, and any cost figure is labeled conditional on quality that hasn't been demonstrated.
**Paired-test recipe (three calls, existing endpoints — don't fall back to unpaired because pairing "looks hard"):** the comparison of an experiment on train, as `references/knowledge/run_an_experiment.md` uses it. On val, read summary numbers only, as `references/knowledge/train_val_test.md` says.
1. For **each** config: `GET .../evals/{eval_id}/eval_config/{eval_config_id}/run_config/{run_config_id}/results` — this endpoint **requires a `split` query param** (omitting it is a 422): `query_params={"split": "train"}`. Use `jq_filter: "[.results[] | {d: .dataset_id, s: .scores}] | sort_by(.d)"` — ~70 compact rows per side.
2. Join the two lists on `dataset_id` (drop items present on only one side — and report the drop as a coverage flag), map each item's score to 0/1 for the dimension under test.
3. `POST /api/statistics` with `{"operation": "mcnemar_paired", "outcomes_a": [...], "outcomes_b": [...]}` (same order both arrays). For continuous metrics use `compare_paired` with `values_a`/`values_b` the same way.

## Pre-Check rule (summary)

`eval_results_summary` returns empty results for unconfigured evals — no separate readiness probe is needed. Surface unconfigured evals via the remediation block below.

Note: `/run_configs` requires no trailing slash — see `references/knowledge/model_create_configs.md` → URL Shape Note.

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

| Endpoint | Load |
|----------|------|
| Evals API catalog | `references/knowledge/api_docs/evals_api_list.md` |
| Run configs API catalog | `references/knowledge/api_docs/run_configs_api_list.md` |
| Specs API catalog | `references/knowledge/api_docs/specs_api_list.md` |
| GET eval results summary (batch, preferred) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_eval_results_summary.md` |
| GET evals list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET eval progress | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md` |
| GET eval configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md` |
| GET eval config | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id.md` |
| GET per-eval-config score summary (drill-down) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md` |
| GET eval configs score summary (judge calibration only) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs_score_summary.md` |
| GET per-config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |
| GET run configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs.md` |
| GET specs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| POST statistics (CIs & significance) | `references/knowledge/api_docs/post_api_statistics.md` |

## Reading Eval Scores



After specs and evals exist, the agent reads scores to build comparison tables for the user. **Prefer the aggregated `eval_results_summary` endpoint** — it returns everything in one call. The three approaches below read the test split (the table at the top).

### Approach 1: eval_results_summary (Preferred)

One call returns scores across **all evals and all run configs** for the task. Response shape: `{ evals_by_id, run_configs_by_id, scores_by_run_config_by_eval }`.

1. **Call the batch endpoint:**

   ```
   # read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_eval_results_summary.md
   call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/eval_results_summary")
   ```

2. **Read the response.** Use `evals_by_id` for eval metadata (name, output scores), `run_configs_by_id` for model/provider/name per rcid, and `scores_by_run_config_by_eval[rcid][eid]` for each cell in the scorecard.

3. **If the batch is empty for specs you expect to have scores, probe per-eval before giving up.** When `dataset_size: 0` (or empty score blocks) appears for specs that `agent_overview` shows as configured with nonzero completion, check why: `eval_results_summary` scores only the eval's default judge (`current_config_id`) on its test split, so an eval with no default judge or an empty test split shows nothing. List the eval's judges (`GET .../evals/{eid}/eval_configs`) and call `score_summary` (Approach 2) for each; scores of a judge that is not the default may exist there — say which judge they came from. Only after this probe also returns empty should you render the remediation block.

4. **Surface unconfigured evals separately in the reply** — list them with numbered remediation, do not hide the gap.

**Remediation block shape** (for step 4 above):

> **Evals without scores (N):**
> - `{eval_name}` — no eval config yet.
>
> **To get scores, complete each step in order:**
>
> 1. [Open the spec](http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}) or [Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/spec_builder) if no spec exists yet
> 2. [Add a judge (eval config)](http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}/{eval_id}/eval_configs)
> 3. Run the eval — I can start it, or click **Run Eval** on the [spec page](http://localhost:8757/specs/{project_id}/{task_id}/{spec_id})
> 4. Re-check scores here — I'll pull a fresh scorecard

### Specs configured, scores empty — the Compare-link fallback

When `eval_results_summary` and the per-judge `score_summary` probe both return `dataset_size: 0` (or empty score blocks) for every spec the user wants to rank across, the user is mid-setup — eval configs exist but no eval runs have completed. **Do not stop at "no scores yet."** Produce three outputs in this order:

1. A **model + cost table** of the candidate run configs (model, provider, input/output $/M, est. $/call from `GET /api/model_info/model_details`), with a `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid}` deep-link per row. State explicitly that ranking is by cost only because no eval data exists yet.
2. A **Compare link** of the form `http://localhost:8757/specs/{project_id}/{task_id}/compare?columns=N&models={rcid1}%2C{rcid2}%2C...` populated with all candidate rcids URL-encoded and comma-joined — the UI compare view renders run outputs side-by-side and lets the user inspect quality manually while eval runs accumulate.
3. The standard remediation block ("To get scores, run each eval"; you can start the runs yourself per `references/knowledge/specs_and_evals.md` ("Running an eval")) — but as a *follow-up*, not as the entire answer.

This applies to "rank my configs", "which should I ship?", and "what's the cheapest passing model?" asks when scores are empty. The cost ladder + manual-Compare path is a real partial answer; "no eval data exists, run your evals first" alone is not.

### No evals yet — minimum viable path (for "cheapest passing model" / "which model is best" queries when no configs or evals exist)

If the user asks for a model ranking on a task but the task has no specs or no eval configs, you can't rank yet. Don't stop at "I can't help" — produce this numbered path:

1. [Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/spec_builder) — define 1–3 quality dimensions (what "good" looks like)
2. [Add a judge (eval config)](http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}/{eval_id}/eval_configs) — pick the judge model and prompt
3. [Run configs page](http://localhost:8757/optimize/{project_id}/{task_id}) — ensure at least 2 configs exist to rank against each other; create candidates with `references/knowledge/model_create_configs.md` if needed
4. Run the eval — the eval job of `references/knowledge/specs_and_evals.md` ("Running an eval")
5. Come back and ask for the scorecard — I'll pull `eval_results_summary` once scores exist

State this as the answer to the ranking question, not as a deferral. The user asked how to rank models; the ranking requires these steps; these steps are the answer.

### Approach 2: score_summary (Single Eval Config Drill-Down)

When you need per-eval-config detail beyond the batch summary — e.g., drilling into one eval config's per-run-config scores or completion — call `score_summary` for that eval config.

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/evals/{eid}/eval_config/{ecid}/score_summary", jq_filter="{scores: [.results | to_entries[] | {run_config: .key, fields: [.value | to_entries[] | {field: .key, score: .value.mean_score}]}], completion: .run_config_percent_complete, dataset_size}")
```

If it returns `400 "No dataset ids in eval set filter"`, the eval config has no dataset — do NOT retry.

### Approach 3: Per-Config Scores (Use Sparingly)

Returns all eval scores for a **single** run config. Use only when checking one or two specific configs.

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/run_configs/{rcid}/eval_scores", jq_filter="{evals: [.eval_results[] | {name: .eval_name, score: .eval_config_result.results | to_entries | map({field: .key, score: .value.mean_score}), pct: .eval_config_result.percent_complete}], cost: .mean_usage}")
```

**Do NOT loop this endpoint over all configs to build a scorecard.** Use Approach 1 instead.

### eval_configs_score_summary (Judge Calibration)

Judge calibration only: it compares the eval's judges against human ratings on the eval's golden set (`eval_configs_filter_id`). It holds no run config's scores, so it is no source for a scorecard.

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs_score_summary.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/evals/{eid}/eval_configs_score_summary", jq_filter="{completion: .eval_config_percent_complete, dataset_size, rated: .fully_rated_count}")
```

### Filtering: Be Smart About What You Query

1. **Check completion first.** Configs with 0% in `run_config_percent_complete` have no scores — skip them.
2. **Match the user's intent.** If they ask about one model, pull that config + a few comparisons, not all 15+.
3. **Filter by tier.** If the user wants cheaper alternatives, skip frontier models they've ruled out.

## Building the Scorecard

Many workflows end with comparing run configs. Follow this pattern:

1. **Use bootstrap `agent_overview.run_configs.items`** for the list of configs (id, name, model_name, model_provider). Only re-fetch `GET /run_configs` if the overview is stale or the rcid set is ambiguous.

2. **Pull batch scores** using Approach 1 above.

3. **Build a comparison table** — every row uses the `id` from `run_configs_by_id` (or the bootstrap) as the rcid for the `http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid}` deep link.

| Config | Model | Spec 1 | Spec 2 | Avg Cost | Link |
|--------|-------|--------|--------|----------|------|
| Baseline | GPT-5 Mini | 92% | 88% | $0.002 | [View](http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid_baseline}) |
| Challenger | GPT 4.1 Mini | 89% | 85% | $0.0004 | [View](http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid_challenger}) |

4. **Always include a prepopulated Compare link** after the table using `http://localhost:8757/specs/{project_id}/{task_id}/compare?columns=N&models=rcid1%2Crcid2%2C...` — the `models=` value must include **every** rcid in the table, URL-encoded comma-joined. A bare `http://localhost:8757/specs/{project_id}/{task_id}/compare` (no `models=`) is incomplete.

## Significance & confidence (call the statistics endpoint, don't hand-compute)

When asked for a standard error, a confidence interval, or whether a difference between run configs is real, load `references/knowledge/api_docs/post_api_statistics.md` and `call_kiln_api` `POST /api/statistics` (set `operation`) instead of computing by hand: `operation="proportion_ci"` (one pass-rate cell), `"compare_proportions"` (unpaired difference), `"compare_paired"` (continuous metrics like latency/cost/tokens). For binary pass/fail compared over the **same** eval items — the usual run-config comparison — prefer `operation="mcnemar_paired"`, the paired test: it is far more powerful at the ~100–200 sample sizes here. It needs per-item outcomes: take them from the results call of the paired-test recipe above, on train, and pair them on `dataset_id` (1 = pass, 0 = fail).

## Viewing and Editing Judge Prompts

The judge prompt lives inside the **EvalConfig** — specifically in `properties["eval_steps"]` (a list of evaluation step strings) and `properties["task_description"]` (optional context string).

### Via API

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md`, then:
- `call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/evals/{eid}/eval_configs", jq_filter="[.[] | {id, name, task_desc: .properties.task_description, steps: .properties.eval_steps}]")`
Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id.md`, then:
- `call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/evals/{eid}/eval_config/{ecid}", jq_filter="{name, task_desc: .properties.task_description, steps: .properties.eval_steps}")`

### Via UI

Navigate to the [Eval configs page](http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}/{eval_id}/eval_configs).

## Benchmark (EvalInput-backed) evals

Benchmark evals (whose `test` split is EvalInput-backed) generate their responses at run time (incl. live synthetic-user drives). Reading their scores works through the same `score_summary`/`eval_results_summary` endpoints; to RUN or benchmark a candidate config against them, load `references/knowledge/benchmark_eval_inputs.md` first.
