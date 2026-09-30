# Evals V2 — Spec-Fidelity Review

**Date:** 2026-06-23
**Branch:** scosman/evals_v2
**Method:** Spec-driven, completeness-first review (the inverse of the prior `/spec deep cr`, which was diff-driven and code-quality-first). 16 reviewers each took one spec unit, enumerated *every* requirement (UX/layout/interaction and "X is cut/deferred" directives treated as first-class), then opened the real code and rendered a per-requirement verdict with `file:line`. 13 adversarial skeptics then tried to *refute* every gap (checking spec + code + `RUN_NOTES.md`/git for intentional overrides) before it counted.

**Scope:** ~700 atomic requirements extracted across 16 units; ~80 candidate gaps; **~55 upheld**, ~25 refuted (intentional overrides, spec-stale, or functionally-equivalent). Per-unit detail in `unit_*.md`; adversarial detail in `confirm_*.md`.

**Why a new review was needed:** the prior deep CR decomposed by *code area touched* and asked "is this code good?" It had no step that enumerates spec requirements and checks each against code, so silently-omitted UX/design requirements (e.g. the Test-Your-Judge panel) were invisible to it. This review decomposes by *spec component* and asks "does every requirement have faithful code?"

---

## Headline findings

### 1. ⛔ MAJOR — The V2 *creation-path migration* (Batch K) was never implemented. The manual UI and Copilot still create **V1** EvalConfigs.

The spec's K-decisions (`components/15 §8`, `§11 sub-task 8`; `components/21 §6`) require that, after V2 ships, the manual create endpoint, the LLM-judge create form, and the Copilot path all emit **V2-shaped** EvalConfigs (`config_type="v2"`, `LlmJudgeProperties` with a Jinja `prompt_template`). They don't:

- The LLM-judge **create form still returns `g_eval`/`llm_as_judge` V1 configs** with `eval_steps` — not `LlmJudgeProperties` (`llm_judge_form.svelte:42-44`, `create_eval_config/+page.svelte:347`).
- The manual `create_eval_config` endpoint passes `request.type` straight through (`eval_api.py:949`).
- The **Copilot path** still creates `EvalConfigType.llm_as_judge` with a dict properties blob and a V1 `eval_set_filter_id` (`copilot_api.py:340`, `:328`).
- The `v1_to_v2_prompt_template()` wrapping helper the spec calls for (K.2) **does not exist anywhere** (grep-clean).
- `CreateEvaluatorRequest` never exposes `eval_input_filter_id` (`eval_api.py:171`).

**Root cause:** the spec's "sub-task 8" (K.1/K.2/K.3 creation-path migration) was **never assigned to any of the 6 implementation phases**, and Phase 6 explicitly designed the LLM-judge form as a "legacy type" emitting the V1 payload (`phase_6.md` step 10d). Same failure mode as finding #2: a load-bearing spec requirement was dropped at the phase-decomposition step.

**Consequence:** nothing is *broken* — V1 configs still run via legacy dispatch (D.5) — but **the enhanced V2 `llm_judge` adapter (per-criterion verdicts, `prompt_template`, `g_eval` toggle as a V2 property) appears unreachable from the standard create UI and Copilot**; it's exercised only by tests and direct API/SDK use. For a project whose headline is "enhanced, typed eval configs," the primary user path doesn't produce them. *Recommend: confirm whether this was a deliberate scope cut or an accidental omission, then either wire the form/endpoint/Copilot to emit V2 `llm_judge`, or record the deferral explicitly.*

### 2. ⛔ MAJOR — "Test Your Judge" was built as free-text textboxes, not the spec'd dataset-item test harness. *(the originally-reported issue — independently re-discovered)*

`components/70 §1–§2` specify the right pane is a **"Test Run"** harness where the user **picks a recent dataset item** to run on; it states verbatim **"Manual free-text input is cut,"** with reference data behind an **Advanced expander**, the **trace coming from the selected item**, and an empty-dataset state (*"Run your task to generate sample inputs"*). The container is responsible for **loading recent dataset items**. Instead:

