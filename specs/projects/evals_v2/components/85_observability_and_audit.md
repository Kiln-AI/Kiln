---
status: complete
approved: true
alignment_refs: [C.runner.1, E.17, E.18]
opens: []
summary: Score provenance, MetricValue provenance, skip records (SkippedReason enum), statistical comparison primitives (deferred).
---

# Observability and Audit

**Author:** sub-agent dispatched 2026-06-03 for Stage 4 gap-fill
**Status:** complete

## TL;DR

- **Score provenance (E.17):** No new schema. The existing `parent_of` chain (`EvalRun -> EvalConfig -> Eval -> Task`) plus `KilnBaseModel.created_at` already answers "where did this score come from?" EvalConfigs are write-once; clone-not-edit (see `components/70_builder_and_onboarding.md` section "No edit -- clone only") preserves the frozen-config provenance guarantee.
- **Skip records (C.runner.1 + E.18):** Partial EvalRun with `skipped_reason: str | None = None` (tolerant string, not a strict enum type) and companion `skipped_detail: str | None = None` free-text field. `SkippedReason(str, Enum)` defines the six canonical values producers set; consumers match against these constants but tolerate unknown strings. Skipped EvalRuns are terminal -- counted toward `percent_complete`, excluded from score means. Transient failures are NOT persisted.
- **MetricValue provenance (E.18):** No persisted MetricValue entity. Aggregation stays on-read in `eval_api.py`. API response shapes (`ScoreSummary` / `EvalResultSummary`) gain `n_used` and `n_excluded` per `(run_config_id x score_key)`.
- **Statistical comparison primitives (E.21, deferred):** Wilson CI, paired bootstrap, Wilcoxon are post-V2. V2.0 ships raw on-read aggregates only. The architecture (`compute on-read, no second source of truth`) supports layering stats on later with zero schema changes.

---

## 1. Score provenance (E.17)

### 1.1 Existing provenance chain is sufficient

V2.0 introduces no new score-provenance fields or entities. The existing Kiln `parent_of` chain already records, for every persisted score:

| What | Where | How |
|---|---|---|
| Which EvalConfig produced this score | `EvalRun` is a child of `EvalConfig` (via `KilnParentedModel`) | `EvalRun.parent_eval_config()` traversal |
| Config details (type, model, properties) | `EvalConfig.config_type`, `.model_name`, `.model_provider`, `.properties` | Immutable on disk -- never rewritten |
| Which Eval governs output-scores spec | `EvalConfig` is a child of `Eval` | `EvalConfig.parent_eval()` traversal |
| Which Task the Eval belongs to | `Eval` is a child of `Task` | `Eval.parent_task()` traversal |
| When the score was produced | `KilnBaseModel.created_at` on EvalRun | Auto-set at creation |
| Which input was scored | `EvalRun.eval_input_id` (V2) or `EvalRun.dataset_id` pointing at source TaskRun (V1 mode) | Per A2.6 |

### 1.2 Clone-not-edit preserves provenance

EvalConfigs are write-once by Kiln convention. "Editing" a config means cloning to a new candidate and modifying the clone (`components/70_builder_and_onboarding.md`, E.17 section). Old EvalRuns continue to point at the exact frozen config that produced them. The `EvalRun -> frozen EvalConfig` chain is the provenance guarantee.

### 1.3 What V2.0 explicitly does NOT add

| Rejected addition | Why |
|---|---|
| `Score.history: list[ScoreEdit]` (Inspect-style inline edit audit trail) | V2.0 has no "correct this score" UX. An empty `history` field is schema weight for an absent feature (`reports/competitive_inspect_ai.md:158,643`). |
| Separate `ScoreAudit` child entity | New entity proliferation; file-per-audit-event is heavy for Kiln's file-based storage. No competitor uses a separate entity for this. |
| `eval_config_hash`, `scorer_version`, `scoring_metadata` fields on EvalRun | The parent_of chain already answers "which config produced this." A hash adds nothing the chain doesn't already provide. |

### 1.4 Future revisit trigger

If/when the feedback pipeline (future project, post-V2) introduces a "correct this score" UX, revisit Inspect-style inline `Score.history` on the score record. That discussion belongs to the future Feedback Pipeline project, not V2.0.

---

## 2. Skip records (C.runner.1 + E.18)

### 2.1 Persistence model

Skips are persisted as **partial EvalRuns with a `skipped_reason` enum field** -- not as a separate entity. One entity type, fewer file types, fewer aggregation queries.

