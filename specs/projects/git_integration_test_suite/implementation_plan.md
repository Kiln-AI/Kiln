---
status: complete
---

# Implementation Plan: Git Integration Test Suite

## Phases

- [x] Phase 1: Fixtures, Helpers, and Fixture Validation Tests
  - Create `app/desktop/git_sync/integration_tests/` directory and `__init__.py`
  - `conftest.py`: import shared helpers from parent conftest (`git_repos`, `commit_in_repo`, `push_from`, `SIG`), add `second_clone`, `manager`, and `write_ctx` (parametrized library/api) fixtures
  - `WriteContext` protocol, `LibraryWriteContext`, `APIWriteContext` implementations
  - `build_test_app()` factory for API-mode tests
  - Git state assertion helpers (`assert_clean_working_tree`, `assert_remote_has_commit`, `assert_stash_contains`, `assert_commit_contains_files`, `assert_linear_history`, `get_head_sync`, `get_stash_list`)
  - Network failure fixtures (`NetworkFailure`, `NETWORK_FAILURES`, `break_network`)
  - `test_fixtures.py`: validation tests proving the infrastructure works — git repo creation, clone, commit, push, second clone divergence, WriteContext in both modes, assertion helpers, network failure injection

- [x] Phase 2: Happy Path and Basic Operations
  - `test_happy_path.py`: scenarios 1–5 (write→commit→push, read passes through, no-op write, multi-file atomic, arbitrary disk writes)
  - `test_file_operations.py`: scenarios 32–33, 42–43 (file deletions, .gitignore, mixed create+delete, net-zero)
  - `test_middleware_routing.py`: scenarios 30–31 (non-project routes, manual mode)

- [x] Phase 3: Rollback, Conflicts, and Network Failures
  - `test_rollback.py`: scenarios 6–7, 34 (handler error, push failure, rebase-then-fail reflog check)
  - `test_conflicts.py`: scenarios 8–9, 38–41 (push race + rebase succeeds, unresolvable rebase, delete/modify, add/add, empty commit, ABA)
  - `test_network_failure.py`: scenarios 17, 26 (parameterized network failures on reads and writes)

- [x] Phase 4: Crash Recovery
  - `test_crash_recovery.py`: scenarios 10–13, 35–37 (dirty state, in-progress rebase, unpushed commits, unrecoverable, all-three-combined, force-push, partial recovery failure)

- [x] Phase 5: Locking, Freshness, Sync, Decorators, and Batch
  - `test_locking.py`: scenarios 14–15, 45 (serialization, timeout, non-reentrant deadlock)
  - `test_freshness.py`: scenarios 16, 18, 29 (pull before write, stale read updates, threshold skips fetch)
  - `test_background_sync.py`: scenarios 19–21 (fetch+ff, no-op, skip diverged)
  - `test_decorators.py`: scenarios 22–25 (@write_lock, @no_write_lock, streaming under lock, long hold warning)
  - `test_no_write_lock_batch.py`: scenario 44 (partial failure across iterations)
  - `test_happy_path.py` addition: scenario 28 (sequential writes each get own commit)
