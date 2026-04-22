---
status: draft
---

# Phase 1: Fixtures, Helpers, and Fixture Validation Tests

## Overview

Set up the integration test infrastructure: directory structure, `conftest.py` with shared fixtures, `WriteContext` abstraction for dual-mode testing (library + API), git state assertion helpers, network failure simulation fixtures, and a `test_fixtures.py` that validates all infrastructure works correctly.

## Steps

1. Create `app/desktop/git_sync/integration_tests/__init__.py` (empty)
2. Create `app/desktop/git_sync/integration_tests/conftest.py` with:
   - Import shared helpers from parent conftest (`git_repos`, `commit_in_repo`, `push_from`, `SIG`, `reset_git_sync_registry`)
   - `WriteResult` and `ReadResult` dataclasses
   - `WriteContext` protocol with `do_write()` and `do_read()` methods
   - `LibraryWriteContext` implementation (acquires write lock, calls ensure_clean/ensure_fresh, runs write_fn, commits+pushes)
   - `APIWriteContext` implementation (stores write_fn, makes HTTP requests via TestClient)
   - `build_test_app()` factory creating a minimal FastAPI app with GitSyncMiddleware and test endpoints
   - `mock_git_sync_config` context manager for patching config lookups
   - `second_clone` fixture
   - `manager` fixture
   - `write_ctx` parametrized fixture (library/api modes)
   - `api_client` fixture (API-only tests)
   - Git state assertion helpers: `assert_remote_has_commit`, `assert_clean_working_tree`, `assert_stash_contains`, `assert_commit_contains_files`, `assert_linear_history`, `get_head_sync`, `get_stash_list`, `remote_has_commit`, `get_commit_count`
   - `NetworkFailure` dataclass and `NETWORK_FAILURES` list
   - `network_failure` parametrized fixture
   - `break_network` fixture (monkeypatches fetch/push to fail)
   - `create_remote_divergence` helper function

3. Create `app/desktop/git_sync/integration_tests/test_fixtures.py` with validation tests:
   - test_git_repos_creates_valid_repos: local and remote exist, local has remote, initial commit present
   - test_commit_and_push: commit_in_repo + push_from works, remote receives commit
   - test_second_clone_independent: second_clone is separate from local, shares same remote
   - test_create_remote_divergence: creates divergence detectable by local
   - test_write_ctx_library_mode: do_write in library mode commits and pushes
   - test_write_ctx_api_mode: do_write in API mode commits and pushes
   - test_write_ctx_no_op: do_write with no file changes produces no commit
   - test_assertion_helpers: assert_clean_working_tree, assert_remote_has_commit, get_head_sync work correctly
   - test_stash_assertions: assert_stash_contains works after stashing
   - test_network_failure_fixture: break_network causes fetch/push to raise

## Tests

All tests are in `test_fixtures.py` -- this phase IS the test infrastructure plus its validation tests. Each test listed above validates a specific piece of infrastructure.
