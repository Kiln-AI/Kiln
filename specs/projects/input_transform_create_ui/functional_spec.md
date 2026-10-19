---
status: complete
---

# Functional Spec: Input Transform Create UI

## 1. Summary

Adds **authoring** of input transforms to the `/run` page. Today the `input_transform` field exists on `KilnAgentRunConfigProperties` (backend, project `templates`) and is displayed read-only on detail/summary surfaces (project `input_transform_ui`), but there is **no way to create or edit one from the UI**. This project adds an "Input Transform" control to the `/run` advanced options, a create/edit modal, and a small backend endpoint that validates a Jinja2 template, plus the wiring that lets a transform round-trip through the "Run Configuration" selector and the save-run-config flow.

V1 supports exactly one transform type: `JinjaInputTransform` (`{ type: "jinja", template: str }`).

## 2. Goals

- A user can attach, edit, or remove a Jinja2 input transform on the `/run` page, and have it apply to runs and be savable as part of a run config.
- The control's state stays consistent with the rest of the run-config form: loading a saved config populates it; changing it makes the "Run Configuration" selector fall back to "Custom".
- Invalid Jinja2 is rejected at author time (on "Create") with a clear error, never silently saved.
- Strong typing and the existing exhaustiveness pattern are preserved — adding a backend transform type later produces a compile error here until handled.

## 3. Non-Goals (V1)

- No backend changes to the transform **engine** (rendering, runtime execution, save-time model validation) — all built in `templates`.
- No changes to the read-only display surfaces built in `input_transform_ui` (detail-page row, summary indicators, read-only modal). Those remain as-is.
- No transform types other than `jinja`.
- No template editor niceties beyond a monospace textarea (no syntax highlighting, no autocomplete, no live preview/render).
- No per-template naming, library, or reuse across configs — a transform is an inline property of the run config, with no ID of its own (consistent with the data model).

## 4. The "Input Transform" Control

Location: the **last** item inside the `/run` page's **Advanced Options** collapsible section (`advanced_run_options.svelte`), after Thinking Level.

Rendered as a `FormElement` with `inputType="fancy_select"`:

- **Label:** "Input Transform"
- **Info tooltip** (`info_description`): "Transform the provided input using a jinja template, before sending the input to the model. Allows you to add context, or filter data."

### 4.1 Options and selection states

The select presents these items:

The control has two parts: **selectable values** (the resting state of the transform) and an **action button** in the dropdown header (the `FancySelect` `action_label`/`action_handler` affordance, the small pill rendered next to the group label) that opens the modal.

**Selectable values:**

| Item | Shown when | Selecting it does |
|---|---|---|
| **None** | always | Clears the transform (`input_transform` → `null`). |
| **Custom Template** | only when a transform is currently set | The resting selected state when a template is set. Re-selecting it is a no-op (does not reopen the modal). |

**Action button** (dropdown header, always present):

| Label | When | Does |
|---|---|---|
| **Create Template** | no transform set | Opens the create modal (§5), empty. |
| **Edit Template** | transform set | Opens the modal (§5) prefilled with the current template. |

Resting (persisted) selection is therefore always **None** or **Custom Template**. The action button is the single entry point for both create and edit; it is not itself a selectable value, so opening or cancelling the modal never changes the resting selection.

State rules:

- No transform set → resting selection is **None**, "Custom Template" not shown, action button reads "Create Template".
- Transform set → resting selection is **Custom Template**, action button reads "Edit Template".
- The underlying form state is a single nullable value: the current `InputTransform | null` (`{ type: "jinja", template }` or `null`).

### 4.2 Interactions

- **Pick "None"** while a template is set → transform cleared to `null`; "Custom Template" disappears; selection becomes "None"; action button reverts to "Create Template". (No confirmation prompt; non-destructive in that nothing is persisted until the user saves/runs, consistent with the rest of the form.)
- **Click the action button ("Create Template" / "Edit Template")** → modal opens (§5), prefilled when editing. The resting selection is untouched; cancelling the modal leaves everything as it was.
- **Pick "Custom Template"** (when shown) → no-op resting state. To edit, the user clicks "Edit Template".

## 5. Create / Edit Modal

Opened by the action button ("Create Template" / "Edit Template").

- **Title:** "Input Transform"
- **Subtitle:** "Transform the provided input using a jinja template, before sending the input to the model. Allows you to add context, or filter data."
- **Body:** a single multi-line **monospace textarea** for the Jinja2 template source. Prefilled with the current template when editing; empty when creating fresh.
- **Primary button:** "Create" (label stays "Create" in both create and edit cases for simplicity; it commits the current textarea contents).
- **Dismissal:** standard Dialog close (X / Escape) cancels without changing the transform.

### 5.1 Create/validate flow

On "Create" click:

1. **Empty check (client-side):** if the textarea is empty or whitespace-only, reject immediately with an inline error (e.g., "Template can't be empty"). Do not call the API or modify form state. Although the backend engine permits an empty template, it is never what the user wants — picking "None" is the way to remove a transform.
2. Otherwise call the validation API (§6) with the textarea contents.
3. **If valid:** set the form's `input_transform` to `{ type: "jinja", template: <contents> }`, switch the select's resting selection to "Custom Template", close the modal.
4. **If invalid:** keep the modal open, show the validation error message inline (near the textarea / button). Do **not** modify the form's transform state.

Notes:

