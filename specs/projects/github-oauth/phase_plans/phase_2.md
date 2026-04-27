---
status: complete
---

# Phase 2: Frontend OAuth Flow

## Overview

Add GitHub OAuth as the primary authentication method in the frontend. This phase creates a shared OAuth flow helper, reworks the credentials step to support OAuth/PAT toggle for GitHub URLs, updates import_project.svelte to plumb oauth_token through, updates api.ts with new types/functions, and regenerates the OpenAPI schema. Frontend tests cover the new oauth_flow.ts helper and the api.ts additions.

## Steps

1. **Update `api.ts`** — Add `OAuthStartResponse` and `OAuthStatusResponse` types, plus `oauthStart()` and `oauthStatus()` functions. `OAuthStartResponse` includes both `install_url` (GitHub App installation URL, opened by default) and `authorize_url` (direct OAuth authorize URL, used as an escape hatch link for users who already have the app installed). Add `has_oauth_token` to `GitSyncConfigResponse`. Add `oauth_token` param to `saveConfig()` and `updateConfig()`. Update `testAccess()` to accept optional `oauth_token` and `auth_mode` params.

2. **Create `oauth_flow.ts`** — New file at `app/web_ui/src/lib/git_sync/oauth_flow.ts`. Shared helper that encapsulates: call oauthStart, open the install URL in a new tab (seamless for new installs via GitHub's setup URL chaining: install → setup redirect → OAuth authorize → callback), poll oauthStatus every 2s, handle success/error/timeout. Returns a cancel handle. Callback-based API.

3. **Rework `step_credentials.svelte`** — Add OAuth/PAT mode toggle. For GitHub URLs, default to OAuth mode with "Connect with GitHub" button. Show pre-selection hints. Show polling spinner. Include an escape-hatch "Already have the app installed? Authorize directly" link (uses `authorize_url`) for returning users whose install page does not auto-redirect. Show errors with retry. Subtle link to switch to PAT mode. Non-GitHub URLs show PAT-only (unchanged).

4. **Update `import_project.svelte`** — Add `oauth_token` state variable. Update `on_credentials_success` to store oauth_token vs pat_token based on auth method. Pass `oauth_token` through to `StepBranch` and `StepComplete`.

5. **Update `step_branch.svelte`** — Accept optional `oauth_token` prop, pass to `listBranches`, `cloneRepo`, `testWriteAccess` calls.

6. **Update `step_complete.svelte`** — Accept optional `oauth_token` prop, pass to `saveConfig` call.

7. **Update `listBranches`, `cloneRepo`, `testWriteAccess`** in `api.ts` — Add optional `oauth_token` param to each function signature and include in request body.

8. **Regenerate OpenAPI schema** — Run `generate_schema.sh`.

9. **Write tests** — Tests for `oauth_flow.ts` (start/poll/cancel/timeout/error). Tests for new `api.ts` functions (`oauthStart`, `oauthStatus`).

## Tests

- `oauth_flow.test.ts`: Test startOAuthFlow calls oauthStart and opens window, polls oauthStatus, calls onSuccess with token on completion, calls onError on failure, stops polling on cancel, times out after 5 minutes
- `api.test.ts`: Test oauthStart sends correct POST request, test oauthStatus sends correct GET request, test updated function signatures pass oauth_token
