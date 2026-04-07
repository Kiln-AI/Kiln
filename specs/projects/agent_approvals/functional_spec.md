---
status: complete
---

# Functional Spec: Agent Approvals

## Overview

Infrastructure for controlling which API endpoints an AI agent can call, which require user approval, and which are blocked entirely. This project covers annotation, validation tooling, and policy backfill — not the approval UI itself.

All code lives in `libs/server/kiln_server/utils/agent_checks/`.

## 1. Endpoint Annotation System

### 1.1 Policy Model

A Pydantic model `AgentPolicy` defines the annotation schema:

```python
class AgentPolicy(BaseModel):
    permission: Literal["allow", "deny"]
    requires_approval: bool
    approval_description: str | None
```

**Validation rules:**
- If `requires_approval` is `True`, `approval_description` must be provided (non-empty string). Raise `ValueError` otherwise.
- If `requires_approval` is `False`, `approval_description` must be `None`. Raise `ValueError` if set.
- If `permission` is `"deny"`, `requires_approval` must be `False`. A denied endpoint can't also require approval. Raise `ValueError` otherwise.

### 1.2 Constructors / Helpers

Three helpers produce `dict` values suitable for FastAPI's `openapi_extra` parameter:

| Helper | Produces |
|--------|----------|
| `DENY_AGENT` | `{"x-agent-policy": {"permission": "deny", "requires_approval": false}}` |
| `ALLOW_AGENT` | `{"x-agent-policy": {"permission": "allow", "requires_approval": false}}` |
| `agent_policy_require_approval(description: str)` | `{"x-agent-policy": {"permission": "allow", "requires_approval": true, "approval_description": description}}` |

- `DENY_AGENT` and `ALLOW_AGENT` are module-level constants (not functions).
- `agent_policy_require_approval` validates that `description` is a non-empty string.
- All three produce the policy under the key `"x-agent-policy"` in the dict.

### 1.3 OpenAPI Representation

The `x-agent-policy` extension appears in the OpenAPI spec under each endpoint's operation object via FastAPI's `openapi_extra` mechanism. The JSON structure matches the `AgentPolicy` model fields.

## 2. Annotation Dump CLI

A CLI tool that reads an OpenAPI spec and writes one JSON file per endpoint into a target folder.

### 2.1 Invocation

```
python -m kiln_server.utils.agent_checks.dump_annotations <source> <target_folder>
```

- `<source>`: Either an HTTP(S) URL (e.g., `http://localhost:8757/openapi.json`) or a local file path. The CLI auto-detects based on whether the string starts with `http://` or `https://`.
- `<target_folder>`: Directory to write JSON files. Created if it doesn't exist.
- Uses `argparse`.

### 2.2 Output Files

One JSON file per endpoint. Filename format: `{method}_{normalized_path}.json`

**Path normalization:**
- Strip leading `/`
- Replace `/` with `_`
- Replace `{` and `}` with empty string (strip them)
- Lowercase everything

Example: `POST /api/projects/{project_id}/tasks` becomes `post_api_projects_project_id_tasks.json`

**JSON content:**

```json
{
  "method": "post",
  "path": "/api/projects/{project_id}/tasks",
  "agent_policy": {
    "permission": "allow",
    "requires_approval": false
  }
}
```

- `method`: lowercase HTTP method
- `path`: original path from OpenAPI spec (with path params intact)
- `agent_policy`: the `x-agent-policy` object if present, or `null` if the endpoint has no annotation

### 2.3 Unannotated Endpoint Handling

After writing all files, the CLI checks for endpoints missing `x-agent-policy`:

- **If all annotated**: exit code 0, print summary (e.g., "42 endpoints processed, all annotated").
- **If any unannotated**: print a warning listing each unannotated endpoint (`METHOD /path`), then exit with code 2. (Standard convention for CLI usage errors.)

### 2.4 Existing Files

The CLI writes files for all endpoints it finds. It does **not** delete existing files in the target folder — old endpoints that no longer exist in the OpenAPI spec will remain. This is intentional: the folder is checked into git, and stale files are needed to serve older client apps.

## 3. Policy Lookup Helper

A class that loads the dumped JSON files and answers policy questions at runtime.

### 3.1 Interface

```python
class AgentPolicyLookup:
    def __init__(self, annotations_dir: str | Path):
        """Initialize with path to folder of annotation JSON files."""

    def get_policy(self, method: str, path: str) -> AgentPolicy:
        """Return the policy for the given method and path.

        Raises AgentPolicyError if the endpoint is unknown (not in annotations).
        """
```

