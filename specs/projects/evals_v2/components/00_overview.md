---
status: complete
approved: true
alignment_refs: [A0.1, A0.2, A0.3, A0.4, A0.5, A0.6]
opens: []
summary: V2 north star, principles in application context, in/out-of-scope, parallel-project coordination.
---

# Kiln Evals V2 -- Overview

This is the front-door document for the V2 evals design. Read this first; follow links into the per-topic design files for implementation detail.

## 1. North star

V2 is a typed, extensible eval framework that replaces V1's single-type LLM-as-judge model with **many EvalConfigTypes producing scores per Eval**, backed by **purpose-built EvalInput datasets with per-case structured reference data**. It is designed for "many small evals" -- lowering the floor for creation so a small focused eval beats both "no eval at all" and an oversized eval that overfits.

V2 is **additive over V1**. V1 records on disk are never rewritten. V1 EvalConfigs (`g_eval`, `llm_as_judge`) continue to load and run unchanged under V2 via legacy adapter dispatch. New eval types, new dataset entities, and new scoring paths live alongside V1 -- they never replace it on disk.

V2.0 (the launch deliverable) ships 8 eval types, a Jinja2 template + extraction layer, a runner that handles both EvalInput and TaskRun sources, minimal-but-complete UI for creating and viewing V2 eval types, and the extensibility seams for post-V2 growth. See section 3 for the full scope map.

Source: `V2_PITCH.md` (direction pitch), `PROJECT.md` (original brief).

---

## 2. Governing principles

Six foundational principles govern every design decision across the V2 design set. Each is locked in `reference/ALIGNMENT.md` (A0.1--A0.6). Below is how each principle applies across the design -- not the principle text itself (see `reference/ALIGNMENT.md` for that), but where it shows up and what it constrains.

### A0.1 -- V2 reads V1; V2 never migrates V1

V2 code adds new fields, new enum values, and new parsing branches. It never rewrites V1 records on disk. V1 clients failing on V2-only records is acceptable (users upgrade forward).

**Where it lands:**
- The entire coexistence layer (`components/15_v1_v2_coexistence.md`) derives from this principle -- legacy enum dispatch, additive fields, parsing routing, validator bypass, filter coexistence.
- `EvalConfig` adds `config_type = "v2"` as a new enum value; legacy `g_eval`/`llm_as_judge` stay in the enum forever (`components/10_data_model.md`).
- `EvalRun` gains additive optional fields (`eval_input_id`, `reference_data`, `skipped_reason`) that V1 EvalRuns load with as `None` (`components/10_data_model.md`).
- Runner constructor branches on source type without changing V1 paths (`components/45_runner_architecture.md`).
- D.5 ("V1 backwards compatibility is absolute") locks zero V1 behavior changes for read + execution of existing records (`components/40_template_and_extraction.md`).

### A0.2 -- Many small evals; builder right-sizes to input

A small focused eval beats either no eval or an oversized eval. The builder should scale synthesis to the input.

**Where it lands:**
- The 1:1 Eval-to-EvalConfig cardinality model (C.9) reinforces "many small evals" -- multi-approach means multi-Eval, not multi-config-under-one-Eval (`components/45_runner_architecture.md`).
- The V2 create container (`components/70_builder_and_onboarding.md`) sits at config-creation altitude under an existing Eval, keeping creation lightweight.
- **The specific right-sizing mechanism is deferred** to a future goal-first onboarding project (see section 4). The principle itself outlives V2 and is recorded as a north-star constraint for that project.

### A0.3 -- Config-first; code is an escape hatch

New eval functionality is config wherever it works. Code is admissible only because B.13 closed the execution story (multiprocessing + trust-gate UX, not full sandbox).

