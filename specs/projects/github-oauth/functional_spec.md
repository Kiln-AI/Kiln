---
status: complete
---

# Functional Spec: GitHub OAuth for Git Sync

## Overview

Add GitHub OAuth as the primary authentication method for GitHub repos in the git import credentials step. Uses a Kiln-owned GitHub App with the user OAuth flow (user access tokens that act as the user for commits). The flow chains GitHub App installation (with repo pre-selection) into OAuth authorization for a seamless two-screen experience.

## User Flow

### Happy Path (GitHub repo, public)

1. User reaches the credentials step with a GitHub URL (e.g. `github.com/Kiln-AI/kiln`)
2. They see a "Connect with GitHub" button (primary action)
3. Below the button, a subtle link: "or use a Personal Access Token"
4. User clicks "Connect with GitHub"
5. Backend resolves the org/user ID and repo ID via GitHub's public API
6. Browser opens the GitHub App **installation** page with org and repo pre-selected
7. User confirms installation (one click — org and repo are pre-filled)
8. GitHub redirects to the OAuth **authorization** page (chained via setup URL)
9. User authorizes (one click)
10. GitHub redirects to `http://localhost:8757/api/git_sync/oauth/callback` with an authorization code
11. Backend exchanges the code for a user access token (using PKCE + client secret)
12. The credentials step automatically advances to branch selection

Two GitHub screens, both pre-filled. Click, click, done.

### Happy Path (GitHub repo, private)

Same as above except:
- Step 5: `GET https://api.github.com/repos/ORG/REPO` returns 404 for private repos, so `repository_ids[]` cannot be pre-filled
- Step 6: Installation page opens with **org pre-selected** (org ID usually resolvable even for private repos) but the user must manually find and select the repo from GitHub's repo picker
- If org ID also can't be resolved: installation page opens without pre-selection. UI shows a hint: "Be sure to select the **ORG_NAME** organization and the **REPO_NAME** repository"

Still better than PAT (no token generation, no permission checkboxes, no copy/paste), but one more manual step for private repos.

### Re-authorization

Users can re-auth anytime. Tokens are stored per-repo in the config, so each repo gets its own token. Running the OAuth flow again for the same repo generates a fresh token and overwrites the old one. If the app is already installed on the org, the installation screen is a quick confirmation (no re-configuration needed).

### PAT Fallback

- Clicking "or use a Personal Access Token" switches to the existing PAT UI (text input, verify button, deep link to GitHub token page)
- A reciprocal subtle link "or connect with GitHub" switches back to OAuth mode
- The toggle is stateless — OAuth is always the default for GitHub

### Non-GitHub Providers

GitLab and other providers: unchanged. PAT-only flow, no OAuth option shown.

## OAuth Details

### GitHub App Configuration

- **App name**: "Kiln AI" (registered on GitHub by the Kiln team)
- **Permissions**: Repository `contents:write`, `metadata:read`
- **User access token expiration**: Disabled (tokens persist until revoked — avoids refresh token complexity)
- **Callback URL**: `http://localhost:8757/api/git_sync/oauth/callback`
- **Setup URL**: The OAuth authorization URL — GitHub redirects here after app installation, chaining install → authorize into one flow
- **PKCE**: Required (`code_challenge_method=S256`)

### Client Secret Handling

The client ID and client secret are embedded in the app source code. This is standard practice for native/desktop OAuth apps — the secret cannot be kept confidential in a distributed binary (GitHub documents this for public clients).

**The code where the secret lives must include a comment linking to GitHub's documentation explaining why this is acceptable for native apps:** https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app

### Chained Install → Authorize Flow

The two GitHub screens are chained using the GitHub App's "setup URL" feature:

1. **Installation URL** (first screen): `https://github.com/apps/kiln-ai/installations/new/permissions?suggested_target_id=ORG_ID&repository_ids[]=REPO_ID`
   - `suggested_target_id`: Numeric org/user ID (pre-selects the account)
   - `repository_ids[]`: Numeric repo ID (pre-selects the repo)
   - Both are best-effort — omitted if we can't resolve them
2. After installation, GitHub redirects to the app's **setup URL**
3. **Setup URL** is configured to redirect to the OAuth authorization endpoint: `https://github.com/login/oauth/authorize?client_id=...&redirect_uri=...&state=...&code_challenge=...&code_challenge_method=S256`
4. After authorization, GitHub redirects to the **callback URL** with `code` and `state`

### Resolving Org/Repo IDs

To pre-fill the installation page, we resolve numeric IDs from the repo URL:

- **Org/user ID**: `GET https://api.github.com/users/{owner}` → `.id` field. Works for public orgs and users. Most orgs are publicly visible even when their repos are private.
- **Repo ID**: `GET https://api.github.com/repos/{owner}/{repo}` → `.id` field. Works for public repos. Returns 404 for private repos.

Fallback behavior when IDs can't be resolved:
- **No org ID**: Skip `suggested_target_id`. Show hint in UI: "Be sure to select the **{owner}** organization"
- **No repo ID**: Skip `repository_ids[]`. Show hint in UI: "Be sure to select the **{repo}** repository"
- These hints appear in the Kiln UI before opening the GitHub page, so the user knows what to look for

### Token Exchange

1. Frontend calls `POST /api/git_sync/oauth/start` with the `git_url`
2. Backend generates `state` and PKCE `code_verifier`/`code_challenge`, resolves org/repo IDs, stores all in memory
3. Backend returns `{ install_url, state, pre_selection_hints }` — `install_url` is the GitHub App installation URL with whatever pre-selection params were resolvable; `pre_selection_hints` tells the frontend what couldn't be pre-filled
4. Frontend displays any hints, then opens `install_url` in a new browser tab
5. User clicks through install → authorize on GitHub
6. GitHub redirects to callback with `code` and `state`
7. Backend callback validates `state`, exchanges `code` + `code_verifier` + `client_secret` for token via `POST https://github.com/login/oauth/access_token`
8. Backend stores token in memory keyed by `state`
9. Backend returns HTML page: "Authorization complete. You can close this tab."
10. Frontend polls `GET /api/git_sync/oauth/status/{state}` until token is ready
11. Frontend calls `testAccess()` to verify the token works on the target repo
12. On success, advances to branch selection

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

**Response**: `{ install_url: string, state: string, owner_name: string, repo_name: string, owner_pre_selected: boolean, repo_pre_selected: boolean }`

### `GET /api/git_sync/oauth/callback`

GitHub redirects here after authorization. Query params: `code`, `state` (or `error` on denial).

**Behavior**:
- Validates `state` matches a pending flow
- If `error` param present, stores error keyed by `state`
- Otherwise exchanges `code` for token using `code_verifier` + `client_secret`
- Stores token (or error) in memory keyed by `state`

**Response**: HTML page — "Authorization complete. You can close this tab." (or error message)

### `GET /api/git_sync/oauth/status/{state}`

Frontend polls this to check completion.

**Response**: `{ complete: boolean, oauth_token: string | null, error: string | null }`

Once successfully polled with `complete: true`, the stored data is cleared (one-time retrieval).

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
| GitHub API rate limit (resolving IDs) | Skip pre-selection, proceed with hints. Not a blocker. |

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
- GitHub App installation + OAuth authorization chained flow
- Org/repo ID resolution for pre-selection (best-effort)
- PAT fallback toggle for GitHub
- Backend OAuth endpoints (start, callback, status)
- PKCE security
- New `github_oauth` auth mode and `oauth_token` storage field

### Out of Scope
- GitLab OAuth
- Refresh token handling (tokens configured not to expire)
- OAuth for GitLab or other providers' edit flows
