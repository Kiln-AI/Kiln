---
status: complete
---

# Phase 4: Web UI

## Overview

Build the full web UI for Code Tools: add-tools cards, a two-step create wizard (Define + Code & Test), a detail page for saved tools, tools-index integration, and `code_tool_helpers.ts` with vitest unit tests. All UI reuses existing components (SchemaSection, CodeEditor, tools_selector, Output, etc.) and follows existing page/route conventions.

## Steps

### 1. Add `code_tool_helpers.ts` — typed placeholder codegen, import-helper, examples

New file `app/web_ui/src/lib/utils/code_tool_helpers.ts`:
- `generateCodeToolPlaceholder(schema, toolDescription)`: generates a typed `def run(...)` stub from `parameters_schema`. Maps JSON Schema types to Python types (string->str, integer->int, number->float, boolean->bool, array->list[<item>], object->dict). Optional properties (not in `required`) get `| None = None`. Includes docstring from `tool_description` and `# TODO: implement` marker.
- `generateImportHelper(functionName)`: returns the import block string.
- `shouldInsertImport(currentCode)`: returns true if code doesn't contain `from kiln import tools`.
- `generateExamples()`: returns array of {label, code} for the examples dialog (parallel-with-retries, async fan-out, json.loads filtering).

### 2. Add `code_tool_helpers.test.ts` — vitest unit tests

New file `app/web_ui/src/lib/utils/code_tool_helpers.test.ts`:
- Test typed param generation for each type (string, int, float, bool, array, object, nested).
- Test optional params get `| None = None`.
- Test zero-arg tools produce `def run()`.
- Test import-helper idempotence (never duplicated).
- Test shouldInsertImport detection.
- Test never-clobber rule: placeholder only fills empty or exact-match code.

### 3. Update `tools_selector.svelte` — add `code` to `tool_set_order`

Add `"code"` to the `tool_set_order` array so code tools appear in the tools picker dropdown.

### 4. Update `add_tools/+page.svelte` — add Code Tool cards

- Remove the "Control GitHub" card from `sampleRemoteMcpServers`.
- Add "Code Tool" card to the `sample_tools` suggested carousel.
- Add "Code Tool" entry in the Custom Tools `KilnSection`.
- Both navigate to `/tools/${project_id}/add_tools/code_tool`.

### 5. Update tools index `+page.svelte` — show code tool rows

- Fetch code tools via `GET /api/projects/{project_id}/code_tools`.
- Render rows: Name = display name, Type = "Code Tool", Description = tool_description, Status = Ready/Archived.
- Row click navigates to `/tools/${project_id}/code_tools/${id}`.
- Include in `is_empty` check.

### 6. Create `code_tool/+page.svelte` + `+page.ts` — two-step wizard

Route: `tools/[project_id]/add_tools/code_tool/`.
Single route with two steps managed via local state variable.

**Step 1 — Define**: AppPage + FormContainer with fields: Name (display name), Tool Name (function name with tool_name_validator), Description (model-facing tool_description), Parameters (SchemaSection structured mode only — no plaintext toggle). Submit = "Continue" → advances to step 2.

**Step 2 — Code & Test**: Two-column layout. Left: CodeEditor pre-filled with generated placeholder. Right top: tools_selector for allowlist. Right bottom: test panel (code_tool_test_panel.svelte). Below editor: Collapse "Advanced" with timeout field. Create button at bottom. Import-helper: when tools selected and code missing `from kiln import tools`, prepend import. Trust dialog (stopgap). warn_before_unload. Save-without-testing confirm.

### 7. Create `code_tool_test_panel.svelte` — shared test panel component

Reusable component for both create flow and detail page.
- Inputs: generates form from `parameters_schema` via RunInputFormElement.
- Warning line: "Runs your code live against real tools — side effects included." (with TODO for security string sign-off).
- Run button → POST test endpoint → spinner/cancel.
- Trust intercept: `not_trusted` → show trust dialog (stopgap via checkCodeEvalTrust/grantCodeEvalTrust).
- Results: Output component for result, tool_call_log table, error display, duration badge.

### 8. Create `code_tools/[code_tool_id]/+page.svelte` + `+page.ts` — detail page

- AppPage with breadcrumbs, action buttons (Edit, Clone, Archive/Unarchive).
- PropertyList for metadata (Type, Function Name, Timeout, Created).
- CodeEditor in readonly mode.
- Tool Access section showing allowlisted tools.
- Test panel (code_tool_test_panel.svelte).
- EditDialog for name (+ description if P2 ships).
- Clone action → navigate to create flow with pre-filled state.
- Archive/Unarchive toggle.
- Delete via DeleteDialog.

### 9. Add types to `types.ts`

Add `CodeToolResponse` type alias from `components["schemas"]["CodeToolResponse"]`.

## Tests

### code_tool_helpers.test.ts (new):
- `test_placeholder_string_param`: string -> str
- `test_placeholder_integer_param`: integer -> int
- `test_placeholder_number_param`: number -> float
- `test_placeholder_boolean_param`: boolean -> bool
- `test_placeholder_array_param`: array -> list[<items_type>]
- `test_placeholder_object_param`: object -> dict
- `test_placeholder_optional_params`: not-required -> `| None = None`
- `test_placeholder_zero_args`: empty properties -> `def run()`
- `test_placeholder_mixed_required_optional`: combined required + optional
- `test_import_helper_content`: correct import string with function name
- `test_should_insert_import_true`: returns true when import missing
- `test_should_insert_import_false`: returns false when import present
- `test_import_idempotence`: import block never duplicated
- `test_examples_content`: examples array has expected structure and count
