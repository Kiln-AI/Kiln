---
status: complete
---

# Architecture: Input Transform Create UI

Mostly frontend (`app/web_ui`), plus one small stateless backend endpoint. Reuses the existing `input_transform` data model (`templates`), the existing TS type aliases/helpers and read-only modal (`input_transform_ui`), and the existing `compile_template_or_raise` engine helper. No data-model changes.

This is a **single architecture doc** — the surface is small (one endpoint, two new Svelte components, edits to three existing functions). No `/components/` designs.

---

## 1. Backend: Jinja validation endpoint

A new stateless endpoint that validates a Jinja2 template string by delegating to `compile_template_or_raise` (`libs/core/kiln_ai/utils/jinja_engine.py:43`). Not project/task scoped — it only checks syntax.

**Location:** `app/desktop/studio_server/run_config_api.py`, inside `connect_run_config_api(app)`.

**Models** (module-level, near the other request models):

```python
class ValidateInputTransformTemplateRequest(BaseModel):
    template: str = Field(description="The Jinja2 template source to validate.")


class ValidateInputTransformTemplateResponse(BaseModel):
    valid: bool = Field(description="Whether the template is valid Jinja2.")
    error: str | None = Field(
        default=None, description="The compile error message, if invalid."
    )
```

**Endpoint:**

```python
@app.post("/api/validate_input_transform_template", tags=["Run Configs"])
async def validate_input_transform_template(
    request: ValidateInputTransformTemplateRequest,
) -> ValidateInputTransformTemplateResponse:
    try:
        compile_template_or_raise(request.template)
        return ValidateInputTransformTemplateResponse(valid=True, error=None)
    except Exception as e:
        return ValidateInputTransformTemplateResponse(valid=False, error=str(e))
```

Notes:
- Returns **HTTP 200** for both valid and invalid (validity is in the body), so the client renders the error uniformly. A missing `template` field is a normal FastAPI 422 (malformed request), which the client surfaces as a generic error.
- Catches broadly (`Exception`) because `compile_template_or_raise` raises `ValueError` on syntax errors, but we never want a malformed template to 500. The message is passed through to the user.
- Import `compile_template_or_raise` from `kiln_ai.utils.jinja_engine`.
- The endpoint does **not** enforce non-empty — an empty template compiles fine. The empty-template rejection is a UI-only product rule (§4.3); keeping the endpoint a pure syntax check keeps it reusable.

### 1.1 OpenAPI client regen

After adding the endpoint, regenerate the TS client so `client.POST("/api/validate_input_transform_template", ...)` is typed:

```
app/web_ui/src/lib/generate_schema.sh   # regenerate
app/web_ui/src/lib/check_schema.sh      # verify up to date (CI check)
```

`ValidateInputTransformTemplateRequest`/`Response` schemas land in `api_schema.d.ts`.

---

## 2. Frontend types & helpers

Reuse the existing aliases in `app/web_ui/src/lib/types.ts` (no change): `InputTransform`, `JinjaInputTransform`. `InputTransform` is `NonNullable<KilnAgentRunConfigProperties["input_transform"]>`, so it auto-widens to a union when a second backend type lands.

Add two small helpers to `app/web_ui/src/lib/utils/run_config_formatters.ts` (the existing home of transform helpers, with the `_exhaustive: never` pattern):

```ts
// Build a transform from raw template text. Single place that constructs the jinja variant.
export function buildJinjaInputTransform(template: string): InputTransform {
  return { type: "jinja", template }
}

// Structural equality used by the /run "custom" detection. Two transforms are equal iff
// both null, or both jinja with identical template strings. Exhaustive on type.
export function inputTransformsEqual(
  a: InputTransform | null | undefined,
  b: InputTransform | null | undefined,
): boolean {
  const an = a ?? null
  const bn = b ?? null
  if (an === null || bn === null) {
    return an === bn
  }
  if (an.type !== bn.type) {
    return false
  }
  switch (an.type) {
    case "jinja":
      // bn.type === an.type === "jinja" here
      return an.template === (bn as JinjaInputTransform).template
    default: {
      const _exhaustive: never = an.type
      throw new Error(`Unknown input transform type: ${_exhaustive}`)
    }
  }
}
```

`buildJinjaInputTransform` localizes the one spot that hand-builds the variant (so adding a non-jinja authoring path later is a single, visible change). `inputTransformsEqual` keeps custom-detection exhaustive and reusable.

---

## 3. New component: `input_transform_create_modal.svelte`

Path: `app/web_ui/src/lib/ui/run_config_component/input_transform_create_modal.svelte`. Distinct from the existing read-only `input_transform_modal.svelte`.

**Props / API:**
```ts
export let on_created: (transform: InputTransform) => void
let dialog: Dialog
export function show(initial_template: string = "") { /* set draft, clear error, dialog.show() */ }
```

**State:**
```ts
let template_draft = ""
let validation_error: string | null = null
let submitting = false
```

