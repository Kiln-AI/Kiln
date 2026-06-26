# Evals V2 — Spec-Fidelity Gaps: Decision Log

Working doc to triage every upheld gap from `SPEC_FIDELITY_REVIEW.md`. Human (scosman) decides; agent manages the queue and recommends. Source evidence: `unit_*.md` (per-requirement) and `confirm_*.md` (adversarial verdicts).

## Classification model

**Axis A — Resolution vehicle** (one per decision):
- **Cleanup** — important but small; rolled into the single cleanup project (includes one-line fixes).
- **Follow-up** — large enough to warrant its own planning + multi-phase build; gets a dedicated project.
- **Override spec** — the code is acceptable as-is; we knowingly diverge from the spec. Record the decision here; we do **not** rewrite the spec (it's not a long-lived doc).
- **Defer** — accept the delta to ship; record desire-to-fix: `important-hard-cut` / `nice-to-have` / `prefer-current`.

**Axis B — Ship gating:** `Ship-blocker` | `Post-ship`.

Status: `pending` (not yet ratified) → `ratified`.

---

## Dedup pass — 65 upheld findings across units → 40 distinct decisions

Refuted findings (intentional overrides, spec-stale, functionally-equivalent) are excluded — see `confirm_*.md`. Each decision lists the member finding IDs it covers (coverage ledger).

| ID | Decision (what's wrong) | Members | Sev | Batch | Vehicle | Gating | Status |
|----|----|----|----|----|----|----|----|
| D01 | LLM-judge create form emits **V1** `g_eval`/`llm_as_judge`, not V2 `LlmJudgeProperties`+`prompt_template` | 21-R39, fa-R02 | major | 1 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D02 | Manual `create_eval_config` endpoint passes V1 `type` straight through | 15-R41, fa-R02 | major | 1 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D03 | Copilot path emits V1 `llm_as_judge` + V1 `eval_set_filter_id` | 15-R42, fa-R01, fa-R30 | major | 1 | Project 2: Copilot & builder | Ship-blocker | **ratified** |
| D04 | `v1_to_v2_prompt_template()` wrapping helper (K.2) never built | 21-R38, 21-R40 | major | 1 | Project 2: Copilot & builder | Ship-blocker | **ratified** |
| D05 | `CreateEvaluatorRequest` lacks `eval_input_filter_id`; spec_builder makes V1 Eval | 15-R48, fa-R19 | minor | 1 | Project 2: Copilot & builder | Ship-blocker | **ratified** |
| D06 | `function_calling` disallowed unconditionally. **Investigated:** MATCHES V1 (`g_eval.py:269-279` disallows for both `g_eval` & `llm_as_judge`); spec's "allow for `g_eval=False`" DIVERGES from V1 with no stated reason. Keep V1 behavior. | 21-R19, 40-R18 | minor | 6 | Override spec | n/a | **ratified** |
| D07 | Test-run uses 4 free-text textareas, not the spec'd recent-dataset-item picker ("free-text is cut") | 70a-R25, deferred-R18 | major | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D08 | Create container never loads recent dataset items (no API call) | 70a-R02 | major | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D09 | Test panel: no Advanced expander, trace not from item, no empty-dataset state | 70a-R26, 70a-R27, 70a-R29 | minor | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D10 | Test-run is a collapse-below-form, not the spec'd left/right two-pane | 70a-R01 | minor | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D11 | Return-shape check vs `output_scores` doesn't gate Save | 70a-R30 | minor | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D12 | Type-picker order/labels diverge; "LLM as Judge (recommended)" not first | 70a-R12, 70a-R13 | minor | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D13 | No URL/history push on type select (Back via manual button) | 70a-R15 | minor | 2 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D14 | `kiln.get_tool_calls()` broken vs real OpenAI-format traces (gallery example finds 0) | 27-R20 | major | 3 | Cleanup | Ship-blocker | **ratified** |
| D15 | `kiln.get_assistant_messages()` returns `list[dict]`, contract is `list[str]` | 27-R21 | minor | 3 | Cleanup | Ship-blocker | **ratified** |
| D16 | Code score range-validated at persist, not execution → test pane accepts out-of-range. **Backend of D11 (return-shape gates Save) — moved out of cleanup to the UI-fix follow-on branch (scosman).** | 27-R14 | minor | 3 | Project 1 / ui-fix follow-on | Ship-blocker | **ratified** |
| D17 | Trust returns skip tuple vs raising `CodeEvalNotTrustedError` | 27-R41 | trivial | 3 | Override spec | n/a | **ratified** |
| D18 | `revoke_code_eval_trust` exists but unexposed | 27-R46 | trivial | 3 | Override spec (no action) | n/a | **ratified** |
| D19 | Code editor missing "Python" label | 27-R49, 70a-R24 | minor | 3 | Override spec (accept) | n/a | **ratified** |
| D20 | code-eval copy/labels: "Use This Example", "Save Anyway", save-modal text | 27-R52, 27-R56, 70a-R32, 27-R57 | minor | 3 | Override spec | n/a | **ratified** |
| D21 | `set_check` form default mode **"equal"** vs backend **"subset"** → silent strict equality. **Expanded:** form must always submit a valid mode + API/datamodel must require a real enum (reject empty/nil) | 22-R71 | moderate | 4 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D22 | Value-expression help text says **"JSONPath"** but engine is **Jinja2** (4 forms). Fix label + add examples-in-tooltip | 70a-R51 | moderate | 4 | Project 1: Manual create UI | Ship-blocker | **ratified** |
| D23 | XOR source uses a `select` where spec says radio group (+ disable inactive) | 22-R67/70a-R38, 22-R68/70a-R44, 22-R69 | minor | 4 | Project 1: Manual create UI | Ship-blocker (low-pri/descopable) | **ratified** |
| D24 | `set_check` expected-set is a textarea, not the spec'd tag-input | 22-R70, 70a-R46 | minor | 4 | Project 1: Manual create UI | Ship-blocker (low-pri/descopable) | **ratified** |
| D25 | `on_unexpected_tools` shown even when match-mode = "never" | 22-R73, 70a-R48 | minor | 4 | Project 1: Manual create UI | Ship-blocker (low-pri/descopable) | **ratified** |
| D26 | No on-blur client validation / inline error rendering across forms | 22-R76, 22-R77, 70a-R42 | minor | 4 | Project 1: Manual create UI | Ship-blocker (low-pri/descopable) | **ratified** |
| D27 | `expected_tools` not validated non-empty at save (vacuous pass) | 22-R46 | minor | 4 | Cleanup | Post-ship | **ratified** |
| D28 | `ArgMatch` regex not compiled at save (invalid regex silently never matches) | 22-R47 | minor | 4 | Cleanup | Ship-blocker | **ratified** |
| D29 | `reference_key` not validated `min_length=1` (empty key always skips at runtime) | 22-R62 | minor | 4 | Cleanup | Post-ship | **ratified** |
| D30 | Useless-template check is surface `{{`-scan, not AST (reference_data-only bypass) | 21-R41, 40-R31 | minor | 4 | Cleanup | Ship-blocker | **ratified** |
| D31 | Show "thinking"/reasoning for V2 `llm_judge` (and `code_eval`) results — hidden for all V2 today. **Cleanup finds the right fix; not prescribed here.** | 70b-R13 | minor | 5 | Cleanup | Ship-blocker (confirm) | **ratified** |
| D32 | Build a **read-only config-detail view** for V2 configs: shows a saved config's type + key properties so a user can see what a candidate does before cloning. Today non-`llm_judge` V2 configs show "No description provided." (§4.3). **Moved to Project 4** (reuses Project 1's per-type forms in readonly mode). | 70b-R14 | minor | 5 | Project 4: read-only views | Ship-blocker (blocked on Project 1) | **ratified** |
| D33 | Unknown V2 type renders raw scores gracefully instead of failing loud — **DESIRED** for cross-Kiln-version sync (older client views newer type's data). Compile-time `assertNever` still guards devs. | 70b-R05 | minor | 5 | Override spec | n/a | **ratified** |
| D34 | Scores render as raw floats, no type-aware badge — accept **parity with V1** (spec assumed a nonexistent badge component; V1 also raw floats) | 70b-R17 | minor | 5 | Override spec | n/a | **ratified** |
| D35 | No UI warning when `n_excluded > 0`. **Fix:** warning icon (warning color) + tooltip on aggregate-results surfaces, esp. the **compare view**, showing how many cases were excluded/skipped. (§3.4) | 85-R17, fa-R03 | minor | 5 | Cleanup | Ship-blocker | **ratified** |
| D36 | `EvalConfig.description` field never implemented (pure metadata; nothing reads it) | 10-R23 | minor | 6 | Defer (`nice-to-have`) | Post-ship | **ratified** |
| D37 | `EvalRun.scores` has `default={}` not in spec — required by spec's own skip semantics (§5.4); code correct | 10-R75 | trivial | 6 | Override spec | n/a | **ratified** |
| D38 | `_V2_ADAPTER_MAP` typed narrower (`type[BaseV2EvalBridge]`) — strictly safer than spec | 20-R08 | trivial | 6 | Override spec | n/a | **ratified** |
| D39 | `components/80 §3.1` checklist names wrong base class — but the wrong guidance is ONLY in the spec doc, not in any code/docstring | 80-R13 | minor | 6 | Override spec | n/a | **ratified** |
| D40 | Runner has no centralized skip-check methods — verified all 6 `SkippedReason`s still emitted; behavior complete | 45-R28, 45-R42 | trivial | 6 | Override spec | n/a | **ratified** |

---

## Final clustering (re-cluster complete — 2026-06-23)

Split by **surface**: the hand-driven create UI is one project; the automated/guided flows (Copilot, questionnaire builder) are another, separately owned. Three projects need build work; the rest are recorded no-work.

- **▶ Project 1 — "Manual eval create UI (V2)"** — Ship-blocker. Plan → `specs/projects/eval_create_ui_v2/project_overview.md`. Members: **D01, D02, D07–D13, D16, D21–D26** (D16 = backend of D11's return-shape Save-gating; scosman handling on the UI-fix follow-on branch). One dev / one branch rebuilds the hand-driven create surface once: rebuild the create container + per-type forms + Test-Your-Judge dataset-item test harness, AND make the manual form + `create_eval_config` endpoint emit V2 `LlmJudgeProperties`. Uses TaskRun/golden-subset datasets and builds `LlmJudgeProperties` directly — needs neither the translation helper nor `eval_input_filter_id`.
- **▶ Project 2 — "Copilot & builder create flows (V2)"** — Ship-blocker *(large, separately-owned dev effort — flagged as a gating-revisit candidate: post-ship fast-follow is defensible)*. Plan → `specs/projects/eval_copilot_builder_v2/project_overview.md`. Members: **D03, D04, D05**. Copilot path → V2 local translation; `spec_builder`/eval-builder (questionnaire, K.4/K.5) → emit V2 Evals+EvalConfigs; `v1_to_v2_prompt_template()` helper (K.2); `CreateEvaluatorRequest.eval_input_filter_id`.
- **▶ Project 3 — "Evals V2 cleanup"** — Plan → `specs/projects/evals_v2_cleanup/project_overview.md`. Members: **D14, D15, D27, D28, D29, D30, D31, D35**. **Fully parallel-safe with Project 1** (no shared files; D27–D30 share `eval.py` with Project 1's D21 but different classes — coordinate, low risk).
  - D14/D15 (Ship-blocker) — normalize `KilnEvalHelpers` to real OpenAI trace format. **Gate:** manual review running `get_tool_calls`/`get_assistant_messages` against a **real trace containing tool calls** before approval — agent fixtures insufficient (tests passed on a fake trace shape, which is how this shipped).
  - D28, D30 (Ship-blocker) / D27, D29 (Post-ship) — save-time validators on the deterministic `*Properties` (compile `ArgMatch` regex; AST useless-template check; non-empty `expected_tools`; `reference_key` min_length=1). Backend-only.
  - D31 (Ship-blocker, confirmed) — surface V2 `llm_judge`/`code_eval` reasoning in results; cleanup finds the right approach (non-prescriptive).
  - D35 (Ship-blocker) — warning icon + tooltip on aggregate/compare views when `n_excluded > 0`; data already in API.
- **▶ Project 4 — "Evals V2 read-only views"** — Plan → `specs/projects/evals_v2_readonly_views/project_overview.md`. Members: **D32**. Read-only config-detail view for V2 configs (§4.3) — reuses Project 1's per-type form components in disabled/readonly mode. **Blocked on Project 1** (`scosman/evals_v2_ui_fix`) finishing the form rebuild first; can't build against forms about to be rewritten. **Clone/prefill stays deferred** (scosman, 2026-06-24) but shares mechanics — a future revisit would extend this project. Ship-blocker, sequenced after Project 1.
- **No-work — Override-spec / no-action:** D06, D17, D18, D19, D20, D33, D34, D37, D38, D39, D40 (recorded above; code stands as-is, spec is stale/wrong/equivalent).
- **Defer (`nice-to-have`):** D36.

**Cross-project note:** Projects 1 & 2 both emit V2 `llm_judge` configs but via different paths (form-built vs V1→V2 translation) and mostly different files (svelte forms + `create_eval_config` endpoint vs `copilot_api.py`/`spec_api.py`) — they can run in parallel. They should agree on the resulting `LlmJudgeProperties` shape. Project 3's UI items touch **results/view** surfaces, not the create container, so no branch conflict with Project 1.

---

## Decision log (chronological, appended as ratified)

- **Batch 1 (D01–D05) — ratified.** → Dedicated Follow-up project **"Move create-eval paths to V2"**, **Ship-blocker**. scosman expanded scope to include the eval builder (`spec_builder`) and the manual non-Copilot path; project needs its own detailed spec that closes the gap across all create-Eval/EvalConfig entry points.
- **Batch 2 (D07–D13) — ratified.** → All three groups folded into one dedicated Follow-up project **"Create-flow redesign (Test-Your-Judge)"**, **Ship-blocker**, requires a new spec. Must coordinate with "Move create-eval paths to V2" (shared create container).
- **Batch 3 — ratified (complete).** A (D14, D15): Cleanup, **Ship-blocker** + manual real-trace gate. B (D16): Cleanup, **Ship-blocker** — reuse extracted score-range validator in the test pane (~10 LOC, zero per-type maintenance). C: D17 Override-spec (skip-tuple is the consistent adapter contract; `CodeEvalNotTrustedError` doesn't exist), D18 Override-spec/no-action (matches spec's "no revoke endpoint"; it's a test helper), D19 Override-spec/accept (Python already conveyed via highlighting + description), D20 Override-spec (current copy is intentional + generic across V2 types).
- **Batch 4 — ratified.** Established **rule: create-flow UI changes roll into "Create-flow redesign", not cleanup** (no parallel branches on the same form files). D21 (must-fix, expanded: form always submits valid mode + API rejects empty/nil enum) + D22 (must-fix: Jinja2 label + tooltip examples) + form-control polish D23–D26 → create-flow-redesign, Ship-blocker. Save-time footguns → Cleanup: D28 + D30 Ship-blocker (insidious silent pass/fail), D27 + D29 Post-ship (visible skip). [scosman to confirm if D27/D29 should also be ship-blocker.]
- **Batch 5 — ratified (complete).** D31 → Cleanup, Ship-blocker (gating: scosman to veto if post-ship), non-prescriptive. D32 → Cleanup, Ship-blocker (read-only config-detail view). D33 → **Override spec** (graceful fallback DESIRED for cross-Kiln-version sync; `assertNever` still guards devs). D34 → **Override spec** (accept V1 parity; badge component never existed). D35 → Cleanup, Ship-blocker (warning icon + tooltip on aggregate/compare views when `n_excluded>0`).
- **Batch 6 — ratified (complete).** D06 → **Override spec** (current MATCHES V1; spec's change diverges from V1 with no stated reason — keep V1 behavior). D36 → **Defer** `nice-to-have` (metadata field nothing reads; model-change unrelated to V2). D37/D38/D39/D40 → **Override spec / no-action** (code correct or strictly better; D39's stale guidance is spec-only, not in code).
- **✅ QUEUE COMPLETE — 40/40 distinct decisions ratified (covers all 65 upheld findings).**
- **Re-cluster (complete).** scosman re-split the two create-flow projects by **surface**: Project 1 "Manual eval create UI (V2)" (D01, D02, D07–D13, D21–D26 — hand-driven UI, one dev) vs Project 2 "Copilot & builder create flows (V2)" (D03, D04, D05 — Copilot + `spec_builder`, large/separately-owned). Cleanup = Project 3. Planning docs written under `specs/projects/{eval_create_ui_v2,eval_copilot_builder_v2,evals_v2_cleanup}/project_overview.md`.
- **Cross-check vs parallel "Manual create UI" agent (2026-06-24).** That agent surfaced its out-of-scope mismatches; all were independently caught here. Outcomes: **(1a fail-loud binding)** = D33 — scosman **keeps graceful fallback** (Override-spec); the agent's "fail loud per §4" is explicitly declined (graceful is required for cross-Kiln-version sync; compile-time `assertNever` still guards devs). **(score-badge §4.1)** = D34 — keep V1 float parity (Override-spec). **(clone/prefill)** = re-raised (was auto-deferred per Phase 6); scosman **keeps it deferred** — not in any project for V2.0. **(read-only config view D32)** — moved out of Cleanup into new **Project 4 "Evals V2 read-only views"** because it reuses Project 1's per-type forms (same files); blocked on Project 1 (`scosman/evals_v2_ui_fix`). Everything else maps cleanly: 1c→D32, 2a→D32, 3a→D03/D04 (Project 2), 3b mechanical `spec_builder`→D05 (Project 2) + onboarding redesign correctly out of evals_v2; 1b richer renderers are illustrative-per-spec (only judge-reasoning D31 slated); 1d mixed-type already tolerated (regression-check only).
- **D16 reassigned (2026-06-24).** D16 (test-pane score-range validation) is the backend half of Project 1's D11 (return-shape gates Save) and touches the shared `test_v2_eval` endpoint → **moved out of Project 3 (cleanup) into the UI-fix follow-on (scosman).** Result: **Project 3 cleanup is now fully parallel-safe with Project 1** and ready to implement (D27–D30 only share `eval.py` with D21 across different classes — coordinate, low risk).
