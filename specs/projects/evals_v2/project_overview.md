---
status: complete
---

# Kiln Evals V2 — Implementation

This project implements **Kiln Evals V2**: a typed, extensible eval framework that replaces V1's single-type LLM-as-judge model with **many EvalConfigTypes producing scores per Eval**, backed by **purpose-built EvalInput datasets with per-case structured reference data**. It is designed for "many small evals" — lowering the floor for creation so a small focused eval beats both "no eval at all" and an oversized eval that overfits.

**V2 is additive over V1.** V1 records on disk are never rewritten. V1 EvalConfigs (`g_eval`, `llm_as_judge`) continue to load and run unchanged under V2 via legacy adapter dispatch. New eval types, new dataset entities, and new scoring paths live alongside V1 — they never replace it on disk.

## How this spec is organized (read this first)

This spec was produced from a long, deliberate design phase. The detail lives in **`components/`** — one focused design doc per topic. The top-level files are thin maps into it:

- **`project_overview.md`** (this file) — what we're building and how to navigate.
- **`functional_spec.md`** — the feature/behavior surface (the eval-type catalog + data model + contracts), as pointers into `components/`.
- **`architecture.md`** — the technical index: data model, runner dispatch, and the component map. **Start here for the build.**
- **`implementation_plan.md`** — the phased build order (the checklist `/spec implement` walks).
- **`components/NN_*.md`** — the real design detail. These are the meat; they already carry implementation-grade detail (schemas, signatures, test plans).
- **`reference/`** — supporting context (see note below). You usually don't need it.

### On the `Ax.x` tags you'll see throughout

A full **alignment phase** preceded this design and is archived in **`reference/ALIGNMENT.md`**. Throughout the `components/` docs you'll see tags like `A2.1`, `B.13`, `E.18`, `C.runner.2` — these reference locked alignment decisions. **You do not need to load `reference/ALIGNMENT.md`** unless you genuinely want the history of *how* a decision was made. The design docs in `components/` capture the *output* of alignment — they are less verbose, more complete, lower-churn, and are the best reference for building. Treat the tags as provenance breadcrumbs, not required reading.

`reference/` also holds two docs that two components cite by name — `backwards_compat_plan_grounded.md` (code-grounded Phase-0 plan with `eval.py` line numbers) and `batch_agent_eval_expansion.md` (the `tool_call_check`/`step_count_check` expansion). Consult them only if a component points you there.

## Scope at a glance

**In V2.0:** the data model (`EvalInput`, V2 `EvalConfig`, additive `EvalRun`/`Eval` fields), V1/V2 coexistence, 8 eval types (`llm_judge`, `exact_match`, `pattern_match`, `set_check`, `contains`, `tool_call_check`, `step_count_check`, `code_eval`), a Jinja2 template+extraction layer, the V2 runner, 6 RAG judge templates, the extensibility seams, and minimal-but-complete create/view UI for the new types.

**Explicitly out of scope** (owned by future, separate projects): the feedback-to-eval pipeline / triage, the goal-first onboarding redesign, spec-builder reliability, and the deferred eval types (`composite`, `threshold`, `json_schema`, `event_ordering`, `embedding_similarity`, `dag_metric`). See `components/00_overview.md §3` for the full scope map and `components/90_open_risks.md` for residual risks.

## Coordination & prerequisites

- **Multi-turn-synthetic** is a parallel project. V2 commits only to the contract surface (`components/26`* is excluded from this folder; the `MultiTurnSyntheticEvalInputData` slot in the data model accommodates it). Don't build multi-turn scoring here.
- **Prereq already landed in `main`:** the general Kiln `input_transform` (Jinja2) capability — `libs/core/kiln_ai/utils/jinja_engine.py` + `InputTransform` on `KilnAgentRunConfigProperties`. `components/06` is its design, kept **for reference only — do not rebuild.**
- **Prereqs still to build** (Phase 1): the `SingleTurnR1ThinkingFormatter` fix (`components/05`) and the V1 `validate_template_properties` bug fix (`components/15 §4.3`). See `implementation_plan.md`.

*The full `components/00_overview.md` is the canonical front door — it expands every point above with links.*
