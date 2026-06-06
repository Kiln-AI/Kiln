---
status: complete
---

# Functional Spec: Kiln Evals V2

The "what it does" surface for V2 — features, behaviors, contracts. The detail lives in `components/`; this file maps the functional surface to those docs so nothing is hunted for. (Authored as a thin index because the design phase produced behavior-complete component docs rather than a single prose spec.)

## 1. The eval-type catalog (the core feature surface)

V2.0 ships **8 EvalConfigTypes**, each producing scores against an Eval's `output_scores`. Behaviors, property schemas, and per-type contracts:

| Type | What it does | Behavior + contract in |
|---|---|---|
| `llm_judge` | Enhanced LLM-as-judge: per-criterion pass/fail verdicts, trace condensation, reference-data templating, `g_eval` toggle, structured output | `components/21_type_llm_judge.md` |
| `exact_match` | Output (or extracted value) equals a literal or reference value | `components/22_type_deterministic_basics.md` |
| `pattern_match` | Output (or extracted value) matches / doesn't match a regex | `components/22_type_deterministic_basics.md` |
| `contains` | Output contains / doesn't contain a substring (literal or reference) | `components/22_type_deterministic_basics.md` |
| `set_check` | Output set vs expected set (subset / superset / equal) | `components/22_type_deterministic_basics.md` |
| `tool_call_check` | Agent trajectory: expected tools called (all/any/ordered/never), arg matching, allowlist | `components/22_type_deterministic_basics.md` (+ `reference/batch_agent_eval_expansion.md` J.37) |
| `step_count_check` | Agent efficiency: tool-call / response / turn counts vs min/max bounds | `components/22_type_deterministic_basics.md` (+ `reference/batch_agent_eval_expansion.md` J.38) |
| `code_eval` | User-authored Python scorer (`def score(...)`), sandboxed, trust-gated, Beta | `components/27_type_code_eval.md` |

The catalog overview, the per-type **adapter contract**, and the extensibility seam for adding new types: `components/20_eval_config_types_overview.md`.

## 2. Data & reference behavior

- **EvalInput** — the purpose-built eval dataset entity (per-case structured `reference` dict + `tags`, discriminated single-turn / multi-turn-synthetic data): `components/10_data_model.md`.
- **Reference data** — flat-dict shape, multi-config consumption, naming guidelines, per-case criteria expressed through reference data: `components/50_reference_data.md`.
- **RAG behavior** — 6 first-party `llm_judge` templates (faithfulness, answer relevance, context relevance, context precision, hallucination, answer correctness) over a canonical reference-key contract: `components/29_rag_judge_templates.md`.

## 3. Template + extraction behavior

How structured eval data is projected into judge prompts and pulled into deterministic checks — Jinja2 `input_transform`, the `extract()` helper, `required_var` skip semantics, save-time template compilation: `components/40_template_and_extraction.md` (built on the already-landed `components/06` prereq infra).

## 4. Runtime behavior

How an eval run flows: EvalInput vs TaskRun sources, two-level adapter dispatch (`config_type` → `properties.type`), multi-config orchestration, candidate calibration, missing-reference **skip-with-reason** behavior: `components/45_runner_architecture.md`.

## 5. Coexistence behavior (V1 ↔ V2)

Every observable V1/V2 interaction — legacy enum dispatch, additive-field loading, parsing routing, validator V2 bypass, filter coexistence, V2-only EvalConfig creation paths, TaskRun→EvalInput runtime translation: `components/15_v1_v2_coexistence.md`. Governing principle: **V2 reads V1; V2 never migrates V1** (`components/00_overview.md §2`, A0.1).

## 6. UI behavior (create + view)

Create any V2 type and view results in existing surfaces: pluggable create container (generic test-run + save + clone-not-edit), code-eval editor (CodeMirror, sandboxed preview, trust gate, Beta), deterministic-type forms, per-type renderer registry with exhaustive enum binding: `components/70_builder_and_onboarding.md`. **Per-type result rendering is intentionally not pinned** — build it from the data each type produces using UI-design judgment (see `components/70 §4.1`).

## 7. Non-goals (V2.0)

Feedback pipeline / triage, goal-first onboarding redesign, spec-builder reliability, deferred eval types, statistical comparison primitives, dataset versioning. Full list with rationale: `components/00_overview.md §3 (Out of scope)`.
