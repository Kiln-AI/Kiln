---
status: complete
---

# Functional Spec: Desktop Lint Config Scope

## Summary

Three things, in this order:

1. Fix the 147 lint findings currently hidden under `app/desktop/`.
2. Move the generated-client exclude up to the root `pyproject.toml`.
3. Delete `[tool.ruff]` from `app/desktop/pyproject.toml`, leaving one ruff config for the repo.

The end state is that `uv run ruff check` from the repo root — which is exactly what CI runs —
covers `app/desktop` under the same rules as every other Python tree, and passes.

## Why the order matters

The config change is the smallest part of the work but it must land **last**.

The moment `[tool.ruff]` is removed from `app/desktop/pyproject.toml`, all 147 findings become
visible to `uv run ruff check`, and CI goes red. There are only two ways to avoid a red main:

- **Fix first, flip last.** The fixes are invisible to CI while they land (they are cleanups
  that pass either way), and the flip is the commit that turns enforcement on. CI is green at
  every commit.
- **Flip first with per-rule ignores, remove them one at a time.** This re-creates exactly the
  silent-exemption state the project exists to remove, and every intermediate commit carries a
  suppression that someone has to remember to delete.

This spec takes the first approach. No commit in this project ever contains a rule suppression
added to make the build pass.

## The audit command

Because the findings are invisible to plain `uv run ruff check` until the final phase, all work
before that phase is verified with an explicit invocation that forces the root config while
preserving the generated-client exclude:

```bash
uv run ruff check \
  --config pyproject.toml \
  --exclude app/desktop/studio_server/api_client/kiln_ai_server_client \
  app/desktop
```

The `--exclude` flag is required. Without it ruff also lints the generated OpenAPI client,
which adds 471 `TID252` and 40 `TID251` findings and takes the total from 147 to 696. Those
are not real findings — they are generated code — and must never be fixed by hand.

After the final phase this command becomes redundant: plain `uv run ruff check` covers the
same ground.

## Scope of findings

All 147 findings, grouped by the kind of work each demands:

### Group A — one repetitive shape (74 findings, 17 files)

`RUF059` unused-unpacked-variable. Every instance is in a test file, and 71 of the 74 are under
`app/desktop/git_sync/`. The shape is always a tuple unpack where one slot is never read:

```python
success, msg, mode = check_remote_access(...)   # msg never used
```

**Default fix:** prefix the unused name with an underscore (`_msg`). This is behaviour-preserving.

**Required judgment:** an unread return value in a test is sometimes a *missing assertion*, not
dead weight — a test that calls a function returning `(success, msg, mode)` and never checks
`msg` may have meant to. The pass over this group must read each site and flag any that look
like a missing assertion rather than blindly underscore-prefixing all 74. Where a missing
assertion is found, note it; adding the assertion is allowed where it is obviously correct, but
adding speculative assertions is not.

### Group B — mechanical, wide (51 findings, 50 files)

`I001` unsorted-imports. Fully auto-fixable with `ruff check --fix`. Zero judgment; touches 50
files with import-block reordering only. Kept in its own phase so the reviewer can skim a large
diff knowing every hunk is machine-generated.

### Group C — needs reading (22 findings, ~9 files)

| Count | Rule | Location | Nature |
|---|---|---|---|
| 9 | `FAST002` | `git_sync/git_sync_api.py` | `Depends()` params need `Annotated[...]` form |
| 5 | `RUF010` | `studio_server/prompt_optimization_job_api.py` | `f"{str(x)}"` → `f"{x!s}"`; auto-fixable |
| 3 | `TID252` | `studio_server/jobs/workers/noop.py` | one relative import (`from ..models import`) with three names |
| 2 | `RUF012` | `git_sync/registry.py` | mutable class attrs on a deliberate singleton |
| 1 | `RUF005` | `studio_server/chat/stream_session.py` | list concat → unpacking |
| 1 | `RUF015` | `studio_server/test_prompt_optimization_job_api.py` | `[...][0]` → `next(...)` |
| 1 | `RUF022` | `studio_server/chat/__init__.py` | `__all__` not sorted; auto-fixable |

Small enough to review line by line, and several carry real decisions.

## Behavioural contract

**No behaviour changes.** This is lint conformance only. Every fix in this project must be
provably behaviour-preserving, or be a deliberate, called-out bug fix reviewed on its own merits.

