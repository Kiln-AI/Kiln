---
status: complete
---

# Phase 6: Create + View UI for V2 Eval Configs

## Overview

This phase delivers the frontend and backend pieces needed to create, test-run, and view results for all 8 V2 eval types. The deliverables:

1. **Test-run endpoint** -- a new POST endpoint that accepts a V2 config properties blob + a single `EvalTaskInput`, runs the appropriate V2 adapter without persisting anything, and returns scores/skip info. Used by the "Try it" panel in the create flow.
2. **`CreateEvalConfigRequest` update** -- make `model_name` and `provider` optional so V2 types that do not use an LLM (all except `llm_judge`) can be created without those fields.
3. **Frontend V2 type registry** -- a single TypeScript module exporting per-type metadata (label, description, icon, Svelte create-form component, result renderer component, `requiresTrust` flag). Compile-time exhaustiveness via `never` + runtime `assertNever`.
4. **Pluggable create container** -- refactor the existing `create_eval_config/+page.svelte` into a container that provides: type picker, per-type form injection via the registry, optional test-run panel, and Save ownership. The existing LLM judge logic (model picker, algorithm selector, eval steps) is extracted into a sub-component rendered by the container for `llm_judge` type.
5. **6 deterministic create forms** -- one Svelte component per deterministic V2 type (`exact_match`, `pattern_match`, `contains`, `set_check`, `tool_call_check`, `step_count_check`), each collecting the type's `*Properties` fields.
6. **`code_eval` create form** -- a form with a CodeMirror 6 Python editor (lazy-loaded via dynamic import) for the `code` field, plus `timeout_seconds`. Includes the trust gate: checks trust on save, shows an ephemeral confirmation modal, calls the Phase-5 grant endpoint, then proceeds.
7. **Per-type result renderers** -- components dispatched by the registry on the `run_result` page. Design is NOT prescribed; implementers must use `get_prompt frontend_design_guide.md` and build from each type's available data.
8. **View surface integration** -- update `run_result/+page.svelte`, eval detail page, and eval configs page to correctly display V2 eval config metadata.
9. **Schema regeneration** -- regenerate `api_schema.d.ts` after backend changes.
10. **Tests** -- vitest for registry, create forms, result renderers; pytest for the new endpoint.

### What this phase does NOT include

- Editing V2 eval configs in place. EvalConfigs are immutable: the user workflow is clone-and-modify (not in scope for this phase).
- Bulk import/export of eval configs.
- OS-level sandboxing UI for `code_eval`.
- Changes to the `EvalRunner`, SSE streaming, or comparison flow (those already handle V2 via the adapter registry).

## Design Decisions

### Test-run endpoint

No test-run/preview endpoint exists today. The existing `run_eval_config` (GET `.../run_comparison`) runs full comparisons with persistence and SSE streaming via `EvalRunner`. That is far too heavy for a quick "try it" during creation.

The new endpoint is a lightweight POST that:
- Accepts `V2EvalConfigProperties` (discriminated union) and an `EvalTaskInput` in the request body.
- Instantiates the adapter via `v2_eval_adapter_from_config()` using a transient in-memory `EvalConfig` (never saved).
- Calls `await adapter.evaluate(eval_input)`.
- Returns `{ scores: EvalScores, skipped_reason: str | null, skipped_detail: str | null }`.
- For `code_eval`, the trust gate still applies -- the endpoint must check trust and return the skip tuple if not granted (the adapter handles this internally).

This endpoint does NOT persist anything. It is POST because the request body is non-trivial.

### `CreateEvalConfigRequest` update

The current `CreateEvalConfigRequest` has `model_name: str` and `provider: ModelProviderName` as required fields. V2 deterministic types do not use a model. We must make both optional:

```python
model_name: str | None = Field(default=None, description="The model to use for evaluation. Required for LLM-based eval types.")
provider: ModelProviderName | None = Field(default=None, description="The provider of the evaluation model. Required for LLM-based eval types.")
```

The existing `create_eval_config` endpoint handler already passes these to `EvalConfig(model_name=..., model_provider=...)`, and the `EvalConfig` model already accepts `None` for both fields.

