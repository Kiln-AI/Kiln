---
status: draft
---

# Phase 1: Core -- types, helpers, modal, details row

## Overview

Add read-only UI for inspecting input transformers on run config details pages. This includes type aliases, exhaustive helper functions, the InputTransformModal component, a new `action` field on `UiProperty`/`PropertyList`, and wiring the "Input Transformer" row + modal on all three `getRunConfigUiProperties` consumer pages. Unit and component tests included.

## Steps

1. **Add type aliases** in `app/web_ui/src/lib/types.ts`:
   - `JinjaInputTransform` re-exported from generated schema
   - `InputTransform` derived via `NonNullable<KilnAgentRunConfigProperties["input_transform"]>`

2. **Add helper functions** in `app/web_ui/src/lib/utils/run_config_formatters.ts`:
   - `getInputTransformDisplay(transform: InputTransform)` -- exhaustive switch returning `{ valueLabel, summaryLabel, modalSubtitle }`
   - `getRunConfigInputTransform(run_config: TaskRunConfig)` -- narrows union, returns transform or null
   - `getRunConfigInputTransformSummaryLabel(run_config: TaskRunConfig)` -- compact label or null

3. **Add `action` field** to `UiProperty` in `app/web_ui/src/lib/ui/property_list.ts`:
   - `action?: () => void` -- renders value as clickable button

4. **Update `PropertyList` component** (`app/web_ui/src/lib/ui/property_list.svelte`):
   - Add `{:else if property.action}` branch before the `{:else if property.link}` branch

5. **Add "Input Transformer" row** to `getRunConfigUiProperties` in `run_config_formatters.ts`:
   - New optional parameter `on_view_input_transform?: () => void`
   - Row placed after "Prompt", value is "Custom Template" (with action) or "None" (plain text)
   - Only in `kiln_agent` branch

6. **Create `InputTransformModal` component** at `app/web_ui/src/lib/ui/run_config_component/input_transform_modal.svelte`:
   - Props: `transform: InputTransform`
   - Exposes `show()` method
   - Uses `Dialog` with title/subtitle and `Output` for body
   - Exhaustive switch on `transform.type` for body content

7. **Wire modal on consumer page 1** -- `optimize/[project_id]/[task_id]/run_config/[run_config_id]/+page.svelte`:
   - Import modal + helper, add callback to `getRunConfigUiProperties`, render modal conditionally

8. **Wire modal on consumer page 2** -- `tools/[project_id]/kiln_task/[tool_server_id]/+page.svelte`:
   - Same pattern as page 1

9. **Wire modal on consumer page 3** -- `prompt_optimization/[project_id]/[task_id]/create_prompt_optimization_job/+page.svelte`:
   - Same pattern as page 1

## Tests

- `getRunConfigInputTransform`: null for MCP, null for kiln_agent without transform, the transform object for kiln_agent with jinja
- `getRunConfigInputTransformSummaryLabel`: null when absent, "Custom" for jinja
- `getInputTransformDisplay`: returns correct three labels for jinja
- `getRunConfigUiProperties`: "Input Transformer" row is "None" (no action) when absent, "Custom Template" (with action) when present and callback provided; row absent for MCP
- Component test for `InputTransformModal`: renders title, subtitle, and template body
