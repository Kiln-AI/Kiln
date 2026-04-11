---
status: complete
---

# Architecture: GitHub OAuth for Git Sync

This project is small enough for a single architecture doc — no component designs needed.

## Overview

The change adds three backend endpoints, a new Python module for OAuth state management, frontend changes to `step_credentials.svelte` and `git_sync_status.svelte`, and minor plumbing changes to support the new `github_oauth` auth mode.

## Data Model Changes

### `config.py`

```python
AuthMode = Literal["system_keys", "pat_token", "github_oauth"]

class GitSyncProjectConfig(TypedDict):
    sync_mode: Literal["auto", "manual"]
    auth_mode: AuthMode
    remote_name: str
    branch: str
    clone_path: str | None
    git_url: str | None
    pat_token: str | None
    oauth_token: str | None  # NEW
```

### `git_sync_api.py` Changes

- `GitSyncConfigResponse`: Add `has_oauth_token: bool` field (default `False`).
- `UpdateConfigRequest`: Add `oauth_token: str | None` field.
- `SaveConfigRequest`: Add `oauth_token: str | None` field.
- All endpoints that read/write config: plumb `oauth_token` through alongside `pat_token`.

### Frontend Types

- `GitSyncConfigResponse` in `api.ts`: Add `has_oauth_token: boolean`.
- `saveConfig()`: Add optional `oauth_token` param.
- `updateConfig()`: Add optional `oauth_token` param.

## Git Credential Plumbing

The OAuth token is used identically to a PAT for git operations via pygit2. The `make_credentials` function in `clone.py` and `_make_remote_callbacks` in `GitSyncManager` already accept `pat_token` + `auth_mode`.

### Changes to `clone.py` `make_credentials()`

Accept an `oauth_token` parameter (or rename the existing one to be generic). When `auth_mode == "github_oauth"`, use `oauth_token` in the `UserPass` credential, same as PAT:

```python
def make_credentials(
    pat_token: str | None = None,
    oauth_token: str | None = None,
    auth_mode: str = "system_keys",
) -> pygit2.RemoteCallbacks:
```

In the credentials callback, for `auth_mode == "github_oauth"`:

```python
if auth_mode == "github_oauth" and oauth_token is not None:
    if allowed_types & pygit2.enums.CredentialType.USERPASS_PLAINTEXT:
        return pygit2.UserPass(username="x-token", password=oauth_token)
```

### Changes to `GitSyncManager.__init__()`

Add `oauth_token` parameter:

```python
def __init__(
    self,
    repo_path: Path,
    auth_mode: AuthMode,
    remote_name: str = "origin",
    pat_token: str | None = None,
    oauth_token: str | None = None,
):
```

Pass it through to `make_credentials` in `_make_remote_callbacks`.

### Changes to `registry.py` `get_or_create()`

Add `oauth_token` parameter, pass to `GitSyncManager`, update existing manager's `_oauth_token` if changed (same pattern as `pat_token`).

## New Module: `oauth.py`

New file: `app/desktop/git_sync/oauth.py`

Handles OAuth state management, GitHub API calls for ID resolution, and token exchange.

### Constants

```python
# GitHub App credentials for Kiln AI.
# Embedded client secret is standard practice for native/desktop OAuth apps —
# the secret cannot be kept confidential in a distributed binary.
# See: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app
GITHUB_CLIENT_ID = "..."  # To be filled after GitHub App registration
GITHUB_CLIENT_SECRET = "..."  # To be filled after GitHub App registration

GITHUB_APP_NAME = "kiln-ai"  # Slug used in install URL
CALLBACK_URL = "http://localhost:8757/api/git_sync/oauth/callback"
OAUTH_TIMEOUT_SECONDS = 300  # 5 minutes
```

### `OAuthFlowState`

Dataclass holding a single in-progress OAuth flow:

```python
@dataclass
class OAuthFlowState:
    state: str                    # Cryptographic random state parameter
    code_verifier: str            # PKCE code verifier
    code_challenge: str           # PKCE code challenge (S256)
    git_url: str                  # The repo URL this flow is for
    created_at: float             # time.monotonic() for TTL cleanup
    # Set after callback:
    oauth_token: str | None = None
    error: str | None = None
    complete: bool = False
```

### `OAuthFlowManager`

Class managing in-progress OAuth flows. Singleton instance used by the API endpoints.

