---
status: complete
---

# Implementation Plan: Evals V2 cleanup

Two phases. Phase 1 is all `libs/core`/API and contains the manual real-trace gate; Phase 2 is frontend + the one API field. See `architecture.md` for the technical detail behind each item (§ references below).

## Phases

- [x] **Phase 1 — Backend: contract, helpers, validators, reasoning capture**
  - `V2EvalResult` model + migrate all 8 V2 `evaluate()` adapters and 5 call sites (arch §1).
  - D14/D15: rewrite `get_tool_calls` (OpenAI-format `{name, arguments, id}`) and `get_assistant_messages` (`list[str]`); add real-format fixtures; update `test_eval_helpers.py:51`, `test_code_eval_samples.py:294` (arch §2).
  - **Gate:** manual run of both helpers against a real tool-calling trace before approval (arch §2.3).
  - D27/D28/D29/D30 save-time validators in `eval.py` (arch §3) — coordinate with Project 1 (different classes, same file).
  - D31 backend: `llm_judge` populates `V2EvalResult.intermediate_outputs`; `_run_v2_job` persists it to `EvalRun` (arch §4).

- [ ] **Phase 2 — Frontend + API surface**
  - Add `intermediate_outputs` to `TestV2EvalResponse`; regenerate OpenAPI client + commit (arch §6).
  - D31 UI: thread `intermediate_outputs` into the run-result renderer; "View reasoning" → `Dialog` modal in `llm_judge_result.svelte` (arch §5).
  - D35 UI: `n_excluded` (i) indicator on the compare view (and judge-comparison view if it renders aggregate scores) — yellow ≤20%, red >20% (arch §7).

## Notes

- Run the full check suite (lint/format/type, py + web tests, schema, build) before each phase CR.
- Phases are independent after Phase 1's `V2EvalResult` lands; Phase 2 depends on the persisted `intermediate_outputs` and the new response field.
- A single combined phase is acceptable if preferred — the split mainly separates the manual trace gate from UI review.