**Render** — `Dialog` (reused) + `FormContainer` with `submit_label="Create"`, mirroring `create_new_run_config_dialog.svelte`:
- `title="Input Transform"`.
- `subtitle="Transform the provided input using a jinja template, before sending the input to the model. Allows you to add context, or filter data."`
- Body: a **monospace multi-line textarea** bound to `template_draft`. Use `FormElement` `inputType="textarea"` with a `font-mono` class (or a raw `<textarea class="textarea textarea-bordered font-mono ...">` if FormElement doesn't allow font override — implementer's choice; visual = monospace, several rows, wraps/scrolls).
- Below the textarea: `{#if validation_error}<div class="text-error text-sm">{validation_error}</div>{/if}`.
- `FormContainer` `submit_label="Create"`, `bind:submitting`, `on:submit={handle_create}`.

**`handle_create` (the create/validate flow, §4.3 of functional spec):**
```ts
async function handle_create() {
  validation_error = null
  const t = template_draft
  if (t.trim().length === 0) {            // 1. empty check, client-side
    validation_error = "Template can't be empty"
    return
  }
  submitting = true                        // (FormContainer also manages this)
  try {
    const { data, error } = await client.POST(
      "/api/validate_input_transform_template",
      { body: { template: t } },
    )
    if (error) throw error                 // network/5xx → fail closed
    if (!data.valid) {                     // 2. invalid jinja
      validation_error = data.error || "Invalid template"
      return
    }
    on_created(buildJinjaInputTransform(t)) // 3. valid → commit
    dialog?.close()
  } catch (e) {
    validation_error = createKilnError(e).getMessage() || "Could not validate template"
  } finally {
    submitting = false
  }
}
```

- Uses the generated `client` (`$lib/api_client`) and `createKilnError` (`$lib/utils/error_handlers`), matching repo conventions.
- Fail-closed: any thrown error (network/5xx) keeps the modal open with an error and never commits.
- Closing via X/Escape (Dialog default) cancels with no `on_created` call.

---

## 4. New component: `input_transform_selector.svelte`

Path: `app/web_ui/src/lib/ui/run_config_component/input_transform_selector.svelte`. Encapsulates the fancy-select control + the create/edit modal. Using `FancySelect`'s **group action button** (`action_label`/`action_handler`, rendered as the pill next to the group label, `fancy_select.svelte:694-705`) for create/edit keeps the reconcile trivial: the action button opens the modal directly, so there is no transient "create" value to manage.

**Props:**
```ts
export let input_transform: InputTransform | null = null   // bind: from parent (source of truth)
```

**Internal:**
```ts
let create_modal: InputTransformCreateModal
let select_value: "none" | "custom" = input_transform ? "custom" : "none"
```

### 4.1 Options

Built reactively so "Custom Template" appears only when set, and the action label reflects create-vs-edit:
```ts
$: options = [
  {
    label: "Input Transform",
    action_label: input_transform ? "Edit Template" : "Create Template",
    action_handler: () => create_modal.show(input_transform?.template ?? ""),
    options: [
      { value: "none", label: "None" },
      ...(input_transform
        ? [{ value: "custom", label: "Custom Template" }]
        : []),
    ],
  },
]
```

Rendered via `FormElement` `inputType="fancy_select"`:
- `label="Input Transform"`, `id="input_transform"`.
- `info_description="Transform the provided input using a jinja template, before sending the input to the model. Allows you to add context, or filter data."`
- `bind:value={select_value}`, `fancy_select_options={options}`.

### 4.2 State machine (reconcile)

The action button is the only modal entry point; `input_transform` is the source of truth. Only two selectable values exist (`none`, `custom`), so the reconcile is two clean reactive statements with no loop fighting (the user-intent statement depends on `select_value`; the resync statement depends on `input_transform` — they never re-trigger each other harmfully, and both effects are idempotent):

```ts
// User picked a value. Only "none" has an effect; "custom" is a no-op resting state.
$: handle_select(select_value)
function handle_select(v) {
  if (v === "none" && input_transform !== null) {
    input_transform = null
  }
}

// Keep the visible selection in sync with the source of truth (external load, or a commit).
$: select_value = input_transform ? "custom" : "none"
```

Reactive ordering: picking "None" sets `select_value="none"` → `handle_select` clears `input_transform` → the resync statement (depends on `input_transform`) sets `select_value="none"` (already none). A modal commit sets `input_transform` → resync flips `select_value="custom"`. No transient state, no guard flags.

Modal commit handler (passed to the modal):
```ts
function on_created(t: InputTransform) {
  input_transform = t        // resync → select_value = "custom", action label → "Edit Template"
}
```

Render the modal:
```svelte
<InputTransformCreateModal bind:this={create_modal} {on_created} />
```

### 4.3 Edge interactions

- Pick "None" while set → `input_transform = null`; resync drops "Custom Template", selects "None", action label → "Create Template".
- Click "Create Template" / "Edit Template" → modal opens (prefilled if set); cancel leaves everything unchanged.
- Pick "Custom Template" → no-op.
- Parent swaps `input_transform` (load config) → resync updates the visible selection and action label.