- The test panel is **four free-text textareas** (`final_message` / `task_input` / `trace` / `reference_data`) — the exact thing the spec cut (`create_eval_config/+page.svelte:567-621`). **(CONTRADICTED, major)**
- **No dataset items are loaded** — there is no API call for them at all (`+page.svelte`, whole file). **(CONTRADICTED, major)**
- No empty-dataset state, no Advanced expander, trace typed by hand. *(downstream of the above)*
- Layout is a single-column **collapse below the form** rather than the spec'd left/right two-pane. Phase 6 chose this (`phase_6.md:91`), so it's a phase-plan deviation, not a coding miss — but it's still a deviation from the approved design you flagged.

Same root cause as #1: `phase_6.md` step 10c reduced the spec's "pick a recent dataset item" to "a textarea or structured input," dropping the picker, the layout, the "free-text is cut" directive, the Advanced expander, and the empty-state. The coding agent built the phase plan faithfully; the phase plan wasn't the spec.

### 3. ⚠️ MODERATE — `kiln.get_tool_calls()` doesn't work against real Kiln traces — and the shipped example gallery depends on it.

`eval_helpers.py:16-24` extracts tool calls by filtering for `role == "tool_call"`, but real Kiln traces are OpenAI-format (`role == "assistant"` with a nested `tool_calls` array — see the correct extraction in `v2_eval_tool_call_check.py:41-66`). So a user copying the **"Check tool usage patterns"** example from the gallery (`components/70 §2`, `components/27 §2.4`) gets **zero tool calls** in production. The helper's tests pass only because they use a non-production trace shape (`test_code_eval_samples.py:294-297`). This is a user-facing contract defect in the code-eval helper library. *Recommend: normalize `get_tool_calls` (and `get_assistant_messages`, which returns `list[dict]` where the spec contract is `list[str]`) to the real trace format, and test against a real trace.*

---

## Upheld findings — full list, by priority

### Moderate (real functional defects; fix before ship)

