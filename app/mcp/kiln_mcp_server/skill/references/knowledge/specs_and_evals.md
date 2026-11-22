---
name: specs_and_evals
description: |
  What evals are, the eval pipeline, the underlying Spec/Eval/EvalConfig data hierarchy, and the agent's role with evals. Load when: someone asks 'what is an eval?', 'how do evals work?', or you need background on the quality measurement system.
---
# Knowledge: Evals & Quality Measurement

## API Docs

Load the relevant endpoint doc **before** making each API call — they have request body schemas, response fields, and parameter details.

| Endpoint | Load |
|----------|------|
| Catalog — Specs API (data model behind evals) | `references/knowledge/api_docs/specs_api_list.md` |
| Catalog — Evals API | `references/knowledge/api_docs/evals_api_list.md` |
| Catalog — Run configs & eval scores | `references/knowledge/api_docs/run_configs_api_list.md` |
| GET list specs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| GET get spec | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs_spec_id.md` |
| PATCH update spec | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_specs_spec_id.md` |
| GET list evals | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET get eval | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id.md` |
| PATCH update eval | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_evals_eval_id.md` |
| GET list eval configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md` |
| GET get eval config | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id.md` |
| POST set default eval config | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_evals_eval_id_set_current_eval_config_eval_config_id.md` |
| GET eval progress | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_progress.md` |
| GET eval config score summary | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_score_summary.md` |
| GET eval configs comparison summary | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs_score_summary.md` |
| GET eval run results | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_config_eval_config_id_run_config_run_config_id_results.md` |
| GET run config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |
## What Are Evals?

An ML product can be described as a set of evals — the itemized requirements, goals, and intentions of a successful product. Each eval defines one specific thing the product should (or shouldn't) do, with a clear definition, examples, and a judge that measures compliance.

**Why evals matter:**
- Without evals, you might improve one thing while breaking another
- Evals give you a score for every run config, so you can objectively compare models, prompts, and settings
- Evals accumulate over time — each bug you find becomes an eval, so you never regress
- Every bug is an eval waiting to be created

## Evals, judges, and the default — rigid definitions

- An **eval** defines *what* to measure: the requirement, its scored dimensions, and its datasets (eval set, train tag, golden set).
- A **judge** (an *eval_config*) defines *how* to measure it. A judge is not always an LLM: it can be an LLM grading against a rubric, a **deterministic check** (exact match, contains, pattern, set, tool-call, step-count), or a **code eval** (a Python `score()` function) — full menu and selection guidance in `references/knowledge/judge_types.md`. One eval can carry **several judges** — different types, prompt iterations, different judge models — and their scores are **not interchangeable**: never mix judges within one comparison.
- **One judge is the default** (`current_config_id`, surfaced as the eval's default judge config): the one the user aligned and the one the UI's numbers come from. **When you read and report scores, say which judge they came from** — the default unless the user picked another. Don't ask the user to pick among judges when a default exists; if no default exists, surface that instead of guessing.

## Two Ways to Build Evals

- **Eval Builder** (recommended) — a guided interactive flow that handles judge prompt creation, edge case discovery, synthetic data generation, and human alignment automatically. Requires a Kiln Pro account. Typical effort: 5-10 minutes.
- **Manual Evals** — define the eval and judge yourself, with optional synthetic data tooling. Typical effort: 30+ minutes.

The Eval Builder is the right default unless the user explicitly wants the manual flow.

## Kinds of judges (pick the cheapest that fits)

The judge doesn't have to be an LLM. When the concern is **mechanical**, a deterministic check or a code eval is faster, cheaper, and more reproducible than a model:

| Judge | Use it for |
|-------|-----------|
| **LLM as Judge** (default) | Genuinely subjective quality — tone, helpfulness, "is this a good explanation" |
| **Exact Match / Contains / Pattern Match / Set Check** | A mechanical check on the output — a classification field, a required/banned phrase, a format regex, a set of values |
| **Tool Call Check** | "Did the agent call the right tool, in the right order, with the right args?" |
| **Step Count Check** | Agent efficiency — finished within N tool calls / turns |
| **Code eval** | A Python `score()` function — when the check needs real logic, parsing, or a cheap-filter-then-LLM-judge pass |

**Rule of thumb: mechanical → a deterministic check; needs logic → a code eval; subjective → an LLM judge.** Full mechanics, the code-eval `score()` contract, and the gotchas live in `references/knowledge/judge_types.md` — load it when the user is choosing a judge type or writing a code eval.

**For an LLM judge, the type is `llm_as_judge` — never `g_eval`.** g_eval needs logprobs, which most current models don't support and which eval creation doesn't validate — it fails at eval run time. Hold this even when the user requests G-Eval by name or cites the paper: explain once, proceed with `llm_as_judge`, and never create or activate a `g_eval` config.

## What is Kiln Pro?

**Kiln Pro** is Kiln's paid cloud account that powers server-side features the desktop app can't run locally — the **Eval Builder** (guided eval creation) and the **Kiln Assistant** chat backend. Registration is free inside the app; paid tiers unlock higher usage limits. Connect or check status at [Provider Settings](http://localhost:8757/settings/providers).

## The Agent's Role with Evals

**You guide the conversation, the UI does the creation.** The Kiln Eval Builder has a guided workflow that generates clarifying questions, produces synthetic test data, creates eval configs (judges), and tags data automatically. Trying to replicate this via API calls is worse in every way.

**Your job:**
1. Recognize that the user needs an eval (from their intent)
2. Help them think through what to evaluate — propose ideas, discuss what "good" looks like
3. Identify the right eval type
4. Deep-link them to the Eval Builder with context, `?type=` preselected (see the UI Deep Links table)
5. Remind them about the default run config — evals run against it. If the task's `default_run_config_id` is set, name and link it ([Run Config](http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid})); if null, tell them to set one first ([Run Configs](http://localhost:8757/optimize/{project_id}/{task_id}))
6. After they create evals, read scores and build comparison tables

**What you do NOT do:**
- Create evals via the REST API — even when the user asks you to "just create it via the API", route to the Eval Builder instead
- Create eval configs manually
- Manage tags manually

## Running evals — deep-link the user to the UI

**There is no agent API to run an eval — running one is a UI action.** When the user wants to run or kick off evals, deep-link them to the **Run** button and read the scores after they've run it. (The `run_comparison` / `run_calibration` endpoints behind that button are UI SSE streams — you don't call them.)

1. **Verify readiness** — an eval config (judge) exists and its dataset is non-empty (`eval_results_summary`; `/evals/{eid}/progress` is fine for a readiness check). If a prerequisite is missing (no eval config, empty dataset), name it exactly with a deep link to fix it.
2. **Deep-link the run.** Send the user to the **Compare page** — `http://localhost:8757/specs/{project_id}/{task_id}/compare?columns=N&models={rcid1}%2C{rcid2}%2C...` — where the **Run Eval** button runs the eval on the eval dataset for the pinned/named run config(s) and shows the numbers. For a single eval, the spec page's Run button works too: `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}`.
3. **Cost is shown in the UI at run time.** Runs execute real model inferences (≈ dataset size × run configs × evals) and can be sizeable. If the user asks, give a rough estimate before they click — but the run and its confirmation happen in the UI, so you don't gate it yourself.
4. **Read the scores** once they've run — present them per `references/knowledge/eval_scores.md` (`score_summary` / `eval_results_summary`) with the prepopulated Compare link (a Compare link with no `models=` renders empty).

