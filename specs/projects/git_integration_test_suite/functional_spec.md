---
status: complete
---

# Functional Spec: Git Integration Test Suite

## Purpose

A clean-room integration test suite for Kiln's git auto-sync system. The tests verify the system's behavioral guarantees using real git repositories — no mocks of git itself. The suite is intentionally written from a black-box perspective: it describes what the system *should do*, not how it's implemented internally.

The implementing agent will read only this spec (it MUST NOT READ the design docs), ensuring tests validate actual behavior rather than mirroring implementation assumptions.

## System Under Test: Behavioral Summary

Kiln's git auto-sync system automatically commits and pushes changes to a remote git repository whenever a mutating API request completes. It keeps the local repo fresh via background polling, handles conflicts via rebase, and recovers from crashes automatically. The system operates at two levels:

1. **Library level (GitSyncManager):** A Python class that manages a git repository. Provides a write lock, commit/push, rollback, conflict resolution, crash recovery, and background sync primitives. All git operations run through a single-threaded executor for thread safety.

2. **API level (FastAPI middleware):** HTTP middleware that automatically wraps mutating requests (POST/PUT/PATCH/DELETE) with the write lock and commit-on-exit behavior. GET/HEAD requests pass through without locking.

### Core Guarantees Being Tested

1. **No data loss:** Every file write is either committed+pushed to remote, or preserved in git stash. Arbitrary disk writes in the project folder are captured — nothing is silently dropped.
2. **Self-healing:** The system can always recover to a "clean, in sync with remote" state without manual intervention, no matter what local state it finds.
3. **Conflict safety:** Git conflicts (push races, rebase failures) are handled automatically. The system never leaves the repo in a state requiring manual conflict resolution.
4. **Atomicity:** Each API request's changes are committed as a single atomic batch. Partial commits never occur.

## Test Infrastructure

### Real Git Repos

All tests use real git repositories created in temporary directories. No mocking of git operations.

- **Fixture:** Each test gets a fresh pair of repos: a bare "remote" repo and a cloned "local" repo.
- **Local remote:** The bare repo acts as the remote. This allows testing push/pull/conflict scenarios without a network.
- **Cleanup:** Repos live in `tmp_path` (pytest manages cleanup).

### Two Test Levels

Every scenario should be tested at both levels where applicable:

1. **Library mode:** Call `GitSyncManager` methods directly — acquire the write lock, write files, call `commit_and_push()`, etc.
2. **API mode:** Use FastAPI `TestClient` to make HTTP requests through the middleware. The middleware handles locking, commit, push automatically.

**Reuse via parameterization:** Use a pytest parameterize or context-manager pattern so each test scenario runs at both levels without duplicating test logic. The fixture/context should:
- In library mode: provide `GitSyncManager`, let the test acquire the write lock and call methods directly.
- In API mode: set up a `TestClient` with `GitSyncMiddleware` and test endpoints, let the test make HTTP requests.

Both modes should expose a consistent interface for: "do a write operation" and "verify the resulting git state."

### Network Failure Simulation

The system must handle a variety of network failure modes gracefully. Use monkeypatch/mock to simulate failures at the git transport layer (fetch, push). Network failure scenarios should be parameterized across multiple failure types where feasible:

- **Connection refused / timeout:** Remote is completely unreachable.
- **Auth failure:** Credentials rejected (e.g., expired token).
- **Intermittent failure:** First attempt fails, subsequent attempts may succeed.

For each failure type, verify:
- The system returns an appropriate error to the caller (not a stack trace or silent corruption).
- Local repo state is not corrupted — either the operation fully succeeded or was cleanly rolled back/stashed.
- The system can process the next request normally after a failure.

### Test Location

Tests live in a dedicated directory, separate from existing unit tests: a new top-level integration test directory (e.g., `app/desktop/git_sync/integration_tests/` or similar). These tests do not import or depend on existing unit test files.

## Test Scenarios

### 1. Happy Path: Write → Commit → Push

**Goal:** A mutating request writes files, and those changes are automatically committed and pushed to remote.

- Make a write operation that creates/modifies one or more files in the repo.
- Verify: local repo has a new commit containing exactly those file changes.
- Verify: remote repo has the same commit (pushed successfully).
- Verify: the commit message includes the file count and API path (API mode).
- Verify: the working tree is clean after the operation.
- Verify: the response is successful (API mode: 200/201).

