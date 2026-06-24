---
status: complete
---

# Architecture: Evals V2 — Create-Flow UI Polish

**Nature of the work:** frontend-only (Svelte 4 / Tailwind / DaisyUI), broad-but-shallow. Most
changes are edits to existing components in the create-eval flow, plus a small set of new
**presentational** components and a few additive fields on the eval-type **registry** (the data
spine). No backend changes; the save/test API contract is unchanged.

**Single-doc decision:** this is organized as one architecture doc (no `components/` sub-docs).
Each unit of work is contained; the functional spec + `design_specs/` already carry per-screen
detail.

Primitives reused (verified this round):
- Two-column shell like `/run`: `flex flex-col xl:flex-row gap-8 xl:gap-16`, fixed side column
  `w-96 flex-none`, column headings `text-xl font-bold` (`routes/(app)/run/+page.svelte:213`,
  `run.svelte:907-909`).
- `warning.svelte` — `large_icon` + `warning_color="warning"` ⇒ large yellow icon, **no**
  background box.
- `property_list.svelte` — `UiProperty.action` renders the value as a link button (the
  "Reference Data: None" control).
- `form_element.svelte` `inputType="header_only"` + `inline_action` + `info_description` — the
  standard form-section header with right-aligned action + tooltip (the "Score Function" header).
- `dialog.svelte` — `width="wide"`, `action_buttons` (isPrimary/isWarning/isCancel). **Note:**
  it hides slot+buttons and shows only a spinner while an `asyncAction` is pending — never give
  it a long-running `asyncAction` (root of the trust-modal bug).
- `info_tooltip.svelte`, `collapse.svelte`, `intro.svelte`, `FancySelect`, tag-input (from prior
  phase), CodeEditor.

---

## 1. Registry as the data spine

**File:** `lib/utils/eval_types/registry.ts` (+ `registry.test.ts`).

Extend `V2EvalTypeMetadata` with additive fields so the select screen, page header, and form
intro are all data-driven (no per-screen hardcoding):

```ts
interface V2EvalTypeMetadata {
  label: string            // clean card name, e.g. "LLM as Judge", "Code", "Exact Match"
  description: string      // select-screen one-liner (functional spec §1 table)
  icon: string
  requiresTrust: boolean
  recommended?: boolean    // NEW — true for llm_judge (drives hero + ★ chip)
  tags: EvalTypeTag[]      // NEW — [{label, tone}] ; tone: "default" | "beta"
  pageTitle: string        // NEW — e.g. "Add an LLM Judge"  (functional spec §2)
  pageSubtitle: string     // NEW — e.g. "Grade outputs with a model and rubric."
  explainer?: string       // NEW — longer "what it does" for the in-form intro (§3)
  example?: string         // NEW (optional) — short concrete example for the intro
  createFormComponent: ComponentType
  resultRendererComponent: ComponentType
}
type EvalTypeTag = { label: string; tone: "default" | "beta" }
```

- Drop the qualifier suffixes currently baked into labels (`"… (recommended)"`,
  `"Pattern Match (regex)"`) — qualifiers now live in `recommended`/`tags`.
- Content values are locked in functional spec §1 (cards/descriptions/tags) and §2 (titles).
- `registry.test.ts`: assert every type has non-empty `pageTitle`/`pageSubtitle`/`tags`, exactly
  one `recommended`, and that `recommended` type is `ALL_V2_EVAL_TYPES[0]`.

---

## 2. Select Eval Type screen

**File:** `create_eval_config/+page.svelte`. New components under
`lib/components/eval_types/select/`.

- Page header (`AppPage`): `title="Add a Judge"`, the new subtitle, no `sub_subtitle`/docs link,
  drop the secondary "Select Eval Type" heading.
- New `eval_type_hero.svelte` — props: `metadata`, `on:continue`. Heavier card (stronger border +
  soft `bg-base-200`-ish fill), Kiln-styled: icon → (name + `★ Recommended` chip + description +
  `EvalTypeTags`) → right-aligned **Continue** `btn-primary`.
- New `eval_type_row.svelte` — props: `metadata`, `on:select`. Lighter row: small icon → (name +
  inline `EvalTypeTags`) → description → right chevron (`bi bi-chevron-right`). Whole row is a
  `<button>`.