**Schema additions on EvalRun** (owned by `components/10_data_model.md`; semantics owned here):

```python
class EvalRun(KilnParentedModel):
    # ... existing fields unchanged ...
    skipped_reason: str | None = None              # NEW -- V2-additive (A0.1 safe)
    # Stored as str for back/forward-compat; set by convention to a SkippedReason value; unknown values tolerated on load.
    skipped_detail: str | None = None              # NEW -- free-form specifics for the skip
```

- `skipped_reason is None` -- normal scored run (V1 EvalRuns always have None).
- `skipped_reason is not None` -- terminal skip. Scores may be empty/None. Output may be absent.

### 2.2 `SkippedReason` enum -- seeded values

The enum is seeded here with six values covering all known skip conditions from the locked alignment decisions and V2 type catalog. The enum is extensible -- new values can be added as new EvalConfigTypes reveal new skip conditions. The `skipped_reason` field on EvalRun is typed as `str | None` (not `SkippedReason | None`) so that an unknown or future value loaded from disk does NOT hard-crash validation (tolerant back/forward-compat, matching the pattern used elsewhere in Kiln). Producers set the field to a `SkippedReason` constant; consumers match against the constants but tolerate unknown strings.

```python
class SkippedReason(str, Enum):
    """Why an (input x config) combination was permanently skipped.
    Convention enum -- producers set skipped_reason to one of these values.
    The field type is str | None (not this enum) for tolerant deserialization."""

    missing_reference_key = "missing_reference_key"
    # EvalInput.reference is missing a key that the bound EvalConfig requires.
    # Source: C.runner.1. The runner checks the EvalConfigType's declared
    # required reference keys at the start of each (input x config) job.
    # Example: llm_judge config declares required_var referencing
    # reference_data.judge_criteria, but EvalInput.reference has no
    # "judge_criteria" key.

    incompatible_input_shape = "incompatible_input_shape"
    # The EvalInput's data variant is incompatible with the EvalConfig's
    # expected input shape.
    # Source: C.runner.1 generalized. Covers:
    #   - Multi-turn TaskRun (parent_task_run_id set) under a single-turn
    #     V2 EvalConfig in the B2.1 runtime translation path.
    #   - Multi-turn V2 EvalConfig consuming V1 TaskRun source (no V1
    #     multi-turn shape to translate from; B2.1 edge case).
    #   - Future: image-gen EvalInput under a text-only EvalConfig, etc.

    extraction_failed = "extraction_failed"
    # A required_var expression (llm_judge) or value_expression
    # (deterministic types) evaluated to null/Undefined on this input.
    # Source: D.3 eval consumer design. The runner pre-checks required_var
    # expressions via extract(); null/Undefined -> skip with this reason.
    # Distinct from missing_reference_key: the key exists but the
    # expression path resolved to nothing (e.g., reference_data.criteria
    # exists but reference_data.criteria.rubric is null).

    missing_trace = "missing_trace"
    # A trace-walking type (tool_call_check, step_count_check) found that
    # EvalTaskInput.trace is None. These types require a trace to operate;
    # a None trace means the eval run did not carry trace data (e.g.,
    # final-answer-only eval run). Source: components/22 section 2.

    code_eval_not_trusted = "code_eval_not_trusted"
    # The project's code_eval trust gate has not been accepted.
    # Source: B.13 trust-gate UX. CodeEvalAdapter checks
    # project_trust_granted() before execution; untrusted -> skip.
    # This is a per-project permanent condition until the user grants
    # trust, so it is a valid terminal skip (not a transient failure).

    type_not_available = "type_not_available"
    # The EvalConfig's V2EvalType is not available in this Kiln
    # installation (e.g., a future plugin-registered type loaded on one
    # machine but not another; or a type added in a newer Kiln version).
    # Source: A2.11 adapter registry dispatch. If the registry has no
    # adapter for the config's properties.type, the runner skips rather
    # than hard-failing the entire eval.
    # For V2.0 (closed catalog per E.36), this should not occur in
    # normal operation. It guards against data-level forward compatibility
    # (a V2.1 EvalConfig loaded by a V2.0 runner).
```

**Rationale for each value:**

