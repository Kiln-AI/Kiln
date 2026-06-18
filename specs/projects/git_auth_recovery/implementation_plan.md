---
status: complete
---

# Implementation Plan: Git Creds Error Recovery

Phases are ordered so each is independently reviewable and committable. Phase 1 is
shippable on its own (fixes the broken error display + misleading message). Phases
2–3 deliver the git re-import recovery. Phase 4 adds local-folder import parity.

See `functional_spec.md` and `architecture.md` for details.

## Phases

- [x] **Phase 1 — Error envelope + auth classification (backend).**
  Middleware error bodies `{"detail": …}` → `{"message": …}` (all sites). Add
  `GitAuthError`; classify auth failures in `GitSyncManager.fetch()`; widen
  `ensure_fresh`/`ensure_fresh_for_read` `except` to `GitSyncError` so it propagates;
  map `GitAuthError` → 401 in the middleware `ERROR_MAP`. Update affected backend
  tests. (Spec: Part A, Part B.)

- [x] **Phase 2 — Git re-import recovery (backend).**
  Add `remove_project_from_config` (libs/core); add the `_deregister_project`
  app-layer wrapper and refactor `delete_project` to use it; add
  `remove_conflicting_id` to `SaveConfigRequest` and the de-register-then-save path in
  `api_save_config`. (Spec: Part C.1–C.3 backend.)

- [x] **Phase 3 — Recovery UI (frontend).**
  Subtle "Re-import project?" link in `select_tasks_menu.svelte` error state + the
  `import_project_url` prop wiring (setup vs app); typed `GitSyncRequestError` +
  `is_duplicate_project_error` + `remove_conflicting_id` in `git_sync/api.ts`; red
  "Remove existing and re-sync" button + `run_save` refactor in `step_complete.svelte`.
  Regenerate OpenAPI bindings. (Spec: Part C.1 entry, C.3–C.4 frontend.)

- [ ] **Phase 4 — Local-folder import parity.**
  `remove_conflicting_id` query param on `POST /api/import_project` (libs/server, via
  the core helper); red "Remove existing and re-import" button on the local-file step
  in `import_project.svelte` using `response.status === 409`. Regenerate bindings.
  (Spec: Part C.5.)
