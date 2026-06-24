---
status: draft
ship_gating: mixed (most ship-blocker; D27/D29 post-ship)
owner: TBD
---

# Project: Evals V2 cleanup

## Why this exists

Holding project for the **important-but-small** fixes from the Evals V2 spec-fidelity review (2026-06-23) that don't warrant their own project. Two kinds: backend helper/validator correctness, and a few results/view-surface UI gaps. **None of these touch the create container**, so there's no branch conflict with the create-flow projects (1 & 2).

- Decision log: [`../evals_v2/spec_fidelity_review/DECISIONS.md`](../evals_v2/spec_fidelity_review/DECISIONS.md)
- Review summary: [`../evals_v2/spec_fidelity_review/SPEC_FIDELITY_REVIEW.md`](../evals_v2/spec_fidelity_review/SPEC_FIDELITY_REVIEW.md)

## Source specs

- [`../evals_v2/components/27_type_code_eval.md`](../evals_v2/components/27_type_code_eval.md) — §2 scorer contract + `KilnEvalHelpers` library (D14/D15/D16).
- [`../evals_v2/components/22_type_deterministic_basics.md`](../evals_v2/components/22_type_deterministic_basics.md) + [`../evals_v2/components/40_template_and_extraction.md`](../evals_v2/components/40_template_and_extraction.md) — save-time validation (D27–D30).
- [`../evals_v2/components/70_builder_and_onboarding.md`](../evals_v2/components/70_builder_and_onboarding.md) §4 — results/view surfaces (D31). _(D32 read-only config-detail view moved to its own project — `specs/projects/evals_v2_readonly_views/` — since it reuses Project 1's per-type forms.)_
- [`../evals_v2/components/85_observability_and_audit.md`](../evals_v2/components/85_observability_and_audit.md) §3.4 — `n_excluded` surfacing (D35).

Evidence: [`confirm_K.md`](../evals_v2/spec_fidelity_review/confirm_K.md) (code-eval), [`confirm_J.md`](../evals_v2/spec_fidelity_review/confirm_J.md) (validators), [`confirm_H.md`](../evals_v2/spec_fidelity_review/confirm_H.md) (view surfaces), [`confirm_L.md`](../evals_v2/spec_fidelity_review/confirm_L.md) (observability).

## Scope — decisions owned

### Ship-blockers

| Decision | Work | Notes |
|---|---|---|
| **D14 / D15** | Normalize `KilnEvalHelpers.get_tool_calls()` / `get_assistant_messages()` to **real OpenAI trace format** (`role=="assistant"` + nested `tool_calls`). `eval_helpers.py` — reuse the correct extraction in `v2_eval_tool_call_check.py:41-66`. | **Gate: manual review on a real trace with tool calls** before approval — agent-written fixtures are insufficient (the bug shipped because tests used a fake trace shape). The shipped code-eval example gallery depends on these helpers. |
| **D16** | Validate returned scores' range in the test pane. Extract `EvalRun.validate_scores` range logic (`eval.py:530-587`) into a shared `validate_scores_against_output_scores(scores, output_scores)`; call from `EvalRun` + `test_v2_eval` (`eval_api.py:996-1003`); add a `score_validation_errors` field to the response. | ~10 net LOC. Zero per-type maintenance — keys off rating type with an exhaustive match. |
| **D28** | Compile `ArgMatch` regex values at save time (`eval.py:154-156`). | Insidious: invalid regex silently never matches at runtime. |
| **D30** | AST-based useless-template check (currently a surface `{{`-scan) so a `reference_data`-only template can't pass save (`eval.py:706-712`). | Insidious: such a template never reads model output → meaningless eval. |
| **D31** | Surface V2 `llm_judge`/`code_eval` **reasoning** in results (Thinking is currently hidden for all V2 configs; `intermediate_outputs` not passed to V2 renderers). `run_result/+page.svelte`, `llm_judge_result.svelte`. | **Non-prescriptive** — find the right way to show it; don't over-engineer. |
| **D35** | Warning icon (warning color) + tooltip on aggregate-results surfaces (esp. the **compare view**) when `n_excluded > 0`, showing how many cases were excluded/skipped. Data already in API (`ScoreSummary.n_excluded`). | |

### Post-ship

| Decision | Work |
|---|---|
| **D27** | Validate `expected_tools` non-empty at save (`eval.py:164`). Visible skip at runtime, so lower urgency. |
| **D29** | Validate `reference_key` `min_length=1` (`eval.py:96,129,144`). Empty key always skips at runtime (visible). |

## Notes

- D14/D15/D16/D27/D28/D29/D30 are **backend-only** (datamodel/helpers/endpoint) — safe to do anytime, no UI-branch conflict.
- D31/D35 are **results/view** surfaces (run-result page, eval-detail, compare view) — distinct from the create container owned by Project 1. (D32 also a view surface, but it reuses the per-type forms → moved to its own project, sequenced after Project 1.)
- Consider splitting execution into a pre-ship batch (D14/D15/D16/D28/D30/D31/D32/D35) and a post-ship batch (D27/D29).

## Out of scope

Everything classified Override-spec / no-action / Defer in `DECISIONS.md` (D06, D17–D20, D33, D34, D36–D40) — recorded there with rationale; no work needed.
