---
name: create_eval
description: |
  Creating an eval: what to evaluate, choosing a deterministic check or an LLM judge, creating a deterministic eval through the API, the Eval Builder for an LLM judge, and the link where the user adds the eval's data. Never the eval's data itself.
---
# Create Eval

How to help the user create an eval. You create a deterministic eval yourself. The Eval Builder in the app is the way to create an LLM-judge eval. The user adds every eval's data in the app.

**Never create eval data through this connection**: no eval inputs, no runs made or tagged to fill an eval's splits, no inputs or outputs you write or generate. Creating eval data needs the user's input at each step, and Kiln's synthetic data tools are built for that (`references/knowledge/synthetic_data.md`). Create the eval only, then send the user to add its data ("Adding the eval's data" below).

Kiln Harness Tuner: the rules for its experimental eval building are in `references/client_guidance/harness_tuner/eval_building.md`. Other agents never read that file.

## Knowledge Required

- `references/knowledge/specs_and_evals.md` — what evals are, the eval pipeline hierarchy, running an eval
- `references/knowledge/judge_types.md` — the judge menu: the deterministic checks, code evals and LLM judges, with their type values
- `references/knowledge/synthetic_data.md` — why eval data is made in the app, and what not to do instead

## API Docs

Load the relevant endpoint doc **before** making each API call.

| Endpoint | Load |
|----------|------|
| Specs API catalog (data model) | `references/knowledge/api_docs/specs_api_list.md` |
| GET task (check `default_run_config_id`) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| GET specs list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| GET list evals | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET list eval configs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals_eval_id_eval_configs.md` |
| GET check the Kiln Pro key | `references/knowledge/api_docs/get_api_provider_verify_kiln_copilot_api_key.md` |
| POST create evaluator (an eval with no spec) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_create_evaluator.md` |
| POST create spec (the spec and its eval) | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_specs.md` |
| POST edit run tags | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_runs_edit_tags.md` |

Use the reads to see what exists before and after the eval is built. To add a judge to an eval that exists, use `references/knowledge/judge_types.md`.

## Discuss what to evaluate

Eval content is **domain-expert territory**. The user knows the regression surface; you do not. Never assume what evals a task needs.

1. Propose eval ideas: "For this task, you might care about: X, Y, Z. Which of these matter? What else?"
2. Help the user state each eval: what "good" looks like, and the failures they have seen.
3. Map the problem to a type of eval ("From a problem to a type of eval" below), then follow the three steps.

**Exception — cold start help:** when the user asks you to write the eval's content ("help me with the cold start", "write the description and examples"), write it at once: the full description, and correct and incorrect examples, in one message. This is text for the user to review, not eval data.

## Creating an eval, in three steps

### 1. Choose the kind of judge

Choose from the concern, with `references/knowledge/judge_types.md`:

- **A deterministic check or a code eval**, when the concern is mechanical: an exact value, a substring, a regex (pattern match), a set of values, a required tool call, a step budget, or logic in a Python `score()` function.
- **An LLM judge**, when the concern is subjective: tone, helpfulness, completeness, factual quality. The `spec_type` values in "Eval Type Reference" below create LLM-judge evals.

### 2. A deterministic check or a code eval: offer to create it

Deterministic eval types include Exact Match, Contains, Pattern Match (regex), Set Check, Tool Call Check, Step Count Check and code evals (the full menu: `references/knowledge/judge_types.md`).

Offer to create the eval yourself. You are good at these, and the API path loses nothing against the app.