### 2. Happy Path: Read Passes Through

**Goal:** GET/HEAD requests do not acquire the write lock and do not commit.

- Make a read operation.
- Verify: no new commits were created.
- Verify: the write lock was not acquired.

### 3. No-Op Write (No File Changes)

**Goal:** A mutating request that doesn't change any files produces no commit.

- Make a write operation that results in no file changes.
- Verify: no new commits created.
- Verify: remote unchanged.

### 4. Multi-File Atomic Commit

**Goal:** All file changes from a single request are committed together as one atomic commit.

- Make a write operation that creates/modifies multiple files.
- Verify: exactly one new commit containing all the changed files.
- Verify: pushed to remote as a single commit.

### 5. Arbitrary Disk Writes Are Captured

**Goal:** Any file written to the project directory is captured by git, even if not created through the data model.

- During a write operation, create files directly via filesystem (not through the data model) — e.g., write a random `.txt` file.
- Verify: the file appears in the commit.
- Verify: pushed to remote.

### 6. Rollback on Handler Error

**Goal:** If the request handler raises an exception, all file changes are rolled back. Nothing is committed or pushed.

- Make a write operation where the handler writes files, then raises an exception.
- Verify: no new commits on local or remote.
- Verify: dirty files are stashed (recoverable via `git stash list`).
- Verify: working tree is clean after rollback.
- Verify: error response returned to client (API mode).

### 7. Rollback on Push Failure (After Retry Exhausted)

**Goal:** If push fails and retry also fails, the local commit is rolled back and changes are stashed.

- Make a write operation.
- Simulate: push fails on both attempts (first push and retry).
- Verify: local repo reset to pre-request HEAD.
- Verify: dirty state stashed (recoverable).
- Verify: error response: 409 (API mode).

### 8. Push Conflict → Fetch + Rebase → Retry Succeeds

**Goal:** When push fails because the remote has diverged, the system fetches, rebases, and retries.

