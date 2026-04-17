---
status: complete
---

# Functional Spec: GitHub OAuth for Git Sync

## Overview

Add GitHub OAuth as the primary authentication method for GitHub repos in the git import credentials step. Uses a Kiln-owned GitHub App with the user OAuth flow (user access tokens that act as the user for commits). The flow uses an authorize-first, install-if-needed 2-step approach: the user authorizes via OAuth first, then installs the GitHub App only if the token lacks access to the repo.

## User Flow

### Happy Path (App already installed)

1. User reaches the credentials step with a GitHub URL (e.g. `github.com/Kiln-AI/kiln`)
2. They see a "Connect with GitHub" button (primary action)
3. Below the button, a subtle link: "or use a Personal Access Token"
4. User clicks "Connect with GitHub"
5. Backend resolves the org/user ID and repo ID via GitHub's public API, generates OAuth state and PKCE values, and returns both the OAuth `authorize_url` and the GitHub App `install_url`
6. Browser opens the GitHub OAuth **authorization** page directly (via `authorize_url`)
7. User authorizes (one click)
8. GitHub redirects to `http://localhost:8757/api/git_sync/oauth/callback` with an authorization code
9. Backend exchanges the code for a user access token (using PKCE + client secret)
10. Frontend polls for the token, then calls `testAccess()` to verify the token works on the target repo
11. Access succeeds — the credentials step advances to branch selection

One GitHub screen. Single click, done.

### Happy Path (App not yet installed)

Same as above through step 10, but:
- Step 10: `testAccess()` fails because the GitHub App is not yet installed on the repo
- Step 11: Frontend shows a "needs install" state with the `install_url` from step 5. User clicks to open the GitHub App installation page (with org and repo pre-selected where possible)
- Step 12: User installs the app on the target repo. GitHub redirects to the app's setup URL (`/api/git_sync/oauth/authorize`), which renders a static "Install Complete -- return to Kiln" page
- Step 13: User returns to Kiln and clicks "Verify Access". Frontend re-runs `testAccess()` with the previously obtained token
- Step 14: Access succeeds — the credentials step advances to branch selection

This authorize-first, install-if-needed approach has fewer failure modes than chaining install into authorize via redirect. When the app is already installed (re-auth, second repo in the same org), the install step is skipped entirely.

### Pre-selection for Installation

When the install step is needed, the install URL includes pre-selection parameters where possible:
- **Org/user ID** (`suggested_target_id`): pre-selects the GitHub account. Works for public orgs and users.
- **Repo ID** (`repository_ids[]`): pre-selects the repository. Works for public repos; returns 404 for private repos.
- If IDs cannot be resolved, the install page opens without pre-selection. The backend includes `owner_name`, `repo_name`, `owner_pre_selected`, and `repo_pre_selected` fields in `OAuthStartResponse` for potential future use, but the frontend does not currently render hints to the user.

### Re-authorization

Users can re-auth anytime. Tokens are stored per-repo in the config, so each repo gets its own token. Running the OAuth flow again for the same repo generates a fresh token and overwrites the old one. If the app is already installed on the org, the install step is skipped entirely (the authorize-first flow detects this via `testAccess()`).

### PAT Fallback

- Clicking "or use a Personal Access Token" switches to the existing PAT UI (text input, verify button, deep link to GitHub token page)
- A reciprocal subtle link "or connect with GitHub" switches back to OAuth mode
- The toggle is stateless — OAuth is always the default for GitHub

### Non-GitHub Providers

GitLab and other providers: unchanged. PAT-only flow, no OAuth option shown.

## OAuth Details

### GitHub App Configuration

- **App name**: "Kiln AI GitHub Sync" (slug: `kiln-ai-github-sync`, registered on GitHub by the Kiln team)
- **Permissions**: Repository `contents:write`, `metadata:read`
- **User access token expiration**: Disabled (tokens persist until revoked — avoids refresh token complexity)
- **Callback URL**: `http://localhost:8757/api/git_sync/oauth/callback`
- **Setup URL**: `http://localhost:8757/api/git_sync/oauth/authorize` — GitHub redirects here after app installation; renders a static "Install Complete" page (no redirect, no flow lookup)
- **PKCE**: Required (`code_challenge_method=S256`)

### Client Secret Handling