- New `eval_type_tags.svelte` — renders `metadata.tags` as DaisyUI badges; `beta` tone =
  `badge-primary badge-outline` (matches existing code-eval Beta badge), default = neutral
  `badge-outline`.
- Data flow: `hero = getV2EvalTypeMetadata(ALL_V2_EVAL_TYPES[0])`; list = the rest. Reuse
  existing `select_v2_type()` for navigation (preserves `next_page`/`save_as_default`).

---

## 3. Create container shell + per-page titles + in-form intro

**Files:** `create_eval_config/[eval_config_type]/+page.svelte`, `eval_config_builder.svelte`,
new `lib/components/eval_types/eval_type_intro.svelte`.

- **Route header:** set `AppPage title={meta.pageTitle}` / `subtitle={meta.pageSubtitle}`, drop
  the generic title + "Read the Docs" sub_subtitle (docs handled in §9-B2).
- **Two-column shell** in the builder: replace the current `flex lg:flex-row gap-6` +
  `lg:w-[400px]` + the outlined box with the `/run` pattern:
  `flex flex-col xl:flex-row gap-8 xl:gap-16`; left = form (`flex-1 min-w-0`); right = Test Run
  pane (`w-96 flex-none`, no border box). Column headings use `text-xl font-bold`.
- **Remove** the secondary-title block (`eval_config_builder.svelte:407-412`) — fixes the indent
  globally.
- **`eval_type_intro.svelte`** — props: `metadata`. Renders at the top of the left column for
  every type: icon + `label` + `explainer` (fallback `description`) + optional `example`. Plain,
  low-key styling (not a warning box). This is the shared "what" section.

---

## 4. Trust Code modal + dismiss-on-trust + main-pane running

**File:** `eval_config_builder.svelte` (the trust `Dialog` + `grant_trust_and_retry` /
`run_test` / `do_save`).

- **Markup:** replace the `alert alert-warning` slot with: a large warning icon (use
  `warning.svelte` with `large_icon warning_color="warning" warning_icon="exclaim"`, or the same
  SVG) beside/above text; then `<p>` line 1 and a **bold** `<p>` line 2 (functional spec §4
  copy). No yellow background.
- **Buttons:** `[{label:"Cancel", isCancel:true}, {label:"Run — I Trust This Code", isPrimary
  (or isWarning), asyncAction: grant_trust}]`.
- **Flow fix (the empty-modal bug):** `grant_trust` does `await grantCodeEvalTrust(project_id)`
  then **kicks off the pending action without awaiting it** and returns `true` so the dialog
  closes immediately:
  ```
  async function grant_trust() {
    await grantCodeEvalTrust(project_id)          // fast
    const action = pending_trust_action; pending_trust_action = null
    if (action === "test") run_test()             // NOT awaited
    else if (action === "save") do_save()         // NOT awaited
    return true                                    // close dialog now
  }
  ```
  `run_test()` sets `test_loading=true` synchronously → the Test Run pane shows the **Running**
  state (§5 State 3) on the page. `do_save()` sets `create_evaluator_loading=true` synchronously
  → Save button spinner on the page. Grant failure: catch → set page error, return `false`
  (keeps modal open with error) — or surface on page; either is acceptable, no stuck spinner.

---

## 5. Test Run pane (extracted, state-machine)

Extract the right column into a presentational component; keep test/save/trust **orchestration**
in the builder (so trust gating stays centralized).

**New files (`lib/components/eval_types/test_run/`):**
- `eval_test_run_pane.svelte` — the pane frame + state switch. Props (from builder):
  `runs_loading`, `runs_error`, `available_runs`, `selected_run`, `reference_data`,
  `test_loading`, `test_result`, `test_error`, `test_shape_warning`, `test_has_valid_run`.
  Events: `select` (run), `run`, `cancel`, `change` (→ open browse), `saveWithoutTesting`,
  `editReferenceData`, `runAgain`, `save`. The builder wires these to its existing functions.
- `test_run_input_card.svelte` — the compact run preview used for BOTH the prominent "Selected
  Run" card and the 2 quick-pick rows. Shows truncated **2-line Input + 2-line Output**; full
  strings via tooltip / `SeeAllDialog` (reuse `formatExpandedContent` + `ClampedText`). Variants:
  `selected` (prominent, Change affordance) vs `pick` (compact, click-to-select).
