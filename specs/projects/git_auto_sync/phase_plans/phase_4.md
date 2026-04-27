---
status: draft
---

# Phase 4: Setup Wizard UI

## Overview

This phase adds the UI-driven setup wizard for Git Auto Sync, including:
- API endpoints to support wizard steps (list branches, clone, test access, scan projects)
- A multi-step wizard UI accessible from the Import Project flow ("Sync from Git")
- Auto/manual mode toggle in project settings
- Token expiration detection with "Update token" re-auth flow

## Steps

### Backend: New API Endpoints

1. **Create `app/desktop/git_sync/git_sync_api.py`** with the following endpoints:
   - `POST /api/git_sync/test_access` — Test access to a git remote URL (with optional PAT). Returns success or auth error.
   - `POST /api/git_sync/list_branches` — List branches from remote. Accepts URL + optional PAT.
   - `POST /api/git_sync/clone` — Clone a repo branch into `.git-projects/` directory. Accepts URL, branch, PAT. Returns clone path.
   - `POST /api/git_sync/test_write_access` — Push an empty commit to verify write access. Accepts clone path + PAT.
   - `POST /api/git_sync/scan_projects` — Scan a cloned repo for `project.kiln` files. Returns list of paths + project names.
   - `POST /api/git_sync/save_config` — Save git sync config for a project. Enables auto-sync.
   - `GET /api/git_sync/config/{project_id}` — Get git sync config for a project.
   - `PATCH /api/git_sync/config/{project_id}` — Update git sync config (e.g., toggle mode, update token).

2. **Update `app/desktop/git_sync/config.py`**:
   - Add `save_git_sync_config()` function
   - Add credential (PAT) field to config, stored as sensitive
   - Add `git_url` field to config

3. **Register new API routes** in `desktop_server.py`.

### Backend: Clone and Credential Logic

4. **Add clone logic** in `git_sync_manager.py` or a new `clone.py`:
   - Clone with credential callbacks for PAT auth
   - Generate `.gitignore` for OS artifacts (.DS_Store, Thumbs.db, desktop.ini, ._*)
   - Calculate clone path: `~/Kiln Projects/.git-projects/[ID] - [projectname][N]`
   - Test write access: empty commit + push

5. **Add credential support** to `git_sync_manager.py`:
   - PAT-based RemoteCallbacks for fetch/push operations
   - Support passing credentials through to the manager

### Frontend: Setup Wizard

6. **Create wizard route** at `app/web_ui/src/routes/(app)/settings/git_sync/+page.svelte`:
   - Multi-step wizard with progress indicator
   - Step 1: Git URL entry + test access
   - Step 2: PAT credential entry (with GitHub deeplink)
   - Step 3: Branch selection + clone + write access test
   - Step 4: Project picker (scan for project.kiln files)
   - Step 5: Save config + completion

7. **Add "Sync from Git" option** to the Import Project flow in the manage_projects page.

8. **Add git sync status** to project settings/edit page showing current sync mode with toggle.

### Frontend: Token Update Flow

9. **Add token update UI**: When sync fails with 401, show "Update token" flow that re-uses Step 2 of the wizard.

## Tests

### Backend Tests (`app/desktop/git_sync/test_git_sync_api.py`)

- `test_test_access_success`: valid remote URL returns success
- `test_test_access_auth_required`: private repo without PAT returns auth error
- `test_test_access_with_pat`: private repo with PAT returns success
- `test_list_branches`: returns branch names from remote
- `test_list_branches_with_default`: default branch is correctly identified
- `test_clone_creates_directory`: clone creates expected directory structure
- `test_clone_path_collision`: duplicate names get counter suffix
- `test_clone_generates_gitignore`: .gitignore contains expected patterns
- `test_test_write_access_push`: empty commit pushed successfully
- `test_scan_projects_single`: finds single project.kiln
- `test_scan_projects_multiple`: finds multiple project.kiln files
- `test_scan_projects_none`: returns empty when no project.kiln found
- `test_save_config`: saves config to settings
- `test_get_config`: retrieves saved config
- `test_update_config_toggle_mode`: switching auto/manual works
- `test_credential_callbacks`: PAT credentials are passed to pygit2

### Frontend Tests (`app/web_ui/src/lib/git_sync/`)

- Component tests for each wizard step using vitest + testing-library