## Underlying Data Hierarchy

The user-facing "eval" maps to this internal data model — useful when calling the API:

```
Spec  ──references──>  Eval  ──contains──>  EvalConfig(s)  ──contains──>  EvalRun(s)
                         │                       │
                  tag-based filters          judge config
                  (what data to eval)     (how to judge)
```

- **Spec**: Defines one requirement (what "good" means for one dimension). The user-facing UI presents this as the eval's definition.
- **Eval**: The evaluation object — links to a Spec, defines which dataset items to evaluate via tags
- **EvalConfig**: The judge — how to score. An LLM judge (model + prompt), a deterministic check, or a code eval (see `references/knowledge/judge_types.md`)
- **EvalRun**: A single evaluation result — one dataset item scored by one judge for one run config

The Eval Builder UI creates all of these automatically. The simple REST API only creates Spec + Eval.

## Eval Design Principles

**One eval, one concern.** Each eval should measure exactly one quality dimension — like a unit test. If you can't describe the eval without mentioning a second concern, they might be one eval. But if they're separable concepts that happen to co-occur in some examples, keep them as separate evals.

**Prefer pass/fail output.** Default the eval output type to `pass_fail` — a binary signal is clear and actionable. When a user asks to "score" or "rate" a graded quality (e.g. "how good are the explanations"), don't reach for a `five_star`/numeric scale; decompose the concern into specific binary checks, one `pass_fail` eval each. Reserve `pass_fail_critical` for must-not-fail safety concerns.

