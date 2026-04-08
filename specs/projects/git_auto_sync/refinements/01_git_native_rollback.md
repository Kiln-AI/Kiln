# Refinement: Git-Native Rollback

**Resolves:** Q3 (rollback strategy), Crit #3 (delete_tree rollback), Crit #10 (pre-deletion enumeration)

## Decision

Use git itself for rollback instead of tracking original file contents in memory.

## What changes from architecture.md

**Remove** `original_contents: dict[Path, bytes | None]` from `WriteContext`.

**Replace with** `new_files: set[Path]` — files that didn't exist before the write (identified via `repo.status_file()` returning `WT_NEW` at write time).

## Rollback flow

On error, instead of restoring saved bytes:

1. **Modified tracked files:** `repo.checkout_head(paths=[...], strategy=CheckoutStrategy.FORCE)` restores to HEAD state.
2. **New files (never committed):** `unlink()` each file in `new_files` set.
3. **Deleted trees (`delete_tree`):** Same `checkout_head(paths=[...])` restores from HEAD. No pre-deletion enumeration needed — git knows the tree contents.

All rollback operations go through `_git_executor` (pygit2 thread safety).

## Why

- No memory bloat — git's object store is the backup, already on disk
- Files could be large; holding bytes in a dict is wasteful
- Idempotent — file modified twice in same context still restores to HEAD
- `delete_tree` rollback solved for free (git knows directory contents)
- Aligns with goal of being "very git-native"

## Key detail

Writes go to the working tree only. Staging (`git add`) and commit happen only on the success path, at context exit. This means HEAD always represents the pre-context state during writes.

## pygit2 API

```python
# Restore tracked files to HEAD
repo.checkout_head(paths=['path/to/file.txt'], strategy=CheckoutStrategy.FORCE)

# Check if file is new (untracked)
from pygit2.enums import FileStatus
status = repo.status_file('path/to/file.txt')
is_new = status & FileStatus.WT_NEW
```
