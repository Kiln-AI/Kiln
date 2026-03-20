---
status: complete
---

# Architecture: OpenAPI Spec Improvements

## Overview

This project modifies existing FastAPI endpoint definitions and Pydantic models to improve OpenAPI documentation, then updates the Svelte frontend to match. No new modules, classes, or data models are introduced.

## File Inventory

Changes touch two categories of files:

**Backend (Python):**
- `libs/server/kiln_server/` — `project_api.py`, `task_api.py`, `prompt_api.py`, `spec_api.py`, `run_api.py`, `document_api.py`, `server.py`
- `app/desktop/studio_server/` — `provider_api.py`, `repair_api.py`, `settings_api.py`, `data_gen_api.py`, `finetune_api.py`, `eval_api.py`, `run_config_api.py`, `import_api.py`, `tool_api.py`, `skill_api.py`, `prompt_optimization_job_api.py`, `copilot_api.py`, `dev_tools.py`
- `libs/core/kiln_ai/datamodel/` — Pydantic model files for schema descriptions
- Existing test files in both `libs/server/` and `app/desktop/` that reference renamed paths

**Frontend (TypeScript/Svelte):**
- `app/web_ui/src/lib/api_schema.d.ts` — regenerated from OpenAPI spec
- Svelte components and stores that reference renamed paths or changed HTTP methods

## Technical Approach

### Adding Docstrings (Operation Descriptions)

FastAPI uses the handler function's docstring as the OpenAPI `description` field. Add docstrings to handler functions.

```python
# Before
@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    ...

# After
@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    """Delete a project and all its contents."""
    ...
```

For endpoints where the summary already says everything, no docstring is needed.

### Adding Summaries (Operation Summaries)

FastAPI auto-generates summaries from function names. To override, use the `summary=` decorator parameter.

```python
@app.post("/api/projects/{project_id}/runs/edit_tags", summary="Edit Run Tags")
async def edit_tags(...):
```

### Adding Parameter Descriptions

Migrate path parameters from bare arguments to `Annotated` with `Path(description=...)`. Query parameters use `Query(description=...)`.

```python
from typing import Annotated
from fastapi import Path, Query

# Before
async def get_project(project_id: str) -> Project:

# After
async def get_project(
    project_id: Annotated[str, Path(description="The unique identifier of the project.")],
) -> Project:
```

This is a safe transformation — `Path()` with only `description` does not change validation or behavior. The parameter name still comes from the function argument name, and the path template `{project_id}` still matches by name.

### Adding Schema/Property Descriptions

Pydantic model docstrings become OpenAPI schema descriptions. `Field(description=...)` adds property descriptions.

```python
class TaskRun(BaseModel):
    """A single execution of a task, containing input, output, and metadata."""

    input: str = Field(description="The input provided to the task.")
    output: TaskOutput | None = Field(default=None, description="The task output, if completed.")
```

Only add `Field(description=...)` where properties aren't self-evident from the name and type. Many properties on Kiln models already use `Field()` for validation — add `description` to the existing `Field()` call rather than creating a new one.

### Adding Tags

Add `tags=` to each route decorator. One tag per endpoint.

```python
@app.get("/api/projects", tags=["Projects"])
async def get_projects() -> list[Project]:
```

### Renaming Paths

Change the path string in the route decorator. Update the handler function name if it no longer matches.

```python
# Before
@app.post("/api/projects/{project_id}/task")
async def create_task(...):

# After
@app.post("/api/projects/{project_id}/tasks", tags=["Tasks"])
async def create_task(...):
```

### Changing HTTP Methods (Provider Connect)

Change `@app.get` to `@app.post` for the two provider connect endpoints. No body parameters needed — the query parameters remain.

### Frontend Update Strategy

The frontend uses a **generated typed API client**:
1. `generate_openapi.py` or the running server produces the OpenAPI JSON
2. `openapi-typescript` generates `api_schema.d.ts` from it
3. `openapi-fetch` provides a typed `client` object where paths and methods are type-checked

**Update process:**
1. Make all backend changes
2. Start the server and regenerate `api_schema.d.ts` via `app/web_ui/src/lib/generate_schema.sh`
3. Run `npx svelte-check` (TypeScript) — every broken path or changed method surfaces as a compile error
4. Fix each compile error in the frontend
5. For the 2 GET→POST provider connect changes, update `client.GET(...)` to `client.POST(...)`

This is very safe — the type system catches all mismatches.

**Exception: raw `fetch()` calls.** Some components use `fetch()` directly (multipart uploads, SSE streaming). These won't produce type errors. The implementer must grep for raw fetch calls that reference renamed paths and update them manually.

## Testing Strategy

### Existing Tests

Endpoint tests use `TestClient` and reference URL paths directly (e.g., `client.get("/api/projects/...")`). Path renames require updating these test URLs.

### No New OpenAPI Schema Tests

Adding snapshot tests for the full OpenAPI schema would be brittle (any future change breaks the snapshot) and low-value given:
- TypeScript generation + `svelte-check` already validates the schema is well-formed and matches frontend expectations
- `check_schema.sh` detects drift between the running server and the committed schema

### Verification Approach

After all changes:
1. Run existing Python tests (`pytest`) — confirms endpoints still work at the new paths
2. Regenerate `api_schema.d.ts` and run `svelte-check` — confirms frontend compiles against new schema
3. Spot-check the Scalar UI at `/scalar` — confirms descriptions, tags, and grouping render correctly
4. Run the full app and smoke-test key flows — confirms SSE endpoints and provider connects still work

## Risk Areas

### Path(description=...) Side Effects
**Risk:** Adding `Path()` annotations could theoretically change FastAPI's parameter parsing.
**Mitigation:** `Path()` with only `description` set doesn't add validation. Existing tests confirm behavior is preserved.

### SSE Endpoints Remain GET
**Risk:** The 4 SSE mutation endpoints stay as GET, which is non-standard.
**Mitigation:** Descriptions explicitly document the side effects and the EventSource constraint. This is a known trade-off, not an oversight.

### Raw fetch() Calls Missed
**Risk:** Path renames in raw `fetch()` calls (not going through the typed client) could be missed.
**Mitigation:** Grep for old path strings across the frontend after renames. TypeScript won't catch these automatically.
