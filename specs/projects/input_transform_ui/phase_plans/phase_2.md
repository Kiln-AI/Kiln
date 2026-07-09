---
status: complete
---

# Phase 2: Summary Surfaces

## Overview

Add the "Input Transform: Custom" indicator to all six summary surfaces where a run config is displayed. The indicator appears only when a transform is present (the common case is absent). All surfaces reuse `getRunConfigInputTransformSummaryLabel` from Phase 1.

## Steps

1. **Selector dropdown** (`saved_run_configs_dropdown.svelte`): Import `getRunConfigInputTransformSummaryLabel`. In `build_options`, for both the default-config and other-config branches (kiln_agent only, not MCP), append `\nInput Transform: ${label}` to the option `description` when the label is non-null.

2. **Compare page column headers** (`compare/+page.svelte`): Import `getRunConfigInputTransformSummaryLabel`. After the prompt display line (~line 899), add a centered `text-xs text-gray-500` line showing `Input Transform: {label}` when label is non-null.

3. **RunConfigSummary card** (`run_config_summary.svelte`): Import `getRunConfigInputTransformSummaryLabel`. In the kiln_agent block (after Skills line), add a `<div>` showing `Input Transform: {label}` when label is non-null.

4. **Compare chart** (`compare_chart.svelte`): Import `getRunConfigInputTransformSummaryLabel`. In `buildLegendSubtext`, append `{sub|Input Transform: ${label}}` when label is non-null. In the tooltip formatter, append `<br/><span style="color: #666;">Input Transform:</span> ${label}` when label is non-null.

5. **Compare radar chart** (`compare_radar_chart.svelte`): Same as compare chart -- add the indicator in `buildLegendSubtext` and in `buildRunConfigTooltip`.

6. **Optimize-page table** (`optimize/[project_id]/[task_id]/+page.svelte`): Import `getRunConfigInputTransformSummaryLabel`. In the model cell of each table row, when the label is non-null, render a small inline badge span `<span class="badge badge-xs">Custom</span>` next to the model name.

## Tests

- Test `getRunConfigInputTransformSummaryLabel` returns null for MCP configs (already covered in Phase 1 tests).
- Test `getRunConfigInputTransformSummaryLabel` returns null for kiln_agent without transform (already covered).
- Test `getRunConfigInputTransformSummaryLabel` returns "Custom" for kiln_agent with jinja transform (already covered).
- Phase 1 tests already provide comprehensive coverage for the summary helper. No additional unit tests needed since the Svelte integration is template-level wiring (import + conditional render) and the helper is already fully tested.