For V2 configs, `properties` must accept `V2EvalConfigProperties` (typed dict with discriminator) rather than `dict[str, Any]`. Since the existing handler does `properties=request.properties` and `EvalConfig.properties` is typed, we update `CreateEvalConfigRequest.properties` to `dict[str, Any] | V2EvalConfigProperties` so the discriminated union validates when `type == "v2"`. Alternatively, keep `dict[str, Any]` and let `EvalConfig`'s own validator handle coercion. Prefer the latter (simpler, already works) unless type-safety on the request body is needed. The implementer should validate that V2 config creation round-trips correctly with the existing endpoint before making changes.

### Frontend type registry shape

```typescript
// $lib/utils/eval_types/registry.ts

export interface V2TypeRegistryEntry {
  type: V2EvalType          // enum value from api_schema
  label: string             // human-readable, e.g. "Exact Match"
  description: string       // one-liner for type picker card
  icon: string              // path or inline SVG reference
  createFormComponent: ComponentType  // Svelte component
  resultRendererComponent: ComponentType  // Svelte component
  requiresTrust: boolean    // true only for code_eval
}
```

A `getV2TypeEntry(type: V2EvalType): V2TypeRegistryEntry` function uses a switch with exhaustive `default: assertNever(type)`. This guarantees compile-time errors when new types are added to the enum without updating the registry.

The `assertNever` helper:
```typescript
export function assertNever(x: never): never {
  throw new Error(`Unexpected V2 eval type: ${x}`)
}
```

### Create container refactoring

The existing `create_eval_config/+page.svelte` (623 lines) is tightly coupled to the LLM judge workflow: model picker -> algorithm selector -> eval steps. The refactoring approach:

1. **Extract LLM judge form** into `create_eval_config/llm_judge_form.svelte`. This component receives `evaluator`, `task`, `spec`, and `available_models` as props, and exposes the collected data (model_name, provider_name, selected_algo, task_description, eval_steps) via bound variables or a `getFormData()` method.

2. **The page becomes the container.** It handles:
   - Loading eval, task, spec (unchanged).
   - **Type picker** -- when `eval.config_type_filter` (or a future field) indicates V2 is available, show a type picker grid before the form. For V2 types, the registry's `createFormComponent` is rendered. For legacy types, the extracted LLM judge form is rendered.
   - **Test-run panel** -- a collapsible section below the form where the user can paste/pick a sample input, click "Try it", and see scores inline. Calls the test-run endpoint. Only shown for V2 types.
   - **Save button** -- the container owns the FormContainer/submit. For V2 types, it POSTs `{ type: "v2", properties: <from child form>, model_name: <if llm_judge>, provider: <if llm_judge> }`. For legacy types, it POSTs the existing payload shape.

3. **`system_prompt` is NOT exposed** in the `llm_judge` form. The default system prompt ("You are an evaluator.") is set at creation time by the backend adapter, not by the user. The form only exposes `prompt_template`, `required_var`, `thinking_instruction`, and `g_eval`.

### CodeMirror 6 lazy loading

CodeMirror 6 and its Python language pack are non-trivial in bundle size. For PyInstaller builds, they must NOT be in the default chunk. The `code_eval` create form must use dynamic import:

```typescript
const { EditorView, basicSetup } = await import("codemirror")
const { python } = await import("@codemirror/lang-python")
```

Wrap the editor in an `{#await}` block or use `onMount` with a loading state. The component is only loaded when the user selects `code_eval` type in the picker.

### Trust gate for `code_eval`