**Where it lands:**
- 7 of the 8 V2.0 launch types are config-driven (`components/20_eval_config_types_overview.md`).
- `code_eval` is the single code-typed escape hatch (`components/27_type_code_eval.md`), gated by a trust-gate UX and shipped as Beta.
- The extensibility stance (E.36) reinforces config-first: closed catalog + `code_eval` for the long tail; no runtime plugin discovery in V2.0 (`components/80_extensibility_contract.md`).

### A0.4 -- Local-first; PyInstaller bundle stays clean

Kiln runs locally. Bundle bloat or runtime dependencies require explicit budget approval.

**Where it lands:**
- `code_eval` execution uses stdlib `multiprocessing` -- 0 MB overhead, no WASM (`components/27_type_code_eval.md`).
- The closed plugin catalog (E.36) is partly driven by this: the PyInstaller bundle cannot `pip install` at runtime (`components/80_extensibility_contract.md`).
- No new runtime dependencies introduced anywhere in the V2 design.

### A0.5 -- Feedback closes the loop (north-star direction; not a V2.0 deliverable)

Feedback should be an entry point into the eval pipeline, not a write-only journal.

**Where it lands:**
- A0.5 survives as a **direction only**. Its implementation (feedback pipeline, triage workspace, clustering, corrected-output promotion) is owned by a future standalone Feedback Pipeline project. Batch F was punted in its entirety on 2026-06-03.
- `EvalInput` ships in V2 **without** `source_task_run_id`; that field is added later, additively, by the Feedback Pipeline project.
- `components/60_feedback_and_triage.md` is out of scope (see section 3).
- See section 4 for coordination with the future project.

### A0.6 -- "Doesn't exist today" is design space, not a gap

V2 is allowed to invent. Framing missing V1 pieces as "gaps to patch" would narrow ambition and re-anchor on V1's constraints.

**Where it lands:**
- `EvalInput` as a purpose-built eval dataset entity (A1.1) -- no V1 precedent, designed fresh (`components/10_data_model.md`).
- Per-case structured reference data (`EvalInput.reference: dict[str, JsonValue]`) -- no V1 precedent, designed fresh (`components/50_reference_data.md`).
- The parallel multi-turn-synthetic project designs its field set from scratch, not as a delta against V1 or kintsugi (`components/26_type_multi_turn_synthetic.md`).
- The trust-gate UX for `code_eval` is a first-class design surface, not a half-measure sandbox (`components/27_type_code_eval.md`).

---

## 3. Scope map -- what is in V2.0 and what is not

### In scope: V2.0 launch deliverables

**Data model** (`components/10_data_model.md`): `EvalInput` entity with discriminated `EvalInputData` variants (single-turn, multi-turn-synthetic), universal `reference: dict[str, JsonValue]` and `tags`. `EvalConfig` V2 shape (`config_type = "v2"`, typed discriminated `properties` union). `EvalRun` additive fields (`eval_input_id`, `reference_data`, `skipped_reason`). `Eval` additive field (`eval_input_filter_id`).

**V1/V2 coexistence** (`components/15_v1_v2_coexistence.md`): Legacy enum dispatch, additive fields, parsing routing, EvalRun field coexistence, filter coexistence, validator V2 bypass, V2-only EvalConfig creation paths (K.3), TaskRun-to-EvalInput runtime translation (B2.1).

**8 V2.0 launch EvalConfigTypes** (`components/20_eval_config_types_overview.md`):

| Type | Category | Design file |
|---|---|---|
| `llm_judge` | Subjective / factual / criteria (enhanced: per-criterion verdicts, trace condensation, reference templating, `g_eval` toggle) | `components/21_type_llm_judge.md` |
| `exact_match` | Deterministic | `components/22_type_deterministic_basics.md` |
| `pattern_match` | Deterministic | `components/22_type_deterministic_basics.md` |
| `set_check` | Deterministic | `components/22_type_deterministic_basics.md` |
| `contains` | Deterministic | `components/22_type_deterministic_basics.md` |
| `tool_call_check` | Agent trajectory | `components/22_type_deterministic_basics.md` |
| `step_count_check` | Agent efficiency | `components/22_type_deterministic_basics.md` |
| `code_eval` | User-authored Python (Beta) | `components/27_type_code_eval.md` |