- Make a write operation that creates a commit.
- Simulate: between commit and push, another commit appears on remote (push a commit to the bare remote from a second clone).
- Verify: the system fetches, rebases, and pushes successfully.
- Verify: remote has both commits (the other user's and ours), linear history.
- Verify: working tree is clean, response is success.

### 9. Push Conflict → Rebase Conflict (Unresolvable)

**Goal:** When rebase produces conflicts that can't be auto-resolved, the system aborts and rolls back cleanly.

- Make a write operation that modifies a specific file.
- Simulate: the same file was modified differently on remote (conflicting content).
- Verify: rebase is aborted, local commit rolled back.
- Verify: dirty state stashed.
- Verify: repo is clean (no conflict markers, no in-progress rebase).
- Verify: error response: 409 (API mode).

### 10. Crash Recovery: Dirty State on Write Request

**Goal:** If the repo is dirty when a new write request arrives (e.g., prior crash left uncommitted files), the system auto-recovers.

- Set up: leave dirty files in the repo (simulate a crash by writing files without committing).
- Make a new write request.
- Verify: the dirty files are stashed (recoverable).
- Verify: the new write operation proceeds normally (commit + push).
- Verify: old dirty state is in `git stash list` with recovery message.

### 11. Crash Recovery: In-Progress Rebase

**Goal:** If the repo has an in-progress rebase from a prior crash, the system aborts it and recovers.

- Set up: leave the repo in a rebase state (start a rebase with conflicts, don't abort).
- Make a new write request.
- Verify: rebase is aborted, dirty state stashed.
- Verify: new write proceeds normally.

### 12. Crash Recovery: Unpushed Local Commits

**Goal:** If the repo has local commits that were never pushed (prior crash after commit but before push), recovery resets to match remote.

- Set up: create a local commit that isn't pushed.
- Make a new write request.
- Verify: the unpushed commit is reset (branch matches remote).
- Verify: the orphaned commit is still in reflog (not truly lost).
- Verify: new write proceeds normally.

### 13. Crash Recovery: Unrecoverable State

**Goal:** If crash recovery can't clean up the repo, the system refuses to operate.

- Set up: put the repo in a state that `ensure_clean` can't fix (e.g., mock the recovery to leave dirty state).
- Make a write request.
- Verify: error response: 500 with "unexpected state" message.
- Verify: no partial commits or pushes occurred.

### 14. Write Lock Serialization

**Goal:** Concurrent write requests are serialized — only one holds the lock at a time.

- Start two write operations concurrently (both try to write files).
- Verify: both succeed (one waits for the other).
- Verify: two separate commits on remote, in some order.
- Verify: no corruption, no partial state.

### 15. Write Lock Timeout

**Goal:** If the write lock can't be acquired within the timeout, the request fails.

- Hold the write lock from a background task.
- Make a write request with a short timeout.
- Verify: request fails with 503 "Another save is in progress" (API mode).
- Verify: no commits or state changes.

### 16. Ensure Fresh: Pull Before Write

**Goal:** Before processing a write request, the system pulls remote changes so the write is based on fresh state.

- Push a new commit to remote from a second clone.
- Make a write request (without manually triggering a sync first).
- Verify: the local repo pulled the remote changes before the handler ran.
- Verify: the handler's changes are on top of the pulled changes.

### 17. Ensure Fresh for Reads: Stale + Unreachable = Error

**Goal:** A read request fails if the local state is stale and the remote is unreachable.

- Let the freshness threshold expire.
- Simulate network failure (parameterized: connection refused, auth failure, timeout).
- Make a read request.
- Verify: error response indicating sync failure (API mode).
- Verify: no state corruption.

### 18. Ensure Fresh for Reads: Stale + Reachable = Updates

**Goal:** A stale read triggers a fetch and fast-forward before serving.

- Push a new commit to remote from a second clone.
- Let the freshness threshold expire.
- Make a read request.
- Verify: local repo was updated with the remote changes before the read was served.

### 19. Background Sync: Fetch + Fast-Forward

**Goal:** The background sync functions detect remote changes and apply them locally.

- Push a new commit to remote from a second clone.
- Call the background sync operations directly (fetch, check for new commits, fast-forward under lock).
- Verify: local repo now has the new commit.
- Verify: working tree reflects the updated content.

Note: We test the sync *functions* (fetch → has_new_remote_commits → fast_forward), not the timer/poll loop.

### 20. Background Sync: No-Op When Up to Date

**Goal:** Background sync does nothing when there are no new remote commits.

- Run background sync operations when local and remote are already in sync.
- Verify: no commits created, HEAD unchanged.

### 21. Background Sync: Skips When Not Fast-Forwardable

**Goal:** If local has diverged (unpushed commits), background sync skips the fast-forward.

- Create a local commit that hasn't been pushed.
- Run background sync (fetch + check).
- Verify: fast-forward is skipped (local commit preserved, no merge).

### 22. Decorator: `@write_lock` Forces Lock on GET

**Goal:** A GET endpoint decorated with `@write_lock` acquires the write lock and triggers commit-on-exit.

- Define a GET endpoint with `@write_lock` that writes a file.
- Make a GET request.
- Verify: the write lock was acquired.
- Verify: the file change was committed and pushed.

### 23. Decorator: `@no_write_lock` Skips Lock on POST

**Goal:** A POST endpoint decorated with `@no_write_lock` does not acquire the write lock.

- Define a POST endpoint with `@no_write_lock`.
- Make a POST request.
- Verify: the write lock was NOT acquired.
- Verify: no automatic commit (the endpoint manages its own commits).

### 24. Safety Net: Streaming Response Under Write Lock

**Goal:** If a write-locked endpoint returns a streaming (SSE) response, the system returns a 500 error instead of holding the lock indefinitely.

- Define a POST endpoint that returns a `text/event-stream` response.
- Make a POST request.
- Verify: 500 response with message about missing `@no_write_lock` decorator.
- Verify: the streaming response is NOT sent to the client.

### 25. Safety Net: Long Lock Hold Warning

**Goal:** If the write lock is held longer than 5 seconds, a warning is logged.

- Define a POST endpoint that takes >5 seconds (simulate with sleep or mock).
- Make a POST request.
- Verify: a warning log is emitted mentioning "consider @no_write_lock."

### 26. Network Failure on Mutating Request

**Goal:** If the remote is unreachable when a write request needs to sync or push, the request fails and changes are rolled back.

- Simulate network failure (parameterized: connection refused, auth failure, timeout).
- Test at two points: failure during pre-write fetch (ensure_fresh), and failure during post-write push.
- Make a write request.
- Verify: error response indicating sync/push failure (API mode).
- Verify: any local file changes are rolled back/stashed.
- Verify: no partial commits pushed.
- Verify: next request after connectivity is restored succeeds normally.

### 27. Stash Preserves Data on Every Failure Path

**Goal:** Across all failure/rollback scenarios, dirty file changes end up in git stash — never silently destroyed.

This is a cross-cutting concern verified in scenarios 6, 7, 9, 10, 11, and 26. Each should confirm:
- `git stash list` contains an entry with the expected message prefix (`[Kiln]`).
- The stashed content matches what was written.

### 28. Sequential Writes: Each Gets Its Own Commit

**Goal:** Multiple sequential write requests each produce their own commit.

- Make 3 sequential write operations, each modifying different files.
- Verify: 3 separate commits on remote, each containing only its own files.
- Verify: linear history.

### 29. Freshness Threshold Prevents Redundant Fetches

**Goal:** If a sync happened recently (within 15s threshold), ensure_fresh skips the fetch.

- Perform a write (which triggers ensure_fresh internally).
- Immediately perform another write.
- Verify: the second write does NOT fetch from remote (it's within the freshness window).

### 30. Non-Project Routes Pass Through

**Goal:** Requests to URLs that don't match the project pattern (e.g., `/api/settings`) are not affected by git sync middleware.

- Make requests to non-project endpoints.
- Verify: no lock acquired, no git operations, request passes through normally.

### 31. Manual Mode Projects Are Unaffected

**Goal:** Projects configured with `sync_mode: "manual"` are not wrapped by the middleware.

- Configure a project in manual mode.
- Make mutating requests.
- Verify: no lock, no commit, no push — requests pass through as normal.

### 32. File Deletions Are Committed and Pushed

**Goal:** When a handler deletes a tracked file, the deletion is committed and pushed — not silently lost.

- Create a file and commit it (setup).
- Make a write operation where the handler deletes that file.
- Verify: the commit contains the file deletion.
- Verify: the file is gone on remote after push.

### 33. .gitignore-Matching Files: Known Gap

**Goal:** Verify and document behavior when a handler writes a file that matches a `.gitignore` pattern.

- Set up a repo with a `.gitignore` that ignores `*.tmp` (or similar).
- Make a write operation where the handler creates a file matching that pattern.
- Verify: the file is NOT committed (git ignores it).
- Verify: the file is NOT stashed on rollback (git stash skips ignored files by default).
- This is a known data-loss gap in the design. The test documents the behavior so it's explicitly understood.

### 34. Rollback After Failed Rebase: Changes in Reflog Not Stash

**Goal:** When push fails on the retry path (after a successful rebase), verify the actual recovery mechanism — changes end up in reflog, not stash.

- Make a write operation that commits successfully.
- Simulate: first push fails, fetch+rebase succeeds, second push also fails.
- Verify: rollback resets to pre-request HEAD.
- Verify: the rebased commit is recoverable via reflog (not stash, since the working tree was clean post-rebase).
- Verify: repo is clean after rollback.

### 35. Crash Recovery: All Three Conditions Simultaneously

**Goal:** Recovery handles dirty files + in-progress rebase + unpushed commits all at once.

- Set up: create an unpushed commit, start a rebase that conflicts (leaving in-progress rebase state), and leave additional dirty files.
- Make a new write request.
- Verify: dirty files stashed, rebase aborted, unpushed commits reset.
- Verify: new write proceeds normally.
- Verify: all three recovery actions are reflected (stash entry, no in-progress rebase, branch matches remote).

### 36. Crash Recovery: Remote Force-Push (History Rewrite)

**Goal:** Recovery succeeds when the remote has been force-pushed, rewriting history.

- Set up: local has commits that diverge from remote (not just "ahead" — histories have genuinely forked due to a force-push on remote).
- Make a new write request.
- Verify: recovery detects the divergence and resets local to match the new remote HEAD.
- Verify: new write proceeds normally.

### 37. Crash Recovery: Recovery Itself Fails Partway

**Goal:** If one recovery step fails (e.g., stash fails), the system still reaches a usable state on the next attempt.

- Set up: dirty repo state where the first `ensure_clean` call fails partway (e.g., mock stash to fail on first call, succeed on second).
- First write request fails with error.
- Second write request retries recovery.
- Verify: second recovery succeeds and proceeds normally.

### 38. Conflict: Delete on Remote, Modify Locally

**Goal:** When remote deletes a file and local modifies it, the conflict is handled cleanly.

- Set up: a file exists in both local and remote.
- Remote: delete the file and push.
- Local: modify the same file in a write request.
- Verify: conflict is detected, rebase aborted, rollback occurs.
- Verify: repo is clean (no conflict markers, no manual resolution needed).

### 39. Conflict: Add/Add — Same Path, Different Content

**Goal:** When both sides create a new file at the same path with different content, the conflict is handled cleanly.

- Remote: create a new file at a path and push.
- Local: create a file at the same path with different content in a write request.
- Verify: push fails, rebase detects conflict, aborts, rollback occurs.
- Verify: repo is clean, error returned to client.

### 40. Conflict: Rebase Produces Empty Commit

**Goal:** If after rebase our changes are already present on remote (identical content), the system handles the empty commit gracefully.

- Remote: push a commit with the exact same changes our local write will make.
- Make a write request that produces identical changes.
- Verify: push fails, rebase produces empty commit (our changes are redundant).
- Verify: system handles this gracefully — no error, no data loss, clean state.

### 41. Conflict: Second Push Fails During Retry (ABA)

**Goal:** The remote changes again between our rebase and retry push, causing the second push to also fail.

- Make a write request that commits.
- Simulate: first push fails (remote diverged). Fetch + rebase succeeds. But remote changes *again* before the retry push.
- Verify: second push fails, system rolls back cleanly.
- Verify: error response (conflict/retry).
- Verify: repo is clean, no partial state.

### 42. File Creates and Deletes in Same Request

**Goal:** A request that both creates new files and deletes existing files produces a single atomic commit containing both operations.

- Set up: repo has existing tracked files.
- Make a write request that creates new files AND deletes existing files.
- Verify: exactly one commit containing both the additions and deletions.
- Verify: pushed to remote.

### 43. Handler Writes Then Deletes Same File (Net-Zero)

**Goal:** If a handler creates a file then removes it within the same request, no commit is produced.

- Make a write operation where the handler creates a temp file, then deletes it before returning.
- Verify: `has_dirty_files` returns false.
- Verify: no commit created.
- This is distinct from Scenario 3 (no filesystem activity at all) — here the filesystem was mutated and reverted.

### 44. `@no_write_lock` Partial Failure Across Iterations

**Goal:** Document and verify that batch operations using `@no_write_lock` are NOT atomic across iterations — earlier commits remain pushed even if a later iteration fails.

- Define a `@no_write_lock` endpoint that does 3 iterations of `write_lock()` + `commit_and_push()`.
- Simulate: iterations 1 and 2 succeed, iteration 3 fails.
- Verify: commits from iterations 1 and 2 are on remote (not rolled back).
- Verify: iteration 3's changes are rolled back.
- This is intentional by design — the test documents the contract.

### 45. Non-Reentrant Lock: Deadlock Detection

**Goal:** If code under the write lock tries to acquire it again, the system times out rather than deadlocking silently.

- Acquire the write lock.
- From within the locked scope, attempt to acquire it again (simulating a handler that triggers a code path calling `write_lock()`).
- Verify: the inner acquisition times out with `WriteLockTimeoutError`, not a silent deadlock.
- Verify: the outer lock scope is still usable after the inner timeout.

## Out of Scope

- **Auth/credentials testing:** Token management, PAT entry, OAuth flows.
- **Setup wizard UI:** Clone creation, branch selection, project scanning.
- **Timer-based polling:** The background sync poll loop timing. We test the sync functions, not the scheduler.
- **UI testing:** No frontend tests.
- **Performance testing:** No benchmarks or load tests.
- **Multi-remote or branch switching:** Single remote, single branch only.
