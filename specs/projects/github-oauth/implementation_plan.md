---
status: complete
---

# Implementation Plan: GitHub OAuth for Git Sync

## Phases

- [ ] Phase 1: Backend OAuth module and API endpoints — `oauth.py` (flow manager, PKCE, GitHub API resolution, token exchange, install URL builder), three new endpoints in `git_sync_api.py` (start, callback, authorize redirect, status), data model changes (`config.py`, request/response models), credential plumbing (`clone.py`, `GitSyncManager`, `registry.py`). Unit tests for all.
- [ ] Phase 2: Frontend OAuth flow — `oauth_flow.ts` shared helper, `step_credentials.svelte` rework (OAuth/PAT toggle for GitHub, polling UI), `api.ts` new types and functions, `import_project.svelte` state plumbing for `oauth_token`. Update OpenAPI schema. Frontend tests.
- [ ] Phase 3: Edit project re-auth — `git_sync_status.svelte` update (OAuth re-auth for GitHub projects, mode toggle, `updateConfig` with `oauth_token`). Frontend tests.
