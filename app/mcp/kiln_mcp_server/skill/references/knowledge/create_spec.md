---
name: create_spec
description: |
  Knowledge for creating evals (quality requirements) — guided conversation, eval types, Eval Builder deep-links. Loaded by the Project Operations mode.
---
# Create Eval

Reference knowledge for guiding eval creation conversations and deep-linking to the Kiln Eval Builder. The agent discusses what to evaluate; the Eval Builder is the recommended way to create the eval.

## Knowledge Required

- `references/knowledge/specs_and_evals.md` — for background on what evals are, the eval pipeline hierarchy, and agent's role
- `references/knowledge/judge_types.md` — the judge menu, when the concern is mechanical (a deterministic check) or the user wants a code eval rather than an LLM judge

## API Docs

Load the relevant endpoint doc **before** making each API call.

| Endpoint | Load |
|----------|------|
| Specs API catalog (data model) | `references/knowledge/api_docs/specs_api_list.md` |
| GET task (check `default_run_config_id`) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| GET specs list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| GET list evals | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET list eval configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md` |
| POST create spec (the spec and its eval) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_specs.md` |
| POST create evaluator (an eval with no spec) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_create_evaluator.md` |

Use them to verify what exists before and after the eval is built. Recommend the Eval Builder for creation where it fits. You may also create the eval yourself ("Creating an eval through the API" below). To add a judge to an eval that exists, use `references/knowledge/judge_types.md`.

## Suggested Questions

1. **What's the problem?** "What's not working, or what quality dimension do you want to measure?" (bug, missing behavior, formatting, hallucinations, tone)
2. **Have they seen specific failures?** Examples of bad outputs help choose the right eval type.
3. **Do they have a Kiln Pro account?** This determines whether to recommend the guided Eval Builder flow or manual setup. If they are not signed in, ask them to sign in at [Kiln Pro](http://localhost:8757/settings/providers/kiln_pro).

## Eval Creation Approaches



### Discuss What to Evaluate

Eval content is **domain-expert territory**. The agent does not know the regression surface — the user does. Never assume what evals a task needs.

1. Propose eval ideas conversationally — "For this task, you might care about: X, Y, Z. Which of these matter? What else?"
2. Help the user articulate each eval — ask what "good" looks like, what failure modes they've seen
3. Recommend an eval type from the reference below and explain why
4. **Always include an Eval Builder deep-link** ([Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/select_template)) — even for conceptual questions about evals, give the user a link so they can act immediately. When the eval type is already chosen, you can link the form for that template instead (`http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type={spec_type}` — `?type=desired_behaviour` for "should do X" asks, `?type=issue` for bugs/regressions)
5. Link to relevant blog posts when they add value (see Reference section at end of file)

**Exception — cold start help:** When the user explicitly asks the agent to write eval content ("help me with the cold start", "write the description and examples"), write it out immediately. Produce the full description, correct and incorrect behavior examples in one message.

### Choose the Creation Method

Always present both options and help the user choose:

**Option 1: Eval Builder (Recommended)** — A guided conversation flow in the UI that handles eval creation automatically: turns rough ideas into refined evals, generates synthetic test data, calibrates the judge prompt, and creates the full Spec → Eval → EvalConfig pipeline.

**Prerequisite:** Requires a **Kiln Pro** account; the user signs in at [Kiln Pro](http://localhost:8757/settings/providers/kiln_pro). A complete eval with the Eval Builder takes ~5 minutes vs 30+ minutes for manual setup.

**Option 2: Manual Setup** — If Kiln Pro is not configured, the user picks a template or a check on the same Eval Builder page, and the app opens the form for it, without the guided flow. The user defines the eval definition, examples, and judge config themselves. Or you create the eval through the API ("Creating an eval through the API" below), and the user adds its data in the app.

**Note:** The guided Eval Builder saves the eval's splits as EvalInputs; the forms for a template or a check, and the API, save splits of task runs (`references/knowledge/train_val_test.md`, "Which items each way of making an eval saves"). An eval made through the API has none of the Eval Builder's generated data or aligned judge. Say so when the user asks for the API path.

### Deep-Link to Eval Builder

When the user is ready, send them to the [Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/select_template). From a description it opens the guided flow; it also lists the templates and the checks. When the eval type is already chosen, you can link the form for that template, with the type in the URL — `?type=desired_behaviour` for "should do X" asks, `?type=issue` for bugs/regressions (values from the `spec_type` reference below):

> "That sounds like a regression test for [issue]. Let me link you to the form for an issue eval, where you can define it with examples:
> [Create Eval](http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type=issue)
>
> A few things to include:
> - Definition: describe the failure mode clearly
> - Examples: 1-2 inputs where the bug occurred, with the correct expected output"

Deep-link to the [Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/select_template), or to the form for a template: `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type={spec_type}`.

**Default run config reminder.** Evals run against the task's default run config. Alongside the Eval Builder handoff, check the task's `default_run_config_id` (GET task): if set, remind the user which config is linked ([Run Config](http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid})); if null, remind them to set a default run config first ([Run Configs](http://localhost:8757/optimize/{project_id}/{task_id})).

### Creating an eval through the API

You may create the eval or the spec yourself through the API. You are particularly good at the evals that a program checks: code evals, regex (pattern match) and conditional checks (`references/knowledge/judge_types.md`).

- **An eval with a spec:** `POST /api/projects/{project_id}/tasks/{task_id}/specs` (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_specs.md`) creates the spec and its eval. Add a judge with `references/knowledge/judge_types.md` before the eval can score.
- **An eval with no spec**, for example a programmatic check: `POST /api/projects/{project_id}/tasks/{task_id}/create_evaluator` (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_create_evaluator.md`), then add its judge with `references/knowledge/judge_types.md`. Its links use `legacy` (`references/knowledge/specs_and_evals.md`, "UI Deep Links").
- Either way, each split holds task runs, selected by a dataset filter, most often a tag (`references/knowledge/train_val_test.md`).

**Never create eval data through this connection**: no eval inputs, no dataset items and no synthetic data. Creating eval data is hard, needs the user's input and Kiln's synthetic data tools, and this connection is not set up for it. Create the eval only, never its dataset, and send the user to the app for the data, for example the [Synthetic Data page](http://localhost:8757/generate/{project_id}/{task_id}/synth).

### Verify Creation

After the user creates evals, verify via API:

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/specs", jq_filter="[.[] | {id, name, spec_type, priority}]")
```

Confirm the evals look right and suggest running them to get baseline scores. (The underlying API still uses `specs` and `spec_type` field names — that's the data-model name; surface them to the user as "evals".)

## From a problem to a type of eval

Every quality problem that the user wants fixed becomes at least one eval, so it stays measured and does not come back:

| The problem | The eval |
|---|---|
| A specific bug | An `issue` eval for that bug |
| Hallucinations, made-up facts | A `hallucinations` or a `factual_correctness` eval |
| General quality | 2–3 evals on the dimensions that matter most, for example `completeness`, `formatting`, `desired_behaviour` |

## Eval Type Reference

These `spec_type` values create **LLM-judge** evals. When the concern is mechanical (an exact value, a regex, a required tool call, a step budget), a deterministic check or a code eval fits better and skips the spec step — deep-link the form for that check, `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?judge={type}&workflow=manual`, and see `references/knowledge/judge_types.md` for the menu and type values.

The underlying `spec_type` enum (kept for API compatibility) defines the kind of eval:

### Functionality
| Type | Use When |
|------|----------|
| `desired_behaviour` | Agent should do something specific |
| `issue` | Agent exhibits a specific problem (bugs, regressions) |
| `tone` | Voice/tone requirements |
| `formatting` | Output format rules |
| `localization` | Language/locale rules |

### Task Performance
| Type | Use When |
|------|----------|
| `appropriate_tool_use` | Agent should use tools correctly |
| `reference_answer_accuracy` | Output must match a reference answer (RAG only)|

### Accuracy
| Type | Use When |
|------|----------|
| `factual_correctness` | No factual errors |
| `hallucinations` | No fabricated information |
| `completeness` | Output must be thorough |

### Safety
| Type | Use When |
|------|----------|
| `toxicity` | No toxic content |
| `bias` | No biased content |
| `jailbreak` | Resist jailbreak attempts |
| `prompt_leakage` | Don't leak system prompt |

**Reference:** [The Requirements Layer Your AI System is Missing](https://kiln.tech/blog/requirements_layer_your_ai_system_is_missing), [Many Small Evals Beat One Big Eval, Every Time](https://kiln.tech/blog/you_need_many_small_evals_for_ai_products).

## See also

When and why, in the knowledge: `references/improving_agents/playbooks/dealing-with-a-wrong-eval.md`, `references/improving_agents/playbooks/dealing-with-a-saturated-eval.md`, `references/improving_agents/playbooks/dealing-with-a-noisy-eval.md`, `references/improving_agents/playbooks/dealing-with-an-eval-near-zero.md`.
