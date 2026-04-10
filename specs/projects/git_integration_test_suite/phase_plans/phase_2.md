---
status: draft
---

# Phase 2: Happy Path and Basic Operations

## Overview

Implement the first set of scenario tests covering happy-path flows, file operations, and middleware routing. These are scenarios 1-5 (happy path), 30-31 (middleware routing), and 32-33, 42-43 (file operations). All dual-mode tests use the `write_ctx` fixture; API-only tests use `api_ctx` or `api_client`.

## Steps

1. Create `app/desktop/git_sync/integration_tests/test_happy_path.py` with:
   - `test_write_commit_push` (scenario 1): write a file via `write_ctx.do_write()`, verify committed, pushed, remote has commit, clean working tree. API mode also checks commit message contains API path and file count.
   - `test_read_passes_through` (scenario 2): API-only. Make a GET request, verify no new commits, no lock acquired.
   - `test_no_op_write` (scenario 3): `do_write` with no file changes, verify no commit created, remote unchanged.
   - `test_multi_file_atomic_commit` (scenario 4): write multiple files in a single `do_write`, verify exactly one commit containing all files, pushed.
   - `test_arbitrary_disk_writes_captured` (scenario 5): write a `.txt` file directly via filesystem in the write_fn, verify it appears in commit and is pushed.

2. Create `app/desktop/git_sync/integration_tests/test_file_operations.py` with:
   - `test_file_deletion_committed` (scenario 32): create and commit a file in setup, then delete it via write_fn, verify the deletion is in the commit and pushed.
   - `test_gitignore_files_not_committed` (scenario 33): set up `.gitignore` with `*.tmp`, write a `.tmp` file in write_fn, verify it's NOT committed.
   - `test_create_and_delete_in_same_request` (scenario 42): write_fn creates new files and deletes existing files, verify single atomic commit with both additions and deletions.
   - `test_net_zero_no_commit` (scenario 43): write_fn creates a temp file then deletes it before returning, verify no commit.

3. Create `app/desktop/git_sync/integration_tests/test_middleware_routing.py` with:
   - `test_non_project_routes_pass_through` (scenario 30): API-only. Make requests to `/api/settings` or similar non-project URL, verify no lock, no git ops, request passes through.
   - `test_manual_mode_unaffected` (scenario 31): API-only. Configure project in manual sync_mode, make mutating requests, verify no lock, no commit.

## Tests

- `test_happy_path.py::test_write_commit_push` -- verifies scenario 1 in both library and API modes
- `test_happy_path.py::test_read_passes_through` -- verifies scenario 2 (API-only)
- `test_happy_path.py::test_no_op_write` -- verifies scenario 3 in both modes
- `test_happy_path.py::test_multi_file_atomic_commit` -- verifies scenario 4 in both modes
- `test_happy_path.py::test_arbitrary_disk_writes_captured` -- verifies scenario 5 in both modes
- `test_file_operations.py::test_file_deletion_committed` -- verifies scenario 32 in both modes
- `test_file_operations.py::test_gitignore_files_not_committed` -- verifies scenario 33 in both modes
- `test_file_operations.py::test_create_and_delete_in_same_request` -- verifies scenario 42 in both modes
- `test_file_operations.py::test_net_zero_no_commit` -- verifies scenario 43 in both modes
- `test_middleware_routing.py::test_non_project_routes_pass_through` -- verifies scenario 30 (API-only)
- `test_middleware_routing.py::test_manual_mode_unaffected` -- verifies scenario 31 (API-only)
