---
status: complete
---

# Phase 2: Manual `llm_judge` emits V2 (ship-blocker)

## Overview

The manual create flow currently writes V1 llm_judge configs (`g_eval`/`llm_as_judge`
config_type with `eval_steps`/`task_description` properties). This phase makes it emit
V2 configs: `config_type="v2"` with typed `LlmJudgeProperties` including a backend-baked
Jinja2 `prompt_template`. The backend owns the template so scale wording stays in sync
with `build_score_schema`. The frontend removes vestigial V1 criteria authoring and sends
only `{model_name, provider, g_eval}` to a new endpoint.

## Steps

### 1. Extract `score_scale_instruction()` in `base_eval.py`

Extract a standalone function `score_scale_instruction(rating_type: TaskOutputRatingType) -> str`
that returns the human-readable scale wording (e.g. "an integer from 1 to 5..."). Refactor
`build_score_schema` to call it, keeping one source of truth.

### 2. Add `build_llm_judge_prompt_template()` and `materialize_llm_judge_properties()` in `base_eval.py`

- `build_llm_judge_prompt_template(output_scores: list[EvalOutputScore]) -> str`: builds the
  owner-approved Jinja2 template with `{% raw %}` for the instruction block and live
  `{{ task_input }}` / `{{ final_message }}` slots.
- `materialize_llm_judge_properties(eval: Eval, model_name: str, model_provider: str, g_eval: bool) -> LlmJudgeProperties`:
  assembles properties with the baked template, explicit `system_prompt` default
  (`"You are an evaluator."`), explicit `thinking_instruction` default
  (`"Think step by step, explaining your reasoning."`), and `required_var=[]`.

### 3. Add `create_llm_judge_config` endpoint in `eval_api.py`

New `POST .../evals/{eval_id}/create_llm_judge_config` accepting
`CreateLlmJudgeConfigRequest { name?, model_name, provider, g_eval }`.
Handler loads the eval, calls `materialize_llm_judge_properties`, creates and saves
`EvalConfig(config_type="v2", properties=...)`.

### 4. Update frontend `llm_judge_form.svelte`

Remove the Advanced section containing `task_description` + `eval_steps` authoring
(the `<Collapse>` with FormElement/FormList). Remove the now-unused `getProperties()`
and `getConfigType()` exports (the form no longer owns properties). Keep model picker
and algorithm selector.

### 5. Update `eval_config_builder.svelte` to use new endpoint

For `llm_judge`, `do_save` calls the new `createLlmJudgeConfig()` API function
(sends `{model_name, provider, g_eval}`) instead of the old `createEvalConfig` with V1
properties. Remove the V1 `getConfigType()` / `getProperties()` calls for the llm_judge
branch. The `can_submit_llm` reactive still gates on model + algo selection.

### 6. Add `createLlmJudgeConfig` to `v2_eval_api.ts`

New TS function that POSTs to the new endpoint and returns the created `EvalConfig`.

### 7. Regenerate OpenAPI schema

Run `generate_schema` to pick up the new endpoint, then `check_schema`.

## Tests

### Python tests (in `test_base_eval.py` or new `test_llm_judge_helpers.py`)

- `test_score_scale_instruction_five_star`: returns "1 to 5" wording
- `test_score_scale_instruction_pass_fail`: returns "pass or fail" wording
- `test_score_scale_instruction_pass_fail_critical`: returns "pass, fail, or critical" wording
- `test_score_scale_instruction_custom_raises`: raises ValueError for custom type
- `test_build_llm_judge_prompt_template`: output contains each score name + instruction + scale
- `test_build_llm_judge_prompt_template_compiles`: Jinja2 compiles and renders
- `test_build_llm_judge_prompt_template_injection`: instruction text with `{{ }}` stays literal
- `test_materialize_llm_judge_properties`: returns correct defaults, required_var=[], compiles

### Backend API tests (in `test_eval_api.py`)

- `test_create_llm_judge_config_success`: persists V2 config with LlmJudgeProperties
- `test_create_llm_judge_config_missing_model`: returns 400
- `test_create_llm_judge_config_missing_eval`: returns 404
