---
status: complete
---

# Architecture: GitHub OAuth Token Refresh

Single-doc architecture (no separate component designs). All paths are relative to the
repo root. This project spans `app/desktop/` (backend) and `app/web_ui/` (frontend), so
it lives at the repo-root `specs/projects/`.

## Overview

Add a renewal layer to the existing OAuth user-access-token flow:

```
connect/reconnect → capture {access, refresh, expiries}  (Phase 1)
                          │ persisted in GitSyncProjectConfig
                          ▼
GitSyncManager.fetch()/commit_and_push()
   → _ensure_valid_oauth_token()  ── proactive refresh (Phase 2)
   → run git op
        └─ on auth rejection → reactive refresh + retry (Phase 3)
        └─ on unrenewable auth → AuthExpiredError → 401 (Phase 3)
frontend threads the new fields through the wizard/settings (Phase 4)
```

## Data model

### `OAuthTokenResult` (new dataclass, `app/desktop/git_sync/oauth.py`)

```python
@dataclass
class OAuthTokenResult:
    access_token: str
    refresh_token: str | None = None
    access_token_expires_at: float | None = None      # epoch seconds (wall-clock)
    refresh_token_expires_at: float | None = None
```

Computed at exchange/refresh time: `expires_at = time.time() + expires_in` when GitHub
returns `expires_in`; else `None`.

### `GitSyncProjectConfig` (`app/desktop/git_sync/config.py`) — add three fields

```python
oauth_refresh_token: str | None
oauth_token_expires_at: float | None
oauth_refresh_token_expires_at: float | None
```

`get_git_sync_config()` must default each to `None` via `.get(...)` (legacy configs lack
them). `save_git_sync_config()` already writes the whole dict — no change beyond the
TypedDict. Add a focused helper:

```python
def update_oauth_tokens(project_path: str, result: OAuthTokenResult) -> None:
    """Synchronous read-modify-write of only the OAuth token fields for one project."""
    config = Config.shared()
    raw = config.git_sync_projects or {}
    entry = raw.get(project_path)
    if entry is None:
        return
    entry["oauth_token"] = result.access_token
    entry["oauth_refresh_token"] = result.refresh_token
    entry["oauth_token_expires_at"] = result.access_token_expires_at
    entry["oauth_refresh_token_expires_at"] = result.refresh_token_expires_at
    raw[project_path] = entry
    config.git_sync_projects = raw   # synchronous persist; no await around this block
```

### `libs/core/kiln_ai/utils/config.py`

In the `git_sync_projects` `ConfigProperty` (~line 202), extend `sensitive_keys`:
`["pat_token", "oauth_token", "oauth_refresh_token"]`.

## Components & changes

### 1. `app/desktop/git_sync/oauth.py`

- **`exchange_code_for_token(code, code_verifier) -> OAuthTokenResult`** (was `-> str`).
  Parse `access_token`, `refresh_token`, `expires_in`, `refresh_token_expires_in`;
  compute absolute expiries; return `OAuthTokenResult`. Keep raising `OAuthError` on the
  `error`/`error_description` path.
- **`refresh_access_token(refresh_token: str) -> OAuthTokenResult`** (new). POST to
  `https://github.com/login/oauth/access_token` with
  `{client_id, client_secret, grant_type: "refresh_token", refresh_token}`,
  `Accept: application/json`, timeout 30s. Parse same fields (response includes a rotated
  `refresh_token`). Raise `OAuthError` if no `access_token` in the response.
- **`OAuthFlowState`**: add `refresh_token`, `oauth_token_expires_at`,
  `oauth_refresh_token_expires_at` fields. `complete_flow()` takes an `OAuthTokenResult`
  (or the extra fields) and stores them on the flow.

> The single caller of `exchange_code_for_token` is the OAuth callback in
> `git_sync_api.py`; update it together (Phase 1). The `time` import already exists.

### 2. `app/desktop/git_sync/git_sync_api.py`

- **`api_oauth_callback`**: `result = await exchange_code_for_token(...)`;
  `oauth_manager.complete_flow(state, result)`.
- **`OAuthStatusResponse`**: add `oauth_refresh_token`, `oauth_token_expires_at`,
  `oauth_refresh_token_expires_at`. `api_oauth_status` returns them from the consumed flow.
- **`SaveConfigRequest`** + **`api_save_config`**: accept and persist the three new fields
  into `GitSyncProjectConfig`.
- **`UpdateConfigRequest`** + **`api_update_config`**: accept the three new fields; when
  set, write them. The existing auth-mode-switch logic that clears `oauth_token` must also
  clear `oauth_refresh_token` / expiries when switching away from `github_oauth`, and the
  `github_oauth` branch should accept the new refresh fields.