### 3.2 Behavior

- **Lazy loading**: JSON files are not read until the first call to `get_policy`. After that, all files are cached in memory for the lifetime of the instance.
- **Lookup**: Match by normalized method (lowercase) and exact path string.
- **Unknown endpoints**: If no annotation file matches, raise `AgentPolicyError` (a custom exception). This is the fail-safe — unknown endpoints are fully blocked.
- **Unannotated but known endpoints**: If the annotation file exists but `agent_policy` is `null`, also raise `AgentPolicyError`. Unannotated endpoints are treated as blocked until explicitly annotated.

### 3.3 AgentPolicyError

```python
class AgentPolicyError(Exception):
    """Raised when an endpoint has no known policy (fail-safe block)."""
```

## 4. Policy Backfill

Annotate all existing endpoints. Start with the general defaults below, then apply the category-specific overrides.

### 4.1 General Defaults

| Method | Default Policy |
|--------|---------------|
| `GET` | `ALLOW_AGENT` |
| `POST` | `ALLOW_AGENT` |
| `DELETE` | `DENY_AGENT` |
| `PATCH` | `agent_policy_require_approval("Allow agent to edit [resource]? Ensure you backup your project before allowing agentic edits.")` |

The `[resource]` in PATCH descriptions should be a human-readable name derived from the endpoint's context (e.g., "project", "task", "prompt").

### 4.2 Category-Specific Overrides

The following overrides take precedence over the general defaults:

| Category | Policy | Rationale |
|----------|--------|-----------|
| **Settings APIs** (any endpoint managing app/user settings) | `DENY_AGENT` | Settings are not exposed to agents. |
| **Desktop-only file system APIs** (open folder, file picker, etc.) | `DENY_AGENT` | Desktop-only actions, not relevant to agents. |
| **Open logs** | `agent_policy_require_approval(...)` | Opens external app; needs user approval. |
| **MCP server management** (add, remove, edit MCP servers) | `DENY_AGENT` | MCP configuration must not be agent-controlled. |
| **Create fine-tune** (`POST` endpoint that starts a fine-tune job) | `agent_policy_require_approval("Creating a fine-tune incurs cost. Allow agent to proceed?")` | Significant cost implication requires user approval. |
| **Prompt optimization start** (`POST /api/projects/{project_id}/tasks/{task_id}/prompt_optimization_jobs/start`) | `agent_policy_require_approval("Running prompt optimizer uses many credits")` | Note: this endpoint already has a partial annotation that should be replaced with the proper constructor. |

### 4.3 Verification

After backfill, re-run the CLI to regenerate annotation JSONs and verify exit code 0.

### 4.4 Implementation Instructions

Unlike typical phases where the coding agent proceeds autonomously, this phase requires a **propose-then-execute** workflow:

1. The agent must first enumerate **every** API endpoint and propose its intended policy assignment (allow / deny / require approval with description) in a single plan.
2. The human reviews and approves (or adjusts) the plan.
3. Only after approval does the agent proceed with annotating the endpoints.

This is necessary because policy assignment is a judgment call per endpoint, and mistakes could silently grant or block agent access.

## 5. CI Integration

Extend the existing `check_api_bindings.yml` workflow:

1. After the server is running and schema is available, run the dump CLI against `http://localhost:8757/openapi.json` targeting the checked-in annotations folder.
2. Check the exit code — fail the CI job if unannotated endpoints exist (non-zero exit).
3. Diff the generated annotation files against what's checked in — fail if they differ (same pattern as the existing schema check).

## Out of Scope

- Approval UI (dialog, approve/deny buttons, etc.)
- Agent chat client implementation
- Runtime middleware that enforces policies on incoming requests
- Per-user or per-role policy overrides

## Edge Cases

- **Endpoint with multiple methods**: Each method gets its own annotation file and policy. They are independent.
- **Path parameter variations**: Paths are compared as strings with parameter placeholders intact (`{project_id}`), not resolved values.
- **Empty OpenAPI spec**: CLI writes no files, exits 0 (nothing to annotate).
- **Malformed x-agent-policy**: CLI should validate the policy object against the `AgentPolicy` model and report errors (print warning, skip the endpoint, exit with non-zero code).
- **Concurrent access to PolicyLookup**: Not required — single-threaded usage expected.
