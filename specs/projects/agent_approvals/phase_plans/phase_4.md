---
status: complete
---

# Phase 4: Backfill All Endpoints with Agent Policy Annotations

## Overview

Annotate every FastAPI endpoint in `libs/server/kiln_server/` and `app/desktop/studio_server/` with agent policy annotations using the constructors from `kiln_server.utils.agent_checks.policy`. Then regenerate annotation JSONs and verify exit code 0.

## Policy Assignment Plan

### General Defaults
- GET -> ALLOW_AGENT
- POST -> ALLOW_AGENT
- DELETE -> DENY_AGENT
- PATCH -> agent_policy_require_approval("Allow agent to edit [resource]? ...")

### Category Overrides
- Settings APIs -> DENY_AGENT
- Desktop file system APIs (open folder, file picker) -> DENY_AGENT
- Open logs -> agent_policy_require_approval("This will open an external application to view logs. Allow?")
- MCP server management (connect/edit/archive remote/local MCP) -> DENY_AGENT
- Create fine-tune POST -> agent_policy_require_approval("Creating a fine-tune incurs cost. Allow agent to proceed?")
- Prompt optimization start -> already annotated (keep existing)

## Steps

1. Add `openapi_extra=ALLOW_AGENT` to all GET endpoints (default)
2. Add `openapi_extra=ALLOW_AGENT` to all POST endpoints (default), except overrides
3. Add `openapi_extra=DENY_AGENT` to all DELETE endpoints
4. Add `openapi_extra=agent_policy_require_approval(...)` to all PATCH endpoints
5. Apply category overrides for settings, file system, MCP, fine-tune, etc.
6. Create annotations output directory and run the dump CLI to generate JSONs
7. Verify exit code 0

## Files to Modify

- libs/server/kiln_server/server.py (ping endpoint)
- libs/server/kiln_server/project_api.py
- libs/server/kiln_server/task_api.py
- libs/server/kiln_server/run_api.py
- libs/server/kiln_server/prompt_api.py
- libs/server/kiln_server/spec_api.py
- libs/server/kiln_server/document_api.py
- app/desktop/studio_server/settings_api.py
- app/desktop/studio_server/import_api.py
- app/desktop/studio_server/provider_api.py
- app/desktop/studio_server/tool_api.py
- app/desktop/studio_server/finetune_api.py
- app/desktop/studio_server/eval_api.py
- app/desktop/studio_server/data_gen_api.py
- app/desktop/studio_server/repair_api.py
- app/desktop/studio_server/copilot_api.py
- app/desktop/studio_server/prompt_api.py
- app/desktop/studio_server/skill_api.py
- app/desktop/studio_server/run_config_api.py
- app/desktop/studio_server/prompt_optimization_job_api.py

## Tests

- No new unit tests needed for this phase (annotations are verified via the dump CLI exit code 0 check)
- Verification: Run dump CLI against live OpenAPI spec and confirm exit code 0