The client ID and client secret are embedded in the app source code. This is standard practice for native/desktop OAuth apps — the secret cannot be kept confidential in a distributed binary (GitHub documents this for public clients).

**The code where the secret lives must include a comment linking to GitHub's documentation explaining why this is acceptable for native apps:** https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app

### Authorize-First, Install-If-Needed Flow

The flow uses two separate steps rather than chaining install into authorize via redirect:

1. **Authorization** (always first): Frontend opens `authorize_url` directly in a popup. The user authorizes the app and GitHub redirects to the callback URL with `code` and `state`.
2. **Installation** (only if needed): After obtaining the token, the frontend calls `testAccess()`. If access fails (app not installed on the repo), the frontend presents the `install_url` for the user to install the GitHub App. After installation, GitHub redirects to the app's setup URL (`/api/git_sync/oauth/authorize`), which renders a static "Install Complete" page. The user returns to Kiln and clicks "Verify Access".

This approach has fewer failure modes than redirect-based chaining: when the app is already installed, the install step is skipped entirely, avoiding edge cases around re-installation and redirect state management.

### Resolving Org/Repo IDs

To pre-fill the installation page, we resolve numeric IDs from the repo URL:

- **Org/user ID**: `GET https://api.github.com/users/{owner}` → `.id` field. Works for public orgs and users. Most orgs are publicly visible even when their repos are private.
- **Repo ID**: `GET https://api.github.com/repos/{owner}/{repo}` → `.id` field. Works for public repos. Returns 404 for private repos.

Fallback behavior when IDs can't be resolved:
- **No org ID**: Skip `suggested_target_id`. The backend sets `owner_pre_selected = false` in the response.
- **No repo ID**: Skip `repository_ids[]`. The backend sets `repo_pre_selected = false` in the response.
- The backend includes `owner_name` and `repo_name` fields for potential future use, but the frontend does not currently render hints to the user.

### Token Exchange

1. Frontend calls `POST /api/git_sync/oauth/start` with the `git_url`
2. Backend generates `state` and PKCE `code_verifier`/`code_challenge`, resolves org/repo IDs, stores all in memory
3. Backend returns `{ authorize_url, install_url, state, owner_name, repo_name, owner_pre_selected, repo_pre_selected }` — `authorize_url` is the GitHub OAuth URL with PKCE params; `install_url` is the GitHub App installation URL with whatever pre-selection params were resolvable
4. Frontend opens `authorize_url` in a popup (the `install_url` is held for later use if needed)
5. User authorizes on GitHub
6. GitHub redirects to callback with `code` and `state`
7. Backend callback validates `state`, exchanges `code` + `code_verifier` + `client_secret` for token via `POST https://github.com/login/oauth/access_token`
8. Backend stores token in memory keyed by `state`
9. Backend returns HTML page: "Authorization Complete -- Return to Kiln to continue setup."
10. Frontend polls `GET /api/git_sync/oauth/status/{state}` until token is ready
11. Frontend calls `testAccess()` to verify the token works on the target repo
12. If access succeeds: advances to branch selection
13. If access fails (app not installed): frontend shows the `install_url` for the user to install the GitHub App, then re-verifies access

## Auth Mode & Token Storage

### New Auth Mode

Add `"github_oauth"` to the `AuthMode` type:

```python
AuthMode = Literal["system_keys", "pat_token", "github_oauth"]
```

### New Token Field

Add `oauth_token` field to `GitSyncProjectConfig` (separate from `pat_token`):

```python
class GitSyncProjectConfig(TypedDict):
    sync_mode: Literal["auto", "manual"]
    auth_mode: AuthMode
    remote_name: str
    branch: str
    clone_path: str | None
    git_url: str | None
    pat_token: str | None
    oauth_token: str | None  # new
```

When `auth_mode` is `"github_oauth"`, the `oauth_token` field is used for git operations. When `"pat_token"`, the `pat_token` field is used. The git sync manager uses whichever field matches the auth mode.

### Config Response

Add `has_oauth_token: bool` to `GitSyncConfigResponse` (mirroring the existing `has_pat_token` pattern — token values are never exposed in API responses).

## Backend Endpoints

### `POST /api/git_sync/oauth/start`

Initiates the OAuth flow.

**Request**: `{ git_url: string }`

