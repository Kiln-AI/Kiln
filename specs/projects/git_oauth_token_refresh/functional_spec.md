---
status: complete
---

# Functional Spec: GitHub OAuth Token Refresh

## Background

Git sync runs entirely client-side in the desktop app (`app/desktop/git_sync/`) using
pygit2. For GitHub-App-connected projects, the OAuth **user access token** is used as the
git HTTPS password (`pygit2.UserPass(username="x-token", password=token)`). These tokens
expire; Kiln currently never refreshes them. See `project_overview.md` for the root cause.

## Goals

1. Persist GitHub's `refresh_token` + token expiry timestamps when a user connects or
   reconnects via OAuth.
2. Keep the OAuth access token valid automatically for the life of the refresh token
   (~6 months), with no user action.
3. When the token genuinely cannot be renewed, surface a clear, correctly-classified
   "reconnect GitHub" error.

## Non-goals

- No change to PAT or SSH auth flows.
- No recovery UI / no fix to the `[Object object]` task-picker rendering (that is
  `git_auth_recovery`).
- No server-to-server (installation-token) auth. This stays a user-access-token (OAuth)
  flow; only the renewal piece is added.

## Behaviors

### B1. Token capture (connect & reconnect)

When `exchange_code_for_token()` succeeds, capture from GitHub's response:
- `access_token`
- `refresh_token` (may be absent — see B6)
- `expires_in` → converted to an absolute `oauth_token_expires_at` (epoch seconds,
  wall-clock, computed server-side at exchange time)
- `refresh_token_expires_in` → absolute `oauth_refresh_token_expires_at`

These flow through the existing OAuth status → wizard → `save_config` path (new connect)
and the `PATCH /config` path (reconnect from project settings), and are persisted in
`GitSyncProjectConfig`.

### B2. Proactive refresh (before each remote op)

Before any fetch or push for a `github_oauth` project, if
`now >= oauth_token_expires_at - REFRESH_SKEW` (skew = 300s), refresh the access token
using the refresh token, persist the new tokens, and use the new access token for the op.
If the token is still valid (or expiry is unknown — B6), do nothing.

### B3. Reactive refresh (on auth rejection)

If a fetch/push fails with an authentication rejection (not a network error) for a
`github_oauth` project that has a refresh token, and a refresh has not already been
attempted in this operation, force a refresh (ignoring skew) and retry the op once. This
covers clock skew and server-side token invalidation that proactive checks miss.

### B4. Refresh token rotation

GitHub rotates the refresh token on every refresh: the response contains a **new**
`refresh_token` and invalidates the old one. The new refresh token (and new expiries)
**must** be persisted immediately on every successful refresh. Persist only after a
successful response; on failure, leave stored credentials untouched.

### B5. Correct error classification

- **Auth cannot be renewed** (refresh token missing/expired, refresh request returns an
  OAuth error, or pygit2 reports credentials rejected and reactive refresh fails) →
  raise a new `AuthExpiredError` → HTTP **401** with detail:
  `"GitHub authorization expired. Reconnect your GitHub account in the project's Git Sync settings."`
- **Genuine network/remote failure** (timeout, DNS, connection refused, non-auth
  `pygit2.GitError`) → keep existing `RemoteUnreachableError` → HTTP 503
  `"Cannot sync with remote. Check your connection."`

### B6. Tokens with no expiry (app setting OFF / legacy)

If GitHub returns no `expires_in`/`refresh_token` (the app's "Expire user authorization
tokens" option is OFF), the access token is long-lived: store
`oauth_token_expires_at = None`, `oauth_refresh_token = None`. Proactive refresh is a
no-op; the token is used as-is. Sync works indefinitely without refresh. (Operational
note: for the refresh path to engage at all, the GitHub App must have "Expire user
authorization tokens" enabled. The production app almost certainly already does, since
that is what produces the bug. This should be verified, not assumed — see verification.)

### B7. Migration of existing OAuth users

Existing configs have `oauth_token` but no refresh token / expiry (`expires_at = None`).
Behavior: the stored token is used until it fails; on failure → `AuthExpiredError` (401
reconnect message), since there is no refresh token to use. After the user reconnects,
the new tokens include a refresh token and auto-refresh works from then on. No migration
script is required.

## Edge cases & error handling

- **No refresh token but token expired** (legacy/setting-off user whose token died):
  `AuthExpiredError`. Do not loop.
- **Refresh request fails (network)**: surface as `AuthExpiredError` (user can reconnect)
  rather than silently retrying forever; the refresh token itself is unverified, so we
  cannot distinguish "GitHub down" from "refresh token dead" cleanly — prefer the
  actionable reconnect message. (Acceptable trade-off; documented.)
- **Concurrent refresh**: background sync (every 10s) and an inbound request can both hit
  expiry at once. Refresh must be serialized per repo with double-checked expiry so the
  single-use refresh token is consumed exactly once.
- **Background sync** auth failures: log clearly and keep the existing
  retry-on-next-poll behavior. Background sync must not crash on `AuthExpiredError`.
- **Multiple Kiln projects sharing one clone** (rare: two imports of the same repo):
  refresh persists to the manager's own project config; other projects sharing the clone
  may retain a stale token in config until their next refresh/restart. Documented known
  limitation; the common one-project-per-clone case is fully correct.

## Contracts

### Config (`GitSyncProjectConfig`) — new fields

```python
oauth_refresh_token: str | None
oauth_token_expires_at: float | None            # epoch seconds, wall-clock
oauth_refresh_token_expires_at: float | None
```
`oauth_refresh_token` is added to `sensitive_keys` for `git_sync_projects` in
`libs/core/kiln_ai/utils/config.py` (redaction in logs/exports).

### API fields (additive, optional, backward-compatible)

- `OAuthStatusResponse`: add `oauth_refresh_token`, `oauth_token_expires_at`,
  `oauth_refresh_token_expires_at`.
- `SaveConfigRequest` and `UpdateConfigRequest`: accept the same three fields.
- `GitSyncConfigResponse`: no raw tokens exposed (unchanged); optionally add a boolean
  `has_oauth_refresh_token` for diagnostics (optional).

### Error → HTTP mapping (middleware `ERROR_MAP`)

| Exception | Status | Detail |
|---|---|---|
| `AuthExpiredError` (new) | 401 | "GitHub authorization expired. Reconnect your GitHub account in the project's Git Sync settings." |
| `RemoteUnreachableError` | 503 | "Cannot sync with remote. Check your connection." (unchanged) |

## Configuration & defaults

- `REFRESH_SKEW_SECONDS = 300` (refresh when within 5 min of expiry).
- GitHub token endpoint: `https://github.com/login/oauth/access_token` with
  `grant_type=refresh_token` (same endpoint used for code exchange).
- httpx timeout for refresh: 30s (matches existing exchange call).

## Constraints

- **Single process / single event loop**: the desktop app is one FastAPI process;
  per-repo `asyncio.Lock` is sufficient for refresh serialization. Config
  read-modify-write for the token fields must be synchronous (no `await` between read and
  write) so coroutines cannot interleave a partial update.
- **Security**: the refresh token transits the localhost frontend (sessionStorage) and
  is stored in the config YAML exactly as `oauth_token` already is. Acceptable for a
  local desktop app; covered by `sensitive_keys` redaction.
- **Clocks**: expiry uses wall-clock `time.time()` (token validity is wall-clock), not
  `time.monotonic()` (which is used only for the in-memory OAuth flow TTL).
