# Spec-Fidelity Skeptic Review: CLUSTER L — Observability aggregation + UI

## 85-R16: percent_complete formula divergence

- **Skeptic verdict:** REFUTED_IMPLEMENTED
- **Corrected verdict:** MET
- **Corrected severity:** n/a
- **Reasoning:** The two formulas are mathematically equivalent for all possible states. The spec says `(n_used + n_excluded) / dataset_size`. The code computes `(dataset_size - incomplete) / dataset_size` where `incomplete = partial_incomplete + remaining_not_run`. Since `dataset_size = n_used + n_excluded + partial_incomplete + remaining`, subtracting the latter two yields `n_used + n_excluded`. Worked example: dataset_size=10, 5 fully scored, 2 skipped, 1 partial, 2 not run. Spec: (5+2)/10=0.7. Code: (10 - (1+2))/10 = 7/10 = 0.7. The formulas never diverge because they are algebraic rearrangements of the same partition. The code additionally handles the "partially incomplete" case (a run exists but is missing some score_keys) identically to how the spec would -- such runs are NOT counted in n_used, so they are NOT counted as complete in either formula.
- **Evidence:** `app/desktop/studio_server/eval_api.py:616-624` -- `remaining_expected_dataset_ids` tracks items with no run; `partial_incomplete_counts` tracks items with incomplete scores; `n_processed = dataset_size - (partial + remaining)` = `n_used + n_excluded` by partition identity. Spec section 3.2: "n_used = Count of EvalRuns with all expected score_keys populated AND skipped_reason is None".

---

## 85-R17 / functional-arch-crosscut-R03: n_excluded aggregate UI warning absent

- **Skeptic verdict:** UPHELD
- **Corrected verdict:** MISSING
- **Corrected severity:** minor
- **Reasoning:** The spec (components/85 section 3.4) explicitly mandates: "Warning + tooltip when n_excluded > 0: '3 of 50 cases skipped -- required reference data missing' (human-readable copy per SkippedReason value)." This is a clear UI requirement, not merely data availability. The `n_excluded` field flows from the backend API (`ScoreSummary.n_excluded`) and appears in the generated TypeScript schema (`api_schema.d.ts:5503`), but NO frontend component reads or renders it. The comparison table (`run_config_comparison_table.svelte`) shows an "incomplete" warning for percent_complete < 1.0, but this is about missing runs, not about skipped/excluded cases. Individual per-run skip rendering exists in `eval_result_scores.svelte` (per-item badge), but the aggregate summary warning the spec describes is absent. No evidence in RUN_NOTES.md of an intentional decision to defer or remove this requirement.
- **Evidence:**
  - Spec: `components/85_observability_and_audit.md` section 3.4 -- "Warning + tooltip when n_excluded > 0"
  - `grep -rn "n_excluded" app/web_ui/src/` returns only `api_schema.d.ts` type definitions; zero consumption in .svelte or .ts files
  - `run_config_comparison_table.svelte:119-131` -- shows "incomplete" warning based on `percent_complete`, never references `n_excluded`
  - `eval_result_scores.svelte:3-21` -- per-item skip badge (detail view only, not aggregate)
  - `RUN_NOTES.md` -- no mention of n_excluded UI or intentional deferral