Concretely:

- `ruff check --fix` (safe fixes) may be applied in bulk. It covers 57 findings.
- `ruff check --unsafe-fixes` **must not** be applied in bulk. It covers 88 further findings,
  and "unsafe" means ruff itself cannot guarantee the fix preserves behaviour. Those findings
  are fixed by hand, or by applying an unsafe fix to a single site and reading the result.
- The desktop test suite must pass after each phase, not merely at the end.

## Decisions

### The `RUF012` findings are not a bug

Both are in `app/desktop/git_sync/registry.py`:

```python
class GitSyncRegistry:
    """Singleton registry of GitSyncManager instances, keyed by repo path."""

    # Class-level mutable state: intentional singleton pattern.
    # All instances share one registry; access is guarded by _lock.
    _managers: dict[Path, GitSyncManager] = {}
    _background_syncs: dict[Path, BackgroundSync] = {}
```

This is shared class-level state on purpose, it is documented as such, and access is lock-guarded.
`ClassVar` is the *correct* annotation here — it states the intent the comment already describes —
not a silencer. Annotate both and leave the behaviour alone.

The overview flagged `RUF012` as deserving real scrutiny rather than a mechanical fix. It got
that scrutiny; the answer is that these two are fine. If more appear before the work lands, each
gets the same read.

### No rule is disabled for this tree

Every one of the 147 findings is fixable without argument. Nothing here justifies an exemption,
so the root config gains no `per-file-ignores`, no `noqa` comments, and no rule removals. The
whole point is that the current exemption was an accident; replacing it with a deliberate one
would be a worse outcome than leaving it alone.

If some future finding genuinely warrants an exemption, it is added to the **root** config with
a comment explaining why — never by re-introducing a config section under `app/desktop`.

### `F401` stays in `extend-select`

The overview correctly notes that `F401` is redundant — it is part of ruff's default `F` ruleset,
so listing it changes nothing. It is kept anyway: it is self-documenting alongside the existing
comments, and removing it is churn with zero effect. Not worth a line of diff.

### The generated-client exclude is load-bearing

It must survive the move, re-pathed from `app/desktop`-relative to root-relative:

```toml
# app/desktop/pyproject.toml (removed)
exclude = ["studio_server/api_client/kiln_ai_server_client"]

# pyproject.toml (root)
exclude = [".worktrees", "app/desktop/studio_server/api_client/kiln_ai_server_client"]
```

The existing `.worktrees` entry must be preserved. The final phase verifies empirically that
the generated client is still skipped — a 696-finding result means the path did not resolve.

### CI needs no changes

`checks.sh:143` and `.github/workflows/format_and_lint.yml:43` both run bare `uv run ruff check`
from the repo root. Ruff's own config discovery is what was routing around `app/desktop`, so
removing the desktop config section makes CI enforce the rules automatically. No workflow edit,
no new CI step, no path list to maintain.

This is worth stating explicitly because it is the reason the fix is three lines rather than a
CI project.

## Edge cases

- **`ruff format` scope changes too.** The desktop `[tool.ruff]` section was the format config
  root as well as the lint config root. Both root and desktop configs set only `exclude` and no
  `[tool.ruff.format]` section, so formatting rules are identical either side of the change —
  but the *exclude* governs whether the generated client gets formatted. The final phase must
  confirm `uv run ruff format --check .` still passes and that the generated client is untouched.

- **Drift during the project.** Between the first fix phase and the config flip, new desktop code
  can introduce new violations that CI still cannot see. The final phase re-runs the full check
  rather than trusting the earlier phases, and any new findings are fixed there. Landing the
  phases promptly keeps this small.

- **The generated client must never be hand-edited.** If a finding's path is under
  `studio_server/api_client/kiln_ai_server_client`, the audit command was run wrong. Re-run it
  with `--exclude`; do not fix the finding.

- **`TID251` (banned `typing.cast`) has no real hits.** All 40 apparent hits are in the generated
  client. Desktop's own code has none, so the banned-api rule costs nothing to turn on.

## Out of scope

- Any behavioural change to the desktop app.
- The web UI's eslint/prettier configuration.
- Whether `ty` or pytest have the same config-root problem. Plausible, unchecked, and a separate
  project — this one does not touch either. Worth filing as a follow-up.
- Fixing anything inside the generated OpenAPI client.
