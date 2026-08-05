---
status: complete
---

# Functional Spec: Evals V2 — Create-Flow UI Polish

Scope: the **manual create-eval flow** — the eval-type select screen, the shared create
container (two-column shell + titles), the per-type forms (Code, LLM, and the six
deterministic types), the Test Run pane, the Trust Code modal, and a set of bugs. This is a
**UI/UX polish** project on top of the now-complete `evals_v2_ui_fix` remediation; behavior
of the underlying eval engine and the save contract is unchanged.

Source-of-truth notes (verified against backend in this round):

- Eval-type registry & order: `app/web_ui/src/lib/utils/eval_types/registry.ts`
  (`ALL_V2_EVAL_TYPES` is already recommended-first).
- Backend behavior per type: `libs/core/kiln_ai/datamodel/eval.py:67-238` +
  `libs/core/kiln_ai/adapters/eval/v2_eval_*.py`. The six deterministic types emit **binary
  0/1 scores only**; only `llm_judge` and `code_eval` produce the full score range.
- `value_expression` (the field we relabel "Output Value to Compare") exists on
  **exact_match, pattern_match, contains, set_check** — so that relabel + Jinja tooltip is a
  shared deterministic pattern.

Design inputs (wireframes — layout guidance only, not visual/string truth):
`design_specs/select_screen.md`, `design_specs/test_run_sidebar.md`.

---

## 0. Cross-cutting decisions

- **D1 — Titles (type-appropriate).** Each per-type page gets its own title + subtitle from
  the registry. "Judge" for LLM/Code; "Check"/"Eval" for deterministic. The generic
  "Add a Judge" + secondary `metadata.label` block is removed. (See §2.)
- **D2 — Polish depth: all forms, full redesign.** All six deterministic forms get the full
  treatment (top "what" section, section titles, progressive disclosure replacing nested
  radios, relabeled fields + tooltips). Exact Match is the worked example; the same pattern
  applies to the other five. (See §8.)
- **D3 — Adopt select-screen tags.** Per-type tag chips, Kiln-styled badges, `beta` tone
  distinct. (See §1.)
- **D4 — Design-bot caveat (project-wide).** Use the wireframes' **layout/structure**; do
  **visual design in Kiln style**; **code is source of truth** for behavior/strings. Resolve
  every wireframe-vs-code conflict explicitly (recorded inline + in §10).

---

## 1. Select Eval Type screen

**File:** `create_eval_config/+page.svelte`. **Design:** `design_specs/select_screen.md`
(Option A: recommended-first list).

### Current state
A flex-wrap grid of identical `card`s (one per type), each icon + label + short description.
Title "Add a Judge" / subtitle "A judge evaluates…" / "Read the Docs" link, plus a secondary
"Select Eval Type" heading.

### Target
A **recommended hero row** + an **"All judge types" list**, both derived from the single
`ALL_V2_EVAL_TYPES` array (hero = first item `llm_judge`; list = the rest). Kiln-styled.

- **Page header:** title **"Add a Judge"**; subtitle **"Select a judge type — every type
  produces the same scores, it just changes how they're computed."** Breadcrumbs unchanged.
  Drop the secondary "Select Eval Type" heading and the generic "Read the Docs" sub-subtitle.
- **Hero row (recommended):** heavier card (stronger border / soft fill). Layout: type icon →
  body (name **LLM as Judge** + `★ Recommended` chip; description; tag chips) → right-aligned
  **Continue** primary button. Clicking Continue selects `llm_judge` and advances.
