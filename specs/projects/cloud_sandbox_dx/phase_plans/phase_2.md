---
status: complete
---

# Phase 2: `setup_env.sh` Rewrite

## Overview

Turn `.config/utils/setup_env.sh` into the single, non-interactive entry point for
building or repairing a Kiln environment (F1–F5).

The script has two jobs. Locally it is what a contributor runs. It is also the
**contents** of the Claude Code cloud environment's setup script — pasted verbatim
into the environment dialog, with only a delimited `CONFIGURATION` block at the top
edited. A wrapper that called the repo copy cannot work: the setup script is
snapshotted and shared across every repo using the environment, so it cannot assume
a particular checkout is on disk (research §12).

That second job drives two design constraints. `set -uo pipefail`, deliberately
**not** `set -e`, because `--best-effort` has to own the exit code — so failures are
recorded rather than aborting the shell. And `--best-effort` itself exists because a
cloud setup script that exits non-zero stops the session from starting, which would
turn one flaky `npm` fetch into a sandbox that will not boot.

The pre-existing worktrunk/Zellij block is preserved verbatim, moved behind
`--human`. It keeps its `read -rp`; that is the one place interactivity is correct.

## Steps

1. **`CONFIGURATION` block.** A contiguous run of four plain assignments at the very
   top of the file — `HUMAN_MODE`, `UPGRADE_TOOLS`, `AGENT`, `BEST_EFFORT` — with a
   comment naming the cloud values (`UPGRADE_TOOLS=true`, `BEST_EFFORT=true`). It is
   the only thing a human edits; steps 1a and 1b are what make that true.

1a. **Bash re-exec.** `set -o pipefail` is not POSIX, so `sh setup_env.sh` would die
   on that line before `--best-effort` was parsed — a session that never starts. If
   `BASH_VERSION` is unset, `exec bash "$0" "$@"`; if `$0` is not readable (a body
   piped to `sh`), print how to re-run it and exit 1.

1b. **Project root discovery**, replacing the `${BASH_SOURCE[0]}`-derived
   `SCRIPT_DIR`/`PROJECT_ROOT`. That derivation is wrong wherever the file is not
   inside the checkout — i.e. every cloud run — and under `set -u` an unset
   `BASH_SOURCE` (script fed on stdin) kills the subshell while the parent
   continues with `PROJECT_ROOT=/`, so as root the `.python-version` write lands at
   `/.python-version`.

   `is_kiln_root` validates a candidate by `pyproject.toml` + `libs/core/kiln_ai/`.
   `find_kiln_root` tries `../..` from `${BASH_SOURCE[0]:-$0}`, then
   `git rev-parse --show-toplevel`, then walks up from `$PWD`, returning the first
   that validates. No match leaves `PROJECT_ROOT` empty, which is a normal state,
   not an error.

2. **Argument parsing**, overriding the block:

   ```
   --human            HUMAN_MODE=true
   --upgrade-tools    UPGRADE_TOOLS=true
   --best-effort      BEST_EFFORT=true
   --agent VALUE      AGENT=VALUE    (also --agent=VALUE)
   -h|--help          usage; exit 0
   *                  error + usage to stderr; exit 2
   ```

   Then validate `AGENT` against `all|claude|cursor|none`; anything else prints the
   error **and usage** to stderr and exits 2.

3. **Failure accounting.** `fail <message>` prints to stderr and sets `FAILED=1`.
   `finish [closing-line]` exits 1 when `FAILED` is set — unless `BEST_EFFORT=true`,
   in which case it says so on stderr and exits 0 — and otherwise prints its
   argument, defaulting to "Environment setup complete."

   Every completion path routes through `finish`. Exactly three exits bypass it,
   all before any work starts: the argument-parsing errors (exit 2, since F1 makes
   that code unconditional and `--best-effort` may not be parsed yet), `--help`
   (exit 0), and the bash guard when `$0` is unreadable (exit 1, before `fail` and
   `finish` are even defined).