---

## 5. Wiring into the form

### 5.1 `advanced_run_options.svelte`

Add a prop and render the selector **last** (after Thinking Level):
```svelte
export let input_transform: InputTransform | null = null
...
<InputTransformSelector bind:input_transform />
```
(Placed inside the existing `<div class="flex flex-col gap-4">`, as the final child.)

### 5.2 `run_config_component.svelte`

Add state and thread it into `AdvancedRunOptions`:
```ts
let input_transform: InputTransform | null = null
...
<AdvancedRunOptions
  ...existing binds...
  bind:input_transform
/>
```

Then update the three existing functions (all currently ignore `input_transform`):

1. **`update_current_run_options_for_selected_run_config()`** (`~158`) — after `thinking_level`:
   ```ts
   input_transform = config_properties.input_transform ?? null
   ```

2. **`reset_to_custom_options_if_needed()`** (`~329`) — add to the change-detection `if`:
   ```ts
   !inputTransformsEqual(config_properties.input_transform ?? null, input_transform)
   ```
   (set↔unset or differing template → falls back to "custom", exactly like other fields).

3. **`run_options_as_run_config_properties()`** (`~378`) — add to the returned `kiln_agent` object:
   ```ts
   input_transform: input_transform,
   ```
   The MCP early-return path is unchanged (MCP configs have no transform).

`input_transform` is also added to the main reactive dependency list (`$: void (model, prompt_method, ...)` at `~202`) so changing it triggers `debounce_update_for_state_changes()` → custom-detection, consistent with every other run option.

`buildJinjaInputTransform` / `inputTransformsEqual` imported from `$lib/utils/run_config_formatters`.

### 5.3 Save flow

No change needed beyond 5.2.3: `save_new_run_config()` already calls `run_options_as_run_config_properties()`, which now carries `input_transform`. The backend (`templates`) accepts and re-validates the field at save time.

---

## 6. Error handling

| Condition | Where | Behavior |
|---|---|---|
| Empty/whitespace template | Modal (client) | Inline error "Template can't be empty"; no API call; no commit. |
| Invalid Jinja2 | Endpoint → modal | `valid:false` + message; inline error; modal stays open; no commit. |
| Validation network/5xx | Modal | `createKilnError` message inline; fail-closed (no commit). |
| Save-time validation (should not happen post-validate) | Existing save-error surface | Existing run-config save error UI reports it. |

The transform is never committed to form state unless validation passed — there is no path that sets `input_transform` to an unvalidated non-empty template.

---

## 7. Exhaustiveness guarantee

`buildJinjaInputTransform` (hand-builds the jinja variant), `inputTransformsEqual` (switch on type), and the existing `getInputTransformDisplay` / read-only modal all switch on `transform.type` with a `never` default. When the backend adds a second transform type and the client is regenerated, `InputTransform` widens and these switches fail `npm run check` until updated — the create UI can't silently ignore a new type.

The selector's `select_value` union (`"none" | "custom"`) is UI-local and unaffected.

---

## 8. Testing strategy

**Backend** (`app/desktop/studio_server/test_run_config_api.py`):
- `validate_input_transform_template`: valid template → `{valid:true, error:null}`; invalid (e.g. `"{{ unclosed"`) → `{valid:false, error:<msg>}`, HTTP 200 in both; empty string → `valid:true` (engine permits it; UI forbids).

**Frontend helpers** (`run_config_formatters.test.ts`, extend existing):
- `buildJinjaInputTransform("x")` → `{type:"jinja", template:"x"}`.
- `inputTransformsEqual`: null/null true; null/set false; same template true; different template false.

**Component — `input_transform_create_modal.test.ts`:**
- Empty/whitespace submit → inline "can't be empty", no fetch, no `on_created`.
- Valid template (mock client returns `valid:true`) → `on_created` called with the jinja transform, modal closes.
- Invalid (`valid:false`) → error rendered, `on_created` not called, modal stays open.
- Network error (client throws) → error rendered, no commit.

**Component — `input_transform_selector.test.ts`:**
- Initial: null → resting "None", no "Custom Template" option, action label "Create Template"; set → resting "Custom Template", action label "Edit Template".
- Pick "None" while set → `input_transform` becomes null (bound out).
- Click the action button → modal `show` called with current template (`""` when unset, current template when set).
- Modal `on_created` → `input_transform` updated, select shows "Custom Template".
- External `input_transform` change → select resyncs (value + action label).

**Integration in `run_config_component`** (extend its existing tests if present, else targeted):
- Loading a saved config with a transform populates the selector; changing the transform flips the selector to "custom"; the save payload includes `input_transform`.

**Checks:** `app/web_ui` lint/format/check/test/build; `uv run` ruff/ty/pytest for the endpoint; `check_schema.sh` must pass (client regenerated).

---

## 9. Out of scope (architecture)

No engine/runtime changes, no new data-model fields, no changes to read-only display surfaces, no template-variable autocomplete or render preview. Single transform type (`jinja`).