- **"All judge types" list:** section label, then one row per remaining type (#2–#8). Each
  row: small icon → name (semibold, no-wrap) with inline tag chips → description beneath →
  right chevron. The whole row is the affordance (no per-row button). Lighter weight than the
  hero. Clicking advances to that type.
- **Navigation:** reuse existing `select_v2_type()` (`goto` to `…/[type]` with preserved
  `next_page` / `save_as_default` query string).

### Content (locked — design strings, Kiln-verified)
| Type | Card name | Description | Tags | Flags |
|---|---|---|---|---|
| llm_judge | LLM as Judge | Grade output against criteria you write — quality, accuracy, or rubric pass/fail. | `Uses LLM`, `Graded` | recommended |
| code_eval | Code | Write a custom Python scorer for anything the built-in types can't express. | `Python`, `Beta` | beta tone |
| exact_match | Exact Match | Output exactly equals an expected value (or a reference-data value). | `Deterministic` | — |
| pattern_match | Pattern Match | Output matches (or doesn't match) a regular expression. | `Deterministic` | — |
| contains | Contains | Output contains (or doesn't contain) a substring or reference value. | `Deterministic` | — |
| set_check | Set Check | Compare a set of values from the output against an expected set. | `Deterministic` | — |
| tool_call_check | Tool Call Check | Check the agent called the right tools, in the right order, with the right arguments. | `Agent`, `Reads trace` | — |
| step_count_check | Step Count Check | Count steps in the trace and check they're within bounds. | `Agent`, `Reads trace` | — |

Registry additions to support this: `recommended: boolean`, `tags: {label, tone}[]`, and the
clean `label` values above (drop the "(recommended)" / "(regex)" suffixes baked into labels
today). `description` updated to the table.

---

## 2. Per-page titles & removing the secondary title

**Files:** `create_eval_config/[eval_config_type]/+page.svelte` (page header),
`eval_config_builder.svelte:407-412` (secondary title block).

### Target
- The builder route sets the `AppPage` **title + subtitle per type** (from new registry
  fields `pageTitle` / `pageSubtitle`), replacing the generic "Add a Judge" + "Read the Docs".
- **Remove** the in-form secondary-title block (`<i> + {metadata.label}`) entirely — this is
  the "Code: Custom Python Code Eval" weirdly-indented heading. Removing the block fixes the
  indent regardless of type. The "what" the type does now lives in the §3 intro section.

### Locked per-type titles / subtitles
| Type | Title | Subtitle |
|---|---|---|
| llm_judge | Add an LLM Judge | Grade outputs with a model and rubric. |
| code_eval | Add a Code Judge | Write a Python function that scores model outputs. |
| exact_match | Add an Exact Match Check | Pass when the output equals an expected value. |
| pattern_match | Add a Pattern Match Check | Pass when the output matches a regular expression. |
| contains | Add a Contains Check | Pass when the output contains (or omits) a substring. |
| set_check | Add a Set Check | Compare a set of values from the output against an expected set. |
| tool_call_check | Add a Tool Call Check | Check the agent called the right tools, order, and arguments. |
| step_count_check | Add a Step Count Check | Check the number of steps in the trace is within bounds. |

---

## 3. Shared create container

**File:** `eval_config_builder.svelte` (left/right two-column shell).

### Target
- **Two-column layout matching the `/run` page** (left = form, right = Test Run pane). Use the
  app's standard column/section treatment; **column titles use the app's standard heading
  font/weight** (consistent with the rest of the app, not the ad-hoc `font-medium text-sm`).
  Reference the `/run` page for exact structure.
- **Shared "what" intro section** at the top of the left column for every type: icon + type
  name + the type's plain-language explanation, and (where it helps) a concise example. This
  is the "Missing context" fix — the explanation that was only on the select screen now also
  appears on the form page. Driven by registry data (description + optional longer
  `explainer` / `example`). Replaces the removed secondary title (§2).
- **Running state on the main page.** Today the only "running" feedback is a small inline
  spinner on the Run button; the Trust modal masks it. The container/Test-Run pane must own a
  prominent **Running** state (§6 State 3) so that after the Trust modal dismisses, the user
  sees the run progressing on the page.

---

## 4. Trust Code modal

**File:** `eval_config_builder.svelte:606-630` (the `Dialog`), `do_save` / `run_test` /
`grant_trust_and_retry` flow.

### Current state
Title "Allow Code Execution"; a yellow `alert alert-warning` box; buttons "Cancel" /
"I Understand, Allow Execution". On trust, `grant_trust_and_retry` is the dialog's
`asyncAction` and `await`s the full eval run, so `dialog.svelte` shows only a spinner
(slot/buttons hidden, lines 152-155) → "ugly empty modal".

### Target — copy & design
- **Title:** "Trust Code and Project?"
- **Body line 1:** "This project wants to run Python code on your machine. Only proceed if you
  trust the eval code and this project."
- **Body line 2 (bold):** "**Never paste code from a stranger or the internet.**"
- **Design:** remove the yellow alert box. Use Kiln's **large warning icon** (e.g.
  `warning.svelte`'s icon treatment) beside/above the text; plain background under the text.
- **Buttons:** primary **"Run — I Trust This Code"** and **"Cancel"**.

### Target — behavior (fix the empty-modal bug)
- On "Run — I Trust This Code": grant trust, **close the modal immediately**, then start the
  run on the main pane. The button's action must **not** `await` the eval run (so
  `dialog.svelte` never enters its long spinner state). The pending action (`test` vs `save`)
  still drives whether we run the test or proceed to save after trust is granted.
- While the run executes, the **Test Run pane shows the Running state** (§6 State 3); the page
  is interactive (Cancel available).
- Trust-grant failure surfaces as an error on the page (not a stuck modal).

---

## 5. Code Judge form

**File:** `code_eval_form.svelte`.

### Target
- **"Score Function" → standard form header** (header-only `FormElement` / form section
  header, used when the content below is custom — here the CodeMirror editor):
  - **Title:** "Score Function"
  - **Subtitle:** "Define a Python score function to evaluate the model's work."
  - **Tooltip (info icon):** "The Python function can use the model's output, trace, and
    eval's reference data to drive pragmatic scoring. Faster and cheaper than LLM as a judge."
  - **Right-aligned action:** rename "See examples" → **"More Examples"**, kept on the right
    of the title. (May require adding an action-slot/`inline_action` to the header treatment.)
- **Remove the footer paragraph** ("Define a `score(output, trace, …)` … five-star uses
  1.0–5.0.") at `code_eval_form.svelte:96-103` — the subtitle + the example snippets cover it.
- The standalone "Beta" badge + duplicate one-liner at the top (`code_eval_form.svelte:66-74`)
  is superseded by the §3 intro + the form header; consolidate so the page isn't redundant.
- Examples modal: keep (wide modal, tabbed, real score keys); just retitle the trigger to
  "More Examples". Timeout field unchanged.

---

## 6. Test Run pane (redesign)

**File:** `eval_config_builder.svelte:437-602` (right column).
**Design:** `design_specs/test_run_sidebar.md` (5 states + picker modal).

### Current state
A bordered/outlined box (`rounded-lg border bg-base-100 p-4`) — "not our style". Selection via
the full `TaskRunPicker` table inline; selected run shows input+output; reference data in an
Advanced collapse textarea; small inline Run spinner; scores in an `alert-success` block.

### Target — frame
- Drop the outline box; adopt the app's standard two-column section styling (per §3), with a
  **"Test Run"** column heading in the app's standard heading font.
- The pane walks the lifecycle: **empty → pick input → running → results**.

### State 1 — Empty dataset (no task runs)
- Educational empty state (per `intro.svelte` spirit): icon, "No sample inputs yet", body
  "Run your task to generate inputs in the dataset, then test against them here.", secondary
  **"Go to Run"** button.
- Footer: **"Save Without Testing"** (the only forward path) → existing "Save Without Testing?"
  confirm modal (§9 covers its bug).

### State 2 — Ready (pick input)
- **Selected run** shown prominently at top — a cleaned-up "Selected Run" card: compact, with
  **truncated 2-line Input and 2-line Output** previews; full strings in a tooltip/`see-all`.
  (Design showed input-only; per owner we show **both** input and output.)
- **+ up to 2 more quick-pick rows** (small, short, clean — truncated 2 lines input+output,
  tooltip for full). So the main pane shows **3 total** (selected + 2). The user can pick one
  of the 2 to make it the selected run.
- **"Browse all dataset inputs"** link → opens the **Browse modal** (State 5).
- **Select-first-by-default:** on load, auto-select the most recent run; **only ever one**
  selected/visible-as-selected at a time.
- Primary **Run** button. Results placeholder beneath ("Run to see scores").

### State 3 — Running
- Prominent centered **spinner** + "Running…" + caption "Executing the scorer on your input".
- Selected input shown but **Change locked** (disabled) while running.
- **Cancel** button always available (runs can be long; reuses existing AbortController).

### State 4 — Results
- Selected input at top (Change enabled). Scores header row: "Scores" + italic
  "preview · not saved".
- Score rows: name + value, **V1-parity float rendering** (no typed badge — out of scope per
  prior project). Skipped scores shown dim with reason; existing score-shape warning preserved
  (missing keys = warning) and gates Save as today (`test_has_valid_run`).
- **Score-range check (D16):** if a returned score falls outside its rating-type range (e.g. `6.0`
  for a five_star — valid 1.0–5.0; pass_fail 0.0–1.0; pass_fail_critical −1.0–1.0), the pane shows
  the scores **and** an inline error, and Save is gated (`test_has_valid_run=false`) — same
  treatment as a shape mismatch. New in this project (implementation Phase 10; backend detail in
  architecture §13). Previously the range was only enforced at persist time, so the test pane
  silently accepted out-of-range scores.
- Footer: **Run again** (default) + primary **Save**. Successful valid test enables Save.

### State 5 — Browse modal ("Browse all dataset inputs")
- **Wide** `Dialog` (`width="wide"`). Title "Choose an input", subtitle "Pick a dataset item
  to test this scorer against."
- Essentially today's `TaskRunPicker` table, **restyled to Kiln table style**, with room to
  breathe. Columns: **Input preview · Output preview · Created** (and Tags if cheaply
  available). Each row selectable; first selected by default. Pagination kept.
- **No search field** (per owner — overrides the wireframe). **Outputs included** (per owner —
  overrides the wireframe's input-only).
- **"Add manual example"** action in the modal → opens a **second modal** with two text areas
  (Input, Output). On confirm, builds an **ephemeral** `EvalTaskInput` (Input → `task_input`,
  Output → `final_message`) used as the selected run for this test only (not persisted to the
  dataset). This is the "manual/custom option" that's currently missing.
- Footer: result-count caption + Cancel / **Use input** (primary). Selecting closes the modal
  and sets the chosen item as the selected run on the main pane.

### Reference Data control
- Replace the Advanced-collapse textarea with a **"Reference Data: None"** property-row style
  control (shows "None" when empty, a short summary when set). Clicking opens a **modal** with
  a JSON editor in our **standard form look**. Stores the same `advanced_reference_data` /
  `eval_input.reference_data`. Invalid JSON surfaces inline in the modal.
- Reference data matters for types/configs that read `reference_key` (exact_match, contains,
  set_check) and for `llm_judge`/`code_eval` templates that reference it.

---

## 7. LLM as Judge form

**File:** `llm_judge_form.svelte`.

### Target
- The model cards (`w-[200px] aspect-[5/6]`, lines 156-178) and the algorithm cards
  (`w-[260px] aspect-[5/6]`, lines 217-235) are **too big** alongside the new right column.
  **Shrink ~40%** and **shrink the icons/images** (`w-10 h-10` → smaller) so the layout works
  within the narrower left column. Keep the same selection behavior (recommended models grid,
  Browse-all, algorithm radio→`g_eval`/`llm_as_judge`, logprob gating).
- Note: this form's internal "Select Judge Model" / "Select Judge Algorithm" headings should
  align to the app's standard heading style used elsewhere (§3 consistency), but the LLM
  judge's two-step model→algorithm flow is otherwise unchanged.

---

## 8. Deterministic forms — full UX redesign (all six)

**Files:** `exact_match_form.svelte`, `pattern_match_form.svelte`, `contains_form.svelte`,
`set_check_form.svelte`, `tool_call_check_form.svelte`, `step_count_check_form.svelte`.

Per D2, all six get the full treatment. Exact Match is the worked example; the same principles
apply to the rest (adapting field names to each type).

### Shared principles
1. **Top "what" section** (§3 intro) — clear explanation of the eval type, with examples where
   helpful. (e.g., what "Exact Match" does, drawn from the verified backend behavior.)
2. **Better field names** — plain, descriptive labels (see Exact Match below).
3. **Better subtitles** — each field's `description` explains it in plain language.
4. **More tooltips** (`info_description`) — explain concepts that intimidate new users (e.g.
   what Jinja is) without repeating definitions in body text for experienced users.
5. **No nested radios.** Replace nested radio-with-inputs (where toggling breaks sections) with
   **progressive disclosure**: pick the high-level choice first, then reveal only the relevant
   follow-up. Use Kiln's standard radio-group/section pattern, not inputs nested inside radio
   labels.
6. **Section titles** to structure each form, relatable to the top explanation.
7. **Consistency** with the Kiln form design guide.

### Exact Match (worked example) — file `exact_match_form.svelte`
Backend: compares an extracted value (default = full model output, or a `value_expression`
Jinja extraction) against either a fixed `expected_value` **or** a `reference_key` from
reference data; optional `case_sensitive`.

Target structure:
- **Top:** Exact Match "what" section.
- **Section "Expected Value":** progressive disclosure — first choose **"Fixed value"** vs
  **"Value from reference data"** (the literal-vs-reference XOR), then show only the relevant
  input (a value field, or a reference-key field). No nested radios; the inactive branch isn't
  shown (or is cleanly disabled).
- **Section "Output Value to Compare":** the renamed `value_expression` field:
  - **Label:** "Output Value to Compare"
  - **Subtitle:** "Leave blank to compare the entire model output, or use a Jinja expression
    like `user.email` to extract fields from JSON in the output."
  - **Tooltip:** explain what Jinja is (a templating syntax for pulling values out of
    structured output).
  - plus **Case sensitive** toggle.

### The other five (apply the same pattern)
- **Pattern Match:** "what" section; section for the regex **Pattern** (clear label + tooltip:
  what a regular expression is, with a tiny example); **Match mode** as progressive disclosure
  /clear control ("must match" vs "must not match"); shared "Output Value to Compare"
  (`value_expression`) section. On-blur regex validity check (already added in prior project —
  keep).
- **Contains:** "what" section; **Expected substring** via progressive disclosure (fixed
  substring vs reference-data value); **Match mode** (must contain vs must not contain);
  case-sensitive; shared "Output Value to Compare" section.
- **Set Check:** "what" section; **Expected set** via progressive disclosure (fixed set vs
  reference key) — fixed set uses the tag-input added previously; **Comparison mode** (subset /
  superset / equal) as a clear labeled control with plain-language descriptions; shared
  "Output Value to Compare" section.
- **Tool Call Check:** "what" section; **Expected tools** list (tool name + optional argument
  matchers); **Match mode** (any / all / ordered / never) with plain-language descriptions;
  **on_unexpected_tools** (ignore / fail) revealed appropriately (hidden on "never" per prior
  project). Reads the trace — note that in the "what" section.
- **Step Count Check:** "what" section; **What to count** (tool calls / model responses /
  turns) with plain-language descriptions; **Bounds** (min / max, at least one required,
  min ≤ max) with on-blur validation. Reads the trace — note that.

---

## 9. Misc bugs

### B1 — Save button stuck spinning after cancelling "Save Without Testing?"
**Root cause:** `form_container.validate_and_submit()` sets `submitting=true` then dispatches;
`handle_submit` opens the confirm (or trust) dialog and returns **without** resetting
`submitting`. Cancelling the dialog leaves the Save button spinning and the user stuck.
**Fix:** when `handle_submit` defers to a modal (confirm-save or trust), reset the submitting
state (`create_evaluator_loading=false`) before/at show time; `do_save` re-sets it when the
user actually proceeds. Cancelling any of these dialogs must return the form to a clean,
clickable state. Applies to both the confirm-save and trust paths.

### B2 — Docs-link audit
**Policy:** remove "Read the Docs" / `docs.kiln.tech` links in the create flow unless the link
is (1) a **real, live** URL and (2) **topically salient** to that screen.
- The generic "Read the Docs" sub-subtitle on the select screen and per-type pages is
  **replaced** by the new per-page subtitles (§1, §2) — i.e. dropped from those pages.
- Any remaining docs link (e.g. a Code Judge → code-eval docs link, if a real page exists)
  must be verified live and topic-specific before keeping.
- Known link locations to audit (file:line): `create_eval_config/+page.svelte:64-65`,
  `create_eval_config/[eval_config_type]/+page.svelte:70-71`, and the `docs_link()` helper +
  usage in `[eval_id]/+page.svelte:620-637` (anchors `#finding-the-ideal-eval-method`,
  `…/evaluate-appropriate-tool-use`). Verify liveness during implementation (network
  permitting); otherwise apply the salience judgment and remove dead/irrelevant links.

---

## 10. Design-bot conflict resolutions (recorded)

From `select_screen.md`:
- Title "Create Eval" (design) → **"Add a Judge"** (Kiln/owner). Subtitle kept (reworded).
- Section label "All eval types" → **"All judge types"** (terminology D1).
- Tags adopted (D3); `beta` tone distinct.

From `test_run_sidebar.md`:
- Wireframe "DatasetRow" / "SelectedInput" show **input only** → we show **input + output**.
- Wireframe modal has a **search field** → **no search** (owner).
- Wireframe modal is input-centric → **outputs included** (owner).
- Main pane shows selected + up to **2** more (3 total), not 4 inline rows.
- **Manual example** added in the modal (ephemeral input/output paste) — not in the wireframe.
- "recent dataset items" framing → backed by **recent `TaskRun`s** (existing Phase-3 harness),
  reusing the run picker; no separate dataset-item store.

---

## 11. Edge cases & error handling

- **No task runs:** Test Run pane shows the educational empty state; only path forward is
  "Save Without Testing" (which still routes through the confirm modal).
- **Invalid reference-data JSON:** surfaced inline in the Reference Data modal; does not crash
  the run.
- **Manual example with empty input/output:** allowed (the eval decides); but the modal should
  guard against confirming with both empty.
- **Trust denied / grant fails:** page returns to a clean state with an inline error; no stuck
  modal, no stuck spinner (ties to B1).
- **Cancel during run:** aborts via AbortController; pane returns to Ready (selected run kept).
- **Score-shape mismatch:** missing declared scores = warning (does not block, but Save stays
  gated behind a valid test or explicit "Save Without Testing"); behavior preserved from prior
  project.
- **Unknown eval type in URL:** existing "Unknown Eval Type" page preserved.

---

## 12. Out of scope

- The eval engine and save/round-trip contract (done in `evals_v2_ui_fix`), **except** the D16
  score-range validation appended as Phase 10 (a small reuse of the existing persist-time range
  check in the test endpoint). V2 `llm_judge` baking is out of scope.
- Typed score badges / fail-loud view binding (explicitly deferred by the prior project).
- View / run-result / comparison surfaces; copilot / eval-builder / questionnaire flows.
- Persisting manual examples to the dataset (manual examples are ephemeral, test-only).
- Backend changes (this is frontend-only, barring trivial registry/string support **and the
  Phase 10 / D16 score-range validation**).

---

## 13. Decisions log

- **D1** Titles: type-appropriate (Judge for LLM/Code, Check for deterministic).
- **D2** Polish depth: all six deterministic forms, full redesign.
- **D3** Select-screen tags: adopt.
- **D4** Design-bot wireframes are layout-only; Kiln visual + code-truth strings.
- Test pane: selected + 2 quick-picks + Browse modal; no search; input+output; manual example
  ephemeral; reference data via modal editor.
- Trust modal: new copy/icon; dismiss-on-trust; run on main pane.
- Bugs: reset submitting on modal-defer (B1); docs-link audit + drop generic "Read the Docs"
  (B2).
- **D16** Test-pane score-range validation appended as Phase 10 — the project's one backend change:
  extract the per-type range check from `EvalRun.validate_scores` into a shared validator, reuse it
  in `test_v2_eval`, and gate Save on out-of-range scores. Moved here from the evals_v2 cleanup
  project because all the create-flow UI it surfaces through lives in this project.