**RAG judge templates** (`components/29_rag_judge_templates.md`): 6 first-party `llm_judge` templates (faithfulness, answer relevance, context relevance, context precision, hallucination, answer correctness) against the `EvalInput.reference` contract.

**Template + extraction layer** (`components/40_template_and_extraction.md`, `components/06_prereq_input_transform.md`): Jinja2 `input_transform` as general Kiln capability (prereq). `extract()` helper. Eval consumer design (EvalTaskInput assembly, `required_var` pre-check, save-time template compilation).

**Runner architecture** (`components/45_runner_architecture.md`): EvalInput flow, adapter dispatch (two-level: outer `config_type`, inner `properties.type`), multi-config orchestration, candidate calibration, missing-reference skip handling, runner constructor branching, TaskRun-to-EvalInput runtime translation (B2.1).

**Reference data** (`components/50_reference_data.md`): Flat dict shape, multi-config consumption, naming guidelines, per-case criteria expressed through reference data.

**Builder and create/view UI** (`components/70_builder_and_onboarding.md`): Shared pluggable create container (config altitude, generic test-run, save, clone-not-edit), type-picker for all V2 types, code-eval editor (CodeMirror 6, sandboxed preview, trust gate, Beta), deterministic-type forms, per-type renderer registry with exhaustive enum binding.

**Extensibility contract** (`components/80_extensibility_contract.md`): Closed catalog + `code_eval` escape hatch for V2.0. Architectural seams preserved for future plugins. How a new built-in type plugs in. Judge template extensibility.

**Observability and audit** (`components/85_observability_and_audit.md`): Score provenance (existing `parent_of` chain sufficient), skip records (`SkippedReason` enum on `EvalRun`), on-read aggregation (`n_used`, `n_excluded`), statistical comparison primitives (deferred).

### Out of scope for V2.0

**Feedback pipeline and triage** (Batch F, punted 2026-06-03): The entire feedback-to-eval loop -- triage workspace, clustering, corrected-output promotion, unified score model, self-improving judges. Owned by a future standalone Feedback Pipeline project. `components/60_feedback_and_triage.md` is not authored. A0.5 stays as a north-star direction only.

**Goal-first builder / onboarding redesign** (Batch G decisions 27/28/30/34, deferred): The "describe your goal in plain text, we pick and size the eval for you" front door, routing logic, hidden-SpecType curation, golden-subset relax. Owned by a future standalone onboarding project. The `competitive_ui_vs_code/` study is its reference brief.

**A0.2 right-sizing mechanism** (deferred with onboarding): The builder automatically right-sizing synthetic dataset count to the input. North-star constraint for the future onboarding project.

**Spec builder reliability** (H.29, out of scope): The ~10-min 300-example single sync request / batch-size / streaming / partial-progress / async fixes. Unrelated to evals V2; owned by a future builder-reliability effort.

**Deferred EvalConfigTypes** (A2.4 post-V2): `composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric`. All can be added later as the discriminated union is open-ended.

**Statistical comparison primitives** (E.21, deferred post-V2): Matched-case intersection, paired-difference analysis, Wilson CI, paired bootstrap CI, Wilcoxon signed-rank. Pure on-read utilities when they land; no schema reservation needed.

**Dataset versioning** (E.33, explicit non-goal): Datasets evolve by design. No snapshot entity, no version pinning. `percent_complete` flags gaps.

**Composite policy / tier** (E.19, E.20, deferred post-V2): Named composite policies and blocking-vs-quality tier are deferred alongside the `composite` type.

**Runtime plugin discovery** (E.36, preserved but not shipped): Setuptools entry-point-based type registration is architecturally possible but not shipped in V2.0.

