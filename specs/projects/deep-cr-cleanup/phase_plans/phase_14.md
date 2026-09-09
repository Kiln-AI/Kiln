---
status: complete
---

# Phase 14: Frontend Cleanups

## Overview

Four targeted frontend cleanups: collapse a dead ternary in `formatEvalConfigName`, remove a dead union member from `exact_match_form.svelte`, deduplicate the repeated `as`-cast property extraction across 7 V2 result components into a shared type-guard util, and replace a local mirror type with the generated schema type in `tool_call_check_result.svelte`.

## Steps

1. **4.1 — Collapse dead ternary in `formatEvalConfigName`** (`formatters.ts:340-345`). The V2 compact and non-compact branches both produce `eval_config.name + " — " + typeName`. Collapse to a single expression removing the ternary.

2. **4.5 — Remove dead `"value_expression"` union member** (`exact_match_form.svelte:22`). The `source` variable's type includes `"value_expression"` but no UI option sets it and the initializer never resolves to it. Remove it from the union type, leaving `"expected_value" | "reference_key"`.

3. **4.6 — Create `extractV2Props` type-guard util** in `registry.ts` (alongside the existing `getV2TypeFromEvalConfig`). The pattern repeated across all 7 result components is:
   ```ts
   $: props =
     eval_config?.properties && "type" in eval_config.properties
       ? (eval_config.properties as { type: "X", ... })
       : null
   ```
   The util signature: `extractV2Props<T extends V2EvalType>(eval_config: EvalConfig | null, expectedType: T): V2PropsMap[T] | null`. Uses a type map keyed by V2 eval type discriminator to return the correct schema type. Returns `null` when `eval_config` is null, properties missing, or type doesn't match. Convert all 7 result components + `code_eval_result` (8 total) to use it.

4. **4.7 — Import `ToolCallSpec` from schema** (`tool_call_check_result.svelte`). Replace the local `type ToolCallSpec = { ... }` with `import type { components } from "$lib/api_schema"` and `type ToolCallSpec = components["schemas"]["ToolCallSpec"]`. Remove the local mirror type.

## Tests

- **extractV2Props unit tests**: test that it returns typed props on match, null on type mismatch, null on null eval_config, null on missing properties.
- Existing result component tests continue to pass (they exercise the rendering with and without eval_config).
- `npm run check` confirms type safety across all converted call sites.