```python
class OAuthFlowManager:
    def __init__(self):
        self._flows: dict[str, OAuthFlowState] = {}
        self._lock: threading.Lock = threading.Lock()

    def start_flow(self, git_url: str) -> OAuthFlowState:
        """Create a new flow: generate state, PKCE values, store in memory."""

    def get_flow(self, state: str) -> OAuthFlowState | None:
        """Retrieve a pending flow by state. Returns None if expired/missing."""

    def complete_flow(self, state: str, oauth_token: str) -> None:
        """Mark a flow as complete with the received token."""

    def fail_flow(self, state: str, error: str) -> None:
        """Mark a flow as failed with an error message."""

    def consume_flow(self, state: str) -> OAuthFlowState | None:
        """Retrieve and delete a completed flow (one-time retrieval)."""

    def cleanup_expired(self) -> None:
        """Remove flows older than OAUTH_TIMEOUT_SECONDS. Called lazily."""
```

Thread safety: all methods acquire `_lock`. The `cleanup_expired()` method is called at the start of `start_flow()` and `get_flow()` to prevent unbounded growth.

### PKCE Generation

```python
import hashlib, base64, secrets

def _generate_pkce() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge)."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
```

### GitHub API ID Resolution

```python
import httpx

async def resolve_github_owner_id(owner: str) -> int | None:
    """GET https://api.github.com/users/{owner} -> .id. Returns None on failure."""

async def resolve_github_repo_id(owner: str, repo: str) -> int | None:
    """GET https://api.github.com/repos/{owner}/{repo} -> .id. Returns None on failure."""
```

Use `httpx` (async) since the calling endpoints are async. Return `None` on any failure (404, rate limit, network error) — pre-selection is best-effort.

### Install URL Builder

```python
def build_install_url(
    owner_id: int | None,
    repo_id: int | None,
) -> str:
    """Build the GitHub App installation URL with available pre-selection params."""
    base = f"https://github.com/apps/{GITHUB_APP_NAME}/installations/new"
    params = {}
    if owner_id is not None:
        params["suggested_target_id"] = str(owner_id)
    if repo_id is not None:
        params["repository_ids[]"] = str(repo_id)
    if params:
        from urllib.parse import urlencode
        return f"{base}/permissions?{urlencode(params)}"
    return base
```

### Token Exchange

```python
async def exchange_code_for_token(
    code: str,
    code_verifier: str,
) -> str:
    """POST to GitHub to exchange auth code for user access token.

    Raises OAuthError on failure.
    """
```

POST to `https://github.com/login/oauth/access_token` via `httpx.AsyncClient` with:
- `client_id`, `client_secret`, `code`, `redirect_uri`, `code_verifier`
- Header: `Accept: application/json`

Parse JSON response. On success, return `access_token`. On error, raise with GitHub's `error_description`.

## API Endpoints

Three new endpoints, all in `git_sync_api.py` inside `connect_git_sync_api()`.

### `POST /api/git_sync/oauth/start`

```python
class OAuthStartRequest(BaseModel):
    git_url: str

class OAuthStartResponse(BaseModel):
    install_url: str
    state: str
    owner_name: str
    repo_name: str
    owner_pre_selected: bool
    repo_pre_selected: bool
```

Implementation:
1. Parse `owner` and `repo` from `git_url` using existing `gitOwnerFromUrl`-equivalent logic (regex for HTTPS/SSH URLs)
2. Call `resolve_github_owner_id(owner)` and `resolve_github_repo_id(owner, repo)` concurrently via `asyncio.gather` (both are async httpx calls)
3. Call `OAuthFlowManager.start_flow(git_url)` to generate state + PKCE
4. Build `install_url` via `build_install_url(owner_id, repo_id)`
5. Return response with pre-selection info

### `GET /api/git_sync/oauth/callback`

Query params: `code`, `state`, or `error`, `error_description`.

Implementation:
1. Look up flow via `OAuthFlowManager.get_flow(state)`
2. If not found: return HTML error page ("Authorization session expired")
3. If `error` param present: `fail_flow(state, error_description)`; return HTML error page
4. Call `await exchange_code_for_token(code, flow.code_verifier)`
5. On success: `complete_flow(state, token)`; return HTML success page
6. On failure: `fail_flow(state, error_message)`; return HTML error page

Returns HTML (not JSON) since this is rendered in the user's browser tab. Simple inline HTML, no template needed:

```python
HTML_SUCCESS = """<!DOCTYPE html><html><body>
<h2>Authorization complete</h2>
<p>You can close this tab and return to Kiln.</p>
<script>window.close()</script>
</body></html>"""
```

### `GET /api/git_sync/oauth/status/{state}`