4. **uv version gate.** `UV_MIN=0.10.0`, compared with `sort -V`:

   ```bash
   uv_too_old() {
     local current="$1"
     [ -z "$current" ] && return 0
     [ "$(printf '%s\n%s\n' "$UV_MIN" "$current" | sort -V | head -1)" != "$UV_MIN" ]
   }
   ```

   The comparison asks whether `UV_MIN` sorts first; equal versions sort to
   `UV_MIN`, so an exactly-minimum uv is not too old. Branch per F2:
   Missing uv is handled first and separately: every branch below runs uv, so
   warning that `uv (not installed)` is too old and then offering an upgrade command
   that cannot run only confuses the reader.

   `--upgrade-tools` upgrades silently; an interactive TTY prompts with
   `read -t 10` defaulting to **yes** on timeout; with no TTY, warn to stderr with
   the exact command and continue. The upgrade is `uv tool install --force uv` —
   unpinned, `--force` mandatory or uv refuses with `Executables already exist`.
   Not `uv self update`, which resolves releases through the GitHub API whose rate
   limit is per egress IP and is routinely exhausted on shared sandbox IPs.

   After a successful install, `hash -r` and re-read the version. Bash hashed the
   old `uv` during the version check, and the replacement usually lands at a
   different path (`~/.local/bin/uv`), so without this the rest of the run keeps
   calling the binary that was just replaced. A re-read still below `UV_MIN` means
   the new binary is shadowed on `PATH` — `fail`, not success.

5. **Python 3.13.** `uv python install 3.13` runs unconditionally; it is not
   repo-specific and a pre-installed interpreter is what an environment snapshot
   wants. Failure is fatal — `fail` then `finish`.

5a. **The no-checkout exit.** With `PROJECT_ROOT` empty, print one notice saying
   dependency install and agent configuration were skipped and pointing at
   `setup_startup.sh`, then `finish "Environment tools ready. Repo-specific setup
   was skipped."` The notice branches on `FAILED`: this is the single line a cloud
   operator reads in the setup log, so it must not say "uv and Python 3.13 are
   ready" directly under an error from the uv step. — "complete" is the wrong word for a run that did none of the
   repo work, and a human who invoked this from the wrong directory needs to see
   the difference. Everything below needs a checkout, starting with the
   `.python-version` write. `PYTHON_PIN` holds the version, rather than `3.13`
   appearing inline in several places, and `PYTHON_MIN_MINOR` the floor.

5c. **The pin write uses the same floor guard as `setup_startup.sh`.** It was
   unconditional, which reset an above-floor pin — including `3.13.1`, the form
   pyenv writes — and this is the script `CONTRIBUTING.md` sends contributors to for
   ordinary setup, not just repair. Rewrite only a missing, malformed, or below-floor
   pin, exactly as the sibling script does.

5b. **Sync failure attribution.** Re-read the uv version after the gate into
   `UV_BELOW_MIN`. When `uv sync` fails and uv is below the floor — a declined or
   failed upgrade — the cause is `required-version`, not the lockfile, so pointing
   at `uv lock` sends the reader the wrong way.

6. **Parallel dependency install**, in the foreground:

   ```bash
   (cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) & py_pid=$!
   (cd "$PROJECT_ROOT/app/web_ui" && npm ci --no-fund --no-audit) & npm_pid=$!
   py_status=0;  wait "$py_pid"  || py_status=$?
   npm_status=0; wait "$npm_pid" || npm_status=$?
   ```

   Both are waited on before either status is evaluated, so one failing does not
   orphan the other and both failures get reported. `--frozen` and `npm ci` are the
   same defense as `required-version`: neither can rewrite a lockfile. Not
   backgrounded past this point — `npm ci` empties `node_modules` before refilling
   it, and an agent working during that window hits phantom import errors.
   `--no-fund --no-audit` matches `setup_startup.sh` and keeps the funding block and
   the audit's vulnerability tally out of a cloud setup log, where they read like
   failures.

7. **Agent configuration.** `run_agent_setup <claude|cursor>` runs
   `.agents/$1/setup.sh` when it exists and warns-and-continues when it does not.
   `all` (the default) runs both: everything they write is gitignored, they emit
   byte-identical `.mcp.json` and `.worktreeinclude`, and the copy is small and
   offline, so running both is free and avoids privileging one editor. `none` keeps
   the script usable in CI.

