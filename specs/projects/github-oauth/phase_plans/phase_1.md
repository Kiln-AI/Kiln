---
status: complete
---

# Phase 1: Backend OAuth Module and API Endpoints

## Overview

Add the backend infrastructure for GitHub OAuth: a new `oauth.py` module handling OAuth state management, PKCE generation, GitHub API ID resolution, and token exchange; three new API endpoints in `git_sync_api.py` (start, callback, authorize redirect, status); data model changes to support `github_oauth` auth mode and `oauth_token` field; credential plumbing through `clone.py`, `GitSyncManager`, and `registry.py`.

## Steps

### 1. Update `config.py` — Add `github_oauth` auth mode and `oauth_token` field

- Extend `AuthMode` to include `"github_oauth"`
- Add `oauth_token: str | None` to `GitSyncProjectConfig`
- Update `get_git_sync_config()` to read `oauth_token` from raw config

### 2. Update `clone.py` — Accept `oauth_token` parameter

- Add `oauth_token` parameter to `make_credentials()`
- Handle `auth_mode == "github_oauth"` same as `pat_token` but using `oauth_token`
- Thread `oauth_token` through `_ls_remote_pygit2`, `test_remote_access`, `list_remote_branches`, `clone_repo`, `_ensure_gitignore`, `test_write_access`

### 3. Update `git_sync_manager.py` — Add `oauth_token` support

- Add `_oauth_token` parameter to `__init__`
- Pass `oauth_token` through `_make_remote_callbacks()`

### 4. Update `registry.py` — Add `oauth_token` to `get_or_create()`

- Add `oauth_token` parameter
- Pass to `GitSyncManager` constructor
- Update existing manager's `_oauth_token` if changed (same pattern as `pat_token`)

### 5. Create `oauth.py` — New OAuth module

- `OAuthError` exception class
- `OAuthFlowState` dataclass
- `OAuthFlowManager` class with thread-safe flow management
- `_generate_pkce()` function
- `resolve_github_owner_id()` and `resolve_github_repo_id()` async functions
- `build_install_url()` function
- `exchange_code_for_token()` async function
- `parse_github_owner_repo()` URL parser
- Constants: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_NAME`, `CALLBACK_URL`, `OAUTH_TIMEOUT_SECONDS`

### 6. Update `git_sync_api.py` — Add OAuth endpoints and update existing models

- Add `oauth_token` to `SaveConfigRequest`, `UpdateConfigRequest`, `ListBranchesRequest`, `CloneRequest`, `TestWriteAccessRequest`, `TestAccessRequest`
- Add `has_oauth_token` to `GitSyncConfigResponse`
- Update `auth_mode` Literal types to include `"github_oauth"`
- Add `POST /api/git_sync/oauth/start` endpoint
- Add `GET /api/git_sync/oauth/callback` endpoint
- Add `GET /api/git_sync/oauth/authorize` endpoint (setup URL redirect)
- Add `GET /api/git_sync/oauth/status/{state}` endpoint
- Thread `oauth_token` through existing endpoints

### 7. Tests

- `test_oauth.py`: PKCE, OAuthFlowManager, build_install_url, exchange_code_for_token (mocked), resolve functions (mocked), URL parsing
- Update `test_config.py`: oauth_token field tests
- Update `test_git_sync_api.py`: new endpoint tests, oauth_token in existing endpoints