```python
class OAuthStatusResponse(BaseModel):
    complete: bool
    oauth_token: str | None = None
    error: str | None = None
```

Implementation:
1. Call `OAuthFlowManager.get_flow(state)` — if not found, return `{complete: false, error: "Session expired"}`
2. If `flow.complete`: call `consume_flow(state)` and return token
3. If `flow.error`: call `consume_flow(state)` and return error
4. Otherwise: return `{complete: false}` (still waiting)

## Frontend Changes

### `api.ts`

Add new functions:

```typescript
export type OAuthStartResponse = {
  install_url: string
  state: string
  owner_name: string
  repo_name: string
  owner_pre_selected: boolean
  repo_pre_selected: boolean
}

export type OAuthStatusResponse = {
  complete: boolean
  oauth_token: string | null
  error: string | null
}

export async function oauthStart(git_url: string): Promise<OAuthStartResponse> {
  return post("/api/git_sync/oauth/start", { git_url })
}

export async function oauthStatus(state: string): Promise<OAuthStatusResponse> {
  const resp = await fetch(`${base_url}/api/git_sync/oauth/status/${state}`)
  if (!resp.ok) throw new Error("Failed to check OAuth status")
  return resp.json()
}
```

### `step_credentials.svelte`

Major rework of this component. Add local state for auth method toggle:

```typescript
let mode: "oauth" | "pat" = is_github ? "oauth" : "pat"
let oauth_state: string | null = null
let oauth_polling = false
let oauth_error: string | null = null
let pre_selection_hints: { owner_name: string; repo_name: string; owner_pre_selected: boolean; repo_pre_selected: boolean } | null = null
```

**OAuth mode UI** (when `mode === "oauth"` and `is_github`):
- "Connect with GitHub" primary button
- Pre-selection hints (if `owner_pre_selected === false` or `repo_pre_selected === false`): show hint text like "Be sure to select the **{owner_name}** organization and the **{repo_name}** repository"
- While polling: show spinner with "Waiting for GitHub authorization..."
- On error: show error with retry button
- Subtle link below: "or use a Personal Access Token" → sets `mode = "pat"`

**PAT mode UI** (when `mode === "pat"` or non-GitHub):
- Existing PAT input UI (unchanged)
- If `is_github`: subtle link "or connect with GitHub" → sets `mode = "oauth"`

**OAuth flow logic:**
1. On "Connect with GitHub" click: call `oauthStart(git_url)`
2. Store `state`, display hints, open `install_url` in new tab via `window.open()`
3. Start polling `oauthStatus(state)` every 2 seconds
4. On `complete: true` with token: call `testAccess(git_url, oauth_token)` to verify, then `on_success(oauth_token, "github_oauth")`
5. On error or 5-minute timeout: show error, stop polling

### `import_project.svelte`

Update state and callbacks:
- `on_credentials_success` already receives `(token, auth_method)`. The `auth_method` will now be `"github_oauth"` when OAuth is used.
- Store `oauth_token` separately from `pat_token` based on `auth_mode`:

```typescript
let pat_token: string | null = null
let oauth_token: string | null = null

function on_credentials_success(token: string, detected_auth_method: string) {
  if (detected_auth_method === "github_oauth") {
    oauth_token = token
    pat_token = null
  } else {
    pat_token = token
    oauth_token = null
  }
  auth_mode = detected_auth_method
  set_step("branch")
}
```

Pass `oauth_token` through to downstream steps (`StepBranch`, `StepComplete`).

### `git_sync_status.svelte`

Update the "Update Auth" form:

- When `is_github`: show two modes (OAuth button vs PAT input) with toggle, same as `step_credentials.svelte`
- For `auth_mode === "github_oauth"`: default to OAuth mode, show "Reconnect with GitHub" button
- For `auth_mode === "pat_token"` + GitHub URL: default to PAT mode, show "or connect with GitHub" link
- On OAuth success: call `updateConfig(project_id, { oauth_token, auth_mode: "github_oauth" })`
- On PAT success: call `updateConfig(project_id, { pat_token, auth_mode: "pat_token" })` (existing behavior)

### Shared OAuth Logic

The OAuth polling logic (start flow, open tab, poll, handle result) is shared between `step_credentials.svelte` and `git_sync_status.svelte`. Extract into a helper:

**`app/web_ui/src/lib/git_sync/oauth_flow.ts`**