- Empty / whitespace-only templates are rejected by the modal (step 1 above). "None" removes a transform; the modal only ever commits a non-empty template.
- Validation is on-demand (on "Create"), not live-as-you-type, to keep it simple and avoid request spam.

## 6. Validation API

A new, small, **stateless** endpoint (not scoped to a project/task) that wraps the existing `compile_template_or_raise` helper (`libs/core/kiln_ai/utils/jinja_engine.py`).

**Request** (`POST`, JSON body):

```json
{ "template": "<jinja2 source string>" }
```

**Response — valid:**

```json
{ "valid": true, "error": null }
```

**Response — invalid:**

```json
{ "valid": false, "error": "<human-readable compile error message>" }
```

Behavior:

- Calls `compile_template_or_raise(template)`. On `ValueError`/compile error, returns `valid: false` with the error string. On success, `valid: true`.
- Returns HTTP 200 in both valid and invalid cases (validity is conveyed in the body, not the status code) so the frontend can render the error message uniformly. Malformed *requests* (e.g., missing `template`) follow normal FastAPI 422 behavior.
- Does not persist anything and does not require a project/task in scope — it only checks Jinja2 syntax.
- Home: `app/desktop/studio_server/run_config_api.py` (the run-config API module), or a comparably general module if that fits better at implementation time.

This endpoint is **independent of saving a run config**: a user can have an unsaved/"Custom" run config with a transform, so transform validity must be checkable before (and without) saving.

## 7. Run Configuration Selector Integration

The top-of-page "Run Configuration" dropdown (`saved_run_configs_dropdown.svelte`) selects a saved `TaskRunConfig`. Three existing code paths in `run_config_component.svelte` currently ignore `input_transform` and must include it:

1. **Load a saved config** (`update_current_run_options_for_selected_run_config`): set the form's `input_transform` from the loaded config's `run_config_properties.input_transform ?? null`. The "Input Transform" control reflects this (None vs Custom Template).
2. **Custom detection** (`reset_to_custom_options_if_needed`): include `input_transform` in the equality comparison against the selected saved config. If the user's current transform differs from the saved config's transform (including set↔unset, or a different template string), the selector falls back to "Custom" — exactly as it does for model/prompt/temperature/etc.
3. **Build the save payload** (`run_options_as_run_config_properties`): include `input_transform` (the current `InputTransform | null`) in the returned `KilnAgentRunConfigProperties`, so saving a run config persists the transform.

Transform equality for custom-detection: two transforms are equal iff both are `null`, or both are `jinja` with identical `template` strings. (Structural compare; for V1's single type this is template-string equality.)

## 8. Save Run Config Flow

When the user saves the current options as a new run config (existing "Save current options" inline action), the payload now carries `input_transform`. The save endpoint already accepts the field (backend built in `templates`), and re-validates the template at save time via the model's `@field_validator`. Because the UI validated on "Create", save-time validation should not fail in normal use; if it ever does, the existing save-error surface reports it.

## 9. Edge Cases

- **Switching models/providers** does not affect the transform — it's model-agnostic.
- **Loading a config with no transform** → control shows "None"; "Custom Template" item hidden.
- **Cancel the modal** → no change to transform state or selection.
- **Validation network/server error** (endpoint unreachable / 5xx) → treat as "could not validate"; keep the modal open and show an error message; do not commit the template. (Fail closed: never commit an unvalidated template.)
- **Whitespace-only / empty template** → rejected by the modal with an inline error before any API call (§5.1 step 1); never committed.
- **MCP-typed run config** → the transform control is part of `kiln_agent` run options on `/run`; `input_transform` only exists on `kiln_agent`. No transform UI applies to MCP configs (consistent with existing helpers returning null for MCP).

## 10. UI Design Notes

The UI surface is small and reuses existing components/patterns (no separate `ui_design.md`).

**Control (§4).** A `FormElement` `inputType="fancy_select"`, matching the look of the existing advanced options (Structured Output, Thinking Level). It sits last in the Advanced Options collapse. Selectable values in the dropdown: **None**, then **Custom Template** (only when set). The **Create Template / Edit Template** action lives in the dropdown header as the group's action button (`action_label`/`action_handler`). The info tooltip uses the standard `info_description` → `InfoTooltip` pattern, identical to neighboring options.

**Modal (§5).** Reuse the existing `Dialog` component (same one the read-only `input_transform_modal.svelte` uses) for title/subtitle/dismissal chrome. Body:
- A single monospace multi-line textarea (FormElement textarea or equivalent), reasonable default height (a few rows), full modal width, wrapping/scrolling for long templates.
- The validation/empty error renders inline directly below the textarea (or between textarea and button) in the standard error style (red text), and clears when the user edits the textarea or on the next "Create" attempt.
- A single primary "Create" button. While the validation request is in flight, the button shows a loading/disabled state to prevent double-submit.

**Progressive disclosure.** The whole feature lives under Advanced Options (collapsed by default), so casual users never see it; the resting select reads "None" with no extra surface area. Power users discover it alongside the other advanced run options. The modal keeps authoring out of the main form until explicitly invoked.

**Consistency.** Selecting a transform and then changing it behaves exactly like every other run option (model, prompt, temperature): the "Run Configuration" selector falls back to "Custom", and "Save current options" persists it — no new mental model for the user.

## 11. Out of Scope

(See §3.) Plus: no migration of existing configs, no bulk edit, no template variables helper/picker, no preview of rendered output against sample input.
