---
status: complete
---

# Implementation Plan: Kiln Evals V2

Phased build order, dependency-first. Each phase is a coherent, reviewable unit. **This is a checklist that references `components/` for detail — it does not restate it.** The coding agent writes a detailed `phase_plans/phase_N.md` (steps, exact changes, test cases) before building each phase, per the spec process.

The phasing is derived from the V2 design's Stage-6 roadmap. Data model first (everything depends on it), then the runtime backbone, then types, then the differentiator (code eval), then UI.

## Prerequisite status (read before Phase 1)

- ✅ **`input_transform` (Jinja2) infra — already in `main`.** `libs/core/kiln_ai/utils/jinja_engine.py` + `InputTransform` on `KilnAgentRunConfigProperties`. Design: `components/06` (reference only — **do not rebuild**). Phase 2 consumes it.
- ⛔ **Two prereqs are built inside Phase 1** (see below): the thinking-formatter fix (`components/05`) and the V1 `validate_template_properties` bug fix (`components/15 §4.3`, still present in `eval.py:479-485`).

## Phases

- [x] **Phase 1 — Prereqs + additive schema foundation.**
  (a) Fix the V1 `validate_template_properties` bug per `components/15 §4.3` (V2 can't create non-template Evals until this lands). (b) Add the opt-in `forward_thinking_instructions` to `SingleTurnR1ThinkingFormatter` per `components/05` (standalone; V2 `llm_judge` uses it in Phase 4; V1 default unchanged). (c) Additive schema per `components/10` + `components/15`: `EvalConfig` v2 enum + typed `V2EvalConfigProperties` union + `mode="before"` parsing validator + `validate_properties` v2 branch; `Eval.eval_input_filter_id` (+ mutual-exclusivity, optional `eval_set_filter_id`); `EvalRun` additive fields (`eval_input_id`, `reference_data`, `skipped_reason`) + relaxed score/output validators when skipped + `validate_output_fields` v2 bypass (C.runner.2); new `EvalInput` `KilnParentedModel` + `Task.parent_of`; `EvalInputFilter` protocol/registry; `legacy_model_fields` helper extraction + `eval_adapter_from_type(EvalConfig)` dispatch refactor. Characterization tests for the existing `GEval` ref-answer path first. Code-grounded line-level plan: `reference/backwards_compat_plan_grounded.md`.

- [x] **Phase 2 — Template + extraction layer + V2 runner backbone.**
  Eval consumer over the landed `input_transform` infra per `components/40`: `EvalTaskInput` assembly, `extract()` usage, `required_var` skip-with-reason pre-check, save-time template/expression compilation. V2 runner per `components/45`: EvalInput flow, two-level adapter dispatch (`config_type` → `properties.type`), multi-config orchestration, missing-reference skip handling, `EvalRunner.__init__` source branching (C.runner.3), TaskRun→EvalInput runtime translation (B2.1). Per-type adapter contract scaffolding per `components/20`. Reference-data consumption per `components/50`. Score provenance / skip records per `components/85`.

- [x] **Phase 3 — Deterministic + agent eval types.**
  The six config-driven types per `components/22`: `exact_match`, `pattern_match`, `contains`, `set_check`, `tool_call_check` (J.37 expanded shape), `step_count_check` (J.38). Each as a V2 adapter plugged into the Phase-2 dispatch, consuming the `extract()` layer. Detail for the agent types: `reference/batch_agent_eval_expansion.md`.

- [x] **Phase 4 — Enhanced `llm_judge` + RAG judge templates.**
  Enhanced `llm_judge` per `components/21`: per-criterion pass/fail, trace condensation, reference-data templating, `g_eval` toggle, structured output. **Wire it to the fixed `SingleTurnR1ThinkingFormatter`** (`forward_thinking_instructions=True`) from Phase 1; add coverage proving reasoning-model judges receive the criteria. Then the 6 first-party RAG `llm_judge` templates per `components/29` (pure content over the reference-key contract — faithfulness, answer relevance, context relevance, context precision, hallucination, answer correctness).

- [x] **Phase 5 — `code_eval` (Beta).**
  Per `components/27` (B.13): `sandbox_worker.py` (`_execute_scorer` + `run_scorer`) in a `multiprocessing` spawn worker with `freeze_support()`; `CodeEvalAdapter` through the V2 registry; scorer contract (`def score(output, trace, reference_data, task_input, kiln) -> dict[str, float]`) + helper library; return-shape validation; wall-clock timeout (`p.join`/`p.kill`); optional `setrlimit` (P2, cut if complex); trust-gate enforcement (`CodeEvalNotTrustedError`); documented limitations (network/FS open, trust-gate-only). Include the cold-start spike on the real bundle.

- [x] **Phase 6 — Create + view UI.**
  Per `components/70`: pluggable per-type create container (generic test-run + save + clone-not-edit, G.1); code-eval create UI (CodeMirror 6 lazy-loaded, sandboxed preview via Phase-5 worker, ephemeral trust gate, Beta, G.2); per-type renderer registry keyed on `properties.type`, exhaustive over `V2EvalType` (G.3); deterministic-type forms (§3.1). **Per-type result rendering is intentionally not pinned** — build it from each type's available data using the UI-design skill; `components/70 §4.1` is illustrative guidance, not a binding layout. View surfaces to integrate: `components/70 §4.2`.

## Not in this build (out of scope — do NOT implement)

These are owned by future, separate projects or deferred post-V2. Listed so they aren't accidentally pulled in:

- **Feedback pipeline / triage** (Batch F punted) — future Feedback Pipeline project. `EvalInput` ships without `source_task_run_id`.
- **Goal-first onboarding redesign** (questionnaire, routing, right-sizing mechanism) — future onboarding project.
- **Spec-builder reliability** (H.29) — unrelated to evals V2.
- **Multi-turn-synthetic scoring/runner** — parallel project (data model leaves a slot only).
- **Deferred eval types** — `composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric` (A2.4).
- **Statistical comparison primitives** (E.21), **dataset versioning** (E.33 non-goal), **runtime plugin discovery** (E.36).

Rationale + full scope map: `components/00_overview.md §3`. Residual risks: `components/90_open_risks.md`.