```typescript
export type OAuthFlowCallbacks = {
  onHints: (hints: OAuthStartResponse) => void
  onPolling: () => void
  onSuccess: (token: string) => void
  onError: (error: string) => void
}

export function startOAuthFlow(
  git_url: string,
  callbacks: OAuthFlowCallbacks,
): { cancel: () => void } {
  // 1. Call oauthStart(git_url)
  // 2. Open install_url in new tab
  // 3. Poll oauthStatus every 2s
  // 4. Call appropriate callback on completion/error/timeout
  // Returns cancel handle to stop polling
}
```

## Setup URL Chaining

The GitHub App's "setup URL" is configured to our OAuth authorization URL. After the user installs the app, GitHub redirects to this URL, which initiates the OAuth authorization.

However, the setup URL is static (configured in GitHub App settings), and our OAuth authorize URL has dynamic params (`state`, `code_challenge`). Two options:

**Option A: Setup URL → backend redirect endpoint**

Configure the setup URL to point to a backend endpoint like `http://localhost:8757/api/git_sync/oauth/authorize`. This endpoint:
1. Looks up the most recent pending `OAuthFlowState`
2. Builds the full GitHub OAuth authorize URL with the correct `state` and `code_challenge`
3. Redirects (302) to GitHub's authorize URL

This works because only one OAuth flow is active at a time in the desktop app.

**Option B: Skip setup URL chaining — two separate redirects**

Don't use the setup URL. Instead:
1. Open the install URL in the browser
2. Frontend detects when the user returns (tab is closed or focus returns) and prompts them to continue
3. Frontend opens the OAuth authorize URL in a second tab

Option A is cleaner (automatic chaining), but has a subtle race if the user starts a flow and then starts another before completing the first. Option B is more explicit but requires two browser tabs or a manual "Continue" click.

**Recommendation: Option A.** The desktop app is single-user, so concurrent flows are unlikely. Add a guard: if multiple pending flows exist, use the most recent one.

### Backend Redirect Endpoint

```python
@app.get("/api/git_sync/oauth/authorize")
async def api_oauth_authorize():
    """Setup URL redirect: after GitHub App install, redirect to OAuth authorize."""
    flow = oauth_manager.get_most_recent_pending_flow()
    if flow is None:
        return HTMLResponse("No pending authorization. Please start over in Kiln.")
    authorize_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&state={flow.state}"
        f"&code_challenge={flow.code_challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(authorize_url)
```

`OAuthFlowManager.get_most_recent_pending_flow()`: returns the flow with the highest `created_at` that is not yet complete.

## Error Handling

All errors in `oauth.py` use a custom `OAuthError` exception class. API endpoints catch this and return appropriate responses.

GitHub API calls (ID resolution) fail silently — return `None`, log a warning. Pre-selection is best-effort.

Token exchange errors propagate via `OAuthFlowState.error` → polled by frontend.

## Testing Strategy

### Unit Tests: `test_oauth.py`

- **PKCE generation**: Verify format (URL-safe base64, correct length), verify challenge matches verifier via SHA256
- **OAuthFlowManager**: Start flow, get flow, complete flow, consume flow, expired flow cleanup, state validation, get_most_recent_pending_flow
- **`build_install_url`**: With both IDs, with only owner ID, with neither, URL encoding
- **`exchange_code_for_token`**: Mock HTTP responses — success, error, network failure
- **`resolve_github_owner_id` / `resolve_github_repo_id`**: Mock HTTP — success, 404, network error, rate limit
- **URL parsing** (extract owner/repo from git URL): HTTPS, SSH, various formats

### Unit Tests: Updated Existing Tests

- **`test_git_sync_api.py`**: Add tests for the three new endpoints. Mock `OAuthFlowManager` and GitHub API calls.
- **`config.py` tests**: Verify `oauth_token` is stored and retrieved correctly with `github_oauth` auth mode.

### Frontend Tests

- **`step_credentials.svelte`**: Test OAuth mode rendering for GitHub URLs, PAT mode for non-GitHub, mode toggle, polling behavior (mock fetch)
- **`git_sync_status.svelte`**: Test OAuth re-auth button for GitHub OAuth projects, PAT input for PAT projects
- **`oauth_flow.ts`**: Test start/poll/cancel/timeout logic with mocked API calls

### Manual Testing

The OAuth flow requires a real GitHub App registration and browser interaction. Manual testing checklist:
- Public repo: verify org + repo pre-selection works
- Private repo: verify org pre-selection, manual repo selection
- Deny authorization: verify error shown
- Close tab without authorizing: verify timeout
- Re-auth from edit project page
- PAT fallback toggle in both directions
