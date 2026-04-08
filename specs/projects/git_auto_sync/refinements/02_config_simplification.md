# Refinement: Config Simplification

**Resolves:** Q1 (config simplification)

## Decision

Per-project config keeps only `sync_mode` and `remote_name`. All timing parameters dropped from user-facing config.

## What changes from architecture.md

**Settings storage** in `~/.kiln_ai/settings.yaml` becomes:

```yaml
git_sync_projects:
  "project_id_abc":
    sync_mode: "auto"       # "auto" | "manual"
    remote_name: "origin"   # git remote name
```

**Removed from config:**
- `branch` — always uses current branch. No clear use case for specifying another.
- `poll_interval` — internal constant, no UI to set it.
- `idle_pause_after` — internal constant, no UI to set it.
- `sync_freshness_threshold` — internal constant, no UI to set it.

**Timing values** become constants in `GitSyncManager` / `BackgroundSync` (e.g. `_POLL_INTERVAL = 10.0`). Easy to promote to config later if a real need emerges.

## Why

- No UI exists to set these values
- Premature configurability adds complexity
- `branch` supporting "another branch" has no defined behavior
- YAGNI — add config surface when there's a real user need
