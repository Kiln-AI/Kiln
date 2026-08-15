---
status: complete
---

# Phase 2b: `setup_startup.sh`, the Per-Session Startup Check

## Overview

Phase 2 builds an environment, but research §12 showed that a cloud environment's
setup script runs **once per environment** and is then snapshotted and skipped — so
nothing repo-aware runs per session, and a session can land on a stale or wrong VM.
This phase adds the missing piece: a cheap, idempotent script agents run before
their first build or test, on a new branch and at the start of every sandbox
session (F8).

It is not a second setup script. It verifies the hard dependencies the environment
was *supposed* to provide and fails fast with the repair command when they are
missing, then tops up dependencies for the branch actually checked out.

Ordering is load-bearing: the uv check must come **before** the sync. A too-old uv
is precisely the thing that rewrites `uv.lock` during a sync, so a check placed
after would fire only once the damage was done.

## Steps

1. New file `.config/utils/setup_startup.sh`. Same bash re-exec guard as
   `setup_env.sh`, then `set -uo pipefail`, with `UV_MIN=0.10.0`, `PYTHON_PIN=3.13`
   and `PYTHON_MIN_MINOR=13`. It takes no options, but it must still parse
   arguments: silently swallowing `--help` into a full sync is worse than rejecting
   it, so `--help` prints usage and exit 0, and anything else is exit 2. A header comment states what it is for and points at
   `setup_env.sh` for the "build an environment" job.

1a. **Project root discovery**, the same `is_kiln_root` / `find_kiln_root` pair as
   `setup_env.sh`. The `${BASH_SOURCE[0]}` derivation is the identical bug here and
   fails more quietly: `cd ""` succeeds as a no-op, so a body fed on stdin yields
   `PROJECT_ROOT=$PWD/../..` and the script writes `.python-version` and syncs two
   directories above the working directory. Unlike `setup_env.sh`, a miss is fatal
   — this script has nothing to do without a checkout.

2. `bad_environment <reason> <repair>` — the single failure path for "this VM is
   wrong". It prints the reason, the repair line, and a note that in a cloud sandbox
   this usually means the environment's VM setup script did not run or ran against a
   different image. Then `exit 1`.

   The repair is an argument, not a constant. Of the nine reasons, five are fixed
   by `setup_env.sh --upgrade-tools` — an unreadable uv version, a too-old uv, and
   the three `.venv` verdicts. The other four are not: it never installs npm and it
   needs a working uv in order to upgrade uv, so those two point at the upstream
   installers; a failed `.python-version` write points at the checkout's
   permissions; and "no Kiln checkout found" points at changing directory. A repair
   line that cannot work is worse than none.

3. **Hard dependency gate**, before anything else touches the lockfile:
   `command -v uv`; `uv --version` non-empty and compared against `UV_MIN` with the
   same `sort -V` expression as `setup_env.sh`; `command -v npm`. The expression is
   duplicated rather than shared, because `setup_env.sh` gets pasted whole into a
   web form and cannot source anything — both copies carry a keep-in-sync comment.
   The empty-version guard matters here: without it an empty `uv --version` reports
   `uv  is older than 0.10.0`.

3a. **Agent configuration**, before the pin and the sync. `.agents/claude/setup.sh`
   and `.agents/cursor/setup.sh`, each skipped silently when absent and warned about
   (with captured output) when it fails.

   This is the fix for the round-2 Critical: `setup_env.sh` normally runs with no
   checkout in reach, so this is the only thing that ever writes `CLAUDE.md`,
   `.claude/skills/` and `.mcp.json` into a cloud session. It goes first because it
   is offline, sub-second, and writes only gitignored files — it must not sit behind
   a sync that can fail. A failure warns rather than aborts: a stale `CLAUDE.md`
   beats no run at all.

3b. **Pin Python before the sync.** Write `PYTHON_PIN` (3.13) to `.python-version`
   when the existing pin is missing, malformed, or below the floor. This is what
   gives F3 a path in a fresh
   sandbox: `setup_env.sh` is snapshotted and shared across repos, so in the cloud
   it usually runs with no checkout in reach and never writes the pin here.
   Without it the sync below builds `.venv` on the system Python — no `tkinter` —
   and the only recovery is a round trip through step 5's failure message. The
   content check keeps the warm path a no-op. `PYTHON_PIN` is separate from
   `PYTHON_MIN_MINOR` so the exact pin is not conflated with the floor.

   `PYTHON_MIN_MINOR` is a minimum, so a contributor deliberately on 3.14 must keep
   it — otherwise every run would silently reset their pin and the next sync would
   rebuild their venv. Parse major and minor with `IFS=.` and ignore any patch
   component: `3.13.1` is what pyenv writes, and a comparison that cannot match it
   would clobber the pins most likely to be deliberate.