| ID(s) | Finding | Evidence | Fix |
|---|---|---|---|
| 22-R71 | `set_check` form default mode is **"equal"**, but the backend/Pydantic default is **"subset"** — users who don't touch the control silently get strict set equality. | `set_check_form.svelte:7` vs `eval.py:145` | Default the form to `subset`. |
| 70a-R51 | Four deterministic forms label the value-expression help text **"JSONPath"**, but the engine is **Jinja2** — actively misleads users into wrong syntax. | `exact_match_form.svelte:70`, `contains_form.svelte:82`, `set_check_form.svelte:88`, `pattern_match_form.svelte:41` | Change copy to "Jinja2 expression". |
| 27-R20 | `get_tool_calls` broken vs real traces (headline #3). | `eval_helpers.py:16-24` | Normalize to OpenAI trace format. |

### Minor — validation footguns (config can be saved that always fails/skips at runtime)

| ID(s) | Finding | Evidence |
|---|---|---|
| 22-R47 | `ArgMatch` regex values not compiled at save time → invalid regex silently never matches at runtime (contrast `PatternMatchProperties:114-122`, which validates). | `eval.py:154-156` |
| 22-R62 | `reference_key` fields have no `min_length=1`; `reference_key=""` passes the XOR validator but always skips at runtime (key `""` never present). | `eval.py:96,129,144` |
| 22-R46 | `ToolCallCheckProperties.expected_tools` has no non-empty validation; empty list + mode "all"/"ordered" vacuously passes. | `eval.py:164-168` |
| 21-R41 / 40-R31 | Useless-template check is a surface string scan for `{{`/`{%`; a `reference_data`-only template (e.g. `{{ reference_data.expected }}`) passes but never references model output. Spec requires AST-based variable analysis. | `eval.py:706-712` |

### Minor — view/results surfaces

| ID(s) | Finding | Evidence |
|---|---|---|
| 70b-R13 | "Thinking" column hidden for **all** V2 configs, including `llm_judge`/`code_eval` that produce `intermediate_outputs`; the judge's reasoning is invisible in results. `intermediate_outputs` isn't even passed to V2 result renderers. | `run_result/+page.svelte:285-286`; `llm_judge_result.svelte` (no reasoning refs) |
| 70b-R14 | No read-only config-detail view for non-`llm_judge` V2 types (in scope per §4.3 so a user can see a config before cloning); they show "No description provided". | no `[eval_config_id]/+page.svelte`; `eval_config_instruction.svelte:6-18` |
| 70b-R05 | Defensive binding incomplete: an unknown/unmapped V2 type string from the API renders raw scores **silently** instead of failing loudly (the compile-time `assertNever` is unreachable for runtime strings). | `registry.ts:163-174`; `run_result/+page.svelte:288-299` |
| 85-R17 / fa-R03 | `components/85 §3.4` requires a UI warning + tooltip when `n_excluded > 0`; `n_excluded` is in the API but **no** frontend component consumes it. | `grep n_excluded app/web_ui/src` → only `api_schema.d.ts` |

### Minor — create-flow polish (deterministic forms & picker)

`22-R73`/`70a-R48` `on_unexpected_tools` shown even when match-mode is "never" (spec: hidden) · `22-R67/68/69` XOR source uses a select where spec says radio group (cosmetic) · `22-R70`/`70a-R46` `expected_set` is a one-per-line textarea, spec says tag-input · `22-R76`/`22-R77`/`70a-R42` no on-blur client validation / no inline error rendering · `70a-R12/R13` type-picker order/labels diverge; "LLM as Judge (recommended)" should lead, is listed 7th as "LLM Judge" · `70a-R15` no URL/history push on type-select (Back uses a manual button) · `27-R49`/`70a-R24` no "Python" label on the editor ("Score Function" instead) · `27-R52`/`27-R56`/`27-R57` code-eval copy/labels differ from spec ("Use This Example", "Save Anyway").

### Minor — backend/data-model & misc

`10-R23` `EvalConfig.description` field never implemented (pure metadata) · `27-R14` score range-validated at persist time, not execution time, so the **test pane** silently accepts out-of-range scores · `21-R19`/`40-R18` `function_calling` structured-output mode disallowed unconditionally where spec allows it for `g_eval=False` (nil real impact — universal `json_schema` fallback; V1 did the same) · `27-R21` `get_assistant_messages` returns `list[dict]` where the contract is `list[str]` (no shipped example uses it) · `27-R41`/`27-R46` trust returns a skip tuple vs raising / `revoke` exists but is unexposed (both work).

---

## Refuted / not defects (checked and dismissed — do **not** action these)

**Intentional later overrides (the spec is now stale; update the spec, not the code):**
- **Trust-modal copy** (27-R47/70a-R34) — you deliberately shortened it (RUN_NOTES Phase 12; commits `8e0484121`, `89a69f249`). Code is correct.
- **`Eval.evaluation_data_type` default `final_answer`** (10-R12) — deliberate V1 back-compat; the V2 path never reads the field; documented in `components/15 §4.1`. `components/10` is stale.
- **Registry split into `legacy_…`/`v2_…` functions** (15-R34/20-R07) and the **`BaseV2EvalBridge` intermediate** (20-R12/21-R42) — both intentional cleanups (deep-cr-cleanup phases 3 & the bridge commit), citing C.11c. Class named `LlmJudgeEval` not `LlmJudgeAdapter` (21-V01) — `*Eval` is the consistent convention; the spec name was illustrative prose.

**Spec-stale / mismatched against the real data model (code is right):**
- `EvalTaskInput.final_message`/`task_input` as `str` not `str|dict` (40-R01/R02) — `TaskOutput.output` and `TaskRun.input` are always `str` in Kiln; the spec's `str|dict` doesn't match the data model.
- "Existing score-badge component" for results (70b-R17) — **no such component exists** in the codebase; V1 renders raw `toFixed(2)` floats too. Spec assumed a component that was never built. (Still worth building type-aware badges as polish, but it's not a regression.)
- `components/80 §3.1` plug-in checklist (80-R13) says "subclass `BaseEval` directly"; reality is "subclass `BaseV2EvalBridge`, implement `evaluate()`". **The spec checklist is wrong and would misguide a future implementer** — fix the spec.
- `MultiTurnSyntheticEvalInputData.synthetic_user_info` as `dict` not a typed model (10-R66) — owned by the parallel multi-turn project (C.5), correctly a placeholder.

**Functionally equivalent (no behavior difference):**
- All runner-internals findings (45-R02/R03/R12/R21/R25/R28/R42, 15-R39) — `stored_output`/`stored_trace` fields, in-memory `EvalInput` synthesis, and centralized skip methods are absent, but every skip reason is still emitted and B2.1 TaskRun-source works via `EvalTaskInput.from_task_run()`. Verified no skip condition is dropped.
- `percent_complete` formula (85-R16) — algebraically identical to the spec's `(n_used+n_excluded)/dataset_size`.
- Clone/prefill & read-only config (70a-R05/R10) — explicitly **out of scope for Phase 6** (`phase_6.md:23,558`).
- LLM-judge excluded from the test panel (70a-R53) — intentional; it has the separate Compare-Judges calibration flow.
- `tool_call_check` args "collapsed by default" (22-R72) — args start empty behind an "+ Add" button; functionally collapsed.

---

## Coverage map

| Unit | Reqs | Upheld gaps (post-adversarial) |
|---|---|---|
| 05 thinking-formatter | 20 | 0 (2 cannot-verify, both benign) |
| 10 data-model | 62 | 1 minor (description field); 10-R12 refuted |
| 15 coexistence | 48 | creation-path cluster (major) + minor |
| 20 types-overview | 32 | 0 real (all refuted/equivalent) |
| 21 llm-judge | 54 | creation-path (major) + g_eval mode (minor) |
| 22 deterministic | 82 | 1 moderate (set_check default) + validation/UX minors |
| 27 code-eval | 60 | get_tool_calls (moderate) + minors |
| 40 template/extraction | 43 | template-check bypass (minor) |
| 45 runner | 42 | 0 real (all functionally equivalent) |
| 50 reference-data | 22 | 0 |
| 70a create-flow | 52 | Test-Your-Judge cluster (major) + form polish |
| 70b view-surfaces | 20 | thinking column, config-detail, fail-loud, badges (minor) |
| 80 extensibility | 28 | spec checklist wrong (fix spec) |
| 85 observability | 22 | n_excluded UI warning (minor) |
| deferred-and-cut | 22 | 21/22 correctly deferred; 1 = the test-run cut |
| functional/arch cross-cut | 30 | dups of creation-path cluster |

---

## Process takeaway

Two of the three headline findings (#1 creation-path migration, #2 Test-Your-Judge) trace to the **same failure mode**: a fully-specified requirement was silently dropped or watered down when the spec was decomposed into `phase_plans/phase_N.md`, and the coding agent then faithfully built the degraded phase plan. The spec was fine; the **spec→phase-plan derivation step had no fidelity check**. The prior deep CR couldn't catch it because it reviewed code-for-quality, never spec-for-coverage. A standing guard for the rest of evals_v2 (and future projects): when deriving a phase plan, diff each phase against its source `components/*.md` and require every UX/layout/"cut" directive to survive or be explicitly logged as deferred.

**Detailed evidence:** per-requirement tables in `unit_*.md`; per-finding adversarial verdicts in `confirm_*.md`, all under this directory.
