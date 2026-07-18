---
status: complete
---

# Implementation Plan: Code Judge LLM Calls

Phased build order. Details live in `functional_spec.md` and `architecture.md` (§ refs below); this is the ordered checklist.

## Phases

- [x] **Phase 1 — Datamodel foundations** (arch §1)
  - `CodeEvalProperties`: add `tool_allowlist` (+ `validate_allowlist` ported from `CodeTool`, minus self-ref), bump `timeout_seconds` default 30 → 180.
  - `KilnBuiltInToolId`: add `LLM` / `LLM_JUDGE`.
  - `ToolCallContext`: add `eval_output_schema: str | None = None`.
  - Tests: allowlist validation, timeout default, tool-id round-trips, context default. Zero migration.

- [ ] **Phase 2 — Built-in LLM tools + registry** (arch §2)
  - `run_llm_call(...)` shared helper (extract from `LlmJudgeEval` non-g-eval path).
  - `LlmTool` (`kiln_tool::llm`) and `LlmJudgeTool` (`kiln_tool::llm_judge`) in `tools/built_in_tools/llm_tools.py`; Jinja render, schema handling, `build_llm_as_judge_score` mapping, off-context error.
  - `tool_from_id_and_project`: two new match arms.
  - Tests (fake adapter): text vs schema→JSON-string; judge float mapping; parity with stock `LlmJudgeEval`; error surfaces.

- [ ] **Phase 3 — Extract shared parent pump** (arch §3.1)
  - New `tools/sandbox_bridge.py`: `NestedToolServer` (`serve`/`name_map`/`tools_info`), `run_bridged_child`, shared depth/semaphore (`CODE_SANDBOX_MAX_CONCURRENCY`).
  - Refactor `PythonCodeTool` to use it — **behavior-preserving**; existing `sandbox/test_code_tool_execution.py` must stay green unchanged.

- [ ] **Phase 4 — Code-eval bridge integration** (arch §3.2–3.4)
  - `adapters/eval/sandbox_worker.py`: `execute_scorer_bridged` (two-queue, `install_tools_modules`, scores-dict result); remove single-queue `run_scorer`.
  - `CodeEvalAdapter.evaluate`: host `run_bridged_child` with the eval-schema context; delete `_code_eval_execution_lock`.
  - Tests (real spawns): `tools.llm`/`tools.llm_judge` from `score()`, sync + `async def score` w/ `gather`, allowlist enforcement, timeout mid-call, parallel code evals (regression vs deleted global lock), trust short-circuit, shared-lock/semaphore identity.

- [ ] **Phase 5 — UI, examples & schema** (arch §4, §6)
  - Allowlist picker in `code_eval_form.svelte` (reuse code-tool picker); inject `llm`/`llm_judge` into the catalog; scope `llm_judge` to the code-eval context.
  - Add `tools.llm_judge` / cheap-triage examples to `code_eval_helpers.ts`; mirror them in `test_code_eval_samples.py`.
  - Regenerate OpenAPI client; UI tests.

## Notes

- Phases 3 and 4 are split deliberately: 3 is a pure, test-guarded refactor of shipped code-tool behavior; 4 builds the new path on top. Review each in one sitting.
- Deferred (not blocking v1): cost/usage surfacing, `llm` in the general agent add-tools UI, refactoring `LlmJudgeEval` onto `run_llm_call` (arch §7).