- (Optional) **`GitSyncConfigResponse`**: add `has_oauth_refresh_token: bool`.

### 3. `app/desktop/git_sync/errors.py`

Add:
```python
class AuthExpiredError(GitSyncError):
    """GitHub authorization expired / revoked and could not be refreshed."""
```

### 4. `app/desktop/git_sync/git_sync_manager.py` — the refresh engine

**New constructor arg**: `project_path: str | None = None` (the project.kiln path used to
key config; needed to read/persist refreshed tokens). Store as `self._project_path`. Add
`self._refresh_lock = asyncio.Lock()`.

**`_is_auth_error(exc: Exception) -> bool`** (module or method): return True when the
pygit2 error indicates credential rejection. The credential callback in `clone.py` raises
`pygit2.GitError("Authentication failed. Credentials were rejected by the server.")`;
detect by checking the message for `"authentication failed"` / `"credentials were
rejected"` / `"401"` / `"403"` (case-insensitive). Anything else is treated as network.

**`_ensure_valid_oauth_token(self, *, force: bool = False) -> None`** (proactive/reactive):
```
if self._auth_mode != "github_oauth": return
cfg = get_git_sync_config(self._project_path)         # None-safe
expires_at = cfg.oauth_token_expires_at
refresh_token = cfg.oauth_refresh_token
if not force:
    if expires_at is None: return                     # non-expiring / legacy → no-op
    if time.time() < expires_at - REFRESH_SKEW_SECONDS: return   # still valid
async with self._refresh_lock:
    cfg = get_git_sync_config(self._project_path)      # re-read under lock (double-check)
    if not force and cfg.expires_at valid: return
    if cfg.oauth_refresh_token is None:
        raise AuthExpiredError(...)                    # nothing to refresh
    try:
        result = await refresh_access_token(cfg.oauth_refresh_token)
    except OAuthError as e:
        raise AuthExpiredError(...) from e
    update_oauth_tokens(self._project_path, result)    # persist rotated tokens
    self._oauth_token = result.access_token            # in-memory for this manager
```

**Wire into remote ops:**
- `fetch()`: call `await self._ensure_valid_oauth_token()` first; then current logic. The
  `except pygit2.GitError` branch becomes:
  ```
  except pygit2.GitError as e:
      if _is_auth_error(e) and <oauth + has refresh + not already refreshed>:
          await self._ensure_valid_oauth_token(force=True)   # reactive
          await self._run_git(self._fetch_sync)              # retry once
      elif _is_auth_error(e):
          raise AuthExpiredError(...) from e
      else:
          raise RemoteUnreachableError(...) from e
  ```
  If the retried fetch still raises an auth error → `AuthExpiredError`.
- `commit_and_push()`: call `await self._ensure_valid_oauth_token()` before the first
  `_push_sync`. Apply the same auth-vs-network classification to push failures (the
  current code logs the first push error and tries fetch+rebase+retry; ensure an auth
  rejection becomes `AuthExpiredError`, not a generic conflict/unreachable).

**Re-raise pass-through**: in `ensure_fresh()` and `ensure_fresh_for_read()`, add
`except AuthExpiredError: raise` alongside the existing `except RemoteUnreachableError:
raise` so the catch-all `except Exception` does not re-wrap it into
`RemoteUnreachableError`.

### 5. `app/desktop/git_sync/registry.py` + call sites

Thread `project_path` through `get_or_create(...)` and into `GitSyncManager(...)`, and
set `existing._project_path = project_path` in the overwrite branch (mirroring the token
overwrite). Call sites to update:
- `app/desktop/git_sync/middleware.py` `_get_manager_for_request` (it already resolves the
  project_path/config — pass it in).
- `app/desktop/desktop_server.py` `_start_background_syncs` (iterates `git_sync_projects`
  keyed by project_path — pass the key).

### 6. `app/desktop/git_sync/middleware.py`

Add to `ERROR_MAP`:
```python
AuthExpiredError: (401, "GitHub authorization expired. Reconnect your GitHub account in the project's Git Sync settings."),
```
Import `AuthExpiredError`. (Background sync already swallows/logs exceptions — confirm an
`AuthExpiredError` there just logs a clear warning and does not crash the poll loop.)

### 7. Frontend (`app/web_ui/`) — thread the new fields through

Backend response/request models gain the fields, so regenerate the OpenAPI bindings
first: `app/web_ui/src/lib/generate_schema.sh` (validated by
`app/web_ui/src/lib/check_schema.sh`). Then update the **hand-written** types/functions
(they duplicate the generated types — both must change):

