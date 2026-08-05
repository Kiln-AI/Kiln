---
status: complete
---

# Functional Spec: Evals V2 Manual Create-Flow Remediation

> **⚠️ Superseded — kept for historical context.** The manual `llm_judge` design below (a backend-baked static template, no in-UI authoring, a minimal `{model, provider, g_eval}` create request) was superseded by **`specs/projects/evals_v2_judge_prompt/`**: the shipped builder has an editable "Advanced: Judge Prompt" section, and its create request carries `judge_prompt`, `system_prompt`, and `reference_keys`.

A **bridge spec**: *current state → target → delta to close*. The **target is the existing
reviewed spec**, not anything restated here. Authoritative destination docs:

- **`evals_v2/components/70_builder_and_onboarding.md`** — builder UI (§1 container/layout, §2
  code-eval test pane, §3 deterministic forms).
- **`evals_v2/components/21_type_llm_judge.md`** — V2 `llm_judge` (`LlmJudgeProperties`, the
  Jinja `prompt_template` model, `g_eval`, `system_prompt`/`thinking_instruction` defaults,
  §10 V1→V2 wrapping).
- **`evals_v2/components/27_type_code_eval.md`**, **`…/22_type_deterministic_basics.md`** —
  code-eval scorer contract + deterministic `…Properties` shapes.

When a row says "target", read the cited section there. **Do not re-spec the screens.**

## Scope — the MANUAL eval-config create flow only

| In scope | Out of scope (separate projects) |
|---|---|
| The manual (hand-driven) create surface: `create_eval_config` page + per-type forms + the create test-run pane. | **Copilot / eval-builder / `spec_builder` / questionnaire** create paths (separate project). |
| Making the manual `llm_judge` path emit **V2**. | **View / run-result / comparison surfaces** (separate cleanup project) — incl. fail-loud render binding, per-type result renderers, typed score badges. |
| The dataset-item test harness + deterministic form fixes. | **Read-only config-detail + clone/prefill** (`70 §4.3`, E.17) — separate follow-up. |
| Route/nav restructure of the create flow. | **Typed score badge** — keep V1 parity (float printing is fine). |

> Note: deferring view surfaces, read-only-detail/clone, and score badges means this project
> does **not** fully close the evals_v2 spec — those remain open, tracked for follow-up projects.

## Built artifacts under review (Phase 6 of evals_v2)

| Area | Path (under `app/web_ui/src/`, except backend) |
|---|---|
| Create container (page) | `routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/+page.svelte` (~748) |
| Type registry | `lib/utils/eval_types/registry.ts` |
| Per-type create forms | `lib/components/eval_types/{llm_judge,code_eval,exact_match,pattern_match,contains,set_check,tool_call_check,step_count_check}_form.svelte` |
| Code editor | `lib/components/code_editor.svelte` + `lib/components/eval_types/code_eval_helpers.ts` |
| Backend | `app/desktop/studio_server/eval_api.py` (`create_eval_config`, `test_v2_eval`); `libs/core/kiln_ai/adapters/eval/{v2_eval_llm_judge,base_eval}.py`; `libs/core/kiln_ai/datamodel/eval.py` |

**Verified correct — keep:** the `test_v2_eval` endpoint + V2 adapter/registry dispatch;
CodeMirror lazy-load + trust gate; existence of all 8 create forms; the deterministic V2
adapters. Mostly frontend, **with a focused backend addition** for V2 `llm_judge` baking (§2).

---

## 1. Navigation architecture — split into routes (structural)

**Current.** In-page state machine: `create_eval_config/+page.svelte:153` holds
`selected_v2_type`; template switches picker↔form on `{#if !selected_v2_type}` (`:477`/`:509`);
`select_v2_type` (`:158`) only mutates local state; an on-screen Back button (`:519-526`) resets
it. Browser Back leaves the page; refresh loses the selection; not deep-linkable. Ignores
`70 §1` ("push history / update URL the SvelteKit-official way").

**Target & delta — DECIDED (owner-confirmed): split into routes.** Two route files + shared
layout/container; native back stack via the SvelteKit history API; no in-page back stack, no
on-screen Back button. Full structure in `architecture.md §1`. **Severity: HIGH.**

---

## 2. Manual `llm_judge` emits V2 — ship-blocker (NEW finding)

**Current — the manual judge path still writes V1.** `do_save()` llm branch
(`+page.svelte:346-353`) sets `config_type = getConfigType()` → `"g_eval"`/`"llm_as_judge"`
(V1) with V1 properties `{eval_steps, task_description}` from `llm_judge_form.svelte`. The
enhanced V2 `llm_judge` is never produced from the UI. (Existing V1 configs still load/run via
the legacy adapter — coexistence unaffected.)

**Target (`components/21`).** Manual create produces a V2 `llm_judge`: `config_type="v2"`,
`LlmJudgeProperties` (`§1`) with a Jinja `prompt_template`, `g_eval: bool`, `model_name`/
`model_provider` on the properties, `system_prompt`/`thinking_instruction` defaults written at
creation (`§6.2`/`§7.1`). `§1.2`: V2 has **no** `eval_steps`/`task_description` field — criteria
live in the Eval's `output_scores` (defined upstream, `70 §1` altitude).

**Delta.**
- **Reuse `llm_judge_form.svelte`; remove the vestigial V1 criteria/steps authoring** (the
  Advanced `task_description`+`eval_steps` section). Keep the model picker + the algorithm
  selector (→ `g_eval` bool; already an explicit no-default pick).