4. **Sync this branch** — the same wait-both parallel pattern as `setup_env.sh`
   §1.4, with `uv sync --frozen --all-packages` and
   `npm install --no-fund --no-audit`. `npm install`, not `npm ci`: the working
   directory is on the snapshotted filesystem (a container restart was measured to
   preserve `node_modules`, `.venv`, and a 1.4 GB uv cache), and `npm ci` would empty
   `node_modules` before refilling it, discarding exactly the cached state that makes
   the top-up cheap. Each failure gets its own message; the `uv sync` one mentions
   `uv lock`, since editing a `pyproject.toml` is the usual cause under `--frozen`.

4a. **Report a rewritten lockfile.** `npm install` regenerates
   `package-lock.json` when it disagrees with `package.json` — the one place either
   script can modify a tracked file, and exactly the scenario this step advertises
   handling. Keeping `npm install` is the deliberate choice (F4); losing the
   guarantee quietly is not. `cksum` the file before and after the install and, on a
   change, warn naming the file and the `git checkout --` command to revert it. Not
   an error: the change may be what the branch intended.

   The check runs *before* the two failure guards. npm rewriting the lock and then
   failing is exactly the case the report exists for, and exiting first would leave
   a modified tracked file with nothing said about it.

5. **Post-sync verification** of the two facts that are properties of `.venv`, and
   so can only be checked once it exists — a single `uv run --frozen python -c`
   printing major version, minor version, and whether `tkinter` resolves.
   `importlib.util.find_spec` rather than a real import, so it needs no display.
   Empty output, a Python below 3.13, or a missing `tkinter` each call
   `bad_environment`. The probe's stderr goes to a temp file and is printed on
   failure rather than discarded — "could not run Python from .venv" on its own
   gives the reader nothing to act on.

   Parse defensively: take the *last* line of the probe output and require both
   version fields to match `^[0-9]+$`. Anything uv prints on stdout ahead of the
   Python output would otherwise reach `[ "$py_major" -lt 3 ]`, producing a raw
   bash `integer expression expected` and then a misleading "no tkinter" verdict.

6. On success, print
   `Ready. Python <major>.<minor>, uv <version>, agent config written.` — success
   criterion 0 requires it to report both versions, and the agent-config clause
   makes step 3a's contribution visible in the one line most readers will see. The branch name in the sync
   banner is captured first and falls back to "this checkout", since
   `git branch --show-current` prints nothing and exits 0 on a detached HEAD.

## Tests

Shell; no unit tests. Verified by running it against deliberately broken `PATH`s
built from stubs and symlinks, and against the real environment:

- No `uv` on `PATH`: prints `uv is not installed`, the repair command, exits 1.
- Stub `uv` reporting 0.8.17: prints `uv 0.8.17 is older than 0.10.0, and would
  corrupt uv.lock`, exits 1 — and does so **without** having run a sync, which is
  the whole point of the ordering.
- Real `uv`, no `npm` on `PATH`: prints `npm is not installed`, exits 1.
- Stub `uv` whose `--version` prints nothing: named as unverifiable rather than
  reported as `uv  is older than 0.10.0`.
- Deleted `.python-version`: recreated with `3.13` before the sync; a second run
  leaves it untouched.
- Detached HEAD: the banner reads `Syncing dependencies for this checkout...`.
- Agent config: with `CLAUDE.md`, `.claude/`, `.cursor/` and `.mcp.json` removed, a
  single run recreates all of them; `git status --porcelain` stays empty.
- `bash < setup_startup.sh` from an unrelated directory: fails with "no Kiln
  checkout found" and writes nothing outside the repo.
- `sh setup_startup.sh` re-execs under bash rather than dying on `pipefail`.
- Missing `npm` and missing `uv` each print a repair line that can actually work,
  not `setup_env.sh --upgrade-tools`.
- `.python-version` holding `3.14`: left untouched. Holding `3.11` or garbage:
  rewritten to `3.13`.
- Probe stdout polluted with a leading line: still parses, no bash arithmetic error.
- `.python-version` holding `3.13.1` or `3.14.2`: left untouched (the pyenv form).
- `setup_startup.sh --help` prints usage and exits 0; `--bogus` exits 2 without
  syncing anything.
- Editing `app/web_ui/package.json` so it disagrees with the lock: the run warns,
  names `package-lock.json`, and still exits 0.
- Healthy environment: exits 0 and prints
  `Ready. Python 3.13, uv 0.12.5, agent config written.`
- Warm re-run: 1.5 s wall (the spec's 5.9 s reference was a colder machine), well
  inside "cheap enough that there is no reason to guess whether it is needed".
- `git status --porcelain` empty and `uv.lock` / `package-lock.json` md5s unchanged
  after a run.
