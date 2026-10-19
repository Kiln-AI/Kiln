---
status: complete
---

# Phase 1 — Registry Foundation

## Overview

Extend `V2EvalTypeMetadata` with additive fields so the select screen, page header, and form
intro are all data-driven from the registry. Update content (labels, descriptions, tags, titles)
to match the functional spec. Drop qualifier suffixes from labels. Add `EvalTypeTag` type.
Update `registry.test.ts` with invariants for the new fields.

## Steps

1. **Add `EvalTypeTag` type** in `registry.ts`:
   ```ts
   export type EvalTypeTag = { label: string; tone: "default" | "beta" }
   ```

2. **Extend `V2EvalTypeMetadata` interface** with new fields:
   - `recommended?: boolean` — true only for `llm_judge`
   - `tags: EvalTypeTag[]` — per-type tag chips
   - `pageTitle: string` — per-page title (e.g. "Add an LLM Judge")
   - `pageSubtitle: string` — per-page subtitle
   - `explainer?: string` — longer explanation for in-form intro
   - `example?: string` — optional concrete example

3. **Update all 8 cases in `getV2EvalTypeMetadata()`**:
   - Clean labels (drop "(recommended)", "(regex)", "Code: Custom Python Code Eval" suffixes)
   - Update descriptions to match functional spec section 1 table
   - Add `recommended`, `tags`, `pageTitle`, `pageSubtitle` from spec sections 1 and 2
   - Add `explainer` and optional `example` for each type

4. **Update `registry.test.ts`** with new invariants:
   - Every type has non-empty `pageTitle`, `pageSubtitle`, and `tags` array
   - Exactly one type has `recommended: true`
   - The recommended type is `ALL_V2_EVAL_TYPES[0]`
   - Updated expected labels (no qualifier suffixes)
   - Tags have valid tone values ("default" or "beta")
   - `buildV2EvalTypeRegistry` covers the new fields

## Tests

- Assert all types have non-empty `pageTitle` and `pageSubtitle`
- Assert all types have a non-empty `tags` array
- Assert exactly one type has `recommended: true` and it is index 0
- Assert every tag has a valid `tone` ("default" or "beta")
- Assert cleaned labels match expected values (no suffixes)
- Existing tests updated to reflect new label strings