| Value | Alignment source | When emitted |
|---|---|---|
| `missing_reference_key` | C.runner.1 | Runner reference-key check at job start |
| `incompatible_input_shape` | C.runner.1 + B2.1 edge cases | Runner input-shape compatibility check |
| `extraction_failed` | D.3 (eval consumer design) | `extract()` pre-check returns null/Undefined |
| `missing_trace` | components/22 section 2 | Trace-walking type (`tool_call_check`, `step_count_check`) finds `trace` is None |
| `code_eval_not_trusted` | B.13 (trust-gate UX) | `CodeEvalAdapter` trust check fails |
| `type_not_available` | A2.11 (adapter registry) | Registry lookup finds no adapter for type |

### 2.3 `skipped_detail` companion field

The `skipped_detail: str | None = None` field on EvalRun carries free-form per-case specifics that complement the enum. The enum is for stable rollups and grouping (dashboards, aggregation queries); the detail string carries the case-specific information.

**Convention for `skipped_detail` per enum value:**

| `SkippedReason` value | `skipped_detail` contains | Example |
|---|---|---|
| `missing_reference_key` | The name of the missing key | `"expected_classification"` |
| `extraction_failed` | The expression that returned null/Undefined | `"reference_data.reference_answer"` |
| `missing_trace` | `None` (no additional detail needed) | — |
| `incompatible_input_shape` | Short description of the mismatch | `"multi-turn TaskRun under single-turn config"` |
| `code_eval_not_trusted` | `None` (condition is per-project, not per-case) | — |
| `type_not_available` | The unavailable type name | `"embedding_similarity"` |

`skipped_detail` is always optional (`None` is valid for any enum value). It is informational -- no code should branch on it. Structured queries group by `skipped_reason`; `skipped_detail` is for human inspection and debugging.

### 2.4 Terminal vs transient distinction

**Terminal (persisted as skipped EvalRun):** Conditions that will not change on retry without user action -- missing data, shape mismatch, trust not granted. These are meaningful signal: "this input was considered and excluded for a stable reason."

**Transient (NOT persisted):** API timeouts, rate limits, model service errors. These surface to the UI ephemerally during a run. DB-level absence ("incomplete") is the correct signal for retry-able / not-yet-run cases. No `failure_reason` field.

### 2.5 Validator relaxation for skipped EvalRuns

A skipped EvalRun carries no scores and may carry no output. Two existing validators must be extended with V2-aware relaxation (detail owned by `components/10_data_model.md` + `components/45_runner_architecture.md`; semantics here):

1. **`EvalRun.validate_scores`** (`eval.py:181-237`): When `skipped_reason is not None`, allow empty/None scores.
2. **`EvalRun.output`** (required `str` field): When `skipped_reason is not None`, allow `None`. Implementation options: make field `str | None` with a validator, or persist a sentinel. Design decision owned by `components/10_data_model.md`.

V1 EvalRuns never set `skipped_reason`, so their behavior is unchanged (additive per A0.1).

### 2.6 Runner skip-emission contract

The runner's responsibility (detail in `components/45_runner_architecture.md`):

1. **Before task execution:** Check reference-key presence, input-shape compatibility, trust gate, type availability. If any check fails, persist a partial EvalRun with the appropriate `skipped_reason` and proceed to the next (input x config) job.
2. **During extraction:** For `llm_judge`, pre-check `required_var` expressions via `extract()`. For deterministic types, evaluate `value_expression`. Null/Undefined result -> persist skipped EvalRun with `extraction_failed`.
3. **After skip persistence:** The skipped EvalRun is a terminal state. No retry. The skip contributes to `n_excluded` in aggregation.

The runner does NOT hard-fail the entire eval on any single skip. Other (input x config) combinations proceed normally (C.runner.1 locked behavior).

---

## 3. MetricValue provenance -- on-read aggregation (E.18)

### 3.1 No persisted MetricValue entity

V2 does not persist aggregate metrics. Aggregation stays on-read in `eval_api.py`. A persisted `MetricValue` or `EvalRunSummary` entity would create a second source of truth that must be kept in sync with the underlying EvalRuns -- rejected per E.18.

Kintsugi's `MetricValue(value, n_used, n_excluded, provenance, version)` tuple (`reports/kintsugi_gaps.md:34`) influenced the on-read response shape but does not become a persisted entity.

### 3.2 On-read aggregation rules

The aggregation function in `eval_api.py` computes per `(run_config_id x score_key)`:

| Field | Computation |
|---|---|
| `n_used` | Count of EvalRuns with all expected `score_keys` populated AND `skipped_reason is None` |
| `n_excluded` | Count of EvalRuns with `skipped_reason is not None` |
| `percent_complete` | `(n_used + n_excluded) / dataset_size` -- skipped runs count toward completion |
| Score means | Computed only over `n_used` EvalRuns |

