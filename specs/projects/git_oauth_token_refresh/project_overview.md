---
status: complete
---

# GitHub OAuth Token Refresh

## Problem

Users who connect a project to GitHub via the **Kiln AI GitHub Sync** GitHub App
("Connect with GitHub" / `auth_mode="github_oauth"`) sync fine at first, then after
roughly 8–24 hours (usually overnight) every sync starts failing with HTTP 503
`"Cannot sync with remote. Check your connection."`.

## Root cause

GitHub App **user access tokens are short-lived** (8h default when "Expire user
authorization tokens" is enabled on the app). GitHub returns a `refresh_token` (valid
~6 months) and `expires_in` alongside the access token so clients can renew silently.

Kiln throws all of that away:

- `app/desktop/git_sync/oauth.py` `exchange_code_for_token()` returns only
  `data["access_token"]` — `refresh_token`, `expires_in`, and
  `refresh_token_expires_in` are discarded.
- `GitSyncProjectConfig` (`app/desktop/git_sync/config.py`) has no field to store a
  refresh token or expiry.
- There is **no refresh logic anywhere** — no `grant_type=refresh_token` call, no
  expiry check.

When the access token expires, pygit2's credential callback is rejected, raising
`pygit2.GitError("Authentication failed...")`, which `GitSyncManager.fetch()` wraps as
`RemoteUnreachableError` → middleware maps to 503 "Check your connection." So an **auth
expiry is mislabeled as a network problem**, and there is no path back to a working
state without manual reconnection.

This only affects `github_oauth` users. PAT (`pat_token`) and SSH (`system_keys`) users
have long-lived credentials and are unaffected.

## Scope of this project

1. **Capture** the refresh token and expiry returned by GitHub at connect/reconnect time
   and persist them.
2. **Auto-refresh** the access token before it expires (proactive), and recover by
   refreshing on an auth-rejection (reactive), so OAuth sync keeps working indefinitely.
3. **Classify the error correctly**: when refresh is impossible (no/expired refresh
   token, revoked access), surface a distinct, accurate "reconnect your GitHub account"
   error instead of the misleading "check your connection."

## Out of scope (belongs to the separate `git_auth_recovery` project)

- The task-picker `[Object object]` rendering bug.
- The user-facing recovery UX (re-auth button, "remove existing and re-sync" flow).

This project's job is *prevention* (keep the token alive) plus emitting a *correct*
auth error when prevention is impossible. `git_auth_recovery` builds the UX that acts on
that error.

## Success criteria

- An OAuth-connected project keeps syncing past 8h / overnight with no user action.
- After ~6 months (refresh-token expiry) or if access is revoked/uninstalled, the user
  sees a clear "reconnect GitHub" error (HTTP 401), not "check your connection."
- Existing OAuth users (who have a token but no stored refresh token) get the clear
  reconnect error once their token expires, and reconnecting enables auto-refresh going
  forward.
- PAT and SSH sync behavior is unchanged.