The `code_eval` create form (or the container's save handler) must:
1. Before saving, call `GET /api/projects/{project_id}/code_eval_trust`.
2. If `trusted === false`, show an ephemeral confirmation modal explaining that code evals execute arbitrary Python.
3. On user confirmation, call `POST /api/projects/{project_id}/grant_code_eval_trust`.
4. Then proceed with save.

Trust is window-scoped and ephemeral (Phase 5 design). The test-run endpoint also respects trust (the adapter's evaluate method checks it).

### Result rendering

Result rendering is intentionally NOT pinned. The implementation plan provides illustrative guidance, not a binding layout. Implementers MUST use `get_prompt frontend_design_guide.md` before building per-type result renderers. Build each renderer from the type's available data:

- **LLM judge results**: scores + reasoning/chain_of_thought (already rendered today, refactor into component).
- **Deterministic results**: scores are typically binary (0.0/1.0). Show pass/fail badges, the extracted value, and the match criteria.
- **code_eval results**: scores + any skipped_reason/skipped_detail.

The registry maps each V2EvalType to a result renderer component. The `run_result` page dispatches to the appropriate renderer based on the eval config's type.

### EvalConfigs are immutable

There is no edit flow. The create flow always produces a new config. If the user wants to iterate, they create a new config (potentially pre-filling from an existing one in a future phase). The UI should not imply configs can be edited in place.

## Steps

### Step 0: Read prerequisite prompts

Before starting implementation, read:
- `get_prompt frontend_design_guide.md` -- required before building any UI.
- `get_prompt python_test_guide.md` -- required before writing backend tests.

### Step 1: Backend -- test-run endpoint

**File: `app/desktop/studio_server/eval_api.py`**

1a. Add a Pydantic request model for the test-run endpoint:

```python
class TestV2EvalRequest(BaseModel):
    """Request to test-run a V2 eval config without persisting."""
    properties: V2EvalConfigProperties = Field(
        description="The V2 eval config properties to test."
    )
    eval_input: EvalTaskInput = Field(
        description="The input to evaluate."
    )
```

1b. Add a Pydantic response model:

```python
class TestV2EvalResponse(BaseModel):
    """Response from a test-run of a V2 eval."""
    scores: EvalScores = Field(default_factory=dict)
    skipped_reason: str | None = None
    skipped_detail: str | None = None
```

1c. Add the endpoint. Place it near the existing eval config endpoints (after `create_eval_config`):

```python
@app.post(
    "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval",
    summary="Test V2 Eval Config",
    tags=["Evals"],
    openapi_extra=DENY_AGENT,
)
async def test_v2_eval(
    project_id: str,
    task_id: str,
    eval_id: str,
    request: TestV2EvalRequest,
) -> TestV2EvalResponse:
```

Implementation:
- Load the eval via `eval_from_id(project_id, task_id, eval_id)` to validate it exists and get output_scores context.
- Build a transient `EvalConfig` in memory (do NOT save):
  ```python
  eval_obj = eval_from_id(project_id, task_id, eval_id)
  transient_config = EvalConfig(
      name="test_run",
      config_type=EvalConfigType.v2,
      properties=request.properties,
      parent=eval_obj,
  )
  ```
  Note: `EvalConfig` requires a `parent` to be set. Since we do not call `save_to_file()`, this is safe.
- Instantiate adapter: `adapter = v2_eval_adapter_from_config(transient_config)`
- Run: `scores, skipped_reason, skipped_detail = await adapter.evaluate(request.eval_input)`
- Return `TestV2EvalResponse(scores=scores, skipped_reason=skipped_reason.value if skipped_reason else None, skipped_detail=skipped_detail)`

Error handling: wrap in try/except for `ValueError`, `NotImplementedError`, returning 400 with detail.

### Step 2: Backend -- make `CreateEvalConfigRequest` fields optional

**File: `app/desktop/studio_server/eval_api.py`**

2a. Update `CreateEvalConfigRequest`:

```python
class CreateEvalConfigRequest(BaseModel):
    """Request to create a new eval configuration."""
    name: str | None = Field(default=None, description="The name of the eval config.")
    type: EvalConfigType = Field(description="The type of eval config.")
    properties: dict[str, Any] = Field(
        description="Properties for the eval config, specific to the type."
    )
    model_name: str | None = Field(default=None, description="The model to use for evaluation. Required for LLM-based eval types.")
    provider: ModelProviderName | None = Field(default=None, description="The provider of the evaluation model. Required for LLM-based eval types.")
```

2b. In the `create_eval_config` handler, validate that LLM-based types still provide model_name/provider:

```python
if request.type in (EvalConfigType.g_eval, EvalConfigType.llm_as_judge):
    if not request.model_name or not request.provider:
        raise HTTPException(status_code=400, detail="model_name and provider are required for LLM-based eval types.")
if request.type == EvalConfigType.v2:
    # V2 llm_judge needs model info; others do not
    props = request.properties
    if isinstance(props, dict) and props.get("type") == "llm_judge":
        if not request.model_name or not request.provider:
            raise HTTPException(status_code=400, detail="model_name and provider are required for llm_judge V2 eval type.")
```

### Step 3: Schema regeneration

After steps 1-2, regenerate the OpenAPI schema and TypeScript client:

```bash
KILN_SKIP_REMOTE_MODEL_LIST=true HOME="$TMPDIR/kiln_test_home" uv run python -c "import json; from app.desktop.desktop_server import make_app; print(json.dumps(make_app().openapi(), ensure_ascii=False))" > "$TMPDIR/openapi.json"
(cd app/web_ui && npx openapi-typescript "$TMPDIR/openapi.json" -o src/lib/api_schema.d.ts)
```

Verify with `app/web_ui/src/lib/check_schema.sh`.

### Step 4: Frontend -- `assertNever` utility

**File: `app/web_ui/src/lib/utils/exhaustive.ts`** (new file)

```typescript
export function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`)
}
```

### Step 5: Frontend -- V2 type registry

**File: `app/web_ui/src/lib/utils/eval_types/registry.ts`** (new file)

5a. Define the registry entry interface and the `getV2TypeEntry()` function with a switch over all `V2EvalType` values. Each case returns `{ type, label, description, icon, createFormComponent, resultRendererComponent, requiresTrust }`.

Labels:
| V2EvalType | label | requiresTrust |
|---|---|---|
| `exact_match` | "Exact Match" | false |
| `pattern_match` | "Pattern Match" | false |
| `contains` | "Contains" | false |
| `set_check` | "Set Check" | false |
| `tool_call_check` | "Tool Call Check" | false |
| `step_count_check` | "Step Count Check" | false |
| `llm_judge` | "LLM Judge" | false |
| `code_eval` | "Code Eval" | true |

5b. Export a `V2_EVAL_TYPES` array with all enum values for iteration (e.g. in the type picker).

5c. The `createFormComponent` and `resultRendererComponent` fields initially reference placeholder components that will be replaced in subsequent steps. Or, use lazy component references that resolve to the actual components.

### Step 6: Frontend -- deterministic create forms

Create one Svelte component per deterministic type. Each component:
- Receives a `bind:formData` prop (or uses a store/event dispatch) to communicate its collected `*Properties` data to the container.
- Renders labeled form fields matching the type's properties.
- Validates required fields client-side.

**Files (all new):**

- `app/web_ui/src/lib/components/eval_types/exact_match_form.svelte`
  - Fields: `value_expression` (optional text, with help text about JSON path), `expected_value` OR `reference_key` (radio toggle), `case_sensitive` (checkbox).

- `app/web_ui/src/lib/components/eval_types/pattern_match_form.svelte`
  - Fields: `value_expression` (optional text), `pattern` (text input with regex hint), `mode` (select: must_match / must_not_match).

- `app/web_ui/src/lib/components/eval_types/contains_form.svelte`
  - Fields: `value_expression` (optional text), `substring` OR `reference_key` (radio toggle), `case_sensitive` (checkbox), `mode` (select: must_contain / must_not_contain).

- `app/web_ui/src/lib/components/eval_types/set_check_form.svelte`
  - Fields: `value_expression` (optional text), `expected_set` OR `reference_key` (radio toggle), `mode` (select: subset / superset / equal). `expected_set` uses a FormList for multiple string entries.

- `app/web_ui/src/lib/components/eval_types/tool_call_check_form.svelte`
  - Fields: `expected_tools` (list of ToolCallSpec, each with `tool_name` text + optional `expected_args` as key-value pairs with match_mode select), `match_mode` (select: any / all / ordered / never), `on_unexpected_tools` (select: ignore / fail).

- `app/web_ui/src/lib/components/eval_types/step_count_check_form.svelte`
  - Fields: `count_type` (select: tool_calls / model_responses / turns), `min_count` (optional number), `max_count` (optional number). Client-side validation: at least one of min/max must be set, min <= max.

Each form component must expose a method or reactive prop that returns the fully populated `*Properties` object (including the `type` discriminator field) for the container to POST.

### Step 7: Frontend -- LLM judge form extraction

**File: `app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte`** (new)

Extract the LLM-judge-specific sections from `create_eval_config/+page.svelte`:
- Model picker (suggested cards + AvailableModelsDropdown) -- "Step 1: Select Judge Model"
- Algorithm selector (g_eval / llm_as_judge cards) -- "Step 2: Select Judge Algorithm"
- Advanced prompts collapse (task_description, eval_steps via FormList) -- "Steps 3-4"

Props in:
- `evaluator: Eval`
- `task: Task`
- `spec: Spec | null`

Props out (bound or dispatched):
- `model_name: string | undefined`
- `provider_name: string | undefined`
- `selected_algo: EvalConfigType | undefined` (g_eval or llm_as_judge, used to set `g_eval: true/false` on properties)
- `task_description: string`
- `eval_steps: string[]`
- `formReady: boolean` (true when model + algo are selected)

The `system_prompt` is NOT exposed in the form. It is silently set to `null` (the adapter defaults it).

This component does NOT contain a submit button -- the container owns save.

### Step 8: Frontend -- `code_eval` create form

**File: `app/web_ui/src/lib/components/eval_types/code_eval_form.svelte`** (new)

8a. The form has two fields:
- `code` -- a CodeMirror 6 editor with Python syntax highlighting.
- `timeout_seconds` -- a number input (default 30, min 1, max 300).

8b. CodeMirror must be lazy-loaded:

```svelte
<script lang="ts">
  import { onMount } from "svelte"

  let editorContainer: HTMLDivElement
  let editorView: any = null
  let loading = true

  onMount(async () => {
    const [{ EditorView, basicSetup }, { python }] = await Promise.all([
      import("codemirror"),
      import("@codemirror/lang-python"),
    ])
    editorView = new EditorView({
      doc: defaultCode,
      extensions: [basicSetup, python()],
      parent: editorContainer,
    })
    loading = false
  })
