---
status: complete
approved: true
alignment_refs: [B.14, A2.4, E.19, E.20, E.21, E.33]
opens: []
summary: What V2 ships unresolved + why; post-V2 backlog (deferred types, deferred event-ordering form, sandboxing reversibility).
---

# Open Risks and Post-V2 Backlog

**Purpose:** Final Stage 4 design file. Collects every residual open from across the design set, every explicit deferral from alignment, and the post-V2 backlog. This file is a register — it catalogs opens but is not itself blocked by them.

**Authored:** 2026-06-03 (Stage 4 close). Sources: all sibling `components/*.md` frontmatter, `OPENS.md`, `reference/ALIGNMENT.md` (B.14, A2.4 deferred types, E.19, E.20, E.21, E.33), `batch_e_cross_cutting.md` (E.19/E.20/E.21/E.33 detail).

---

## Part 1 — What V2.0 ships unresolved

These are the residual opens that remain at Stage 4 close. Each entry names the open, which file owns it, what it blocks, and why shipping with it unresolved is acceptable.

### 1.1 Design-file frontmatter opens

At Stage 4 close, `components/29_rag_judge_templates.md` was the only file with non-empty `opens:`. **Both were resolved at Stage 5 (2026-06-06); `components/29` was `status: complete`.** With RAG templates now deferred from V2.0 (see `/specs/projects/rag_templates/`), these items are moot. Recorded here for the audit trail:

#### O-rag-template-var-rendering — RESOLVED (2026-06-06)

- **Owning file:** `components/29_rag_judge_templates.md` (section 6).
- **Was:** Does the `llm_judge` template engine support Jinja2 list iteration over `reference_data.retrieved_context` (a `list[str]`)?
- **Resolution:** Yes, no engine/schema change. The engine is Jinja2 `SandboxedEnvironment` (`components/06`); `{% for %}` and `loop.index` are core control structures, not blocked by the sandbox. Authoring rule added: each template declares its required reference keys in `required_var` so a missing key yields a clean pre-render skip (`extraction_failed` / `missing_reference_key`, C.runner.1) rather than a `StrictUndefined` crash.

#### O-rag-min-judge-model — RESOLVED (2026-06-06, Steve)

- **Owning file:** `components/29_rag_judge_templates.md` (section 6).
- **Was:** What minimum judge-model quality should the RAG claim-extraction templates recommend?
- **Resolution:** Documented recommendation only (capable/frontier-class judge), no gate — Kiln's existing model picker already steers users to frontier models. Phase 6 golden-dataset validation can sharpen the wording. No schema or design change.

### 1.2 OPENS.md items that remain live

Beyond the design-file frontmatter opens above, the following OPENS.md items remain unresolved and relevant to V2.0. Items that were resolved during Stage 3 alignment are struck through in OPENS.md and not repeated here.

**Data model / runner:**

- **Skipped EvalRun validator bypass shape** — E.18 adds `skipped_reason` and treats a skipped EvalRun as a terminal state with no scores, but `validate_scores` (requires non-empty scores) and `output: str` (required field) need V2-aware relaxation. Exact shape (optional output vs sentinel, validator gating) is Stage 5/implementation detail. Owned by `components/45` + `components/10`. Not a design blocker — both files are complete with this noted as an implementation task.
- **Reference-key collision warning** — when two EvalConfigs on the same Eval declare the same reference key. Allow but warn at bind time. Implementation-time decision; no schema impact.
- **Naming guidelines for reference keys** — convention guidance (prefer type-prefixed names like `llm_judge_criteria` over generic `criteria`). Documentation task, not a design gate.

**Code-eval (Phase 5 implementation items):**