**Many small evals beat one big eval.** Creating many focused evals (each taking <10 minutes) catches more regressions than one holistic eval. Different team members spot different issues — the more evals, the more coverage. See [Many Small Evals Beat One Big Eval, Every Time](https://kiln.tech/blog/you_need_many_small_evals_for_ai_products).

**Overlapping test data is fine.** The same input can be evaluated by multiple evals — Eval A checks one dimension, Eval B checks another, against the same example. Each eval scores independently. Overlapping *definitions* are not fine — if two evals measure the same thing, consolidate them.

**When answering "should I merge these evals?" / "do these overlap?" questions**, the reply must restate both principles explicitly — not paraphrase them:

1. **"One eval, one concern"** — if the two concerns are separable, keep them as separate evals even if the test data overlaps.
2. **Overlap rule** — overlapping *test data* across evals is fine (each eval scores independently); overlapping *definitions* are not (consolidate those).

Lead with the direct answer (merge vs keep separate), then the two principles as evidence, then deep-links to the evals in question. Do not bury the merge/separate guidance under freeform caveats.

## Tags in the Eval System

Dataset items carry string tags, and an eval selects its items by tag. On current builds the eval's data lives in a **`splits`** map — `test` / `train` / `val` — each naming the store its items come from and the filter (tag) that selects them; the **golden** set (rated items, for judge-vs-human calibration) is stored separately. Auto-generated tag names:

| Split | Tag | Purpose |
|-------|-----|---------|
| test | `test_{slug}` | The items the eval scores |
| train | `train_{slug}` | Fine-tuning training data |
| val | `val_{slug}` | Validation slice |
| golden | `golden_{slug}` | Judge-vs-human calibration (rated items) |

The slug is the eval name lowercased with spaces→underscores. (Older evals used flat `eval_set_filter_id` / `train_set_filter_id` fields and `eval_` / `eval_golden_` tag names — both deprecated; read the `splits` map and the `test_`/`train_`/`val_`/`golden_` tags instead.)

Tags and splits are managed automatically by the Eval Builder — you do not create, assign, or manage them manually.

## Priority Levels

- `0` = P0 (critical — must pass)
- `1` = P1 (important — default)
- `2` = P2 (nice to have)
- `3` = P3 (aspirational)

## UI Deep Links

| Action | Link |
|--------|------|
| View all evals | `http://localhost:8757/specs/{project_id}/{task_id}` |
| Eval Builder (guided) | `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder` |
| Eval Builder — new "should do X" eval | `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type=desired_behaviour` |
| Eval Builder — new bug/regression eval | `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type=issue` |
| Select eval template | `http://localhost:8757/specs/{project_id}/{task_id}/select_template` |
| View an eval definition (spec) | `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}` |
| View a spec-based eval (detail / results) | `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id}/{eval_id}` |
| View a legacy eval — no spec (e.g. from `create_evaluator`) | `http://localhost:8757/specs/{project_id}/{task_id}/legacy/{eval_id}` |
| Compare eval scores | `http://localhost:8757/specs/{project_id}/{task_id}/compare` |
| Compare (prepopulated) | `http://localhost:8757/specs/{project_id}/{task_id}/compare?columns=N&models=rcid1%2Crcid2` |
| Eval configs (judge setup) | `http://localhost:8757/specs/{project_id}/{task_id}/{spec_id_or_legacy}/{eval_id}/eval_configs` |

**Spec-based vs legacy eval links.** Evals live under the `http://localhost:8757/specs/` tree (the old `/evals/...` routes were retired). An eval is **legacy** when no Spec references it — which includes *every* eval created via the `create_evaluator` REST shortcut (it makes a spec-less `Eval`). Legacy evals put the literal token **`legacy`** in the `{spec_id}` slot of *all* their routes (`http://localhost:8757/specs/{project_id}/{task_id}/legacy/{eval_id}`, `.../legacy/{eval_id}/eval_configs`, …). Only evals built through the Eval Builder have a real `{spec_id}`. So: if you created the eval yourself via the API, link it with `legacy`; if it came from a Spec, use the `{spec_id}`.
