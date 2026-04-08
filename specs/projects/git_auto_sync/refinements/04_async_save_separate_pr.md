# Refinement: Async Save Migration is a Separate PR

**Resolves:** Q2 (async save — separate PR?)

## Decision

The `save_to_file()` → `await asave_to_file()` migration is the last phase of the project and ships as a separate PR (branch before starting it).

## What changes from architecture.md

- The ~54 API handler call sites and ~30 `libs/core/` adapter calls migration is **not** part of the main git auto sync PR
- The main PR works with the existing sync `save_to_file()` path, which is already functional with git sync (blocks event loop briefly during lock contention, acceptable)
- `asave_to_file()` / `adelete()` methods can be added in the same project but as a final phase on a separate branch/PR

## Why

- Keeps the main PR focused on git sync functionality
- The sync path works correctly today — async is an optimization
- Mechanical migration of ~84 call sites is high-churn, low-risk — better reviewed separately