### Open risks (`components/90_open_risks.md`)

Residual risks and the post-V2 backlog are collected in `components/90_open_risks.md`. Key items: `code_eval` security is trust-gate-only (B.14 reversibility to WASM if attack pressure emerges), deferred `event_ordering` form, sandboxing reversibility path, deferred types, and statistical primitives.

---

## 4. Parallel-project coordination

### Multi-turn-synthetic (parallel project)

Designed by a separate project running in parallel. Evals V2 commits to the **contract surface only** -- `components/26_type_multi_turn_synthetic.md` captures what V2 provides (the `MultiTurnSyntheticEvalInputData` variant in `EvalInputData`, the `SyntheticUserInfo` typed model slot per C.5) and what the parallel project owns (field list, scoring, runner design for multi-turn). The parallel project ships its design into that slot whenever ready; V2's schema accommodates it.

### Future Feedback Pipeline project

A0.5 is the north-star direction. The future project owns all of:
- `source_task_run_id` on `EvalInput` (additive -- F.1/F.2 un-locked 2026-06-03).
- Triage workspace, clustering, corrected-output promotion, unified score model.
- `components/60_feedback_and_triage.md` authoring.
- Everything in V2's `EvalInput` model is additive per A0.1, so the future project can extend it without migrating V2 data.

### Future goal-first onboarding project

Batch G's original scope (goal-first questionnaire, routing logic, right-sizing mechanism, hidden-SpecType curation) is handed to this project. V2 provides the infrastructure it will build on: the type catalog, the pluggable create container (G.1), the per-type renderer registry (G.3). The `competitive_ui_vs_code/` study is a reference brief for this project, not a V2 deliverable.

---

## 5. Design file index

| File | Summary |
|---|---|
| `components/05_prereq_thinking_formatter_fix.md` | SingleTurnR1ThinkingFormatter fix -- opt-in `forward_thinking_instructions` param for reasoning models. |
| `components/06_prereq_input_transform.md` | General Kiln `input_transform` capability -- Jinja2 template + `extract()` on RunConfig. |
| `components/10_data_model.md` | Eval, EvalConfig, EvalInput, EvalRun Pydantic schemas (V2 shape). |
| `components/15_v1_v2_coexistence.md` | Every V1/V2 coexistence pattern. |
| `components/20_eval_config_types_overview.md` | V2.0 catalog (lean surface), per-type adapter contract, plugin-extensibility seam. |
| `components/21_type_llm_judge.md` | Enhanced V2 `llm_judge` -- per-criterion verdicts, `g_eval` toggle, Jinja2 templates, structured output. |
| `components/22_type_deterministic_basics.md` | `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`. |
| `components/26_type_multi_turn_synthetic.md` | Coordination contract with parallel multi-turn-synthetic project. |
| `components/27_type_code_eval.md` | `code_eval` properties, scorer contract, helper library, execution model, trust gate. |
| `components/29_rag_judge_templates.md` | 6 first-party RAG judge templates. |
| `components/40_template_and_extraction.md` | Jinja2 input transform, `extract()` helper, eval consumer design, V1 BC. |
| `components/45_runner_architecture.md` | EvalInput flow, adapter dispatch, orchestration, skip handling, runtime translation. |
| `components/50_reference_data.md` | Flat dict shape, multi-config consumption, naming guidelines, per-case criteria. |
| `components/60_feedback_and_triage.md` | OUT OF SCOPE -- Batch F punted; future Feedback Pipeline project. |
| `components/70_builder_and_onboarding.md` | V2 eval-type create + view UI. Goal-first questionnaire deferred. |
| `components/80_extensibility_contract.md` | Closed catalog + `code_eval` escape hatch; architectural seams for future plugins. |
| `components/85_observability_and_audit.md` | Score provenance, skip records, aggregation rules. |
| `components/90_open_risks.md` | Residual risks, post-V2 backlog, deferred types. |
