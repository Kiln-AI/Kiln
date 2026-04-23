---
status: draft
---

# Phase 4: Crash Recovery

## Overview

Implements `test_crash_recovery.py` covering scenarios 10-13 and 35-37 from the functional spec. These tests verify that the system can auto-recover from dirty state, in-progress rebases, unpushed commits, combined corruption states, remote force-pushes, and partial recovery failures.

## Steps

1. Create `app/desktop/git_sync/integration_tests/test_crash_recovery.py` with the following test classes:
   - `TestDirtyStateRecovery` (Scenario 10): Leave dirty files in repo, verify ensure_clean stashes them, next write succeeds
   - `TestInProgressRebaseRecovery` (Scenario 11): Leave repo in rebase state with conflicts, verify ensure_clean aborts rebase and stashes dirty files
   - `TestUnpushedCommitsRecovery` (Scenario 12): Create local-only commits, verify ensure_clean resets to match remote, orphaned commit in reflog
   - `TestUnrecoverableState` (Scenario 13): Mock ensure_clean to leave dirty state, verify 500 error with "unexpected state" message
   - `TestAllThreeSimultaneous` (Scenario 35): Combine unpushed commit + rebase conflict + dirty files, verify all three recovered
   - `TestRemoteForcePush` (Scenario 36): Fork local/remote history (force-push), verify recovery detects divergence and resets
   - `TestPartialRecoveryFailure` (Scenario 37): Mock stash to fail on first call, verify second attempt succeeds

## Tests

- `test_dirty_state_stashed_on_write`: Dirty files are stashed before new write proceeds (Scenario 10)
- `test_dirty_state_stash_has_recovery_message`: Stash entry has "[Kiln]" recovery message
- `test_dirty_state_new_write_succeeds`: After dirty state recovery, new write commits and pushes normally
- `test_in_progress_rebase_aborted`: In-progress rebase is aborted, dirty state stashed (Scenario 11)
- `test_in_progress_rebase_new_write_succeeds`: After rebase recovery, new write proceeds normally
- `test_unpushed_commits_reset`: Unpushed commits are reset to match remote (Scenario 12)
- `test_unpushed_commits_in_reflog`: Orphaned commit is still in reflog (recoverable)
- `test_unpushed_commits_new_write_succeeds`: After reset, new write proceeds normally
- `test_unrecoverable_state_returns_error`: Unrecoverable state returns CorruptRepoError/500 (Scenario 13)
- `test_unrecoverable_state_no_partial_commits`: No partial commits or pushes occurred
- `test_all_three_simultaneous_recovery`: Combined dirty+rebase+unpushed all recovered (Scenario 35)
- `test_all_three_new_write_succeeds`: After combined recovery, new write proceeds
- `test_force_push_recovery`: Local divergence from remote force-push is detected and reset (Scenario 36)
- `test_force_push_new_write_succeeds`: After force-push recovery, new write proceeds
- `test_partial_recovery_first_fails`: First recovery attempt fails (Scenario 37)
- `test_partial_recovery_second_succeeds`: Second recovery attempt succeeds and write proceeds
