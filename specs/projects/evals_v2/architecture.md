---
status: complete
---

# Architecture: Kiln Evals V2

This is the technical index. The real architecture lives in the **`components/`** design docs — each is implementation-grade (Pydantic schemas, function signatures, test plans). This file gives the shared technical frame and maps every component to the build.

**Two-phase by design:** this is a large project, so it uses architecture-doc-plus-component-designs. The component docs ARE the architecture; this index ties them together. Don't re-derive design here — follow the links.

## 1. Technical frame (the load-bearing decisions)

- **Additive over V1 (A0.1).** No V1 schema rewrites, no `model_validator`-based migrations. V2 adds enum values, optional fields, and parsing branches. V1 records load and run unchanged. The entire coexistence layer is `components/15`.
- **Typed discriminated EvalConfig.** `EvalConfig.config_type` gains `"v2"`; `properties` becomes a typed discriminated union keyed on `properties.type` (the `V2EvalType` enum). Legacy `g_eval`/`llm_as_judge` stay in the enum forever. Schema: `components/10`.
- **Two-level adapter dispatch.** Outer dispatch on `config_type` (legacy vs v2); inner dispatch on `properties.type` (which V2 eval type). `eval_adapter_from_type(EvalConfig)` (note: takes the config, not just the type). Runner detail: `components/45`; contract per type: `components/20`.
- **EvalInput as a first-class dataset entity (A0.6).** A new `KilnParentedModel` under `Task`, with per-case structured `reference: dict[str, JsonValue]` and `tags`, and a discriminated `EvalInputData` (single-turn / multi-turn-synthetic). No V1 precedent — designed fresh. Schema: `components/10`; reference shape: `components/50`.
- **EvalRun additive fields.** `eval_input_id`, `reference_data`, `skipped_reason` — all optional, V1 EvalRuns load them as `None`. Skip-with-reason relaxes the score/output validators when set. Detail: `components/10 §5`, `components/45`.
- **Template + extraction on top of the landed `input_transform` prereq.** Jinja2 `render` (StrictUndefined) for judge prompts; `extract()` (Undefined) for deterministic value pulls and `required_var` pre-checks. Engine already in `main` (`components/06`); eval consumer design in `components/40`.
- **Config-first; `code_eval` is the one escape hatch (A0.3).** `code_eval` runs user Python in a `multiprocessing` (spawn) worker with a UX trust gate — no language sandbox (B.13). Detail: `components/27`.
- **Local-first (A0.4).** Stdlib only; no new runtime deps; PyInstaller-bundle-clean.

## 2. Data model + flow (one paragraph)

A `Task` owns `EvalInput`s (new) alongside its existing `TaskRun`s. An `Eval` declares `output_scores` and points at a dataset filter (`eval_set_filter_id` for TaskRuns, or the new `eval_input_filter_id` for EvalInputs). An `Eval` has one-or-more candidate `EvalConfig`s (calibration candidates; 1 produces all scores — C.9). The runner takes each item (TaskRun **or** EvalInput), assembles the synthetic eval input, dispatches by `config_type` → `properties.type` to the right adapter, runs the scorer, and persists an `EvalRun` (with `reference_data`, score records, or `skipped_reason`). Aggregation is on-read. Full flow: `components/45`.

## 3. Component map

Build from these. Phase column = where each is consumed in `implementation_plan.md`.

| Component | One-liner | Phase |
|---|---|---|
| `components/00_overview.md` | V2 north star, principles (A0.x), full in/out scope map, parallel-project coordination | all (orientation) |
| `components/05_prereq_thinking_formatter_fix.md` | `SingleTurnR1ThinkingFormatter` fix — opt-in `forward_thinking_instructions` for reasoning models | 1 (prereq) |
| `components/06_prereq_input_transform.md` | General Kiln `input_transform` (Jinja2 + `extract()`). **✅ Already in `main` — reference only, do not rebuild.** | — (landed) |
| `components/10_data_model.md` | Eval, EvalConfig, EvalInput, EvalRun Pydantic schemas (V2 shape) | 1 |
| `components/15_v1_v2_coexistence.md` | Every V1/V2 coexistence pattern (incl. V1 `validate_template_properties` fix §4.3) | 1 |
| `components/40_template_and_extraction.md` | Jinja2 input transform, `extract()` helper, eval consumer (EvalTaskInput, `required_var`), V1 BC | 2 |
| `components/45_runner_architecture.md` | EvalInput flow, two-level dispatch, orchestration, skip handling, runtime translation | 2 |
| `components/20_eval_config_types_overview.md` | V2.0 catalog, per-type adapter contract, plugin-extensibility seam | 2 |
| `components/22_type_deterministic_basics.md` | `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check` | 3 |
| `components/21_type_llm_judge.md` | Enhanced `llm_judge` — per-criterion verdicts, `g_eval` toggle, Jinja2 templates, structured output | 4 |
| `components/29_rag_judge_templates.md` | 6 first-party RAG judge templates (content over the reference-key contract) -- **deferred from V2.0** (see `/specs/projects/rag_templates/`) | 4 |
| `components/27_type_code_eval.md` | `code_eval` properties, scorer contract, helper library, `multiprocessing` execution, trust gate | 5 |
| `components/70_builder_and_onboarding.md` | V2 create + view UI (create container, code-eval editor, renderer registry) | 6 |
| `components/50_reference_data.md` | Flat-dict reference shape, multi-config consumption, naming guidelines | 1–4 (consumed) |
| `components/80_extensibility_contract.md` | Closed catalog + `code_eval` escape hatch; seams for future plugins | reference |
| `components/85_observability_and_audit.md` | Score provenance, skip records, aggregation rules | 1–2 (consumed) |
| `components/90_open_risks.md` | Residual risks, post-V2 backlog, deferred types | reference |

(`components/26_type_multi_turn_synthetic.md` is intentionally **not** included — owned by the parallel multi-turn project. The data model leaves a slot for it.)

## 4. References (provenance, not required reading)

`reference/ALIGNMENT.md` is the decision ledger behind the `Ax.x` tags — load only for decision history (see `project_overview.md`). `reference/backwards_compat_plan_grounded.md` and `reference/batch_agent_eval_expansion.md` are cited by name from `components/15` and `components/22` respectively; consult when pointed there.

## 5. Testing strategy

Per-component test plans live in each `components/` doc (the design phase specified them by name). General bar: tests catch real breakage, target high coverage, reuse helpers, and verify both the V2 path and **V1-unchanged** behavior (coexistence tests are first-class — V1 records must keep loading and running). Each phase's coding agent writes its detailed test list into `phase_plans/phase_N.md` before building, then runs the project's automated checks (lint/format/type-check/build/tests) to green.
