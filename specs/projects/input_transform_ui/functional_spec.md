---
status: complete
---

# Functional Spec: Input Transformer UI

Read-only UI surfacing whether a run config has an input transformer, and letting the user inspect it. UI design is folded into this spec (the surface is modest).

> **Open questions resolved with the user (Q&A):**
> 1. Modal subtitle → **transform type** ("Type: Custom Jinja2 Template"). A transform has no ID of its own.
> 2. Indicator surfaces → **all** of: details PropertyList, selector dropdown, compare column headers, `RunConfigSummary` card, comparison charts (legend subtext **and** tooltip), and the optimize-page table. Indicator string is **"Input Transform: Custom"**.
> 3. On all summary surfaces, show the indicator **only when a transform is present** (absent is ~99% of cases, so when present it earns the space).
> 4. Modal body → **reuse `Output` as-is** (word-wrapping; no nowrap change).

## 1. Background / Data Model (read-only consumer)

The backend already ships (generated TypeScript in `app/web_ui/src/lib/api_schema.d.ts`):

```ts
JinjaInputTransform: { type: "jinja"; template: string }
// on KilnAgentRunConfigProperties:
input_transform?: components["schemas"]["JinjaInputTransform"] | null
```

Facts that shape the UI:

- The field is **optional + nullable**. `null`/absent = **no transform** (the common case, current behavior).
- A transform currently has **no ID of its own** — it is just `{ type, template }`. (This is why "ID: N" in the brief can't be a transform ID — see §4.)
- The field only exists on `KilnAgentRunConfigProperties` (`type: "kiln_agent"`), **not** on `McpRunConfigProperties`. MCP run configs never show an input transformer.
- Today the generated type is effectively a single-member union (`JinjaInputTransform | null`). The UI must switch on `transform.type` with an exhaustive `never` default so that when the backend adds a second transform type (the union becomes `JinjaInputTransform | <New> | null`), the UI **fails to compile** until updated.

## 2. Feature: "Input Transformer" row on the run config details properties list

The run config details properties list is built by `getRunConfigUiProperties()` in
`app/web_ui/src/lib/utils/run_config_formatters.ts`. That function is reused on **three** pages:

1. Run config details — `optimize/[project_id]/[task_id]/run_config/[run_config_id]/+page.svelte` (the page in the brief)
2. Kiln-task tool page — `tools/[project_id]/kiln_task/[tool_server_id]/+page.svelte`
3. Prompt-optimization job creation — `prompt_optimization/[project_id]/[task_id]/create_prompt_optimization_job/+page.svelte`

Adding the row in `getRunConfigUiProperties` makes it appear on all three (the brief's "make this work anywhere it's used").

**Behavior** (only in the `kiln_agent` branch — MCP run configs are unchanged):

- Add a property named **"Input Transformer"**, placed logically in the list (proposed: after "Prompt").
- Value:
  - **No transform** (`input_transform` null/absent): renders the text **"None"** (gray, like other empty values).
  - **Jinja transform** (`type: "jinja"`): renders **"Custom Template"** as a clickable link/button that opens the modal (§3).
- Future transform types: a `never`-exhaustive switch on `transform.type` means an unhandled new type is a compile error.

**Why a link, not navigation:** the value opens a modal, so it can't use `UiProperty.link` (an `<a href>`). The cell uses `PropertyList`'s existing `use_custom_slot` mechanism; each of the three pages supplies the slot wiring (shared via a small reusable component — see architecture). Pages where the run config is MCP-typed simply never get the row.

## 3. Feature: Input Transformer modal

Reuses the standard `Dialog` (`app/web_ui/src/lib/ui/dialog.svelte`) and the copyable `Output` control (`app/web_ui/src/lib/ui/output.svelte`).

- **Title:** "Input Transformer"
- **Subtitle:** **"Type: Custom Jinja2 Template"** (the transform's type; a transform has no ID of its own). Derived via an exhaustive switch on `transform.type` so a new backend type forces an update here too.
- **Body:** the transform's `template` string in a copyable monospace block via `Output` (`raw_output={template}`). `Output` has a built-in copy-to-clipboard button. Reused **as-is** — long lines word-wrap (no nowrap change).
- **Close:** standard `Dialog` close button (X) + Escape. No action buttons needed.
- **Anything else** (answering the brief's question): the type is conveyed by the subtitle and the copy control is built into `Output`. Nothing else is needed for a clean read-only inspector. (No Jinja docs link is added — no such docs page exists in the app yet.)

## 4. Feature: Input transformer indicator on other run config summaries

Surface the transformer anywhere a run config is summarized (model + prompt). The indicator string is **"Input Transform: Custom"** and appears **only when a transform is present** (so on the ~99% "None" configs nothing is added; when present it earns the space). None of these summaries open the modal — modal-on-click is required **only on the details page** (§3). All six surfaces are included:

1. **Run config selector dropdown** — `SavedRunConfigurationsDropdown` (`app/web_ui/src/lib/ui/run_config_component/saved_run_configs_dropdown.svelte`), used on `/run`, the compare page, prompt-optimization, and add-tool. Each option's description shows `Model: … / Prompt: …`; add an `Input Transform: Custom` line when present.
2. **Compare page column headers** — inline model/prompt summary per column in `specs/[project_id]/[task_id]/compare/+page.svelte`. Add a small centered gray line when present.
3. **`RunConfigSummary` card** — `app/web_ui/src/lib/ui/run_config_component/run_config_summary.svelte` (used in the eval `compare_run_configs` table). Add a row when present.
4. **Comparison charts** — `compare_chart.svelte` and `compare_radar_chart.svelte`. Add the indicator in **both** the legend subtext and the hover tooltip, when present.
5. **Optimize-page run configs table** — `optimize/[project_id]/[task_id]/+page.svelte`. **Exception to the only-when-present rule:** add a dedicated **"Input Transform"** column positioned immediately right of the "Tools" column, showing **"None"** or **"Custom"** for every row (value = `getRunConfigInputTransformSummaryLabel(config) ?? "None"`). This replaces the earlier inline badge approach.

The per-type label ("Custom") comes from the same exhaustive helper as everywhere else (§5), so a new backend transform type forces an update here too. **Not** included: the prompt-optimization job page (`prompt_optimization/.../prompt_optimization_job/[job_id]/+page.svelte`) shows model only and is not a model+prompt summary.

## 5. Typing / exhaustiveness contract

- Introduce a typed alias for the transform (e.g. re-export `JinjaInputTransform`, and an `InputTransform` union alias) in `app/web_ui/src/lib/types.ts`, mirroring the existing `RunConfigProperties` aliases.
- All rendering logic switches on `transform.type` and ends with the repo's standard exhaustiveness guard:
  ```ts
  default: {
    const _exhaustive: never = transform_type
    throw new Error(`Unknown input transform type: ${_exhaustive}`)
  }
  ```
- The `null`/absent case ("None") is handled **before** the type switch, so the switch is purely over present transform types.

## 6. Edge cases

- **MCP run configs:** never have `input_transform`; no row, no indicator. (Enforced by only touching the `kiln_agent` branch.)
- **`input_transform` absent vs explicitly null:** treated identically as "None".
- **Empty template string:** still a present "jinja" transform → "Custom Template" + modal showing an empty body. (Backend save-validation prevents truly invalid templates; empty-but-valid is possible.)
- **Loading state:** the row follows the page's existing loading pattern; no transform-specific loading is required (the transform travels with the already-fetched run config).

## 7. Out of scope

- Creating/editing/deleting input transformers in the UI (read-only display only).
- Rendering/previewing the transform's output against sample input.
- Any backend change.

## 8. Testing

- Unit tests for the new formatter/helper(s) in `run_config_formatters.test.ts` style: "None" when absent, "Custom Template" for jinja, exhaustiveness over `type`.
- Component test that the modal shows the template body and is copyable (follow existing `Dialog`/`Output` test patterns).
- Verify the row appears on all three `getRunConfigUiProperties` consumers and the selected summary surfaces.