- `test_run_browse_dialog.svelte` — `width="wide"` Dialog. Restyled `TaskRunPicker` table
  (Input · Output · Created), pagination kept, **no search**. First row preselected. "Add manual
  example" button → opens `manual_example_dialog`. Footer: count caption + Cancel / **Use input**.
- `manual_example_dialog.svelte` — two textareas (Input, Output). On confirm builds an
  **ephemeral** synthetic run `{ input, output: { output } }` (no `trace`) and selects it. Guards
  against both-empty.
- `reference_data_field.svelte` — `property_list`-style row "Reference Data" with value "None"
  (or a short JSON summary) and `action` → opens a Dialog with a JSON editor (standard form look).
  On save: `JSON.parse` validate; store into `reference_data`; inline error on bad JSON.

**State machine (driven by builder props):**
1. `runs_loading` → spinner. `runs_error` → inline error.
2. **Empty** (`available_runs.length === 0`): educational empty state (icon, "No sample inputs
   yet", "Go to Run"); footer **Save Without Testing** → `confirm_save_dialog`.
3. **Ready**: `Selected Run` card (auto-selected = `available_runs[0]`) + up to **2** quick-pick
   rows (next runs, excluding selected) + "Browse all dataset inputs" link → browse dialog +
   `reference_data_field` + primary **Run**; results placeholder.
4. **Running** (`test_loading`): centered spinner + "Running…" + caption; selected input shown,
   Change locked; **Cancel**.
5. **Results** (`test_result`): scores header (`Scores` + italic `preview · not saved`); score
   rows V1-parity floats; skipped dim + reason; existing `test_shape_warning`. Footer: **Run
   again** + primary **Save** (enabled when `test_has_valid_run`).

**Builder state changes:** initialize selection after `load_task_runs()` →
`selected_task_run = available_runs[0] ?? null`. `reference_data` replaces the
`advanced_reference_data` collapse (same downstream parse in `build_eval_input`). Quick-pick
list = `available_runs.filter(r => r !== selected).slice(0,2)`.

---

## 6. LLM as Judge form (card sizing)

**File:** `llm_judge_form.svelte`. Visual-only:
- Recommended-model cards `w-[200px] aspect-[5/6]` → ~`w-[120px]` (≈40% smaller), image
  `w-10 h-10` → `w-6 h-6`, padding/gap reduced. Algorithm cards `w-[260px] aspect-[5/6]` →
  ~`w-[156px]`, radio/spacing tightened. Keep behavior (suggested-model selection, Browse-all,
  algorithm radios, logprob gating). Internal headings aligned to app heading style.

---

## 7. Deterministic forms — shared patterns + per-form redesign

**New shared components (`lib/components/eval_types/form_parts/`):**
- `form_section.svelte` — a titled section: bold section title + optional subtitle/tooltip +
  slot. Used to add "Expected Value" / "Output Value to Compare" etc. section structure.
- `disclosure_radio_group.svelte` — Kiln-styled radio **group** (not nested-input radios):
  options each with label + description; `bind:value`; reveals the active branch via a slot keyed
  by value (or the parent conditionally renders the follow-up). Replaces the broken nested-radio
  pattern. Inactive branch hidden (preferred) or cleanly disabled.
- `output_value_field.svelte` — the shared `value_expression` control: label **"Output Value to
  Compare"**, the §8 subtitle, Jinja `info_description`. Reused by exact_match / pattern_match /
  contains / set_check.

**Per-form edits** (each: prepend `eval_type_intro` via the container, then restructure):
- `exact_match_form.svelte` — sections "Expected Value" (disclosure: Fixed value | Reference
  data → relevant input) + "Output Value to Compare" (`output_value_field` + Case sensitive).
- `pattern_match_form.svelte` — Pattern (regex, tooltip + example, on-blur validity) + Match mode
  (must match | must not match) + `output_value_field`.
- `contains_form.svelte` — Expected substring (disclosure: fixed | reference) + Match mode +
  case sensitive + `output_value_field`.
- `set_check_form.svelte` — Expected set (disclosure: fixed tag-input | reference) + Comparison
  mode (subset/superset/equal, plain descriptions) + `output_value_field`.
- `tool_call_check_form.svelte` — Expected tools list + Match mode (any/all/ordered/never) +
  `on_unexpected_tools` (hidden on "never", per prior phase) — restructured with `form_section`,
  better labels/tooltips. Intro notes it reads the trace.
- `step_count_check_form.svelte` — What to count (tool_calls/model_responses/turns, plain
  descriptions) + Bounds (min/max, ≥1 required, min≤max on-blur). Intro notes it reads the trace.

Forms keep their `getProperties()` / `validate()` API (the `EvalTypeFormApi` contract) so the
builder + tests are unaffected.

---

## 8. Bugs

- **B1 — stuck Save spinner.** In `eval_config_builder.handle_submit`, when deferring to a dialog
  (`confirm_save_dialog` or `trust_dialog`), set `create_evaluator_loading = false` before
  `…show()` and `return`. `do_save()` re-sets it true when the user actually proceeds. (Root
  cause: `form_container.validate_and_submit` sets `submitting=true` via the two-way `bind`, only
  `do_save`'s `finally` clears it.) Add a regression test using `form_container_stub`/`dialog_stub`.
- **B2 — docs links.** Remove `sub_subtitle`/`sub_subtitle_link` from the two create-flow pages
  (replaced by per-page subtitles). Audit `[eval_id]/+page.svelte:620-637` `docs_link()` anchors;
  keep a link only if live + topic-salient. Attempt liveness verification during implementation
  (WebFetch; network may be restricted) — otherwise apply salience judgment and drop
  dead/irrelevant links. Do not introduce new unverified links.

---

## 9. State & data flow summary (builder ↔ pane)

The builder remains the single orchestrator:
- Owns: `available_runs`, `selected_task_run`, `reference_data`, `test_*` state, `create_*`
  state, trust/confirm dialogs, `run_test`/`do_save`/`grant_trust`.
- Passes state down to `eval_test_run_pane` as props; receives intent via events.
- Left form ref (`v2FormComponent`/`llmJudgeFormComponent`) unchanged — `run_test`/`do_save`
  still pull `getProperties()`/`validate()` from it.
- Trust gating unchanged in logic, only the dialog dismiss/await behavior changes (§4).

---

## 10. Error handling

- Bad reference-data JSON → inline error in the reference-data modal; run not started.
- Manual example both-empty → confirm disabled.
- Trust grant failure → page/modal error, no stuck spinner/modal.
- Run cancel → AbortController abort → back to Ready (selection kept).
- Score-shape mismatch → warning, Save gated (unchanged).
- Unknown type URL → existing error page.

---

## 11. Testing strategy

Svelte component tests via the existing `__tests__` stubs (`app_page_stub`, `dialog_stub`,
`form_container_stub`, `task_run_picker_stub`, `llm_judge_form_stub`, `collapse_stub`,
`v2_form_stub`) + Vitest. Targets:
- `registry.test.ts` — new fields/invariants (§1).
- Select screen — hero renders recommended; list renders the rest; click → `goto` with preserved
  query; tags render with correct tone.
- Builder — per-type `pageTitle`/`pageSubtitle`; secondary-title block gone; two-column shell.
- Trust flow — trust button closes modal immediately and triggers run/save; pane enters Running;
  grant-failure path.
- B1 — cancel "Save Without Testing?" / trust dialog leaves Save clickable (not spinning).
- Test Run pane — each state; auto-select first; quick-pick → select; browse dialog select →
  selected; manual example → ephemeral run; reference-data modal valid/invalid JSON.
- Deterministic forms — `disclosure_radio_group` reveals correct branch; `output_value_field`
  relabel; per-form `validate()` still correct; existing on-blur validations preserved.
- Keep `npm run check`, `lint`, `format_check`, `test_run`, `build`, and the OpenAPI schema check
  green (no schema change expected — frontend only).

---

## 12. Sequencing (feeds the implementation plan)

1. Registry fields + content (unblocks everything).
2. Select screen (hero/list/tags).
3. Container: titles, two-column shell, remove secondary title, `eval_type_intro`.
4. Trust modal copy/icon + dismiss-on-trust + main-pane running; B1 spinner fix (same file).
5. Test Run pane extraction + states + browse/manual/reference-data modals.
6. Code Judge form header (header_only + inline_action) + footer removal.
7. LLM card sizing.
8. Deterministic forms: shared `form_parts` + per-form redesign (largest).
9. Docs-link audit (B2) + final polish pass.

Steps 4 and 8 are the riskiest; 1–3 are low-risk and unblock the rest.
