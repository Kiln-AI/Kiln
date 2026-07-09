---
status: complete
---

# Phase 3 — Container shell + titles + intro

## Overview

Replace the generic "Add a Judge" page header with per-type titles from the registry, adopt the
`/run`-style two-column layout in `eval_config_builder`, remove the secondary-title block (fixing
the indent), and add an `eval_type_intro` component at the top of the left column.

## Steps

1. **Per-page titles in the route** (`[eval_config_type]/+page.svelte`)
   - Import `getV2EvalTypeMetadata` and look up `pageTitle`/`pageSubtitle` from the registry.
   - Set `AppPage title={meta.pageTitle}` and `subtitle={meta.pageSubtitle}`.
   - Remove the `sub_subtitle` and `sub_subtitle_link` props (the generic "Read the Docs" link).

2. **Two-column shell** (`eval_config_builder.svelte`)
   - Replace the `flex flex-col lg:flex-row gap-6` outer container with the `/run`-page pattern:
     `flex flex-col xl:flex-row gap-8 xl:gap-16`.
   - Left column: keep `flex-1 min-w-0`.
   - Right column: replace `lg:w-[400px]` with `w-72 2xl:w-96 flex-none` (matches `/run`).
   - Drop the bordered box wrapper (`rounded-lg border bg-base-100 p-4`) on the right column.
   - Change the "Test Run" heading from `font-medium text-sm` to `text-xl font-bold` (matches
     `/run`'s column headings).

3. **Remove secondary-title block** (`eval_config_builder.svelte`)
   - Delete the `<div class="flex items-center gap-2 pt-4 mb-2">` block containing the icon +
     label (lines 407-412). This fixes the global indent issue.

4. **New `eval_type_intro` component** (`lib/components/eval_types/eval_type_intro.svelte`)
   - Props: `metadata: V2EvalTypeMetadata`.
   - Renders: icon + label heading + explainer (fallback to description) + optional example.
   - Low-key styling: no background box or border; plain text with a subtle icon accent.

5. **Wire intro into builder** (`eval_config_builder.svelte`)
   - Import `eval_type_intro` and render it at the top of the left column, above the form
     component, passing `{metadata}`.

## Tests

- Route page renders per-type `pageTitle` for each eval type (via `renderBuilderRoutePage`).
- No `sub_subtitle` or "Read the Docs" on the builder route page.
- Two-column shell uses `xl:flex-row` (not `lg:flex-row`).
- Secondary-title block is gone (no `.flex.items-center` icon+label block).
- `eval_type_intro` renders explainer text and icon for each type.
- Right column has no bordered box wrapper.
- Existing builder behavior (trust flow, save flow, test run) still passes.