1. Create the eval with no spec: `POST /api/projects/{project_id}/tasks/{task_id}/create_evaluator` (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_create_evaluator.md`). Its links use `legacy` (`references/knowledge/specs_and_evals.md`, "UI Deep Links").
2. Add its judge with `references/knowledge/judge_types.md`. A code eval needs code trust first.
3. Send the user to add its data ("Adding the eval's data" below).

When the user prefers the app, link the form for the check: `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?judge={type}&workflow=manual` (type values in `references/knowledge/judge_types.md`).

### 3. An LLM judge: the Eval Builder

The guided **Eval Builder** is the best way to make an LLM-judge eval. It asks the user clarifying questions, generates test data from their answers, has the user rate it, and aligns the judge to those ratings. It needs a **Kiln Pro** account (`references/knowledge/specs_and_evals.md`, "What is Kiln Pro?"). It takes about 5 minutes, against 30 or more by hand.

1. Check Kiln Pro: `GET /api/provider/verify_kiln_copilot_api_key` returns `is_valid`.
2. **Kiln Pro is connected:** link the [Eval Builder](http://localhost:8757/specs/{project_id}/{task_id}/builder). It opens on a box where the user describes the eval.
3. **Kiln Pro is not connected:** recommend that the user signs in at [Kiln Pro](http://localhost:8757/settings/providers/kiln_pro), because the Eval Builder gives the best LLM-judge eval. Registration is free. When they have signed in, check again and link the Eval Builder.
4. **The user declines Kiln Pro:** link the [Create Eval](http://localhost:8757/specs/{project_id}/{task_id}/select_template) page. It offers every way to make an eval; without Kiln Pro it opens on the templates, where the user defines the eval, its examples and its judge. When the type is already chosen, link the form for that template instead: `http://localhost:8757/specs/{project_id}/{task_id}/spec_builder?type={spec_type}` (`?type=desired_behaviour` for "should do X", `?type=issue` for a bug or a regression).

**When the user asks you to build the LLM judge in the chat**, say that it is not recommended: an eval built this way has no clarifying questions, no generated data and no judge aligned with the user's ratings, so its scores are less trustworthy. If the user still wants it, create it: `POST /api/projects/{project_id}/tasks/{task_id}/specs` (`references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_specs.md`) creates the spec and its eval, and `references/knowledge/judge_types.md` adds the judge. Then send the user to add its data ("Adding the eval's data" below). Never create the data yourself.

The Eval Builder saves the eval's splits as eval inputs, with its data. The forms for a template or a check, and the API, save splits of task runs, selected by a tag (`references/knowledge/train_val_test.md`, "Which items each way of making an eval saves").

### Adding the eval's data

The Eval Builder generates the eval's data as part of its flow. An eval that you create through the API has no data: it needs items in its train, val and test splits. Always end with the link to the page where the user adds them:

`http://localhost:8757/dataset/{project_id}/{task_id}/add_data?reason=eval&eval_id={eval_id}`

Use the eval's own `id`. The page reads the rest from the eval: which tags the data goes to and in what shares, the tool of a tool-call eval, and the link back. Do not add other parameters.

The page offers several ways to add the data, and sends each item to the eval's splits:

- generate synthetic data, the recommended way (`references/knowledge/synthetic_data.md`);
- upload a CSV file;
- tag existing runs in the dataset.

- **Existing runs.** When the user names real runs and asks you to tag them into one of the eval's splits, tag them with `POST /api/projects/{project_id}/tasks/{task_id}/runs/edit_tags`. Never choose runs yourself to fill a split, and never make runs to tag.
- **An eval whose test split holds eval inputs** (a benchmark eval, `references/knowledge/benchmark_eval_inputs.md`): the page cannot add to it. Its data comes from the Eval Builder.

**Default run config reminder.** Evals run against the task's default run config. With the handoff, check the task's `default_run_config_id` (GET task): if set, name the linked config ([Run Config](http://localhost:8757/optimize/{project_id}/{task_id}/run_config/{rcid})); if null, tell the user to set a default run config first ([Run Configs](http://localhost:8757/optimize/{project_id}/{task_id})).

### Verify creation

After the eval exists, verify it through the API:

```
# read first: references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md
call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/specs", jq_filter="[.[] | {id, name, spec_type, priority}]")
```

Confirm the evals look right. When their data is in, suggest running them for baseline scores. (The API uses the names `specs` and `spec_type`, from the data model; call them "evals" to the user.)

## From a problem to a type of eval

Every quality problem that the user wants fixed becomes at least one eval, so it stays measured and does not come back:

| The problem | The eval |
|---|---|
| A specific bug | An `issue` eval for that bug |
| Hallucinations, made-up facts | A `hallucinations` or a `factual_correctness` eval |
| General quality | 2–3 evals on the dimensions that matter most, for example `completeness`, `formatting`, `desired_behaviour` |

## Eval Type Reference

These `spec_type` values create **LLM-judge** evals (step 3 above). When the concern is mechanical (an exact value, a regex, a required tool call, a step budget), a deterministic check or a code eval fits better and skips the spec step (step 2 above).

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
