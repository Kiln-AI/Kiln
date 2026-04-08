# Refinement: Reset to Last Clean Commit on Failure

**Resolves:** Crit #7 (push retry unpushed commit tracking), Crit #8 (leftover staged files)

## Decision

On any failure (push failure, rollback, error), reset to the last clean commit. This means:

1. Unstage all staged files (`git reset HEAD` equivalent)
2. Restore working tree to HEAD (`checkout_head` — per refinement 01)
3. Delete any new untracked files created during the context

Commits already pushed via `manager.push()` during nested contexts (e.g. periodic push in eval loops) are done and stay done — we don't roll those back.

## What this simplifies

- No need to track "which commits are pushed vs unpushed"
- No need to track remote HEAD SHA before final push
- Leftover staged files from a failed `git add` + `git commit` sequence are cleaned up automatically by the reset
- Single recovery mechanism for all failure modes

## pygit2

```python
# Unstage everything
repo.reset(repo.head.target, pygit2.enums.ResetMode.MIXED)

# Restore working tree to HEAD (tracked files)
repo.checkout_head(strategy=CheckoutStrategy.FORCE)

# Delete new untracked files
for path in ctx.new_files:
    path.unlink(missing_ok=True)
```
