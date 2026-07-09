# Cluster H — View surfaces (components/70 S4) — Skeptic Confirmation

## 70b-R05

- **Finding ID:** 70b-view-surfaces-R05
- **Skeptic verdict:** UPHELD
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** The spec (S4 "Defensive enum binding") requires: "A backend type added without a UI module **fails loudly** rather than rendering blank." The compile-time guard (`assertNever` in `getV2EvalTypeMetadata` default branch, `registry.ts:155`) is solid and will throw at runtime — but it is never reachable for an unknown API string. The runtime entry point is `getV2TypeFromEvalConfig` (`registry.ts:163-174`), which checks `ALL_V2_EVAL_TYPES.includes(t)` and returns `null` for any unrecognized string. That null propagates to `run_result/+page.svelte:211-216` where `v2_result_component` becomes null. At line 288, the condition `is_v2_config && v2_result_component` is false, so the fallback renders generic per-score columns (lines 291-299) — no error, no warning, no console log. The V2 config with an unknown type renders silently as a raw-scores table. This is a real gap vs the spec's "fails loudly" requirement, but severity is minor because the scenario (backend adds a type the frontend doesn't know about) is rare in a monorepo and the fallback is functionally adequate (scores still display).
- **Evidence:**
  - Spec: S4 "Defensive enum binding" — "A backend type added without a UI module fails loudly rather than rendering blank."
  - `registry.ts:163-174` — `getV2TypeFromEvalConfig` returns `null` for unrecognized type strings (never calls `getV2EvalTypeMetadata` → `assertNever` is unreachable at runtime for this path).
  - `run_result/+page.svelte:288-299` — silent fallback to per-score columns when `v2_result_component` is null.
  - `assertNever` (`exhaustive.ts:10`) DOES throw at runtime but is only compile-time reachable in the `getV2EvalTypeMetadata` switch default.

---

## 70b-R13

- **Finding ID:** 70b-view-surfaces-R13
- **Skeptic verdict:** UPHELD
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** The spec S4.1 says the Thinking column should be "conditional on intermediate_outputs (only llm_judge/code_eval)." The code (`run_result/+page.svelte:285-286`) hides the Thinking column for ALL V2 configs with `{#if !is_v2_config}`. This means V2 llm_judge and code_eval configs — which DO produce `intermediate_outputs` (reasoning / chain_of_thought) — lose the Thinking column entirely. Furthermore, the V2 result renderers (`llm_judge_result.svelte`, `code_eval_result.svelte`) do not receive `intermediate_outputs` as a prop (line 354-362 only passes `scores`, `skipped_reason`, `skipped_detail`, `eval_config`) and contain zero references to reasoning/chain_of_thought. So intermediate_outputs are invisible for V2 llm_judge/code_eval results. This is a real UX loss. However, the spec's S4.1 table is marked "illustrative guidance — agent builds it" and "not a binding layout spec," so the content details (like showing reasoning for llm_judge) are agent judgment calls. The firm requirement is just scores + skip state, which ARE shown. Severity stays minor: the data is lost from the view but accessible via API/library.
- **Evidence:**
  - Spec: S4.1 — "Thinking column conditional on intermediate_outputs (only llm_judge/code_eval)" — but the table is marked "illustrative guidance."
  - `run_result/+page.svelte:285-286` — `{#if !is_v2_config}` hides Thinking column for all V2 configs.
  - `run_result/+page.svelte:354-362` — V2 result renderer receives only `scores`, `skipped_reason`, `skipped_detail`, `eval_config`. No `intermediate_outputs`.
  - `llm_judge_result.svelte` — zero references to `intermediate_outputs`, `reasoning`, or `chain_of_thought`.
  - `code_eval_result.svelte` — same, zero references.

---

## 70b-R14

- **Finding ID:** 70b-view-surfaces-R14
- **Skeptic verdict:** UPHELD
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor
- **Reasoning:** The spec S4.3 states: "the saved-config view is **read-only and in scope for V2.0** (a user must be able to see what a candidate config does before cloning it). It reuses the same per-type module's createForm in a disabled/read-only mode, or a lightweight configDetail renderer." No dedicated config-detail page exists at the `[eval_config_id]` route level — the only page under `[eval_config_id]` is `[run_config_id]/run_result/+page.svelte`. The `EvalConfigInstruction` component (`eval_config_instruction.svelte`) is shown in the eval_configs list table for all configs (line 801) but only understands `eval_steps` and `task_description` — properties unique to llm_judge. For V2 non-llm_judge types (exact_match, code_eval, etc.), it shows "No description provided." with no eval steps. The per-type result renderers DO show some config properties inline (e.g., code_eval shows timeout, llm_judge shows model name and g_eval badge), but this is within the result context only — a user cannot inspect a config's full properties before running it or cloning it. This is a real gap. Severity is minor because partial config info IS visible inline in result views, and the clone flow prefills from the existing config (providing implicit visibility).
- **Evidence:**
  - Spec: S4.3 — "read-only and in scope for V2.0 (a user must be able to see what a candidate config does before cloning it)."
  - No `[eval_config_id]/+page.svelte` exists — only `[eval_config_id]/[run_config_id]/run_result/+page.svelte`.
  - `eval_config_instruction.svelte:6-18` — only extracts `eval_steps` and `task_description` (llm_judge properties).
  - `eval_configs/+page.svelte:801` — shows `EvalConfigInstruction` for all configs including V2, but it's llm_judge-only content.
  - V2 result renderers show minimal config info inline (e.g., `llm_judge_result.svelte:21` model name, `code_eval_result.svelte:23` timeout) but not full config detail.

---

## 70b-R17

- **Finding ID:** 70b-view-surfaces-R17
- **Skeptic verdict:** UPHELD_DOWNGRADE
- **Corrected verdict:** PARTIAL
- **Corrected severity:** minor (not MISSING — scores ARE shown, just not as type-aware badges)
- **Reasoning:** The spec S4.1 firm requirement says: "every type's result renderer shows **the score(s)** against output_scores (the existing score badge component — pass/fail / pass_fail_critical / five_star)." The parenthetical references "the existing score badge component" — but **no such component exists anywhere in the codebase**. The V1 code paths also render scores as raw floats via `toFixed(2)` (`run_result/+page.svelte:369`, `run_config_comparison_table.svelte:219`). `OutputTypeTablePreview` shows score TYPE labels ("pass/fail", "1 to 5") in table headers but does not render score VALUES as badges. The V2 `eval_result_scores.svelte:26-30` renders `key: value.toFixed(2)` — identical to the V1 pattern. Since the "existing score badge component" does not exist and V1 also uses raw floats, this is a pre-existing gap that the spec incorrectly assumes was already built. V2 matches V1 behavior. The actual firm requirement (show scores + skip state) IS met: scores render correctly and skip state renders as a badge with reason text. Downgrading from MISSING to PARTIAL because scores ARE shown (just not as type-aware badges), and the spec references a non-existent component — this is a spec bug, not an implementation omission.
- **Evidence:**
  - Spec: S4.1 — "the existing score badge component — pass/fail / pass_fail_critical / five_star" — component does not exist.
  - `eval_result_scores.svelte:24-32` — renders `key: value.toFixed(2)` (raw floats).
  - `run_result/+page.svelte:369` — V1 path also uses `score_value.toFixed(2)`.
  - `run_config_comparison_table.svelte:219` — comparison table also uses `score.toFixed(2)`.
  - `output_type_table_preview.svelte` — only shows score TYPE label in headers, not score VALUES.
  - No component matching "score badge" exists in the codebase (searched `*badge*score*`, `*score*badge*`, `ScoreBadge`).
