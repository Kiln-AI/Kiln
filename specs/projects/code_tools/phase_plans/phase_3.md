---
status: complete
---

# Phase 3: Desktop API

## Overview

Create the desktop API layer for Code Tools: CRUD endpoints (create, list, get, metadata-only PATCH, archive, delete), a transient test endpoint with agent-run-id lifecycle, agent access policies with approval gates, the CODE group in `available_tools`, and router wiring into `desktop_server.py`. Regenerate the OpenAPI TypeScript client.

## Steps

### 1. Add `CODE` to `ToolSetType` enum in `tool_api.py`

Add `CODE = "code"` to the `ToolSetType` enum.

### 2. Add CODE group to `get_available_tools` in `tool_api.py`

After the existing tool set assembly, add a block that loads non-archived code tools from the project and appends a `ToolSetApiDescription(type=ToolSetType.CODE, set_name="Code Tools", tools=[...])` with each tool's `id=build_code_tool_id(ct.id)`, `name=ct.tool_function_name`, `description=ct.tool_description`.

### 3. Create `code_tool_api.py` in `app/desktop/studio_server/`

Models:
- `CodeToolCreateRequest(BaseModel)`: all functional + metadata fields from CodeTool (name, description, tool_function_name, tool_description, parameters_schema, code, timeout_seconds, tool_allowlist).
- `CodeToolResponse(BaseModel)`: all fields + id, created_at, created_by. Used for all responses returning a code tool.
- `CodeToolUpdateRequest(BaseModel)`: only `name: str | None`, `description: str | None`. Structurally prevents functional field mutation.
- `CodeToolArchiveRequest(BaseModel)`: `archived: bool`.
- `TestCodeToolRequest(BaseModel)`: functional fields + `params: dict[str, Any]`.
- `ToolCallLogEntryResponse(BaseModel)`: mirrors `ToolCallLogEntry` from code_tool.py.
- `TestCodeToolResponse(BaseModel)`: result, error, traceback, not_trusted, stdout, stderr, tool_call_log, duration_ms.

`connect_code_tool_api(app)` function with endpoints:
- `POST /api/projects/{project_id}/code_tools` — create. Approval-gated. Enforce tool_function_name uniqueness among non-archived siblings (400). Construct CodeTool with parent=project, save_to_file().
- `POST /api/projects/{project_id}/test_code_tool` — transient test. Approval-gated. Build transient CodeTool (name="test_run", parent=project). Validate params against parameters_schema. Trust check. Agent-run-id lifecycle: generate_agent_run_id, set_agent_run_id, construct PythonCodeTool with recorder, invoke, cleanup MCP session, clear_agent_run_id in finally. Map ChildOutcome to TestCodeToolResponse. Persist nothing.
- `GET /api/projects/{project_id}/code_tools` — list. ALLOW_AGENT. Return all, archived sorted last.
- `GET /api/projects/{project_id}/code_tools/{code_tool_id}` — get. ALLOW_AGENT. 404 if missing.
- `PATCH /api/projects/{project_id}/code_tools/{code_tool_id}` — update metadata only. ALLOW_AGENT. Only name/description mutable.
- `POST /api/projects/{project_id}/code_tools/{code_tool_id}/archive` — archive/unarchive. ALLOW_AGENT.
- `DELETE /api/projects/{project_id}/code_tools/{code_tool_id}` — delete. DENY_AGENT.

### 4. Wire router into `desktop_server.py`

Import and call `connect_code_tool_api(app)` alongside the other connect calls.

### 5. Regenerate OpenAPI TypeScript client

Run the schema generation tool to update `api_schema.d.ts`.

## Tests

Test file: `app/desktop/studio_server/test_code_tool_api.py` (new).

### CRUD tests:
- `test_create_code_tool_success`: POST creates and returns a valid code tool
- `test_create_code_tool_uniqueness_conflict`: duplicate tool_function_name among non-archived -> 400
- `test_create_code_tool_validation_error`: bad code/schema -> 400
- `test_list_code_tools`: lists all code tools, archived sorted last
- `test_get_code_tool`: returns full artifact by id
- `test_get_code_tool_not_found`: 404 for missing id
- `test_patch_metadata_only`: name/description update works
- `test_patch_preserves_functional_fields`: only name/description changed, functional content unchanged
- `test_archive_unarchive`: toggle archived flag
- `test_delete_code_tool`: removes the artifact
- `test_delete_code_tool_not_found`: 404 for missing id

### Test endpoint tests:
- `test_test_code_tool_success`: transient execution returns result
- `test_test_code_tool_validation_error`: bad schema -> 400
- `test_test_code_tool_params_validation_error`: params don't match schema -> 400
- `test_test_code_tool_not_trusted`: not trusted -> 200 with not_trusted=true
- `test_test_code_tool_error_result`: user code error -> 200 with error/traceback
- `test_nothing_persisted`: no new files after test execution
- `test_test_code_tool_mcp_cleanup`: agent_run_id set/cleared and MCP session cleaned up

### Available tools test:
- `test_available_tools_includes_code_tools`: CODE group appears with non-archived code tools
