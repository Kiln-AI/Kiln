---
status: complete
---

# Implementation Plan: Git Auto Sync

## Phases

- [x] Phase 1: Core GitSyncManager
  - Error types (`errors.py`)
  - Config model and helpers (`config.py`)
  - `GitSyncManager` class: pygit2 single-threaded executor, write lock, all core operations (`ensure_clean`, `ensure_fresh`, `get_head`, `has_dirty_files`, `commit_and_push`, `rollback`, `fetch`, `can_fast_forward`, `fast_forward`, `close`)
  - Commit message generation (`commit_message.py`)
  - Unit tests using temporary bare/cloned git repos via pygit2

- [x] Phase 2: Middleware, Decorators, and Registry
  - `@write_lock` and `@no_write_lock` decorator annotations
  - `GitSyncRegistry` singleton registry
  - `GitSyncMiddleware` (BaseHTTPMiddleware): lock acquisition, clean/fresh checks, commit-on-exit, rollback-on-error, response buffering, error-to-HTTP mapping
  - Dev-mode safety nets (dirty state detection, long lock hold warning)
  - Register middleware in `desktop_server.py`
  - Early integration test: verify BaseHTTPMiddleware holds lock correctly across request lifecycle (blocking gate per spec)
  - Unit + integration tests for middleware and registry

- [x] Phase 3: Background Sync and End-to-End
  - `BackgroundSync` class: two-phase poll loop (fetch without lock, fast-forward under lock), idle pause/resume
  - Lifecycle management via FastAPI lifespan
  - `ensure_fresh_for_read()` freshness threshold for GET requests
  - End-to-end integration tests (full request lifecycle, concurrent writes, conflict simulation, crash recovery, background pickup)
  - README documentation

- [ ] Phase 4: Setup Wizard UI
  - Auto/manual mode toggle in project settings UI
  - Setup wizard: "Sync from Git" option in Import Project flow
  - Step 1: Git URL entry + remote access check
  - Step 2: PAT credential entry (with GitHub deeplink), test access on save
  - Step 3: Branch selection from remote, clone into `.git-projects/`, test write access
  - Step 4: Project picker (scan for `project.kiln` files, auto-select if single)
  - Step 5: Save config, enable auto-sync
  - Token expiration detection and "Update token" re-auth flow
  - API endpoints to support wizard steps (list branches, clone, test access, scan projects)