- **Worker module hygiene enforcement** — lint/CI rule preventing heavy imports in `sandbox_worker.py`. Implementation detail for Phase 5.
- **Windows resource limits** — no rlimits on Windows in V2.0; wall-clock timeout + crash isolation are sufficient. Track via post-launch feedback. Revisit with `pywin32` Job Objects if needed.
- **`code_eval` properties shape** — inline code string vs file reference vs import path. Owned by `components/27_type_code_eval.md` (complete). Decision: inline code string (self-contained EvalConfig).
- **Eval helper library surface** — what functions ship pre-imported in the `exec()` env. Owned by `components/27`. Implementation detail for Phase 5.
- **Worker stdout/stderr in windowed PyInstaller** — child has `sys.stdout = None`; need capture/redirect. Phase 5 implementation.
- **Queue result serialization protocol** — result payload shape. Owned by `components/27`. Implementation detail.
- **Spawn thread-safety lock** — concurrent spawns on Linux PyInstaller (issue #7410). Phase 5 implementation note.
- **Code-eval scorer contract** (`O-codeeval-scorer-contract`) — injected variables and return shape. Owned by `components/27` (complete); gates `components/70` examples-gallery content (noted as a sequencing dependency in G.2).

**Filtering / performance (all post-V2 or implementation-time):**

- **Filter-then-judge composition** — new design needed. Post-V2 analytics layer.
- **Aggregation caching** — score means recomputed on every API call. Post-V2 performance optimization.
- **Generic trace signal extractor** — V2 uses per-type extraction (D.2/D.3); a generalized abstraction is post-V2.

**Builder:**

- **Manual builder incomplete eval** — Eval-creation + dataset-onboarding guidance deferred to future onboarding project.
- **Spec builder remote API dependency** — `api.kiln.tech` conflicts with local-first. Out of V2 data-model scope; offline fallback is a future consideration.

**Other:**

- **Bridge between data guide examples and eval datasets** — promotion mechanism. Out of V2 scope.
- **`Spec.eval_id` allows multiple specs per eval** — no constraint prevents this. Noted; no V2 action.
- **`eval_configs_filter_id` required for most templates** — barrier to "many small evals." Golden-subset requirement relax deferred in Batch G (decision 34).
- **Anthropic Console eval features** — competitive monitoring. Not actionable for V2.

---

## Part 2 — Post-V2 backlog

Organized by category. Each item names the deferral source, a one-line rationale for deferral, and the re-evaluation trigger.

### 2.1 Deferred eval types (A2.4)

Per reference/ALIGNMENT.md A2.4, V2.0 ships 8 types. The following are deferred to post-V2 as V2.x candidates:

| Deferred type | Why deferred | Re-evaluate when |
|---|---|---|
| `composite` | Steve flagged "not important" during catalog scoping. No user demand signal. | Real user request for AND/OR/weighted combination of child config scores. |
| `threshold` | Numeric-score-to-pass/fail bridge is not a V2.0 differentiator. Trivial to add later (additive union member). | Users need pass/fail gating on continuous scores (e.g., CI pipelines). |
| `json_schema` | Library-backed validation (`jsonschema` or Pydantic); can land without redesign. | Users need output-conformance checks beyond what `exact_match`/`pattern_match` cover. |
| `event_ordering` | Moved from should-ship to post-V2 by Steve. Complex DSL design should be driven by real usage patterns, not pre-emptive. Per B.14, `code_eval` is the interim host. | Repeated `code_eval` implementations of ordering checks suggest a common shape worth promoting. |
| `embedding_similarity` | Requires embedding model call infrastructure (model selection, caching, distance metric). Not blocking V2.0. | RAG evaluation demand grows beyond the 6 LLM-judge templates in `components/29`. |
| `dag_metric` | DeepEval-style deterministic decision-tree with LLM at nodes. Design exploration, not a V2.0 differentiator. | Users need composite deterministic+LLM evaluation that `composite` type alone doesn't serve. |

**Extensibility path:** All deferred types add to the existing `V2EvalType` enum + `V2EvalConfigProperties` discriminated union (per A2.1). No advance schema reservation required. Plugin extensibility (E.36) preserves the door for third-party implementations.

### 2.2 Deferred event-ordering form (B.14)

**What:** `event_ordering` was the most complex proposed deterministic type — a DSL for expressing temporal ordering constraints on agent traces (e.g., `event_type(pattern) BEFORE event_type(pattern)`).

**Why deferred:** B.12 locked `code_eval` as a V2 EvalConfigType. Users needing event-ordering checks can write them as Python in `code_eval` today. The tension ("does event_ordering need a DSL or code?") dissolves — code is available for all such cases. Promoting to a built-in type becomes a "is this pattern common enough?" question answerable only from real usage data.

**Re-evaluate when:** Multiple users implement similar ordering-check patterns in `code_eval`, revealing a common shape that justifies a dedicated DSL.

### 2.3 Sandboxing reversibility (B.13 / B.14)

**What:** V2.0's `code_eval` execution model is `multiprocessing` (spawn) + `freeze_support()` + trust-gate UX. This provides crash isolation and wall-clock timeout but no language-level sandbox — no network restrictions, no filesystem path restrictions, no Windows resource limits.

**Residual risks accepted for V2.0:**
- **Network access is wide open.** User code can make arbitrary network calls. Mitigated by the trust-gate UX ("never paste code from a stranger or the internet here") and the fact that Kiln is a local-first tool (the user running code_eval is the same user whose filesystem/network it accesses).
- **Filesystem access is wide open.** Same mitigation as network.
- **Windows has no resource limits.** Wall-clock timeout catches infinite loops; crash isolation catches segfaults. Runaway memory is unmitigated on Windows.

**Reversibility path:** The architecture explicitly supports upgrading:
- **WASM sandbox (V2.x):** If real attack pressure emerges (shared-project compromise scenario), `multiprocessing` can be swapped for a WASM-based execution under the same `CodeEvalAdapter` + `run_scorer` surface. The ~20MB bundle cost (A0.4) becomes an explicit budget decision at that time.
- **Windows Job Objects (V2.x):** If Windows users hit runaway-code issues, `pywin32` Job Objects provide process-level CPU/memory caps. Additive; no architecture change.
- **Seam:** `CodeEvalAdapter` and `run_scorer` are the upgrade seams. Neither the adapter interface nor the V2 type catalog needs to change for a sandbox upgrade.

**Re-evaluate when:** User reports of code_eval being used with untrusted code, or shared-project scenarios where the trust-gate UX is insufficient.

### 2.4 Dataset versioning — explicit non-goal (E.33)

**What:** Braintrust pins experiments to dataset versions for reproducibility. V2 explicitly does NOT version datasets, snapshot them, or pin EvalRuns to a "dataset version."

**Why this is a non-goal (not a deferral):**
- Datasets evolve by design — adding new EvalInputs is normal. Comparison is always between run_configs at the current dataset state.
- Per-input reproducibility already holds: EvalConfigs are immutable (E.17), EvalRuns pin to specific inputs via `eval_input_id` (A2.6), and EvalInputs are self-contained (carry all data needed for an eval run).
- `percent_complete < 1` (E.18) signals "this run_config hasn't kept up with new dataset items" — the natural workflow is to backfill.
- Git handles "show me the dataset as of last Tuesday" for power users.

**This is not revisited unless:** The product principles change (e.g., Kiln moves to cloud-hosted experiment tracking where dataset drift between runs becomes a real UX problem).

### 2.5 Composite policy registry (E.19)

**What:** Named composite scoring policies (`tiered_60_40`, `blocking_only`, etc. from kintsugi) that govern how child config scores combine into a composite eval score.

**Why deferred:** Composite policies are consumed only by the `composite` EvalConfigType, which itself is deferred (section 2.1). No V2.0 schema hook, field, or placeholder is needed. When `composite` lands, its policy field lives inside `CompositeProperties` (per A2.1's extensible union). Reservation check confirmed: `Eval.output_scores` + per-config scoring (C.9) already give a future composite type everything it needs.

**Re-evaluate when:** `composite` type is prioritized for V2.x.

### 2.6 Blocking vs quality tier (E.20)

**What:** Kintsugi's `tier: blocking | quality` tag on evaluation criteria, feeding composite policies.

**Why deferred:** Tiers feed into composite scoring (E.19), which is deferred alongside composite (A2.4). No `tier` field ships on `EvalOutputScore`, `EvalInput.reference`, or anywhere else. A display-only tier (without an aggregation policy backing it) was rejected — UX would confuse without semantics.

**Re-evaluate when:** `composite` type is prioritized (tiers are part of its policy design), OR Steve identifies a V2.x display use case for tiers independent of composite scoring.

### 2.7 Statistical comparison primitives (E.21)

**What:** Matched-case intersection, paired-difference analysis, Wilson CI, paired bootstrap CI, Wilcoxon signed-rank. Kintsugi implements all of these (`comparator.py`, `stats.py`).

**Why deferred:** V2.0 ships raw on-read aggregates (means, `percent_complete`, `n_used`/`n_excluded` per E.18). Statistical primitives are pure on-read utility functions with zero schema impact — they compute on demand from per-case scores in existing EvalRuns. Deferral is cheap to revisit; no lock-in. Most competitors also lack built-in matched-case + statistical-significance UX.

**Where they live (post-V2):** Utility module (e.g., `kiln_ai/eval/stats.py`) consumed by the aggregation/comparison API layer, not embedded in `eval_api.py`. Per E.21, no persisted aggregates, no new schema.

**Re-evaluate when:** V2.0's aggregation layer is stable and users request "is this difference between Config A and Config B real or noise?" answers.

### 2.8 Feedback pipeline (Batch F — punted 2026-06-03)

**What:** The entire feedback-to-eval pipeline: unified score model, triage data model, clustering, corrected-output promotion, V1/V2 routing, self-improving judges. Originally Batch F; punted to a future standalone Feedback Pipeline project.

**Why punted:** Feedback's only evals-V2 footprint was additive data-model change (`source_task_run_id` on EvalInput) that pre-commits schema for an unplanned project. Per A0.1, additive fields can be added when the project is actually designed. The triage workspace + clustering UI is its own product surface.

**V2.0 consequence:** `EvalInput` ships without `source_task_run_id`. A0.5 ("Feedback closes the loop") remains a north-star direction, not a V2.0 deliverable.

**Re-evaluate when:** The Feedback Pipeline project is prioritized as a standalone effort.

### 2.9 Future onboarding project (Batch G partial deferral)

**What:** Goal-first questionnaire, routing logic (describe goal in plain text, system picks and sizes eval), right-sizing mechanism (A0.2), hidden-SpecType curation, golden-subset requirement relax. Originally Batch G decisions 27/28/30/34.

**Why deferred:** Reframed as a UX project in its own right. V2's UI obligation is narrower: expose V2 eval types via create + view surfaces (G.1/G.2/G.3). The `competitive_ui_vs_code/` study is the reference brief for the future project.

**Re-evaluate when:** V2 ships and the onboarding experience becomes a user-facing priority.

### 2.10 Post-V2 builder follow-ups

- **Server-side output generation becomes optional** — V2 EvalInputs don't require outputs; the remote `api.kiln.tech` output-generation step can be made optional post-V2, reducing Copilot generation time (~10min to ~3-4min). Requires old-client upgrade coordination.
- **Manual flow migration to EvalInput-source datasets** — manual evals currently produce TaskRuns; V2 EvalConfigs consume them via B2.1 runtime translation. Post-V2, the manual flow could migrate to producing EvalInputs (matching the Copilot path's shape). Requires synthetic data UI redesign. Explicitly out of scope per Steve.

### 2.11 RAG judge templates + continuous scoring (punted from V2.0)

**What:** 6 first-party RAGAS-style `llm_judge` templates (faithfulness, answer relevance, context relevance, context precision, hallucination, answer correctness) and the continuous 0-1 scoring model they required.

**Why punted:** Continuous scoring was not a first-class V2 feature (modeled by abusing `pass_fail` as float), deviated from V1's discrete convention and the phase plan (`phase_4.md:183` says `allow_float_scores=False`), leaked leniency into V1's battle-tested scorer, g-eval cannot compute continuous fractions, and UI/doc support was missing.

**V2.0 consequence:** V2 `llm_judge` uses discrete model output only (`allow_float_scores=False`), matching V1. The shared scorer (`build_llm_as_judge_score`) is restored to its pristine strict behavior with no float-leniency.

**Bring-back plan:** `/specs/projects/rag_templates/project_overview.md`. Design preserved in `components/29_rag_judge_templates.md` (status: deferred).

**Re-evaluate when:** First-class continuous-score representation is designed (proper 0-1 score type, not pass_fail-as-float), g-eval incompatibility is resolved, and docs/UI support for continuous scoring exists.

---

## Risk register — consolidated

| # | Risk | Severity | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | `code_eval` trust-gate UX is insufficient for shared-project scenarios (untrusted code from collaborators) | Medium | Low (Kiln is local-first; primary user runs their own code) | Trust gate warns clearly; WASM upgrade path preserved (section 2.3) | `components/27` |
| R3 | ~~RAG templates assume Jinja2 list iteration works (O-rag-template-var-rendering)~~ RESOLVED 2026-06-06 — sandboxed Jinja2 supports it; `required_var` handles missing-key skips (section 1.1) | — | — | Closed | `components/29` |
| R4 | No dataset versioning confuses users expecting Braintrust-style pinning | Low | Low (Kiln's product model is current-state comparison, not experiment pinning) | `percent_complete` signals gaps; git handles historical needs | E.33 (non-goal) |
| R5 | Deferred composite/tier/stats leaves V2 dashboards showing only raw means | Medium | Certain (by design) | Raw aggregates + skip reporting are the V2.0 surface; statistical primitives are the highest-value post-V2 analytics enhancement | E.19/E.20/E.21 |
| R6 | Windows `code_eval` runaway memory (no rlimits) | Low | Low (wall-clock timeout catches most runaways; Kiln users typically run lightweight scorers) | `pywin32` Job Objects upgrade path (section 2.3) | `components/27` |
| R7 | Worker module hygiene drift — heavy imports in `sandbox_worker.py` silently balloon child cold start | Medium | Medium (easy to introduce accidentally) | Lint rule / CI check required at Phase 5 implementation | `components/27` |
| R8 | Feedback pipeline deferral means V2 has no feedback-to-eval loop (A0.5 is north-star only) | Medium | Certain (by design) | Standalone Feedback Pipeline project is the planned follow-up; V2 EvalInput schema is additively extensible | Batch F (punted) |
