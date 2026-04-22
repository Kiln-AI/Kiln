---
status: complete
---

# Phase 3: Edit Project Re-Auth

## Overview

Update `git_sync_status.svelte` on the edit project page to support GitHub OAuth re-authentication, mirroring the UX introduced in Phase 2 for the import flow. For GitHub projects, show an OAuth/PAT mode toggle: `github_oauth`-authed projects default to OAuth (with a "Reconnect with GitHub" primary button), PAT-authed GitHub projects keep PAT as default but offer a subtle link to switch to OAuth. Non-GitHub and `system_keys` projects are unchanged. On OAuth success we call `updateConfig` with both `oauth_token` and `auth_mode: "github_oauth"` so switching modes propagates to the backend. Uses the shared `startOAuthFlow` helper from Phase 2 and replicates the popup-blocker-safe generation pattern from `step_credentials.svelte`.

## Steps

1. **`git_sync_status.svelte` — script block**
   - Import `startOAuthFlow` and `OAuthFlowCallbacks` from `$lib/git_sync/oauth_flow`, and `OAuthStartResponse` from `$lib/git_sync/api`.
   - Import `MarkdownBlock`, `onDestroy`.
   - Add reactive `is_github_oauth = config?.auth_mode === "github_oauth"`.
   - Add local state: `mode: "oauth" | "pat"` initialized from auth mode + URL (OAuth for github_oauth or unset-but-GitHub), OAuth state variables (`oauth_polling`, `oauth_starting`, `oauth_error`, `cancel_oauth`, `start_response`, `oauth_generation`) — same shape as `step_credentials.svelte`.
   - When `show_auth_form` toggles off (Cancel), call `reset_oauth()` to stop polling and clear state.
   - When `show_auth_form` toggles on, recompute initial `mode` from the config.

2. **`git_sync_status.svelte` — OAuth logic**
   - `reset_oauth()`: cancel ongoing flow, clear state, increment generation.
   - `start_oauth()`: replicate pattern from `step_credentials.svelte` — cancel prior flow, capture `this_generation`, call `startOAuthFlow(config.git_url, callbacks)` where:
     - `onStarted` stores `start_response`, clears `oauth_starting`.
     - `onPolling` sets `oauth_polling = true`.
     - `onSuccess(token)` awaits `testAccess(git_url, null, "github_oauth", token)`; on pass call `updateConfig(project_id, { oauth_token: token, auth_mode: "github_oauth" })` and refresh local config, reset form state and close. On failure set `oauth_error`.
     - `onError` sets `oauth_error`.
   - `onDestroy` cancels outstanding flow.

3. **`git_sync_status.svelte` — PAT save**
   - Update `save_token()` so when `is_github` and current mode/config is switching away from OAuth to PAT, we explicitly send `auth_mode: "pat_token"` in the `updateConfig` call (spec: "Switching to PAT and saving changes auth_mode to pat_token").

4. **`git_sync_status.svelte` — template**
   - Inside `{#if show_auth_form}` block:
     - Keep the existing `system_keys` warning branch unchanged.
     - For GitHub URLs: render OAuth vs PAT sub-UIs based on `mode`. Include a toggle link "or use a Personal Access Token" / "or connect with GitHub".
     - OAuth sub-UI: "Reconnect with GitHub" primary button (text changes based on whether already github_oauth). While polling show spinner + "Waiting for GitHub authorization..." + pre-selection hint (if any) + "Already have the app installed? Authorize directly" escape-hatch link + Cancel. On error, show error via `Warning` and keep the button to retry.
     - PAT sub-UI: existing PAT input unchanged.
   - For non-GitHub (GitLab + generic): render existing PAT UI unchanged (no toggle).

5. **Frontend tests — `git_sync_status.test.ts` (new)**
   - Use @testing-library/svelte (already used elsewhere? check) — if not present use direct render. Since existing frontend uses vitest + component tests sparingly, keep scope to testing behaviour that's straightforward. Fallback: unit-test helper pure logic.
   - Simpler approach: add a new unit-test-friendly helper module if needed. Given the patterns in this repo lean toward API/pure-function tests, write tests that exercise the OAuth interaction indirectly by testing `updateConfig` signature and the new typed callbacks do not regress. Focus on verifying the public api contract (updateConfig allows oauth_token + auth_mode simultaneously) — this is already covered by api tests. Instead, add component-level tests using `@testing-library/svelte` if installed.

   Decision: check if `@testing-library/svelte` is installed. If yes, add component tests covering:
   - GitHub OAuth project: clicking "Update Auth" shows OAuth mode by default with Reconnect button.
   - GitHub PAT project: clicking "Update Auth" shows PAT mode by default with a link to switch to OAuth.
   - Non-GitHub project: clicking "Update Auth" shows PAT mode with no OAuth toggle.
   - `system_keys` project: shows the existing warning.

   If not installed, add a focused unit helper module (`auth_form_mode.ts`) that encapsulates the initial-mode calculation + the `updateConfig` payload builder, and test those in isolation so the component stays declaratively driven.

## Tests

- `auth_form_mode.test.ts` (or `git_sync_status.test.ts` if @testing-library/svelte available): initial mode selection — github_oauth -> oauth, pat_token + github -> pat, pat_token + gitlab -> pat (and no OAuth toggle), system_keys -> system_keys branch
- Payload builder tests: OAuth success builds `{ oauth_token, auth_mode: "github_oauth" }`; PAT save when switching from OAuth builds `{ pat_token, auth_mode: "pat_token" }`; PAT save on existing PAT GitHub project does not need auth_mode switch