</script>
```

8c. Provide a sensible `defaultCode` scaffold:

```python
def score(output, kiln):
    """Score the output. Return a dict of score_name -> float."""
    return {"score": 1.0}
```

8d. The form exposes the collected `CodeEvalProperties` via a bound prop.

### Step 9: Frontend -- trust gate in create flow

The trust gate logic lives in the container (step 10), not in the `code_eval` form itself.

When the container's save handler detects `type === "code_eval"`:
1. Call `client.GET("/api/projects/{project_id}/code_eval_trust", ...)`.
2. If `data.trusted === false`, show a DaisyUI modal with a warning explaining code execution risks and an "I understand, grant trust" button.
3. On confirmation, call `client.POST("/api/projects/{project_id}/grant_code_eval_trust", ...)`.
4. On success, proceed with the normal save flow.
5. If the user cancels the modal, abort save.

The modal is ephemeral -- it exists only in the create page, not as a global component. Trust persists in memory for the session (Phase 5 design).

### Step 10: Frontend -- refactor create container

**File: `app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/create_eval_config/+page.svelte`**

This is the biggest refactoring step. The page keeps its existing responsibilities (loading eval/task/spec, breadcrumbs, AppPage wrapper) but restructures the form area:

10a. **Type picker section.** Before the form, add a type selection step. Show cards for each V2 type from the registry (`V2_EVAL_TYPES.map(t => getV2TypeEntry(t))`). Also include legacy types ("LLM as Judge" leading to the extracted llm_judge_form). When the user picks a type, the corresponding form component is rendered.

For backward compatibility: if the URL has a query param like `?config_type=g_eval` or `?config_type=llm_as_judge`, skip the type picker and go directly to the LLM judge form (preserving existing links that navigate here).

10b. **Form injection.** Below the type picker, render `svelte:component this={selectedTypeEntry.createFormComponent}` for V2 types, or the extracted `LlmJudgeForm` for legacy types. Bind the form data.

10c. **Test-run panel** (V2 types only). A collapsible section below the form:
- A textarea or structured input for `EvalTaskInput` fields (`final_message`, optionally `trace`, `reference_data`, `task_input`).
- A "Try It" button that calls the test-run endpoint.
- A results area showing returned scores or skip info.
- Loading/error states.

10d. **Save handler.** The FormContainer submit handler branches:
- **Legacy types:** POST with existing payload shape (model_name, provider, type: selected_algo, properties: { eval_steps, task_description }).
- **V2 types:** POST with `{ type: "v2", properties: <V2EvalConfigProperties from child form>, model_name: <if llm_judge>, provider: <if llm_judge> }`.

10e. **Trust gate.** Before V2 save, if the selected type is `code_eval`, execute the trust gate flow (step 9).

10f. **Post-save navigation.** Unchanged from current behavior: respects `next_page` query param, defaults to eval detail page.

### Step 11: Frontend -- per-type result renderers

**Important: Use `get_prompt frontend_design_guide.md` before building these components.** The layouts described below are illustrative guidance, not binding. Build each renderer from the type's available data and the frontend design guide principles.

Create one Svelte component per V2 type for rendering individual eval run results.

**Files (all new, under `app/web_ui/src/lib/components/eval_types/`):**

- `exact_match_result.svelte` -- shows pass/fail, extracted value vs expected value.
- `pattern_match_result.svelte` -- shows pass/fail, the matched pattern, extracted value.
- `contains_result.svelte` -- shows pass/fail, substring, extracted value.
- `set_check_result.svelte` -- shows pass/fail, expected set vs actual set, mode.
- `tool_call_check_result.svelte` -- shows pass/fail, expected tools vs actual tool calls.
- `step_count_check_result.svelte` -- shows pass/fail, actual count vs min/max bounds.
- `llm_judge_result.svelte` -- extract from existing `run_result` page: scores + reasoning/chain_of_thought with truncation and "see all" dialog.
- `code_eval_result.svelte` -- shows scores, skipped_reason/detail if applicable.

Each renderer receives the `EvalRun` (containing `scores`, `intermediate_outputs`, `input`, `output`, etc.) and the `EvalConfig` (for properties context) as props.

### Step 12: Frontend -- update `run_result` page for V2 dispatch

**File: `app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/[eval_config_id]/[run_config_id]/run_result/+page.svelte`**

12a. Import `getV2TypeEntry` from the registry.

12b. In `get_eval_properties()`, handle V2 configs:
- If `eval_config.config_type === "v2"`, show type-specific properties (e.g. "Type: Exact Match", relevant config fields) instead of "Judge Model" / "Model Provider".

12c. In the results table, dispatch rendering per row:
- If the eval config is V2, use `svelte:component this={getV2TypeEntry(config.properties.type).resultRendererComponent}` for each result row.
- If legacy, keep existing rendering (or use the extracted `llm_judge_result.svelte`).

12d. The "Thinking" column should be conditionally shown -- only for types that produce `intermediate_outputs` (llm_judge, code_eval). For deterministic types, hide the column.

### Step 13: Frontend -- update eval detail and eval configs pages

**File: `app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/+page.svelte`**

13a. Where eval configs are listed, show V2 type labels from the registry instead of (or alongside) the generic "v2" config_type string. Use `getV2TypeEntry(config.properties.type).label`.

13b. In the eval config summary cards/rows, show relevant V2 properties (e.g. "Pattern: /regex/" for pattern_match).

**File: `app/web_ui/src/routes/(app)/specs/[project_id]/[task_id]/[spec_id]/[eval_id]/eval_configs/+page.svelte`**

13c. Same treatment: display V2 type label and key properties in the configs comparison table.

**File: `app/web_ui/src/lib/components/run_config_comparison_table.svelte`**

13d. Ensure comparison table tolerates mixed V2/legacy eval configs. V2 configs may not have `model_name` or `model_provider` -- display "N/A" or the V2 type label in those columns.

**File: `app/web_ui/src/lib/utils/formatters.ts`**

13e. Update `eval_config_to_ui_name()` to handle `config_type === "v2"` by reading the properties type and returning the registry label.

### Step 14: npm dependencies

If CodeMirror 6 packages are not already in `package.json`, install them:

```bash
cd app/web_ui && npm install codemirror @codemirror/lang-python
```

These are lazy-loaded at runtime so they do not affect initial bundle size.

### Step 15: Schema check

Verify the generated schema matches:

```bash
app/web_ui/src/lib/check_schema.sh
```

## Tests

### Backend tests

**File: `app/desktop/studio_server/test_eval_api.py`** (or appropriate test file)

Use `get_prompt python_test_guide.md` before writing tests. Run tests with:
```bash
HOME="$TMPDIR/kiln_test_home" UV_CACHE_DIR="/Users/scosman/.cache/uv" uv run python3 -m pytest --benchmark-quiet -q -n auto .
```

Test cases for the test-run endpoint:
- Valid exact_match properties + matching input -> scores `{"score": 1.0}`.
- Valid exact_match properties + non-matching input -> scores `{"score": 0.0}`.
- Valid pattern_match with bad regex -> 400/422 (validation error).
- code_eval without trust -> scores `{}`, skipped_reason `"code_eval_not_trusted"`.
- Invalid properties type -> 400/422.
- Non-existent eval_id -> 404.

Test cases for `CreateEvalConfigRequest` update:
- V2 exact_match without model_name/provider -> success (created).
- Legacy g_eval without model_name -> 400.
- V2 llm_judge without model_name -> 400.

### Frontend tests

**File locations:** colocate `.test.ts` files alongside their components.

Run tests with:
```bash
cd app/web_ui && npm run test_run
```

Registry tests (`app/web_ui/src/lib/utils/eval_types/registry.test.ts`):
- `getV2TypeEntry` returns correct label/description for each type.
- `getV2TypeEntry` with unknown type throws (runtime guard).
- All `V2_EVAL_TYPES` entries have non-empty label and description.
- `code_eval` has `requiresTrust === true`, others `false`.

Create form tests (one per type):
- Renders without errors.
- Produces correct properties shape on form fill.
- Client-side validation rejects invalid input (e.g. step_count_check with neither min nor max).

## Linting and formatting

After all changes, run the full check suite:
```bash
uv run ./checks.sh --agent-mode
```

Fix any issues. Specifically:
- `uv run ruff check --fix` for Python lint.
- `uv run ruff format .` for Python format.
- `cd app/web_ui && npm run format` for frontend format.
- `cd app/web_ui && npm run lint` for frontend lint.
- `cd app/web_ui && npm run check` for Svelte/TS type check.

## UI Signoff

Before marking this phase complete, the implementer must:
1. Manually test the full create flow for each of the 8 V2 types.
2. Verify the test-run panel works for at least one deterministic type and one LLM-backed type.
3. Verify the trust gate modal appears for `code_eval` and correctly grants trust.
4. Verify CodeMirror loads lazily (check network tab for dynamic chunks).
5. Verify the run_result page correctly dispatches to per-type renderers.
6. Verify eval detail and eval configs pages display V2 type labels and properties.
7. Verify backward compatibility: existing LLM judge configs (g_eval, llm_as_judge) still create and display correctly.
8. Screenshot key flows and attach to the PR.

## Out of Scope

- Edit/clone flow for eval configs (future phase).
- Bulk operations on eval configs.
- OS-level sandbox UI or configuration for code_eval.
- Changes to EvalRunner, SSE streaming, or comparison execution.
- E2e Playwright tests (manual UI signoff suffices for this phase).
- Icon design -- use placeholder icons initially; can be refined in a polish pass.
