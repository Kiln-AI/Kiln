---
status: complete
---

# Architecture: Input Transformer UI

Pure frontend (`app/web_ui`), read-only. No backend changes. The plan centers all type-switching in a few small helpers so the exhaustiveness guarantee lives in one place and every surface reuses it.

## 1. Types (`app/web_ui/src/lib/types.ts`)

`KilnAgentRunConfigProperties` is already aliased here. Add:

```ts
export type JinjaInputTransform = components["schemas"]["JinjaInputTransform"]
// Auto-expands to a union the moment the backend adds a second transform type,
// which makes every exhaustive switch below fail to compile until updated.
export type InputTransform = NonNullable<
  KilnAgentRunConfigProperties["input_transform"]
>
```

`InputTransform` deliberately derives from the generated field (`JinjaInputTransform | null`) via `NonNullable`, rather than aliasing `JinjaInputTransform` directly — so when the field becomes `JinjaInputTransform | RegexInputTransform | null`, `InputTransform` becomes the union automatically.

## 2. Helpers (`app/web_ui/src/lib/utils/run_config_formatters.ts`)

This file already holds the run-config display logic and the `const _exhaustive: never` pattern. Add:

```ts
// Single exhaustive switch: the ONLY place that maps a transform type to display strings.
export function getInputTransformDisplay(transform: InputTransform): {
  valueLabel: string // details PropertyList cell
  summaryLabel: string // compact indicator on summary surfaces
  modalSubtitle: string // modal subtitle
} {
  switch (transform.type) {
    case "jinja":
      return {
        valueLabel: "Custom Template",
        summaryLabel: "Custom",
        modalSubtitle: "Type: Custom Jinja2 Template",
      }
    default: {
      const _exhaustive: never = transform.type
      throw new Error(`Unknown input transform type: ${_exhaustive}`)
    }
  }
}

// Narrows the run-config union; returns the transform or null (None / MCP / absent).
export function getRunConfigInputTransform(
  run_config: TaskRunConfig,
): InputTransform | null {
  const t = run_config.run_config_properties.type
  switch (t) {
    case "mcp":
      return null
    case "kiln_agent":
      return run_config.run_config_properties.input_transform ?? null
    default: {
      const _exhaustive: never = t
      throw new Error(`Unknown run config type: ${_exhaustive}`)
    }
  }
}

// Compact label for summary surfaces, or null when absent (drives "only when present").
export function getRunConfigInputTransformSummaryLabel(
  run_config: TaskRunConfig,
): string | null {
  const transform = getRunConfigInputTransform(run_config)
  return transform ? getInputTransformDisplay(transform).summaryLabel : null
}
```

All summary surfaces format their own prefix, e.g. `Input Transform: ${label}`, keeping the helper presentation-neutral.

## 3. Modal component (`app/web_ui/src/lib/ui/run_config_component/input_transform_modal.svelte`)

New component wrapping `Dialog` + `Output`.

- **Props:** `transform: InputTransform`.
- **Exposes:** `show()` (delegates to the inner `Dialog`).
- **Render:**
  - `Dialog` `title="Input Transformer"`, `subtitle={getInputTransformDisplay(transform).modalSubtitle}`.
  - Body switches on `transform.type` (so the body is also exhaustive): for `"jinja"`, `<Output raw_output={transform.template} show_border={true} />`. The `template` field only exists on `JinjaInputTransform`, so this narrowing is required, not optional. `default` → `never` guard.
  - No action buttons; the `Dialog` X + Escape close it.

## 4. `PropertyList` gains an `action` field (mirrors `link`)

The "Custom Template" cell opens the modal via a click handler. Rather than a slot, add a reusable `action` field to `UiProperty`, directly analogous to the existing `link` field (which `getRunConfigUiProperties` already uses for the "Prompt" row, computed by `prompt_link`).

`app/web_ui/src/lib/ui/property_list.ts`:

```ts
export type UiProperty = {
  // ...existing fields...
  link?: string
  // Renders the value as a clickable button invoking this handler (e.g. open a modal).
  // Mutually exclusive with `link` in practice.
  action?: () => void
}
```

`app/web_ui/src/lib/ui/property_list.svelte` — add a branch alongside the existing `link` branch (the file already uses `on:click` for badge buttons at lines 47, 77):

```svelte
{:else if property.action}
  <button class="link text-left" on:click={property.action}>{property.value}</button>
{:else if property.link}
  <a href={property.link} class="link">{property.value}</a>
```

### Wiring the row (covers all three consumer pages)

`getRunConfigUiProperties` gains one optional callback param (just as it already takes `project_id`, `task_id`, etc.), and sets it on the row in the `kiln_agent` branch only, after "Prompt":

