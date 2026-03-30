---
status: compelete
---

# Implementation Plan: OpenAPI Spec Improvements

Two PRs: first for documentation-only changes (no frontend impact), second for path/method changes (requires frontend updates).

## PR 1: Documentation-Only Changes

- [x] Phase 1: Operation descriptions, summaries, and tags
- [x] Phase 2: Parameter descriptions
- [x] Phase 3: Schema and property descriptions

## PR 2: Functional Changes

- [ ] Phase 4: Path renames, HTTP method changes, and frontend updates
- [ ] Phase 5: Guided manual validation

## Phase Details

### Phase 1: Operation descriptions, summaries, and tags

Add docstrings, `summary=` overrides, and `tags=` to all endpoint decorators across both `libs/server/kiln_server/` and `app/desktop/studio_server/`.

Includes:
- Docstrings for ~150 operations missing descriptions (per functional spec style guide — short and to the point)
- Summary renames: "Edit Tags" disambiguation, repair endpoint summaries, eval endpoint summaries
- `tags=[...]` on every route decorator per the tag grouping in the functional spec
- Clean up `check_entitlements` docstring

### Phase 2: Parameter descriptions

Add `Path(description=...)` and `Query(description=...)` annotations to all ~315 undescribed parameters across both `libs/server/` and `app/desktop/`.

Includes:
- Migrate bare path parameters to `Annotated[str, Path(description=...)]`
- Add `Query(description=...)` to query parameters that lack descriptions
- Standardized descriptions for recurring ID parameters (project_id, task_id, etc.)

### Phase 3: Schema and property descriptions

Add docstrings to ~172 Pydantic model classes and `Field(description=...)` to ~788 properties in `libs/core/kiln_ai/datamodel/` and related model files.

Includes:
- Prioritize high-value schemas: `TaskRun`, `Eval`, `RunConfig`, `Document`, `Project`, `Task`, all `*Properties` eval schemas
- Add `description=` to existing `Field()` calls where possible (don't duplicate)
- Skip properties where name + type are fully self-evident

### Phase 4: Path renames, HTTP method changes, and frontend updates

All breaking API changes shipped together with their frontend fixes.

Backend:
- Singular → plural path standardization (~15 endpoints)
- Run config path unification (3 endpoints)
- Repair endpoint path renames (2 endpoints)
- Eval endpoint path renames (2 endpoints)
- GET → POST for 2 provider connect endpoints
- Update all backend tests referencing renamed paths

Frontend:
- Regenerate `api_schema.d.ts`
- Fix all TypeScript compile errors from path/method changes
- Grep for raw `fetch()` calls referencing old paths and update them

### Phase 5: Guided manual validation

Guided walkthrough to verify all changes render correctly. The implementer runs through each check with the user, confirming results before proceeding.

**Prerequisites:** Start the desktop app server and open Scalar UI at `/scalar`.

**Checklist:**

1. **Tags render correctly**
   - Open the Scalar UI. Confirm all endpoints are grouped under the expected tags from the functional spec.
   - Confirm no endpoints are untagged or in a "default" group.

2. **Descriptions spot-check**
   - Pick 5 endpoints that previously had no description. Confirm descriptions appear and follow the style guide (short, to the point).
   - Check the `run` vs `runs` endpoints — confirm descriptions clearly distinguish execution vs storage.
   - Check the repair endpoints — confirm "Generate Repair" and "Save Repair" summaries and descriptions are clear.
   - Check the eval execution endpoints — confirm the renamed summaries are unambiguous.

3. **Parameter descriptions spot-check**
   - Expand 3-4 endpoints in Scalar. Confirm path parameters show descriptions.
   - Confirm `project_id` and `task_id` descriptions appear consistently.

4. **Schema descriptions spot-check**
   - Check 3-4 schemas in Scalar. Confirm model-level and property-level descriptions appear.
   - Check at least one `*Properties` eval schema.

5. **Path renames verified**
   - Confirm no singular `/task/`, `/spec/`, `/eval/` paths remain (all should be plural).
   - Confirm run config endpoints are under `/run_configs`.
   - Confirm repair endpoints show `/generate_repair` and `/save_repair`.

6. **HTTP method changes verified**
   - Confirm provider connect endpoints show as POST in Scalar.
   - Confirm the 4 SSE endpoints still show as GET with side-effect documentation in their descriptions.

7. **Frontend smoke test**
   - Create a project, create a task — confirms project/task paths work.
   - Navigate to runs, documents, evals pages — confirms key read paths work.
   - If possible, trigger a provider connect — confirms GET→POST change works end-to-end.