8. **`--human` extras.** `if [ "$HUMAN_MODE" != true ]; then finish; fi`, then the
   pre-existing worktrunk/Zellij/`wk` block — **not** unchanged. It was written
   under `set -e`, where the first failing `brew install` aborted the script; with
   no `set -e` it would run on and report success. Each `brew install`, the
   `wt config shell install`, the `uv tool install`, and the config symlink route
   failures through a local `workspace_fail`, which calls `fail` and also sets a
   section-local flag. "Workspaces ready!" is gated on that flag, not the global
   `FAILED` — an earlier unrelated failure such as a flaky `npm ci` must not
   suppress a workspace summary that is true.

9. Update `.config/wt/README.md`, whose setup line still promised the workspace
   offer from a bare invocation; point it at `--human`.

## Tests

Shell and config; no unit tests. Verified by exercising every row of the
architecture's error-handling table, with stub `uv`/`npm` on `PATH` where a real
failure or an old uv had to be simulated, and a pty harness for the prompt:

- `--help` exits 0 with usage on stdout.
- `--bogus` exits 2 with the error and usage on stderr.
- `--agent bogus`, `--agent=bogus`, and a valueless trailing `--agent` all exit 2
  with the error and usage on stderr.
- Version comparison table: `<none>`, 0.8.17, 0.9.0, 0.9.9 too old; 0.10.0, 0.10.1,
  0.12.5, 1.0.0 accepted.
- Too-old uv, no TTY, no flag: warns with the repair command and continues; the
  install steps still run.
- Too-old uv, `--upgrade-tools`: runs `uv tool install --force uv` with no prompt.
- Too-old uv under a pty, answered `n`: skips the upgrade and continues.
- Too-old uv under a pty, unanswered: prompt times out at 10.0 s and upgrades.
- `npm ci` fails: names npm, exits 1. Same case with `--best-effort`: reports the
  error on stderr, says it is exiting 0 anyway, exits 0.
- Both installs fail: **both** are named, exit 1.
- `uv python install 3.13` fails: exits 1 without attempting the installs; with
  `--best-effort`, same message and exit 0.
- Missing `.agents/cursor/setup.sh`: warns, continues, exits 0.
- Root discovery: run from the checkout, from a subdirectory of it, and from an
  unrelated temp directory with the file copied out of the repo — the first two
  find the real root, the third finds none.
- No-checkout run (copy in a temp dir, stubbed uv/npm): prints the single skip
  notice, exits 0, and writes **no** `.python-version` anywhere outside the repo.
- `bash < setup_env.sh` from `/`: no unbound-variable crash, no `/.python-version`
  created.
- `sh setup_env.sh` re-execs under bash and behaves identically to `bash
  setup_env.sh`.
- Stub uv whose upgrade "succeeds" but leaves the version below the floor: the
  script fails rather than reporting a successful upgrade.
- No uv on `PATH`: one "uv is not installed" error naming the installer, with no
  version warning and no upgrade prompt.
- `--human` with a stub `brew` that exits 1: the failure is reported, "Workspaces
  ready!" is suppressed, and the script exits 1.
- `--human` succeeding after an earlier `npm ci` failure: "Workspaces ready!" still
  prints, and the run still exits 1 for the npm failure.
- No-checkout run closes with "Environment tools ready. Repo-specific setup was
  skipped.", not "complete" — and after a failed uv upgrade it points at the errors
  instead of claiming the tools are ready.
- `.python-version` holding `3.14` or `3.13.1` survives a full `setup_env.sh` run.
- `--agent none` from a clean state creates no `CLAUDE.md`, `.claude/`, `.cursor/`,
  `.mcp.json`, or `.worktreeinclude`.
- Default (`all`) from that same clean state creates all of them, with
  `.claude/skills/` and `.cursor/skills/` each holding all five repo skills and
  `.mcp.json` byte-identical to `.agents/mcp.json`.
- `git status --porcelain` empty after every variation above.
