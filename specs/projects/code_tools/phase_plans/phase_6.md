---
status: complete
---

# Phase 6: Trust Integration

Implements the trust gate for Code Tools, closing two gaps: (1) the create endpoint was not trust-gated, and (2) project imports had no trust confirmation step.

## Part 1 -- Session-scoped code-execution trust on CREATE

### Backend

- `code_tool_api.py`: the CREATE endpoint now checks `is_code_eval_trusted(str(project.path))` before persisting. If untrusted, returns `CodeToolCreateResponse(not_trusted=True)` (HTTP 200, same shape as the test endpoint's not-trusted response).
- New response model `CodeToolCreateResponse` extends `CodeToolResponse` fields with a `not_trusted: bool = False` flag, mirroring `TestCodeToolResponse`.
- Existing TEST + RUN trust gates confirmed intact (no changes needed).

### Frontend

- Factored the inline trust dialog from `code_tool_test_panel.svelte` into a shared `CodeTrustDialog` component at `lib/components/code_tools/code_trust_dialog.svelte`.
- The test panel now uses `CodeTrustDialog` via binding; on trust grant it retries the test.
- The create wizard (`+page.svelte`) detects `not_trusted` in the create response, shows the same `CodeTrustDialog`, and on trust grant retries `do_create()`.

### Tests

- `test_code_tool_api.py`: existing create tests patched to pass trust; new `test_create_not_trusted` verifies the not-trusted response.

## Part 2 -- Import-time project trust gate

### Backend

- `POST /api/import_project` (`project_api.py`): new `trusted: bool = False` query param. When false/missing, returns HTTP 400 with message "Import cancelled: you must confirm you trust this project before importing. Kiln projects can contain code that runs on your machine."
- `POST /api/git_sync/save_config` (`git_sync_api.py`): `SaveConfigRequest` gains `trusted: bool = False` body field. Same 400 response when false/missing.

### Frontend

- `import_project.svelte`: two new wizard steps (`local_trust_confirm`, `trust_confirm`) added to the step machine. Both render a full interstitial trust page with:
  - Yellow warning icon (exclaim-circle SVG from `warning.svelte`)
  - Title: "Trust this Project?"
  - Body: "Kiln projects can contain code that runs on your machine. Only import projects from sources you trust."
  - Local: [Cancel] returns to the file-path entry step; Git: [Cancel] returns to the import home (method selection). [Trust Project] proceeds with `trusted=true`.
- Local file flow: after path entry, "Continue" goes to trust page; on confirm, imports with `trusted=true`.
- Git wizard flow: trust page is shown immediately after URL validation / credential entry, **before** any clone or local write. The step order is: url -> credentials -> trust_confirm -> branch (clone) -> project -> complete. This ensures no repository data is written to disk until the user explicitly confirms trust.
- `step_complete.svelte`: `saveConfig` call updated to pass `trusted: true`.
- `api.ts`: `saveConfig` type updated to accept optional `trusted` field.

### Tests

- `test_project_api.py`: happy-path tests updated to pass `trusted=true`; two new rejection tests (`test_import_project_rejected_when_not_trusted`, `test_import_project_rejected_when_trusted_false`).
- `test_git_sync_api.py`: all save_config happy-path tests updated to pass `trusted: True`; two new rejection tests (`test_save_rejected_when_not_trusted`, `test_save_rejected_when_trusted_false`).

## Security strings (human-approved)

All security-related strings have been reviewed and approved by the project owner. The `# TODO` markers have been removed; the strings are finalized as shipped.
