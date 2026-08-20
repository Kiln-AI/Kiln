---
status: complete
---

# Phase 1: Rich, Editable Judge Prompt

## Overview

Restore V1-fidelity auto-filled judge prompts for V2 llm_judge eval configs and make them editable in the create UI. The rich content is assembled server-side from data already stored on the eval's task and spec -- no datamodel changes, no LLM calls.

## Steps

1. **Core: `_conditionally_raw_wrap` + `_defuse_endraw`** in `libs/core/kiln_ai/adapters/eval/base_eval.py`
   - Add `_JINJA_OPENERS = ("{{", "{%", "{#")`
   - Add `_defuse_endraw(text: str) -> str` to neutralize `{% endraw %}` tokens
   - Add `_conditionally_raw_wrap(text: str) -> str` that checks for Jinja openers and wraps only when needed
   - Remove `_sanitize_for_raw_block`

2. **Core: `build_default_llm_judge_prompt`** in same file
   - New public function `build_default_llm_judge_prompt(eval: Eval) -> str`
   - Assembles: Task Description block (from `eval.parent_task().instruction`), Evaluation Steps (criteria lines from spec/score), safety line, data slots
   - Criteria: for each score, use `spec.definition` if spec-matched, else `score.instruction`, else `score.name`
   - Scale text via `score_scale_instruction`
   - Remove or gut `build_llm_judge_prompt_template`

3. **Core: extend `materialize_llm_judge_properties`** signature
   - Add `judge_prompt: str | None = None, system_prompt: str | None = None`
   - Use override if non-empty, else build default

4. **API: `LlmJudgeBuilderInput` fields** in `app/desktop/studio_server/eval_api.py`
   - Add `judge_prompt: str | None = None` and `system_prompt: str | None = None`
   - Thread through `create_llm_judge_config` and `test_v2_eval`

5. **API: `GET default_llm_judge_prompt`** endpoint
   - `DefaultLlmJudgePromptResponse` model
   - Route returns `build_default_llm_judge_prompt(eval)` + default system prompt

6. **Frontend: `v2_eval_api.ts`** wrapper
   - `getDefaultLlmJudgePrompt` function
   - Thread `judge_prompt`/`system_prompt` through `createLlmJudgeConfig` and `testV2EvalLlmJudge`

7. **Frontend: `llm_judge_form.svelte`** UI
   - Add `project_id`, `eval_id`, `task_id` props + bound `judge_prompt`/`system_prompt`
   - Fetch default on mount, populate fields
   - Render "Advanced: Judge Prompt" Collapse with two FormElement textareas

8. **Frontend: `eval_config_builder.svelte`** integration
   - Hold `llm_judge_prompt`/`llm_system_prompt` state
   - Pass into LlmJudgeForm, include in create and test calls

9. **Regenerate OpenAPI client**

## Tests

- `test_conditionally_raw_wrap_bare`: clean text returns unchanged
- `test_conditionally_raw_wrap_jinja_detected`: text with `{{` gets wrapped
- `test_conditionally_raw_wrap_lone_brace`: `{` alone stays bare
- `test_defuse_endraw`: `{% endraw %}` token is neutralized
- `test_build_default_llm_judge_prompt_spec_backed`: spec-backed eval uses spec.definition
- `test_build_default_llm_judge_prompt_no_spec`: legacy eval falls to score.instruction
- `test_build_default_llm_judge_prompt_no_instruction`: score falls to score.name
- `test_build_default_llm_judge_prompt_no_task_instruction`: omits Task Description block
- `test_build_default_llm_judge_prompt_multi_score`: multi-score with only spec-matched using definition
- `test_build_default_llm_judge_prompt_jinja_in_content`: conditional raw wrapping applied
- `test_build_default_llm_judge_prompt_v1_fidelity`: characterization test pinning structure
- `test_materialize_with_overrides`: judge_prompt/system_prompt overrides used
- `test_materialize_empty_override_uses_default`: empty string falls to default
- API tests for GET default_llm_judge_prompt, create with overrides, test with overrides
- Frontend tests for pre-fill, edit propagation, graceful fetch failure
