---
status: complete
---

# Phase 2: Select Eval Type Screen

## Overview

Rebuild `create_eval_config/+page.svelte` from a flat card grid into a recommended-hero +
"All judge types" list layout, data-driven from `ALL_V2_EVAL_TYPES`. Three new presentational
components under `lib/components/eval_types/select/`. Updated page header copy; secondary
heading and docs link removed.

## Steps

1. **Create `eval_type_tags.svelte`** (`lib/components/eval_types/select/eval_type_tags.svelte`)
   - Renders `EvalTypeTag[]` as DaisyUI badge chips.
   - Default tone: `badge badge-outline`. Beta tone: `badge-primary badge-outline`.

2. **Create `eval_type_hero.svelte`** (`lib/components/eval_types/select/eval_type_hero.svelte`)
   - Props: `metadata: V2EvalTypeMetadata`. Dispatches `continue` event.
   - Heavier card (bg-base-200, stronger border), icon + name + Recommended chip + description +
     tags + right-aligned Continue button.

3. **Create `eval_type_row.svelte`** (`lib/components/eval_types/select/eval_type_row.svelte`)
   - Props: `metadata: V2EvalTypeMetadata`. Dispatches `select` event.
   - Lighter row: small icon + name (semibold) + inline tags + description beneath + right chevron.
     Entire row is a `<button>`.

4. **Rebuild `create_eval_config/+page.svelte`**
   - Title "Add a Judge", new subtitle, no sub_subtitle/docs link.
   - Remove "Select Eval Type" secondary heading + description.
   - Hero from `ALL_V2_EVAL_TYPES[0]`; list from the rest.
   - Reuse existing `select_v2_type()` for navigation.

## Tests

- Hero renders for the recommended type with name, description, tags, Continue button.
- "All judge types" list renders the remaining 7 types.
- Click hero Continue calls `goto` with the correct path.
- Click list row calls `goto` with the correct path.
- Query params (next_page, save_as_default) are preserved on navigation.
- Tags render with correct tone classes (beta vs default).
