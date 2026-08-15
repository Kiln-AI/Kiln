---
status: complete
---

# Phase 4: `AGENTS.md` Environment-Setup Section

## Overview

Documents the interface Phases 2 and 2b created, so an agent landing in a fresh
checkout does not need tribal knowledge (F7). It depends on those phases being
settled, since it describes them.

Three things have to be conveyed and nothing more: run `setup_startup.sh` before
your first build or test; `setup_env.sh` with its flags is how you build or repair
an environment; and two consequences that will otherwise bite — `--frozen` means a
dependency edit needs `uv lock` first, and `CLAUDE.md` is generated from `AGENTS.md`
and clobbered on every setup run.

That last point is new fallout from this project: `.agents/claude/setup.sh` has
always overwritten `CLAUDE.md` unconditionally, but before Phase 2 it only ran when
someone invoked it directly. It now runs on every plain `setup_env.sh`, so anyone
keeping personal notes in the repo copy would lose them. The section says to keep
them in user-scope `~/.claude/CLAUDE.md` instead.

Keep it brief and keep the research numbers out of it — the measurements live in the
spec folder.

## Steps

1. Add an `### Environment Setup` section to `AGENTS.md`, between `### Tech Stack`
   and `### Agent Tools`, containing:
   - A lead paragraph on `bash .config/utils/setup_startup.sh`: run it before your
     first build or test run, on a new branch and at the start of every cloud
     sandbox session; it syncs dependencies for the current branch and fails fast
     with instructions when the environment itself cannot build Kiln; warm it is
     close to a no-op, so re-running is cheap.
   - `bash .config/utils/setup_env.sh` as the way to build or repair an environment
     from scratch, with a flag table covering the bare invocation, `--human`,
     `--upgrade-tools`, `--agent all|claude|cursor|none`, and `--best-effort`.
   - Four notes: the uv ≥ 0.10 requirement and why (older uv silently re-resolves
     and rewrites `uv.lock`; `required-version` now makes that fail loudly); the
     `--frozen` / `uv lock` caveat; the generated, gitignored `.python-version` and
     what it means for pyenv users, whose shims read the same file; and the
     generated-`CLAUDE.md` warning.

2. Update `CONTRIBUTING.md`'s setup section, which is the file the *human* half of
   the stated audience reads. It still said "install uv, `uv sync`, `npm install`",
   which now walks a contributor on uv 0.9 into a bare `required-version` refusal
   with nothing naming the fix. Add `setup_env.sh --human` as the quick path, keep
   the manual steps, and state the uv floor with its repair command plus the
   `.python-version` / pyenv interaction. F7 is widened to say so, rather than
   leaving the docs technically in scope and practically wrong.

3. Do not regenerate `CLAUDE.md` by hand — it is gitignored and produced by
   `.agents/claude/setup.sh`, which both setup scripts invoke.

## Tests

Documentation only; no tests. Verified:

- Every flag in the table matches `setup_env.sh --help` and the parser's actual
  accepted set.
- Running `.agents/claude/setup.sh` (via either setup script) regenerates
  `CLAUDE.md` from the edited `AGENTS.md`, and `git status --porcelain` stays empty
  because both it and `.claude/` are gitignored.
- Every command named in `CONTRIBUTING.md`'s setup section runs as written.
- `uv run ./checks.sh --agent-mode` green.
