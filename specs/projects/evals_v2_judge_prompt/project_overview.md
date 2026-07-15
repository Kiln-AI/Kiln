---
status: complete
---

# Evals V2 — LLM-as-Judge Prompt Regression Fix

On the `scosman/evals_v2` branch we're building evals v2. The "LLM as judge" eval-config
creation flow has two issues. Example UI URL:
`.../create_eval_config/llm_judge?next_page=eval_configs` (issues are likely backend).

## Issue 1 — The judge prompt is a major regression vs V1

The V2 judge prompt is generic and impoverished. For a "Be Funny" joke spec, V2 produces a
prompt whose only criterion is the auto-generated one-liner
`"Evaluate if the model's behaviour meets the spec: Be Funny."`, with system prompt
`"You are an evaluator."`.

An **old V1** LLM-as-judge for the same eval/spec was far richer — it had a full task
description (the joke-task description) and detailed, numbered evaluation steps. The V1
prompt leverages the work the user already did (task instruction, spec definition,
examples); the V2 one throws all of that away.

## Issue 2 — No way to edit the judge prompt when creating one

There is zero opportunity in the UI to edit the judge prompt when creating a new LLM judge.
Auto-filling it is good, but it should be editable. This is a regression vs `main`.

---

## Root cause (corrected — the data is already there)

The rich content is **not missing from the system** — it's already stored on objects the
create flow holds in hand, and the V2 code simply stops assembling it:

- On `main`, `create_eval_config/+page.svelte` builds the prompt at create time from
  **already-stored data**: `task_description = task.instruction`, and
  `eval_steps = get_eval_steps(evaluator.template, task, evaluator, spec)` — derived from
  the eval template, task requirements, and the **spec's** definition/examples. It shows
  these in **editable** fields and POSTs them.
- V2 deleted the assembly (`eval_steps_utils.ts` / `get_eval_steps`) and the
  `task.instruction` seeding. The V2 endpoint `create_llm_judge_config` accepts only
  `model_name`/`provider`/`g_eval`/`name` and bakes the prompt in
  `build_llm_judge_prompt_template()` (`libs/core/kiln_ai/adapters/eval/base_eval.py`) from
  the single field `eval.output_scores[].instruction` — which specs auto-fill with just the
  generic one-liner. The V2 create form (`llm_judge_form.svelte`) shows only a model +
  algorithm picker and no editable prompt.
- The V2 create flow **already has** `evaluator`, `task`, and `spec` in hand
  (`EvalConfigBuilder` receives them), and server-side an eval can reach its task via
  `eval.parent_task()` and its spec via `eval.associated_spec()` (returns `None` for legacy
  evals). So `task.instruction`, `spec.definition`, and examples are all reachable — nothing
  new needs to be stored.

## Agreed design (simple: one editable string, full flexibility)

- The judge prompt is **one editable string** (the full prompt template). The user can edit
  anything they want — we stop modelling it as separate `task_description` / `eval_steps`
  concepts in the API and UI.
- A **server-side assembly** builds a *rich default* judge-prompt string from the eval + its
  task + its associated spec (task instruction, spec definition, examples, per-score scale),
  replacing the impoverished `build_llm_judge_prompt_template`. Deterministic — no LLM call.
- The create UI **fetches** that default (new endpoint), renders it in a single editable
  textarea, and sends the (possibly edited) string back.
- `create_llm_judge_config` accepts a single optional `judge_prompt` string → stored as
  `LlmJudgeProperties.prompt_template`. If omitted, the endpoint assembles the same rich
  default server-side (so agents/API get richness too).
- The "test your judge" path uses the same string, so the test reflects the edited prompt.

### Explicitly out of scope

No datamodel/storage changes. No snapshotting. No Copilot V1→V2 config migration (tracked
separately in `eval_copilot_builder_v2`). No structured `task_description`/`eval_steps`
fields in the API or UI.

## Goal

Restore a rich, V1-fidelity auto-filled judge prompt (assembled from the user's existing
task/spec data) and make it fully editable as a single string in the create UI.