- `app/web_ui/src/lib/git_sync/api.ts`: `OAuthStatusResponse` type; `saveConfig` and
  `updateConfig` inline request types/bodies — add `oauth_refresh_token`,
  `oauth_token_expires_at`, `oauth_refresh_token_expires_at`.
- `app/web_ui/src/lib/git_sync/oauth_flow.ts`: `OAuthFlowCallbacks.onSuccess` changes
  from `(token: string)` to a payload object `{ oauth_token, oauth_refresh_token,
  oauth_token_expires_at, oauth_refresh_token_expires_at }`; the poll code reads the new
  fields off the status response.
- `app/web_ui/src/lib/git_sync/oauth_with_install.ts`: `on_success` signature + the
  `stored_token` holder become the payload object; `check_access` forwards it.
- `app/web_ui/src/lib/stores/git_import_wizard_store.ts`: add the three fields to
  `GitImportWizardState`, initial state, and keep the `github_oauth` validation.
- `app/web_ui/src/lib/components/import/step_credentials.svelte`,
  `import_project.svelte` (`on_credentials_success`), `step_complete.svelte`
  (`saveConfig` body): carry the payload into the store and into `saveConfig`.
  `step_branch.svelte` only needs the access token for clone/list/test (unchanged
  semantics — it can keep using `oauth_token`).
- `app/web_ui/src/lib/git_sync/git_sync_status.svelte`: reconnect `on_success` passes the
  payload to `updateConfig`.

> Frontend timestamps are **opaque pass-through** values (computed server-side). The
> frontend never interprets or refreshes; it only carries them from OAuth status into
> save/update config.

## Concurrency & correctness

- One `GitSyncManager` per repo (registry singleton); background sync uses the same
  instance. A per-manager `asyncio.Lock` (`_refresh_lock`) serializes refreshes →
  GitHub's single-use refresh token is consumed exactly once. Double-check expiry after
  acquiring the lock so a coroutine that waited doesn't refresh again.
- Persist (`update_oauth_tokens`) is a synchronous read-modify-write of the config dict
  with no `await` in the middle → no event-loop interleaving across projects.

## Error handling strategy

- Renewable problems are renewed silently (B2/B3).
- Unrenewable auth → `AuthExpiredError` → 401 with an actionable message (consumed later
  by `git_auth_recovery`).
- Network/remote → `RemoteUnreachableError` → 503 (unchanged).
- Persist tokens only after a successful refresh; never persist partial state.

## Testing strategy

Python (`pytest`), colocated `app/desktop/git_sync/test_*.py` + integration tests:

- **oauth**: `exchange_code_for_token` parses all fields and computes `expires_at`
  (mock httpx); missing `expires_in` → `None`; `refresh_access_token` success + rotation
  + `OAuthError` on failure. Patch `time.time` for deterministic expiry.
- **config**: new fields round-trip; legacy config (missing keys) defaults to `None`;
  `update_oauth_tokens` updates only token fields and is a no-op for unknown project_path.
- **manager**: `_ensure_valid_oauth_token` — valid (no network call), within skew (no
  call), expired+refresh (calls refresh, persists, updates `_oauth_token`),
  expired+no-refresh (`AuthExpiredError`), non-oauth mode (no-op), `force=True`; refresh
  serialized under concurrency (two awaiters → one network refresh). `_is_auth_error`
  classification. `fetch()`/`commit_and_push()` reactive refresh + single retry; auth vs
  network branching. `ensure_fresh*` re-raise `AuthExpiredError`.
- **middleware**: `AuthExpiredError` → 401 + message; `RemoteUnreachableError` still 503.
- **api**: callback stores refresh fields in flow; status returns them; save/update
  persist them; auth-mode switch clears refresh fields.
- **background_sync**: `AuthExpiredError` is logged and the poll loop survives.

Frontend (`vitest`):
- `oauth_flow.test.ts`: `onSuccess` receives the payload object; status mocks include the
  new fields.
- `api.test.ts` / wizard store tests: new fields threaded into save/update bodies.

## Verification (end-to-end)

1. `uv run ./checks.sh --agent-mode` (lint, format, ty, pytest, web lint/format/check/
   test/build, schema check).
2. Schema regen: `app/web_ui/src/lib/generate_schema.sh`, confirm
   `app/web_ui/src/lib/check_schema.sh` passes.
3. Manual (optional): connect a repo via OAuth; set `oauth_token_expires_at` in config to
   a near-past value to force B2; confirm a fetch triggers a refresh (new token persisted)
   and sync continues. Clear `oauth_refresh_token`; confirm the next op returns 401 with
   the reconnect message (not 503).
4. **Prerequisite check**: confirm the GitHub App has "Expire user authorization tokens"
   enabled (GitHub App settings → Optional features) — required for GitHub to issue
   refresh tokens at all (B6).