**Behavior**:
- Parses owner/repo from `git_url`
- Resolves org ID via `GET https://api.github.com/users/{owner}` (best-effort)
- Resolves repo ID via `GET https://api.github.com/repos/{owner}/{repo}` (best-effort)
- Generates cryptographic `state` and PKCE `code_verifier`/`code_challenge`
- Stores `state`, `code_verifier` in memory (keyed by `state`, with a TTL for cleanup)
- Builds the installation URL with available pre-selection params

**Response**: `{ authorize_url: string, install_url: string, state: string, owner_name: string, repo_name: string, owner_pre_selected: boolean, repo_pre_selected: boolean }`

The `authorize_url` is the GitHub OAuth URL with PKCE parameters that the frontend opens directly. The `install_url` is held by the frontend for use only if the app is not yet installed on the target repo.

### `GET /api/git_sync/oauth/callback`

GitHub redirects here after authorization. Query params: `code`, `state` (or `error` on denial).

**Behavior**:
- Validates `state` matches a pending flow
- If `error` param present, stores error keyed by `state`
- Otherwise exchanges `code` for token using `code_verifier` + `client_secret`
- Stores token (or error) in memory keyed by `state`

**Response**: HTML page — "Authorization Complete" with "Return to Kiln to continue setup" (or error message)

### `GET /api/git_sync/oauth/status/{state}`

Frontend polls this to check completion.

**Response**: `{ complete: boolean, oauth_token: string | null, error: string | null }`

All `complete: true` responses (including error cases via `fail_flow`) consume the flow via one-time retrieval. A "flow not found" case (expired or never existed) returns `{ complete: false, error: "Session expired or not found." }` without consuming anything.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| User denies authorization on GitHub | Callback receives `error` param. Status endpoint returns error. Frontend shows error with retry/PAT options. |
| Token exchange fails | Status endpoint returns error. Frontend shows error with retry option. |
| `state` mismatch on callback | Reject (possible CSRF). Return error HTML. |
| Polling timeout (5 minutes) | Frontend stops polling, shows "Authorization timed out" with retry option. |
| User closes GitHub tab | Same as timeout — frontend eventually stops polling. |
| App not installed on repo | `testAccess()` fails after token retrieval. Frontend shows error explaining the app needs to be installed, with a link to retry the install flow. |
| Token lacks repo access | Same as above — caught by `testAccess()`. |
| GitHub API rate limit (resolving IDs) | Skip pre-selection, proceed without pre-selection. Not a blocker. |

## Edit Project Re-Auth

The edit project page (`git_sync_status.svelte`) has an "Update Auth" button that currently shows a PAT input. This must be updated to support GitHub OAuth re-auth.

### Behavior by Auth Mode

When the user clicks "Update Auth":

- **`github_oauth` auth mode + GitHub URL**: Show a "Reconnect with GitHub" button (same OAuth flow as initial setup). Below it, a subtle link "or use a Personal Access Token" to switch to PAT input. Completing OAuth updates the `oauth_token` and keeps `auth_mode` as `github_oauth`. Switching to PAT and saving changes `auth_mode` to `pat_token`.
- **`pat_token` auth mode + GitHub URL**: Show the PAT input (existing behavior). Add a subtle link "or connect with GitHub" to switch to OAuth. Completing OAuth changes `auth_mode` to `github_oauth`.
- **`pat_token` auth mode + non-GitHub URL**: Existing PAT-only behavior, unchanged.
- **`system_keys` auth mode**: Existing warning message, unchanged.

### Re-Auth OAuth Flow

Uses the same `/api/git_sync/oauth/start` → poll → `/api/git_sync/oauth/status` flow as the import wizard. On success, calls `updateConfig()` with the new `oauth_token` and `auth_mode: "github_oauth"`.

### Update Config Endpoint Changes

The `PATCH /api/git_sync/update_config/{project_id}` endpoint's `UpdateConfigRequest` must accept `oauth_token` in addition to the existing `pat_token` field.

## Scope

### In Scope
- GitHub OAuth authorization with install-if-needed flow
- Org/repo ID resolution for pre-selection (best-effort)
- PAT fallback toggle for GitHub
- Backend OAuth endpoints (start, callback, status)
- PKCE security
- New `github_oauth` auth mode and `oauth_token` storage field

### Out of Scope
- GitLab OAuth
- Refresh token handling (tokens configured not to expire)
- OAuth for GitLab or other providers' edit flows
