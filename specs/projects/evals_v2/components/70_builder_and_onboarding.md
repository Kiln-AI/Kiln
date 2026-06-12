---
status: complete
approved: true
alignment_refs: [A0.2, G.1, G.2, G.3, C.9, E.17, A2.4, A2.11, C.11b, B.13, K.1, K.2, K.3, K.4, K.5]
opens: []
summary: V2 eval-type create + view UI — pluggable per-type create container, code-eval editor, renderer registry. (Goal-first questionnaire deferred out of V2.)
---

# Builder & Onboarding — V2 eval-type create + view UI

## Scope

Evals V2's UI deliverable is **minimal-but-complete UI to create the new eval types and view them in the existing surfaces** — nothing more. It is *not* an onboarding redesign.

**In scope:**
- A pluggable create surface that lets a user author any V2 eval type (LLM judge, code eval, and the deterministic types) and attach it to an existing Eval.
- Code-eval authoring in-browser (CodeMirror editor + sandboxed test-run preview + trust gate).
- View surfaces rendering each type via a per-type renderer registry.
- Defensive binding so a backend type with no UI fails loudly.

**Out of scope (deferred to a future goal-first onboarding project):**
- Goal-first questionnaire ("describe your goal in plain text") — original decision 27.
- Routing logic (questionnaire → type + dataset path + count) — original decision 28.
- Hidden-SpecType curation — original decision 30 (K.4 maps all 17 → `llm_judge` regardless of UI visibility).
- Relaxing the golden-subset (`eval_configs_filter_id`) requirement — original decision 34.
- The "builder auto-right-sizes the synthetic dataset to the input" mechanism (A0.2's right-sizing leg). The **principle** stands as a Kiln north-star; the build is the onboarding project's.

The fresh `competitive_ui_vs_code/` study is the reference brief for that future project, not for V2.

**Untouched by this batch:**
- **Copilot** (Kiln Pro) — still the plain-language → `llm_judge` + dataset path; stays `llm_judge`-only (per K.2/K.4). Does not route through the create container below.
- **SDG / synthetic dataset generation** — the Eval and its dataset already exist by the time a config is created; new types ride that dataset and never generate.
- **Mechanical V2 EvalConfig production** (the K decisions) — see §5; this batch designs the *UI surface* K plumbs.

---

## 1. Create container architecture (G.1)

### Altitude

The create container lives at **config-creation altitude — under an existing Eval**. The Eval, its `output_scores`, and its dataset are already in place (manual/SDG flow). The container adds an `EvalConfig` (a "run config" / scorer candidate) to that Eval. It is reached from the eval-detail page's "Add run config" affordance and is **re-entrant** — users return to add 2nd/3rd candidate configs for calibration.

Naming: keep it config-level (`create_eval_config`-style route under `…/[spec_id]/[eval_id]/…`). Avoid `create_manual_eval`, which reads as Eval-level and drags Eval creation + SDG back into scope.

### Layout

Standard Kiln left=main / right=details:
- **Left** — the injected per-type **authoring component** (the type-specific form / editor).
- **Right** — **"Test Run"**: pick a recent dataset item → Run → Results.

### Responsibility split (container vs. component)

The container owns everything generic so each new type is cheap to add:

| Owned by **container** (generic, all types) | Owned by **per-type component** |
|---|---|
| Load test data (recent dataset items) | Render the authoring form (left pane) |
| **Run the test** — uniform `(config + input) → scores` call (backend adapter registry dispatches by type) | Produce the `EvalConfig` properties to hand up for save |
| Save button + Save flow | Optionally supply a custom **result renderer** |
| Clone / prefill-from-existing | Declare `requiresTrust: bool` (gates the run behind the trust modal) |
| Result-shape validation against `output_scores` | |

**Key consequence:** test-run is *not* per-component. Because the backend already dispatches by type, the container runs every type's test the same way — so **every future type gets test-run for free**. The only per-type knowledge the container needs to *run* is `requiresTrust`.

### Output scores are Eval-level (C.9 — settled, not a UI decision)

`Eval.output_scores` is fixed before any config is added; **every EvalConfig must produce all of them** (1:N is calibration *candidates*, not scores-split-across-configs). The container passes `output_scores` down to the component and the test API. The return-shape check is well-defined: *did the result include every declared score name, each with a value valid for its type* (`five_star` / `pass_fail` / `pass_fail_critical`)?

### No edit — clone only (E.17)

EvalConfigs are immutable for provenance (`EvalRun → frozen EvalConfig`). There is **no edit-in-place**. "Edit a config" = **clone to a new candidate and modify**, using the existing Kiln clone pattern. Saved configs render read-only; the container supports prefill-from-existing for the clone path. Promotion of a candidate is via `current_config_id` (calibration), unchanged.

### Type picker

Initial state of the container = **Select Eval Type**:
- "LLM as Judge (recommended)" first.
- Then the rest: "Code — Custom Python Code eval", "Exact Match", "Pattern Match (regex)", "Contains", "Set Check", "Tool Call Check", "Step Count Check".
- **No applicability filtering** — all V2 types always listed. A trajectory check against a trace that happens to have zero tool calls is still a valid check; same logic for step count. Showing-all avoids a brittle "why is this type missing?" UX.
- On select: push history / update URL the SvelteKit-official way, so **Back** returns to the picker.

The existing LLM-as-judge `create_eval_config/+page.svelte` becomes the **LLM-judge authoring component** inside this container — its Save button removed and wired to the container's Save.

**Note on `system_prompt`:** The `system_prompt` field is **not exposed in the LLM-judge create form**. When the user creates an `llm_judge` config, the builder writes a default `"You are an evaluator."` into the EvalConfig's `system_prompt` field at creation time. Power users can adjust it via the code/library API only. See `components/21` section 6.2 and `components/40` section 7.1.

---

## 2. Code-eval create UI (G.2) — Beta

Code evals are authored **in the Kiln UI**, not SDK-only. Larger build than the deterministic forms, deliberately taken on.

### Editor
- **CodeMirror 6** with `@codemirror/lang-python` — Python only, syntax highlighting, "Python" label top-left of the box.
- **Lazy-loaded** — imported only on the code-eval page so CM6 stays out of the default/bundled load (matters for the PyInstaller bundle).
- Loads with a **minimal valid eval example**.
- Built as a **reusable component** (we'll want it elsewhere).
- **Format / lint buttons are cut** — not native to CM6, would need a server ruff/black round-trip; not worth V2. Highlighting only.
- **"See examples"** → tabbed modal of a few common cases ("Parse JSON and compare fields", …), each with a "Use this template" button.

### Test pane (right)
- **"Test Run"** → **Input Section** lists recent dataset items to pick from. **Manual free-text input is cut.** Reference data is available via an **Advanced expander**; the **trace comes from the selected dataset item**.
- **Run** → new server API: executes the code in the **same B.13 sandbox** (`multiprocessing` spawn worker) with the **same pre-save validators** (limited imports). It will not run anything it would refuse to save. It **previews** the result without persisting and **checks the return shape against `output_scores`** (great error if it doesn't match; check can be server-side).
- **Async UX:** spinner + **Cancel** while running (also satisfies the open runaway-`code_eval` cancellation affordance from B.13).
- **Empty-dataset state:** "Run your task to generate sample inputs." Rare. In that state **Save Without Testing is the only path** (the Save-Without-Testing modal becomes load-bearing, not just an escape hatch).
- **Results:** appear after a run, rendered via the type's result renderer (scores against `output_scores`).

### Save
- A **successful test run** (executed *and* returned a valid shape matching `output_scores`) enables Save.
- Saving without a successful test → **"Save Without Testing"** confirm modal: "I know, you're a great coder, but it never hurts to run it once." Buttons: red **Save Without Testing** / **Cancel**.

### Trust gate
- **"Trust this code?"** modal on first **run or save**: "never paste code from a stranger or the internet here."
- Answer held **in-memory, window-scoped**; **re-asked on next app launch**; **no disk/DB persistence**. (Locks the open B.13 trust-gate-shape question at the conservative/ephemeral end.)

### Beta + P2
- **Beta** label under the header — **code-eval only**. Deterministic types ship stable.
- **P2 (not V2.0-gating):** "Ask assistant for help" button → launches the assistant pane with a new chat pre-seeded: "I need help writing a python-based eval. I need it to check…".

### Scorer contract (resolved — cross-ref `components/27` section 2)

The **minimal valid example**, the **examples-gallery content**, and the **return-shape check** all encode the code-eval **scorer signature**. That contract is fully specified in `components/27_type_code_eval.md` section 2 (scorer contract) and section 2.4 (gallery examples).

**Scorer function:** User code defines a `def score(...)` function. Kiln calls it with five arguments:

| Parameter | Type | Source |
|---|---|---|
| `output` | `str \| dict` | Model's final output (`TaskRun.output.output`) |
| `trace` | `list[dict] \| None` | Full conversation trace (OpenAI format); `None` for final-answer-only runs |
| `reference_data` | `dict[str, Any] \| None` | `EvalInput.reference` for this case |
| `task_input` | `str \| dict` | Original task input |
| `kiln` | `KilnEvalHelpers` | Helper library (trace navigation, tool-call extraction, scoring constructors, assertion helpers) |

**Return shape:** The `score()` function returns a `dict[str, float]` keyed on the Eval's `output_scores` names. Values must be floats in the correct range for the score's `rating_type` (0-1 for `pass_fail` / `pass_fail_critical`; 0-5 for `five_star`). No bool convenience -- use `kiln.pass_fail(passed)` or `kiln.five_star(rating)` helpers to produce correct floats. Missing keys are `None` (skip); extra keys are ignored.

**Return-shape validation in the test pane:** After a test run, the container checks that every key in `output_scores` appears in the returned dict with a float value valid for its `rating_type`. Missing keys surface as warnings; type/range errors surface as errors (including bool values, which are not accepted). This check can run server-side (same validator the `CodeEvalAdapter` uses in production).

**Minimal valid example** (loaded into the CodeMirror editor on first open):

```python
def score(output, trace, reference_data, task_input, kiln):
    # Check if the output contains "hello"
    passed = "hello" in output.lower()
    return {"greeting_quality": kiln.pass_fail(passed)}
```

(Assumes the Eval has an `output_score` named `greeting_quality` with type `pass_fail`.)

**Examples gallery** ("See examples" modal tabs) — content from `components/27` section 2.4:

1. **"Parse JSON and compare fields"**
```python
import json

def score(output, trace, reference_data, task_input, kiln):
    parsed = json.loads(output) if isinstance(output, str) else output
    expected = reference_data["expected_fields"]

    matches = sum(1 for k, v in expected.items() if parsed.get(k) == v)
    total = len(expected)

    return {"field_accuracy": matches / total if total > 0 else 0.0}
```

2. **"Check tool usage patterns"**
```python
def score(output, trace, reference_data, task_input, kiln):
    tool_calls = kiln.get_tool_calls(trace)

    used_search = kiln.has_tool_call(tool_calls, "web_search")
    used_forbidden = kiln.has_tool_call(tool_calls, "delete_record")

    return {
        "used_correct_tool": kiln.pass_fail(used_search),
        "avoided_forbidden": kiln.pass_fail(not used_forbidden),
    }
```

3. **"Domain-specific grading with reference"**
```python
import re

def score(output, trace, reference_data, task_input, kiln):
    # Extract numeric answer from output
    numbers = re.findall(r"[-+]?\d*\.?\d+", output)
    predicted = float(numbers[-1]) if numbers else None

    expected = reference_data["expected_value"]
    tolerance = reference_data.get("tolerance", 0.01)

    passed = predicted is not None and abs(predicted - expected) <= tolerance
    return {"numerical_accuracy": kiln.pass_fail(passed)}
```

Each example tab has a **"Use this template"** button that replaces the editor content.

---

## 3. Deterministic-type create components

`exact_match`, `pattern_match` (regex), `contains`, `set_check`, `tool_call_check`, `step_count_check` each get a small per-type authoring form (left pane) producing their `…Properties` (shapes in `components/22_type_deterministic_basics.md`; J.37/J.38 for the agent ones). They reuse the container's generic test-run and save. Forms ship **stable** (no Beta label).

### 3.1 Form layouts (derived from `components/22` properties shapes)

All forms share common patterns: field labels, help text, validation feedback on invalid input, and the container's Save / Test Run affordances. Each form produces a typed `…Properties` object handed up to the container for save.

**`exact_match`:**
- **Value expression** — optional text input (Jinja2 expression). Help text: "Leave blank to compare the full model output." Validation: `compile_expression_or_raise` on blur.
- **Comparison source** — radio group: "Compare against a literal value" / "Compare against reference data key." Exactly one must be selected (mirrors the `expected_value` XOR `reference_key` validator).
  - If literal: text input for `expected_value`.
  - If reference: text input for `reference_key` (min 1 char).
- **Case sensitive** — checkbox (default checked).

**`pattern_match`:**
- **Value expression** — same as `exact_match` (optional Jinja2 expression).
- **Regex pattern** — text input (required). Validation: `re.compile()` on blur; show error if invalid regex.
- **Mode** — select: "Must match" (default) / "Must not match."

**`contains`:**
- **Value expression** — same as above (optional Jinja2 expression).
- **Search string source** — radio group: "Literal substring" / "From reference data key." Exactly one selected.
  - If literal: text input for `substring`.
  - If reference: text input for `reference_key`.
- **Case sensitive** — checkbox (default checked).
- **Mode** — select: "Must contain" (default) / "Must not contain."

**`set_check`:**
- **Value expression** — same as above (optional Jinja2 expression).
- **Expected set source** — radio group: "Literal set" / "From reference data key." Exactly one selected.
  - If literal: tag-input / multi-value field for `expected_set` (list of strings). Add items via enter or comma.
  - If reference: text input for `reference_key`.
- **Mode** — select: "Subset (output values must all be in expected)" (default) / "Superset (output must include all expected)" / "Equal (exact set match)."

**`tool_call_check`:**
- **Expected tools** — dynamic list builder. Each entry:
  - **Tool name** — text input (required).
  - **Expected arguments** — optional collapsible section. Each arg:
    - **Argument name** — text input.
    - **Expected value** — text input (JSON value).
    - **Match mode** — select: "Exact" (default) / "Contains" / "Regex."
  - Add/remove arg rows.
- Add/remove tool-spec rows.
- **Match mode** — select: "All (every tool called, any order)" (default) / "Any (at least one called)" / "Ordered (called in listed sequence)" / "Never (none of these called — forbidden list)."
- **On unexpected tools** — select: "Ignore (allow other tools)" (default) / "Fail (strict allowlist)." Hidden when match mode is "Never."

**`step_count_check`:**
- **Count type** — select: "Tool calls" / "Model responses" / "Turns."
- **Minimum count** — optional number input (integer, >= 0).
- **Maximum count** — optional number input (integer, >= 0).
- Validation: at least one of min/max must be set; min <= max when both set. Shown as inline error.

### 3.2 Shared form conventions

- **Value expression fields** include a small "?" help icon linking to Jinja2 expression docs (or inline tooltip: "Jinja2 expression evaluated against the eval input. Leave blank to use the full model output.").
- **Reference key fields** include help text: "Key name in the eval input's reference data."
- All validation runs on blur (not on every keystroke) and again on Save attempt. Server-side validation is the final gate.
- Radio groups for XOR fields (literal vs reference) disable the inactive input to avoid confusion.
- `tool_call_check` is the most complex form; it uses Kiln's existing dynamic-list-builder pattern (add/remove rows). The arg-matching section is collapsed by default to keep the simple "just check tool names" case clean.

---

## 4. View surfaces + defensive binding (G.3)

### Renderer registry
- View surfaces render per-type via a **renderer registry keyed on the same `properties.type` discriminator the backend adapter registry uses** (mirror of A2.11 / C.11b — front/back stay in sync).
- Two parallel front-end registries — **create-form-by-type** and **result-renderer-by-type** — best expressed as **one per-type module** exporting `{ label, icon, createForm, resultRenderer, requiresTrust }`. A new type = one registered file.
- **Mixed-type display:** an Eval whose candidate configs are different types must not choke the view.
- Detailed view-screen layout: **deferred to Stage 5** (architecture locked here, layout later).

### Defensive enum binding
- The registry is **exhaustive over the `V2EvalType` enum**: compile-time (TS exhaustiveness / `never`) + runtime assert that every enum value maps to a module.
- A backend type added without a UI module **fails loudly** rather than rendering blank. Existing Kiln pattern; point it at the registry map.

### 4.1 Per-type renderer content (illustrative guidance — agent builds it)

The renderer registry's `resultRenderer` (run-result content) and the read-only config-detail view each need per-type content. **This is not a binding layout spec.** The coding agent should *take a run at it* from the data each type already produces, using its UI-design judgment; a later standalone UI pass may tune it. The table below is **illustrative guidance** — what data is available and worth surfacing per type — not a contract to implement verbatim.

The one firm requirement: every type's result renderer shows **the score(s)** against `output_scores` (the existing score badge component — pass/fail / pass_fail_critical / five_star) and **skip state** (`skipped_reason`) when set. Everything below that is the agent's call.

| Type | Result renderer adds (under the score badge) | Read-only config-detail shows |
|---|---|---|
| `llm_judge` | The judge's **reasoning text** + per-criterion pass/fail breakdown (the structured judge output already persisted). | The criteria/rubric, `g_eval_mode` flag, judge model. (`system_prompt`/`prompt_template` collapsed under "Advanced".) |
| `code_eval` | **stdout/stderr** (collapsible) + the returned **score dict**; on error, the exception/traceback. | Read-only code (CodeMirror, no-edit) + Beta badge. |
| `exact_match` | **Extracted value** vs **expected** (literal or resolved `reference_key`), side by side. | Value expression, comparison source, case-sensitivity. |
| `pattern_match` | **Extracted value** + the **regex** + match/no-match + (mode). | Value expression, regex pattern, mode. |
| `contains` | **Extracted value** + the **search string** + found/not-found + (mode). | Value expression, search-string source, case-sensitivity, mode. |
| `set_check` | **Extracted set** vs **expected set**, with missing/extra members called out + (mode). | Value expression, expected-set source, mode. |
| `tool_call_check` | **Matched vs missing tools** (and, when strict, unexpected tools); arg-mismatch detail per tool when present. | Expected-tools list (+ arg matchers), match mode, on-unexpected behavior. |
| `step_count_check` | **Actual count** vs the **min/max bounds** + which bound failed. | Count type, min, max. |

Mixed-type display (an Eval with candidate configs of different types) just renders each config through its own module — no special handling beyond the registry doing its job.

### 4.2 Affected view surfaces

The renderer registry plugs into the existing eval routes (verified against the current web UI). No new routes — V2 configs/results must render wherever V1 ones already do:

- `…/[eval_id]/+page.svelte` — eval detail (config list + summary scores).
- `…/[eval_id]/eval_configs/+page.svelte` — eval-configs list / candidates.
- `…/[eval_id]/compare_run_configs/+page.svelte` + `lib/components/run_config_comparison_table.svelte` — calibration comparison table (must tolerate mixed types per §4).
- `…/[eval_id]/[eval_config_id]/[run_config_id]/run_result/+page.svelte` — per-run result detail (the primary home of the `resultRenderer` content above).

### 4.3 Read-only config-detail view — in scope (minimal)

Because configs are clone-only (E.17), the saved-config view is **read-only and in scope for V2.0** (a user must be able to see what a candidate config does before cloning it). It reuses the same per-type module's `createForm` in a disabled/read-only mode, or a lightweight `configDetail` renderer — implementer's choice; the content is the right-hand column of the table in §4.1. No separate design needed beyond that content list.

---

## 5. Mechanical V2 EvalConfig production (the K decisions)

This batch designs the *UI surface*; the *mechanical* plumbing that makes existing paths emit V2 EvalConfigs is already locked in Batch K and not re-derived here:
- **K.1** — manual `create_eval_config` endpoint stays LLM-judge-focused, constructs a V2 `EvalConfig` internally (`g_eval_mode: bool`, D.4 defaults).
- **K.2** — Copilot path local V1→V2 translation; no remote `api.kiln.tech` changes.
- **K.3** (amended by B2.1) — V2-only EvalConfig creation; per-flow dataset shape.
- **K.4** — all 17 SpecTypes → `llm_judge`; SpecType orthogonal to `g_eval_mode`.
- **K.5** — minimal frontend payload tweaks; `spec_builder` is a no-op.

The create container above (§1) extends the manual path beyond K.1's LLM-judge-only endpoint to the full type catalog — that extension is *this* batch's new surface, where K explicitly stopped ("K is not a builder upgrade").

---

## Opens

None. All blocking dependencies resolved:

- **`O-codeeval-scorer-contract`** — resolved by `components/27_type_code_eval.md` section 2. Scorer contract, examples gallery, and return-shape validation are now fully specified in section 2 above.
- **Deterministic-type form layouts** — filled in section 3.1 above from `components/22` properties shapes.
- **View-screen layout detail** (per-type result renderers, mixed-type eval presentation) — **filled in §4.1–§4.3** (Stage-6 prep, 2026-06-06): per-type renderer content baseline, affected view routes (verified against the live web UI), and read-only config-detail scope. Logged in `design_phase_calls.md` S7. Richer per-type visualizations remain post-V2 polish.
