---
status: complete
---

# Implementation Plan: Evals V2 — LLM-as-Judge Prompt Regression Fix

Small, coherent change across core + API + web. One phase — reviewable in a single sitting.

## Phases

- [x] Phase 1: Rich, editable judge prompt

  Backend (core): add `build_default_llm_judge_prompt(eval)` + `_conditionally_raw_wrap`
  (per-piece `{% raw %}`, `{{`/`{%`/`{#` detection, `{% endraw %}` defuse); remove the blanket
  `{% raw %}` + `_sanitize_for_raw_block`; extend `materialize_llm_judge_properties` with
  `judge_prompt` / `system_prompt` overrides. Update `test_base_eval.py` incl. the V1-parity
  characterization test.

  Backend (API): add `judge_prompt` / `system_prompt` to `LlmJudgeBuilderInput`; thread through
  `create_llm_judge_config` + `test_v2_eval`; add `GET .../default_llm_judge_prompt` +
  `DefaultLlmJudgePromptResponse`. Add API tests.

  Frontend: `getDefaultLlmJudgePrompt` wrapper; regenerate OpenAPI client; thread overrides
  through `createLlmJudgeConfig` / `testV2EvalLlmJudge`; add the "Advanced: Judge Prompt"
  collapse (judge prompt + system prompt fields, pre-filled, graceful fetch failure) in
  `llm_judge_form.svelte` / `eval_config_builder.svelte`. Add vitest coverage.

  Close-out: run the full checks suite (ruff, ty, pytest, web lint/format/check/test/build,
  schema check) and fix anything introduced.