```ts
export function getRunConfigUiProperties(
  /* ...existing params... */
  on_view_input_transform?: () => void,
): UiProperty[] {
  // kiln_agent branch:
  const input_transform = run_config.run_config_properties.input_transform ?? null
  // ...after the Prompt entry:
  {
    name: "Input Transformer",
    value: input_transform
      ? getInputTransformDisplay(input_transform).valueLabel // "Custom Template"
      : "None",
    action: input_transform ? on_view_input_transform : undefined, // None → plain text
  }
}
```

Each of the **three** pages that call `getRunConfigUiProperties` adds the modal + callback (run config already in scope on each):

```svelte
<script>
  import InputTransformModal from "$lib/ui/run_config_component/input_transform_modal.svelte"
  import { getRunConfigInputTransform } from "$lib/utils/run_config_formatters"
  let input_transform_modal: InputTransformModal
  $: input_transform = run_config ? getRunConfigInputTransform(run_config) : null
  $: properties = run_config
    ? getRunConfigUiProperties(
        project_id, task_id, run_config, $model_info, task_prompts, $available_tools,
        () => input_transform_modal?.show(),
      )
    : null
</script>

<!-- ...existing <PropertyList {properties} />... -->

{#if input_transform}
  <InputTransformModal bind:this={input_transform_modal} transform={input_transform} />
{/if}
```

The three pages:
1. `optimize/[project_id]/[task_id]/run_config/[run_config_id]/+page.svelte` (`run_config` in scope)
2. `tools/[project_id]/kiln_task/[tool_server_id]/+page.svelte`
3. `prompt_optimization/[project_id]/[task_id]/create_prompt_optimization_job/+page.svelte`

For (2) and (3), if the displayed run config is MCP-typed, `getRunConfigInputTransform` returns null → no modal rendered, and the row never appears (only added in the `kiln_agent` branch): a clean no-op.

## 5. Summary surfaces (all gated on `getRunConfigInputTransformSummaryLabel(...) != null`)

| Surface | File | Integration |
|---|---|---|
| Selector dropdown | `lib/ui/run_config_component/saved_run_configs_dropdown.svelte` | In `build_options`, append `\nInput Transform: ${label}` to the option `description` (both the default-config and other-config branches), kiln_agent only. |
| Compare column header | `routes/(app)/specs/[project_id]/[task_id]/compare/+page.svelte` (~850–903) | Add a centered `text-xs text-gray-500` line under the prompt line: `Input Transform: {label}`. |
| `RunConfigSummary` card | `lib/ui/run_config_component/run_config_summary.svelte` | Add a row after Skills: `Input Transform: {label}` (kiln_agent block). |
| Compare chart | `lib/components/compare_chart.svelte` | In `buildLegendSubtext` add a `{sub|Input Transform: ${label}}` part; in the tooltip builder append `<br/><span style="color:#666;">Input Transform:</span> ${label}`. |
| Compare radar chart | `lib/components/compare_radar_chart.svelte` | Same as compare chart (mirror its legend + tooltip builders). |
| Optimize table | `routes/(app)/optimize/[project_id]/[task_id]/+page.svelte` | **Dedicated column** "Input Transform" inserted right after the "Tools" column (both in the `columns` array and the body `<td>` order), value `getRunConfigInputTransformSummaryLabel(config) ?? "None"` → "None"/"Custom" on every row. This column is the exception to "only when present". |

All read the label from `getRunConfigInputTransformSummaryLabel`; none open the modal.

## 6. Exhaustiveness guarantee — how it triggers

When the backend adds a second transform type and the schema is regenerated:
- `InputTransform` (§1) becomes `JinjaInputTransform | <New>`.
- `getInputTransformDisplay` (§2) and the modal body switch (§3) lose `never` in their `default` → **compile error** at `npm run check`.
- Every surface routes through `getInputTransformDisplay`, so a single fix point updates all of them (plus the modal body, which has its own switch for type-specific rendering).

## 7. Testing

- `run_config_formatters.test.ts`: extend existing tests.
  - `getRunConfigInputTransform`: null for MCP, null for kiln_agent without transform, the transform for kiln_agent with jinja.
  - `getRunConfigInputTransformSummaryLabel`: null when absent, "Custom" for jinja.
  - `getInputTransformDisplay`: returns the three labels for jinja.
- `getRunConfigUiProperties`: asserts the "Input Transformer" row is "None" (no `action`) when absent and "Custom Template" (with `action` set, when a callback is passed) when present; row absent on MCP.
- Component test for `input_transform_modal.svelte`: renders title/subtitle and the template body via `Output`.
- Lint/format/type-check/build per `app/web_ui` checks; OpenAPI client already up to date (no backend change).

## 8. No component design docs

Surface is small and fully specified above. Skip `/components/`.
