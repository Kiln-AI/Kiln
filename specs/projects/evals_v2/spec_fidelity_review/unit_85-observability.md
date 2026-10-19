# Spec-Fidelity Review: Unit 85-observability (Observability & Audit)

Requirements: 20 total — MET 14, PARTIAL 1, MISSING 1, CONTRADICTED 0, DEFERRED_OK 4, CANNOT_VERIFY 0

---

## Requirements Table

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 85-R01 | Data Model | MET | — | EvalRun has `skipped_reason: str \| None = None` field | §2.1 "skipped_reason: str \| None = None" | `libs/core/kiln_ai/datamodel/eval.py:468-471` — field typed as `str \| None` with default None | — |
| 85-R02 | Data Model | MET | — | EvalRun has `skipped_detail: str \| None = None` field | §2.3 "skipped_detail: str \| None = None" | `libs/core/kiln_ai/datamodel/eval.py:472-475` — field typed as `str \| None` with default None | — |
| 85-R03 | Enum | MET | — | SkippedReason enum contains `missing_reference_key` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:257` | — |
| 85-R04 | Enum | MET | — | SkippedReason enum contains `incompatible_input_shape` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:260` | — |
| 85-R05 | Enum | MET | — | SkippedReason enum contains `extraction_failed` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:258` | — |
| 85-R06 | Enum | MET | — | SkippedReason enum contains `missing_trace` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:259` | — |
| 85-R07 | Enum | MET | — | SkippedReason enum contains `code_eval_not_trusted` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:261` | — |
| 85-R08 | Enum | MET | — | SkippedReason enum contains `type_not_available` | §2.2 enum listing | `libs/core/kiln_ai/datamodel/eval.py:262` | — |
| 85-R09 | Validation | MET | — | validate_scores relaxes when skipped_reason is set (empty scores allowed) | §2.5 "When skipped_reason is not None, allow empty/None scores" | `libs/core/kiln_ai/datamodel/eval.py:531-533` — early return when `self.skipped_reason is not None` | — |
| 85-R10 | Validation | MET | — | EvalRun.output allows None when skipped | §2.5 "When skipped_reason is not None, allow None" | `libs/core/kiln_ai/datamodel/eval.py:435-438` — field is `str \| None`, validator at line 500 only rejects None output when `skipped_reason is None` | — |
| 85-R11 | Runner | MET | — | Runner emits skip for type_not_available (NotImplementedError -> SkippedReason.type_not_available) | §2.6 point 1 + §2.2 | `libs/core/kiln_ai/adapters/eval/eval_runner.py:393-412` — catches NotImplementedError, persists skipped EvalRun with `SkippedReason.type_not_available.value` | — |
| 85-R12 | Runner | MET | — | Runner emits skip for incompatible_input_shape (multi-turn detection) | §2.6 point 1 + §2.2 | `libs/core/kiln_ai/adapters/eval/eval_runner.py:414-439` — detects multi-turn, persists skipped EvalRun with `SkippedReason.incompatible_input_shape.value` | — |
| 85-R13 | Runner | MET | — | Transient failures NOT persisted as skipped runs | §2.4 "Transient (NOT persisted)" | `libs/core/kiln_ai/adapters/eval/eval_runner.py:288-305` — retryable errors raise RetryableError (retried by AsyncJobRunner), non-retryable errors propagate; no EvalRun is saved for either path | — |
| 85-R14 | API / Aggregation | MET | — | ScoreSummary has `n_used: int` field | §3.3 "n_used: int" | `app/desktop/studio_server/eval_api.py:262-263` | — |
| 85-R15 | API / Aggregation | MET | — | ScoreSummary has `n_excluded: int` field | §3.3 "n_excluded: int" | `app/desktop/studio_server/eval_api.py:265-266` | — |
| 85-R16 | Aggregation | PARTIAL | minor | Skipped runs count toward percent_complete; when n_used == 0, mean is None | §3.2 "percent_complete: (n_used + n_excluded) / dataset_size" and "when n_used == 0, the mean is None" | `eval_api.py:581-584` (skip removes from remaining, doesn't become "incomplete"); line 611 `mean_score=... if count > 0 else None`. However, percent_complete formula does not precisely match spec: it's `(dataset_size - incomplete) / dataset_size` where incomplete = partial + remaining. Skipped runs are implicitly counted as complete (correct), but the formula doesn't literally compute `(n_used + n_excluded) / dataset_size`. | The formula is semantically equivalent for all practical cases but differs in structure from spec. When all inputs are either scored or skipped, both formulas produce 1.0. The partial_incomplete handling adds nuance the spec formula omits. This is a minor structural deviation but functionally correct. |
| 85-R17 | UI | MISSING | minor | Warning + tooltip when n_excluded > 0 showing "X of Y cases skipped" with human-readable copy | §3.4 "Warning + tooltip when n_excluded > 0: '3 of 50 cases skipped -- required reference data missing'" | No frontend component references `n_excluded` from ScoreSummary in any aggregate/summary view. Individual skipped runs show their reason in detail views (`eval_result_scores.svelte:11-21`), but no aggregate warning exists in dashboard/summary panes. | The per-run skip display exists, but the aggregate `n_excluded` warning/tooltip specified in §3.4 is not implemented in summary views. |
| 85-R18 | Provenance | MET | — | Existing parent_of chain (EvalRun -> EvalConfig -> Eval -> Task) is sufficient; no new provenance entity added | §1.1 "V2.0 introduces no new score-provenance fields" + §1.3 rejected additions | Chain confirmed: `Task` parent_of `Eval` (`task.py:136`), `Eval` parent_of `EvalConfig` (`eval.py:751`), `EvalConfig` parent_of `EvalRun` (`eval.py:610`). `created_at` on base model (`basemodel.py:327`). No new provenance entity. | — |
| 85-R19 | Deferred | DEFERRED_OK | — | Statistical comparison primitives (Wilson CI, paired bootstrap, Wilcoxon, matched_intersection, etc.) are post-V2 and correctly absent | §4.1 "V2.0 ships raw aggregates only" + §4.2 "post-V2 primitives catalog" | No `stats.py`, no `comparator.py`, no wilson/bootstrap/wilcoxon implementations found anywhere in `libs/core/`. | — |
| 85-R20 | Deferred | DEFERRED_OK | — | No persisted MetricValue entity | §3.1 "V2 does not persist aggregate metrics" | No `MetricValue` class or entity anywhere in the codebase. Aggregation is purely on-read in `eval_api.py`. | — |

---

## Verifier-Added Items

| ID | Category | Verdict | Severity | Requirement | Spec Quote / Section | Evidence | Divergence |
|---|---|---|---|---|---|---|---|
| 85-R21 | Deferred | DEFERRED_OK | — | No Score.history or inline edit audit trail | §1.3 "Rejected addition: Score.history" | No such field exists on any model. | — |
| 85-R22 | Deferred | DEFERRED_OK | — | No eval_config_hash, scorer_version, scoring_metadata on EvalRun | §1.3 "Rejected addition" | No such fields exist on EvalRun. | — |

---

## Summary

The implementation is highly faithful to the spec. All six SkippedReason enum values are present. Skip persistence, validator relaxation, runner emission, transient-failure non-persistence, provenance chain, on-read aggregation with n_used/n_excluded, and all deferred items are correctly handled.

The only notable gap is the absence of the aggregate `n_excluded` warning/tooltip in the UI summary views (85-R17). The data flows correctly through the API, but the frontend does not consume it for the aggregate warning the spec describes. This is a minor gap since individual skipped results are still visible in detail views.