- **Backend bakes `LlmJudgeProperties`** (matches `K.1`; keeps one canonical Python template +
  scale wording shared with `build_score_schema`). Frontend sends `{ model_name, provider,
  g_eval }`. The baked `prompt_template` is the **owner-approved static template** (presents
  `<task_input>`/`<model_response>` with injection guarding; bakes each `output_score` as a
  criterion line using the schema's scale wording). Construction detail: `architecture.md §2`.
- `system_prompt`/`thinking_instruction`/`required_var` written **explicitly at creation** (no
  reliance on the adapter's runtime `props.system_prompt or _DEFAULT` fallback,
  `v2_eval_llm_judge.py:118`).

**Severity: HIGH (ship-blocker).** Backward-compat: existing V1 configs unchanged; manual
create now only produces V2 (the V1 create path is retired from the UI).

---

## 3. Test Run dataset-item harness (`70 §1`/`§2`)

| # | Current | Target | Delta | Sev |
|---|---|---|---|---|
| 3.1 | Four free-text inputs (`test_final_message`, `test_task_input`, `test_trace`, `test_reference_data` — `+page.svelte:187-190,567-622`) in a `<Collapse>` below the form (`:562`). | "Test Run → **lists recent dataset items to pick from. Manual free-text input is cut.** Reference via an **Advanced expander**; the **trace comes from the selected item**." Right-pane, left=form. | Replace inputs with a **recent-`TaskRun` picker** (the entity with output+trace); map → `EvalTaskInput`; Advanced reference_data; right-pane layout. | **HIGH** |
| 3.2 | Test pane gated `can_submit_v2 = type && !is_llm_judge` (`:205-206`) — never shown for judges. | Harness runs uniformly for every V2 type. | After §2, **include `llm_judge`** in the harness. | MED |
| 3.3 | `test_has_run` set regardless of returned shape. | "a successful test run (**valid shape** vs `output_scores`) enables Save." | Gate Save on **shape-valid** run, not merely "ran." | MED |
| 3.4 | No empty-dataset handling. | "**Run your task to generate sample inputs**" → Save-Without-Testing only. | Add empty-dataset state. | MED |
| 3.5 | Spinner + Cancel present (`:636-651`); trust gate present. | `§2` async UX + trust gate. | **Keep.** | — |

Backend `test_v2_eval` is reused. For `llm_judge`, the test request carries the same minimal
`{model, provider, g_eval}` and the **backend bakes** the template before running (shared with
§2 create) so the harness works pre-save (`architecture.md §3`).

---

## 4. Deterministic forms + type picker (`70 §3`, `§1`)

| # | Current | Target | Delta | Sev |
|---|---|---|---|---|
| 4.1 | `set_check_form.svelte:7` defaults `mode:"equal"`; backend `SetCheckProperties.mode` defaults `"subset"` (`eval.py`). Silent wrong-behavior. | Explicit, no silent default. | **Double-robustness:** make `mode` **required** on the properties model (drop the default); UI always sends an explicit value; **audit** other V2 mode-style enums for the same trap. | **MED** |
| 4.2 | Value-expression help says **"JSONPath"** (`exact_match_form.svelte:70`, etc.); engine is **Jinja2**. | `§3.2` Jinja2 wording + help. | Fix wording across forms; add help text/icon. | MED |
| 4.3 | No on-blur validation. | `§3.1`/`§3.2` validate on blur. | Regex compile, min≤max, XOR — on blur. | MED |
| 4.4 | `tool_call_check`: `on_unexpected_tools` always shown; `expected_args` always shown (`tool_call_check_form.svelte:98-108`). | `§3.1`: hide `on_unexpected_tools` on "Never"; collapse `expected_args` by default. | Conditional visibility + collapse. | MED |
| 4.5 | Picker order: deterministic first, llm_judge 7th, label "LLM Judge"; no history push (`registry.ts:39-48,140`). | `§1`: "LLM as Judge (recommended)" first; Back returns to picker. | Reorder + "(recommended)"; history handled by §1 route split. | LOW |
| 4.6 | XOR source = `<select>` (exact_match/contains/set_check); `set_check.expected_set` = textarea. | `§3.1`: radio group (disable inactive); tag-input. | Convert controls. | LOW |

---

## 5. Out of scope (deferred to other projects)

- **View/run-result/comparison surfaces:** fail-loud unknown-type binding at the view layer,
  per-type result renderers, `eval_config_instruction` for non-LLM, typed score badges. *(Score
  display stays V1 float-parity — owner decision.)*
- **Read-only config-detail + clone/prefill** (`70 §4.3`, E.17).
- **Copilot / eval-builder / questionnaire** emitting V2.
- Anything `70` marks out of scope (onboarding, SDG, right-sizing).

## 6. Decisions (owner-confirmed)

- **Q1 Nav → split into routes** (two route files + shared container). `architecture.md §1`.
- **Q2 Scope → manual create flow only**, fully + phased; LOW polish is a droppable final phase.
  View surfaces / read-only-detail / clone deferred to separate projects.
- **Q3 Recent drift → keep newer** (dynamic code-eval examples + trust/save copy). No restore.
- **`llm_judge` template → backend-baked static template** (owner-approved), no criteria/steps
  authoring; criteria = `output_scores`. Scale wording reused from `build_score_schema`.
- **Score rendering → keep V1 parity** (float printing); no score-badge component.
- **No silent API defaults** for meaningful-choice fields (e.g. `set_check.mode` required); UI
  never sends `null` to trigger a default.
