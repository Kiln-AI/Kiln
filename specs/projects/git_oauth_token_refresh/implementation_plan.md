---
status: complete
---

# Implementation Plan: GitHub OAuth Token Refresh

See `architecture.md` for per-file detail. Each phase is independently reviewable and
ends with the project's automated checks passing.

## Phases

- [ ] **Phase 1 — Token capture & storage (backend)**
  `oauth.py` (`OAuthTokenResult`, `exchange_code_for_token` returns it, `refresh_access_token`,
  `OAuthFlowState` fields), `git_sync_api.py` (callback stores refresh/expiry,
  `OAuthStatusResponse` + `SaveConfigRequest` + `UpdateConfigRequest` carry/persist the new
  fields, auth-mode-switch clears refresh fields), `config.py` (TypedDict fields, `get_*`
  defaults, `update_oauth_tokens` helper), `libs/core/.../config.py` (`sensitive_keys`).
  Tests for oauth + config + api persistence.

- [ ] **Phase 2 — Auto-refresh engine in the manager**
  `errors.py` (`AuthExpiredError`), `git_sync_manager.py` (`project_path` + `_refresh_lock`,
  `_ensure_valid_oauth_token` proactive refresh + persist, call before `fetch`/`push`),
  `registry.py` + call sites (`middleware.py`, `desktop_server.py`) thread `project_path`.
  Tests for proactive refresh, persistence, rotation, concurrency, no-op cases.

- [ ] **Phase 3 — Error classification, reactive refresh, middleware mapping**
  `git_sync_manager.py` (`_is_auth_error`, auth-vs-network branching in `fetch`/
  `commit_and_push`, reactive refresh + single retry, `ensure_fresh*` re-raise
  `AuthExpiredError`), `middleware.py` (`ERROR_MAP` → 401 reconnect message), confirm
  `background_sync` survives `AuthExpiredError`. Tests for classification, reactive path,
  401 mapping, background-sync resilience.

- [ ] **Phase 4 — Frontend plumbing**
  Regenerate OpenAPI bindings (`generate_schema.sh`), then update hand-written types and
  the OAuth-token path: `api.ts`, `oauth_flow.ts`, `oauth_with_install.ts`,
  `git_import_wizard_store.ts`, `step_credentials.svelte`, `import_project.svelte`,
  `step_complete.svelte`, `git_sync_status.svelte`. Update `oauth_flow.test.ts` and
  related tests for the new `onSuccess` payload shape.

## Notes

- Phases 1→2→3 are sequential (3 depends on the manager work in 2; 2 depends on the
  config/capture in 1). Phase 4 depends on Phase 1's backend model changes (for schema
  regen) but is otherwise independent of 2/3.
- Boundary: this project does **not** build recovery UX or fix the `[Object object]`
  task-picker error — that is the separate `git_auth_recovery` project, which consumes the
  401 `AuthExpiredError` introduced here.