**Key semantics:**
- Skipped runs count toward completion (they represent considered-and-excluded cases, not missing work).
- No `n_pending` / `n_failed_retryable` counts -- `1 - percent_complete` covers those.
- `None` / NaN means (following kintsugi pattern): when `n_used == 0`, the mean is `None` (undefined), never silently 0.

### 3.3 API surface additions

`ScoreSummary` / `EvalResultSummary` response shapes gain:

```python
class ScoreSummary(BaseModel):
    # ... existing fields (mean, count, etc.) ...
    n_used: int       # NEW -- cases contributing to score statistics
    n_excluded: int   # NEW -- cases skipped (SkippedReason set)
```

### 3.4 UI division of labor

Aggregation returns whatever it can compute plus completion metadata (`percent_complete`, `n_used`, `n_excluded`). UI gates display of incomplete-eval results (existing pattern: hide means below a completion threshold). V2 adds:

- Warning + tooltip when `n_excluded > 0`: "3 of 50 cases skipped -- required reference data missing" (human-readable copy per `SkippedReason` value).
- The existing completion-threshold heuristic for hiding incomplete eval means is preserved. Exact threshold is a UI implementation detail, not a schema concern.

---

## 4. Statistical comparison primitives (E.21 -- deferred post-V2)

### 4.1 V2.0 ships raw aggregates only

V2.0 dashboards display raw side-by-side means without confidence intervals or significance tests. This is acceptable for launch -- most competitors (Promptfoo, DeepEval, LangSmith, Braintrust) also lack built-in matched-case + statistical-significance UX.

### 4.2 Post-V2 primitives catalog

When shipped (post-V2), these are pure on-read utility functions in a utility module (e.g., `kiln_ai/eval/stats.py`), consumed at report/render time. No persisted aggregates, no new schema, no V2.0 hook required.

Primitives from kintsugi's `comparator.py` + `stats.py` (`reports/kintsugi_gaps.md:50-53`):

| Primitive | Purpose |
|---|---|
| `matched_intersection()` | Find the common input set between two run_configs for apples-to-apples comparison |
| `matched_aggregate()` | Compute aggregates over the matched subset only |
| `per_case_paired()` | Pair per-case scores across two configs for difference analysis |
| `wilson_difference_ci()` | Wilson score interval on the proportion difference |
| `paired_bootstrap_diff_ci()` | Bootstrap confidence interval on paired score differences |
| `wilcoxon_signed_rank_p()` | Non-parametric significance test for paired scores |

### 4.3 Why deferral is cheap

- Zero schema impact -- per-case scores in existing EvalRuns are sufficient input.
- Kiln's "compute on-read, no second source of truth" principle (established in E.18) extends naturally -- comparison primitives compute on demand.
- Datasets are small enough for on-the-fly stats (no pre-computation or caching needed for V2-scale datasets).
- Adding these post-V2 is a meaningful differentiator opportunity, not a launch requirement.

---

## 5. Cross-file ownership boundaries

This file owns the **semantics** of provenance, skip records, and statistical primitives. The schema fields and runtime behavior are owned by sibling files:

| Concern | Owner | This file's role |
|---|---|---|
| `EvalRun.skipped_reason` + `skipped_detail` field definitions | `components/10_data_model.md` (E.18) | Semantics: what each enum value means, `skipped_detail` conventions, when it's terminal |
| `SkippedReason` enum value list (6 values) | Seeded here (section 2.2); runtime emission owned by `components/45_runner_architecture.md` | Canonical value definitions + rationale |
| Runner skip-emission behavior | `components/45_runner_architecture.md` (C.runner.1, E.18) | Contract reference (section 2.5) |
| Validator relaxation for skipped EvalRuns | `components/10_data_model.md` + `components/45_runner_architecture.md` | Semantic requirement (section 2.4) |
| Clone-not-edit provenance rationale | `components/70_builder_and_onboarding.md` (E.17) | Cross-reference (section 1.2) |
| `ScoreSummary` API shape | `eval_api.py` implementation (Phase 1) | Response shape additions (section 3.3) |
| Statistical primitives implementation | Future `kiln_ai/eval/stats.py` (post-V2) | Deferred catalog (section 4.2) |

---

## Opens

None. All alignment_refs (C.runner.1, E.17, E.18) are fully covered. E.21 (statistical primitives) is explicitly deferred per reference/ALIGNMENT.md and documented as such in section 4.
