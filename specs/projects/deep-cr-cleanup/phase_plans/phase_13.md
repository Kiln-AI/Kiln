---
status: complete
---

# Phase 13: Frontend typed form contract

## Overview

Replace the `any`-typed imperative API on V2 eval-type form components with a proper shared interface `EvalTypeFormApi`. The V2 form components expose `getProperties()` and optionally `validate()` — these are called imperatively via `bind:this` in `create_eval_config/+page.svelte`. Currently the bound reference is typed `any` (with eslint-disable) and the registry types `createFormComponent` as `SvelteComponent<any>`. This phase introduces a named interface, narrows the call sites, and removes the eslint-disable suppressions.

## Steps

1. **Define `EvalTypeFormApi` interface** in `registry.ts`:
   ```ts
   export interface EvalTypeFormApi {
     getProperties(): V2EvalConfigProperties
     validate?(): string | null
   }
   ```
   The `getProperties()` return type uses `V2EvalConfigProperties` (the union of all property schema types). Each form's concrete return is a member of that union, so it's assignable. `validate` is optional since only `step_count_check_form` implements it.

2. **Type `createFormComponent` in `V2EvalTypeMetadata`** — change from `typeof SvelteComponent<any>` to `typeof SvelteComponent` (removing `<any>` to avoid the eslint-disable). The Svelte 4 component class constructor type doesn't encode imperative methods, so the form-API contract lives in `EvalTypeFormApi` rather than the component type. Remove both `eslint-disable` comments on lines 52-55.

3. **Narrow `v2FormComponent` in `+page.svelte`** from `any` to `EvalTypeFormApi | undefined`. Remove the `eslint-disable` on line 174. Update the imperative call sites (validate, getProperties) to use the typed reference — the existing `typeof v2FormComponent.validate === "function"` guard is compatible since validate is optional.

4. **Verify** each V2 form component's `getProperties()` return type is assignable to `V2EvalConfigProperties`. The code_eval form returns `CodeEvalProperties & { timeout_seconds?: number }` which is structurally `CodeEvalProperties` (timeout_seconds already exists in the schema). All others return their exact schema type directly.

## Tests

- Existing `registry.test.ts` tests continue to pass (no behavioral changes).
- Existing `npm run check` (svelte-check + tsc) validates the new types are consistent.
- `npm run lint` passes without the removed eslint-disable comments.
- No new runtime tests needed — this is a compile-time type-safety change.
