---
status: draft
ship_gating: ship-blocker (revisit — large, separately-owned; post-ship fast-follow defensible)
owner: TBD (separate dev — large effort)
---

# Project: Copilot & builder create flows (V2)

## Why this exists

The Evals V2 spec-fidelity review (2026-06-23) found that the **automated/guided** eval-creation flows still emit **V1** EvalConfigs. The spec's Batch-K decisions (`components/15 §8`) require every creation path to emit V2 going forward, and the review's adversarial pass traced the root cause: the spec's "sub-task 8" (K.1/K.2/K.3 creation-path migration) **was never assigned to any implementation phase**, and the `v1_to_v2_prompt_template()` helper was never built. This project migrates the Copilot and questionnaire-builder flows to V2.

This is the **large, separately-owned** half of the create-path work (the hand-driven UI is Project 1, `eval_create_ui_v2`).

- Decision log: [`../evals_v2/spec_fidelity_review/DECISIONS.md`](../evals_v2/spec_fidelity_review/DECISIONS.md)
- Root-cause investigation (read this first): [`confirm_A.md`](../evals_v2/spec_fidelity_review/confirm_A.md)
- Evidence: [`unit_15-coexistence.md`](../evals_v2/spec_fidelity_review/unit_15-coexistence.md), [`unit_21-llm-judge.md`](../evals_v2/spec_fidelity_review/unit_21-llm-judge.md), [`unit_functional-arch-crosscut.md`](../evals_v2/spec_fidelity_review/unit_functional-arch-crosscut.md)

## Source specs (authoritative design)

- [`../evals_v2/components/15_v1_v2_coexistence.md`](../evals_v2/components/15_v1_v2_coexistence.md) — **§8 (K.1–K.5)** the creation-path migration decisions; **§8.2** dataset shape per flow; §11 implementation sub-tasks (note sub-task 8 was never phased).
- [`../evals_v2/components/21_type_llm_judge.md`](../evals_v2/components/21_type_llm_judge.md) — §6 (`llm_judge` create internals; default `system_prompt`).
- [`../evals_v2/components/70_builder_and_onboarding.md`](../evals_v2/components/70_builder_and_onboarding.md) — §5 (mechanical K-decision plumbing this project realizes).

## Scope — decisions owned (Ship-blocker; gating to confirm)

| Decision | Work | Files |
|---|---|---|
| **D04** | Build `v1_to_v2_prompt_template()` — wraps a V1-style prompt/criteria into a V2 `LlmJudgeProperties.prompt_template` (K.2). Shared by Copilot + builder. `required_var=[]` for wrapped templates. | `libs/core/.../eval` |
| **D03** | Copilot path: local V1→V2 translation; emit a V2 `llm_judge` EvalConfig (no `api.kiln.tech` change per K.2); stop writing V1 `eval_set_filter_id` where the V2 EvalInput path applies. | `app/desktop/studio_server/copilot_api.py` |
| **D05** | `spec_builder` / questionnaire builder: all 17 SpecTypes → `llm_judge` (K.4); emit V2 Evals + EvalConfigs; add `CreateEvaluatorRequest.eval_input_filter_id` so V2 EvalInput-backed Evals can be created. | `spec_api.py`, `eval_api.py` (`CreateEvaluatorRequest`) |

## Proposed phases

1. **Shared infra.** `v1_to_v2_prompt_template()` (D04) + `CreateEvaluatorRequest.eval_input_filter_id` (D05 API part). Unit-test the wrapper against representative V1 prompts.
2. **Copilot → V2** (D03). Local translation; verify Copilot-created configs load+run as V2 and produce per-criterion verdicts.
3. **Builder → V2** (D05 builder part). SpecType→`llm_judge` mapping (K.4/K.5); emit V2 Evals+EvalConfigs; per-flow dataset shape per `components/15 §8.2`.

## Acceptance / definition of done

- A repo-wide check proves **no creation path writes a V1-shaped EvalConfig** (`config_type in {g_eval, llm_as_judge}`) going forward (the review's `deferred-and-cut` negative check, inverted into a guard).
- Existing V1 records still load+run unchanged (D.5 absolute back-compat — see `components/15 §1`).

## Dependencies & coordination

- Shares the target `LlmJudgeProperties` shape with **Project 1** (`eval_create_ui_v2`) — align on it; different construction paths (translation vs form-built), mostly different files, can run in parallel.
- Depends on the V2 `LlmJudgeProperties` data model + the V2 `llm_judge` adapter (both already exist — `components/10`, `components/21`).

## Open questions / gating

- **Ship gating:** ratified Ship-blocker (Batch 1), but flagged for revisit given size + separate ownership + that Copilot is Kiln Pro. Decide whether this is launch-gating or a post-ship fast-follow before committing the dev.
- Confirm Copilot's V1→V2 translation can be fully local (K.2) with no remote changes.
