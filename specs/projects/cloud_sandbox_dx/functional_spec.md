---
status: complete
---

# Functional Spec: Cloud Sandbox Developer Experience

## Purpose

Make the Kiln repo work correctly and quickly inside Claude Code cloud sandboxes,
without special knowledge or manual repair steps. Today a fresh cloud session
starts with no virtualenv, no `node_modules`, no agent configuration, a `uv` too
old to read the repo's own `pyproject.toml`, and a Python without `tkinter`. The
documented commands actively corrupt the environment.

Everything here is grounded in measurements taken on a live sandbox; see
[research_findings.md](research_findings.md). Decisions are recorded in
[project_overview.md](project_overview.md).

## Audience

Two, with different needs:

- **Cloud agents.** Unattended. Need everything to work with zero prompts and no
  tribal knowledge. Primary audience.
- **Human contributors.** Interactive. Must not have their global tooling
  silently mutated, and must not be forced through cloud-only steps.

The same script serves both, differing only by flags.

## Features

### F1 — `setup_env.sh` becomes the single, non-interactive setup entry point

`.config/utils/setup_env.sh` is reworked. Its default mode is fully
non-interactive and safe to run unattended.

It has two jobs. Locally it is the command a contributor runs to build an
environment. It is also **the cloud environment's setup script**: its contents are
pasted verbatim into the environment dialog, with only a clearly delimited
`CONFIGURATION` block at the top edited (there `UPGRADE_TOOLS=true` and
`BEST_EFFORT=true`). Keeping one file means the cloud path is version-controlled,
reviewable, and testable locally, instead of living only in a web form.

**Command contract:**

| Invocation | Behavior |
|---|---|
| `setup_env.sh` | Deps + all agent configs. No prompts except the uv check (F2). |
| `setup_env.sh --human` | Adds the interactive worktrunk/zellij install offer. |
| `setup_env.sh --upgrade-tools` | Upgrades a too-old uv without asking. |
| `setup_env.sh --agent <all\|claude\|cursor\|none>` | Which agent configs to write. Default `all`. |
| `setup_env.sh --best-effort` | Never exit non-zero. |
| `setup_env.sh --help` | Usage. |

Unknown flags, and an unrecognized `--agent` value, are an error with usage and
exit 2.

`--best-effort` exists because a cloud setup script that exits non-zero stops the
session from starting (research §12). Without it, one flaky `npm` fetch would mean
a sandbox that will not boot. Errors are still reported on stderr; only the exit
code is suppressed.

**What it does, in order:**

1. Check uv version; upgrade or prompt or warn (F2).
2. Ensure Python 3.13 is available and pinned (F3).
3. Install Python and Node dependencies **in parallel** (F4).
4. Write agent configuration (F5).
5. `--human` only: offer the worktrunk/zellij extras.

### F2 — uv version handling

The repo's `pyproject.toml` uses `exclude-newer = "7 days"`, which uv < 0.10.0
cannot parse. Such a uv silently ignores the setting and re-resolves the whole
dependency graph on every `uv run`, rewriting `uv.lock` and installing a broken
fastapi/starlette pair.

Two independent defenses:

- **Loud failure.** `required-version = ">=0.10"` in `[tool.uv]`. Any too-old uv
  now fails with an explicit message instead of silently corrupting the lockfile.
- **Self-service upgrade.** `setup_env.sh` detects a too-old uv and resolves it:

| Context | Behavior |
|---|---|
| `--upgrade-tools` passed | Upgrade immediately, no prompt. |
| Interactive TTY, no flag | Prompt, `read -t 10`, **default yes on timeout**. |
| No TTY, no flag | Warn with the exact command; do not upgrade; continue. |

The upgrade command is `uv tool install --force uv`. Deliberately **not pinned** —
always latest. `--force` is required or uv refuses with `Executables already
exist`. Notably `uv self update` does **not** work in this environment: it
resolves releases via the GitHub API, whose rate limit is per egress IP and is
routinely exhausted on shared sandbox IPs. `pip` is not used.

Timeout-defaults-to-yes is deliberate: without the upgrade the repo does not
work, and the person has chosen not to answer a prompt they were shown.

### F3 — Python 3.13

The sandbox's system Python (3.11) has no `tkinter`, which breaks 5 test modules
and both OpenAPI schema scripts. uv-managed CPython builds bundle Tk, and 3.13 is
what CI and the desktop app already target.

`setup_env.sh` runs `uv python install 3.13` and writes a `.python-version` file
containing `3.13`. The file is **gitignored**, not tracked — it is generated, and
this avoids adding a tracked top-level file.

`.python-version` is preferred over `uv sync --python 3.13` because uv consults
the file on every subsequent sync, so deleting `.venv` and re-syncing still
produces 3.13 rather than silently reverting to system Python.

`setup_startup.sh` (F8) writes the same file, before its sync, when it is missing,
malformed, or names a Python below the floor. A pin at or above the floor is left
alone, patch component and all — `3.13.1` is what pyenv writes, and resetting it
would clobber the pin most likely to be deliberate. Without that, F3 has no path in
a fresh sandbox: the cloud
`setup_env.sh` usually runs with no checkout in reach, so the first sync in the
session would build `.venv` on the system Python and the only recovery would be a
round trip through F8's failure message and a human.

Contributors using pyenv should know the file exists, since pyenv shims read it
too. Noted in `AGENTS.md`.

No repo source changes for `tkinter`. The imports in `desktop_server.py` and
`import_api.py` stay exactly as they are.

### F4 — Dependency installation

- Python: `uv sync --frozen --all-packages`. `--frozen` guarantees the lockfile is
  used as-is and never rewritten.
- Node: `npm ci` in `app/web_ui`, not `npm install`. `npm ci` cannot rewrite
  `package-lock.json` — the same class of bug as the uv problem — and measured
  faster (25.6 s vs 27.3 s) on a from-scratch install. The per-session top-up in
  F8 uses `npm install` instead, because `npm ci` empties `node_modules` before
  refilling it and so throws away exactly the cached state that makes the top-up
  fast.

  **That trade is real and is accepted deliberately.** `npm install` rewrites
  `package-lock.json` whenever it disagrees with `package.json`, so F8 — unlike
  every other step in either script — can leave a tracked file modified. The
  alternative is `npm ci` in F8, which would empty and refill `node_modules` on
  every session and cost the top-up its whole reason to exist. So the guarantee is
  narrowed rather than abandoned: F8 hashes `package-lock.json` around its install
  and prints a warning naming the file when it changed, with the command to revert
  it. The Python half keeps `--frozen`, so it has no equivalent exposure.
- The two run **in parallel with each other, in the foreground**. Measured: ~37 s
  serial → ~26 s parallel, since npm dominates.

Not backgrounded. `npm ci` deletes `node_modules` before repopulating it, so an
agent that began work during setup would hit intermittent phantom import errors —
precisely the failure class this project exists to remove. The ~26 s saved is not
worth reintroducing it.

If either install fails, report which one and exit non-zero. A failure in one must
not be masked by success in the other.

**Human caveat:** because the sync is `--frozen`, a contributor who has edited
dependencies in `pyproject.toml` must run `uv lock` before `setup_env.sh` picks
the change up. This is called out in `--help` and in `AGENTS.md`.

### F5 — Agent configuration

`setup_env.sh --agent` runs the existing per-editor setup scripts, which copy
`AGENTS.md` → `CLAUDE.md`, the canonical `.agents/skills/` into `.claude/skills/`
or `.cursor/skills/`, `.agents/mcp.json` → `.mcp.json`, and `.worktreeinclude`.

Default is `all` — both Claude and Cursor. Everything written is gitignored, the
two scripts emit byte-identical `.mcp.json` and `.worktreeinclude`, and the whole
copy is 176 KB with no network, so running both is free and avoids privileging one
editor. `none` exists so the script stays usable in CI.

If a requested agent's setup script is missing, warn and continue.

Verified working: after running the Claude script mid-session, `CLAUDE.md` and all
five repo skills became available without a session restart.

**`setup_startup.sh` runs the same agent setup, unconditionally, every session**
(F8). This is not redundant — it is the only path that works in the cloud. The
environment's `setup_env.sh` runs once per environment, before and independently of
any checkout, so in the normal cloud case it reaches the agent-config step with no
repo to write into. Without F8 doing it, `CLAUDE.md`, `.claude/skills/` and
`.mcp.json` would simply never exist in a sandbox session, and success criterion 7
would be unmeetable there. The work is offline, sub-second, and writes only
gitignored files, so doing it every session is cheaper than reasoning about whether
it is needed.

**Known limitation — the bootstrap is circular.** The only thing that tells an
agent to run `setup_startup.sh` is `AGENTS.md`, and the repo copies `AGENTS.md` to
`CLAUDE.md` precisely because `CLAUDE.md` is the file Claude Code actually reads. In
a fresh sandbox with no agent config, nothing has told the agent the script exists.
So F5 in the cloud depends on a precondition outside the repo: the operator's task
prompt, or a human, naming `setup_startup.sh` at least once. Once it has run, the
loop is closed for that session and every later one on that filesystem.

Until that exists, the gap is covered by an item in the implementation plan's
environment-side checklist rather than by anything in the repo.

The candidate fix is a `SessionStart` hook, which Claude Code runs before the agent
reads anything, so it does not depend on the agent having been told. It is not
adopted here — but not because it is hard. It needs a tracked
`.claude/settings.json`, and while `.claude/` is gitignored wholesale, that is two
`!` negation lines away and nothing depends on the wholesale ignore. What makes it a
decision rather than a task is that it would make part of `.claude/` source in a
repo where everything under it is currently generated and disposable. Tracked as an
open decision in the implementation plan.

### F6 — Python test startup cost

The root `conftest.py` imports `litellm` at module scope. pytest imports the root
conftest on **every** invocation, so every run pays ~4 s even when no test touches
litellm. This is the tax on the most common agent action: iterating on one test
file.

The import becomes lazy. Measured effect, on the research sandbox:

| | before | after |
|---|---|---|
| single test file (42 tests, 0.14 s of testing) | 7.40 / 7.73 / 6.86 s | **0.96 / 0.91 / 2.03 s** |
| full suite `-n auto` | 63.3 s | **58.9 s** |
| pass / skip counts | 6369 / 10020 | **identical** |

The durable claim is qualitative: **the inner loop stops paying for the litellm
import**, which takes several seconds off every pytest invocation that does not
need it, and the pass/skip counts do not move.

Do not read a specific multiple out of this. The tables are point measurements and
the ratio varies a lot with hardware and cache state — the litellm import is much
more expensive cold than warm, so a cold first import inflates the "before" side.
Three independent measurements of the same single file, each against a same-machine
baseline taken by temporarily restoring the module-scope `import litellm`:

| machine | before | after |
|---|---|---|
| research sandbox | 7.40 / 7.73 / 6.86 s | 0.96 / 0.91 / 2.03 s |
| verification machine | 11.72 / 11.31 / 11.20 s | 1.93 / 1.93 / 1.93 s |

A third measurement, on the review machine, got 3.29 / 3.18 / 3.05 s after, with
the litellm import timed separately at 3.93–4.08 s warm — about 2.3× rather than
the ~6× the first two suggest. That is the honest spread: the first two "before"
figures plausibly include a cold import, and litellm fetches its model-cost map on
first import, so a warm box sees a much smaller multiple.

All three show the same direction and all three report 6369 / 10020. What is
reliable is that the import cost leaves the inner loop; how big that is depends on
the box and the cache.

Behavior that must not change: every test that currently gets a flushed litellm
client cache must still get one, and litellm logging must still be configured
exactly once per session for runs that use litellm.

### F7 — Documentation

`AGENTS.md` gains a short environment-setup section: `setup_startup.sh` before a
first build or test, `setup_env.sh` as the way to set up an environment, what the
flags do, the `uv lock` caveat from F4, the generated `.python-version` and what it
means for pyenv users, and a note that `CLAUDE.md` is generated from `AGENTS.md`
and overwritten on every run — so personal agent notes belong in user-scope
`~/.claude/CLAUDE.md`, not the repo copy.

`CONTRIBUTING.md` gets the same treatment for the other audience. Its setup section
predates this project and still reads "install uv, `uv sync`, `npm install`", which
now walks a contributor on uv 0.9 straight into a bare `required-version` refusal
with nothing pointing at the fix. Scoping the docs to `AGENTS.md` alone would leave
the human half of the stated audience worse off than before the uv floor landed, so
`CONTRIBUTING.md` covers the script, the floor and its repair command, and the
`.python-version` / pyenv interaction.

### F8 — `setup_startup.sh`, the per-session startup check

`setup_env.sh` builds an environment, but it runs once per cloud environment and
is then snapshotted and skipped (research §12). Nothing repo-aware runs per
session, and a session can also land on a stale or wrong VM. `AGENTS.md` therefore
instructs agents to run `.config/utils/setup_startup.sh` before their first build
or test — on a new branch, and at the start of every sandbox session.

It does five things, in this order:

1. **Gate on the tools the environment was supposed to provide** — `uv` present and
   ≥ 0.10, `npm` present. These come first because they are prerequisites for
   everything below, and because a too-old uv is what would corrupt `uv.lock`
   during step 4.
2. **Write the agent configuration** (F5). Placed here because it is offline,
   sub-second, and the thing that makes the repo's own instructions readable — so
   it must not sit behind a sync that might fail. In the cloud this is the only
   step that ever writes `CLAUDE.md`, `.claude/skills/` and `.mcp.json`.
3. **Pin Python** — write `.python-version` if it is missing, malformed, or below
   the floor (F3), before the sync, so the sync builds `.venv` on 3.13 instead of
   the system Python. A pin at or above the floor is a deliberate choice and is
   left alone.
4. **Sync dependencies for the current branch**, `uv sync --frozen --all-packages`
   and `npm install` in parallel, so a branch that changed a lockfile is not run
   against stale packages.
5. **Verify the virtualenv** — Python 3.13 or newer and `tkinter` importable. These
   are properties of `.venv`, so they can only be checked once step 4 has built it.

Every *environment* failure — the nine that mean "this VM is wrong" — prints one
repair line and notes that in a sandbox this usually means the VM setup script did
not run. Exit 1.

The repair line is per-reason, not global. `setup_env.sh --upgrade-tools` is right
for the five reasons it can actually fix — an unreadable uv version, a too-old uv,
and the three `.venv` verdicts — but it cannot install npm and it needs a working
uv in order to upgrade uv, so those two point at the upstream installers instead. A
failed `.python-version` write points at the checkout's permissions, and a missing
checkout points at changing directory.

The two step-4 failures are not in that set and deliberately read differently: a
failed `uv sync` or `npm install` says which one failed and exits 1, without the
sandbox note, because a lockfile the branch changed is a normal development
situation rather than a broken VM. The `uv sync` message names `uv lock`, since an
edited `pyproject.toml` is the usual cause under `--frozen`; the npm one has no
repair to offer beyond its own output.

Unlike `setup_env.sh`, this script requires a checkout, so it discovers its project
root the same way and treats a miss as fatal rather than as a skip.

The uv check must come **before** the sync, not after: a too-old uv is precisely
the thing that would rewrite `uv.lock` during that sync, so checking afterwards
would do the damage the check exists to prevent.

It is cheap and idempotent by design — measured **5.9 s** warm — so re-running it
costs little and there is no reason for an agent to try to guess whether it is
needed.

## Out of Scope

- **Dependency caching / an R2-style artifact cache.** Measured cold vs warm:
  37 s vs 39 s. The caches are already irrelevant because PyPI and the npm
  registry are in the sandbox's `no_proxy` list; the bottleneck is disk linking,
  not network. Building one would save approximately zero.
- **Source changes for `tkinter`** — solved by F3.
- **Ignoring the paid-heavy test files at collection.** The 8 files holding ~9,734
  of the ~10,020 paid tests can be `--ignore`d, but it saves only ~1.7 s and
  carries the one genuinely dangerous failure mode here: silently not running
  tests.
- **`LITELLM_LOCAL_MODEL_COST_MAP` / `.env` changes.** Worth ~0.6 s of a 3.9 s
  import, ~1 % of a suite run, and nothing on the inner loop once F6 lands.
- **Installing `misspell`.** `checks.sh` warns and skips; accepted.
- **`debug_detector` firing on `TODO` in spec markdown**, and **mutation-sweep
  scripts leaving mutated source in the working tree.** Real problems, unrelated
  to sandboxes.
- **Adding `--frozen` to every `uv run` call site** in `checks.sh`, the `Makefile`,
  `hooks_mcp.yaml`, the schema scripts, and the skills. Once uv ≥ 0.10 is
  enforced, plain `uv run` is correct and costs 0.07 s. Fixing the root cause
  removes the need for the workaround rather than institutionalizing it.

## Environment-side changes (outside the repo)

These cannot be fixed by repo code and belong in the Claude Code cloud environment
configuration. They are documented here so they are not lost:

1. **Setup script** — paste the contents of `.config/utils/setup_env.sh` into the
   environment's **Setup script** field, and edit only its `CONFIGURATION` block:

   ```bash
   HUMAN_MODE=false
   UPGRADE_TOOLS=true  # was false
   AGENT=all
   BEST_EFFORT=true    # was false
   ```

   The field must run the script with **bash**. `set -o pipefail` is not POSIX, so
   a runner that starts it with `sh` would kill it on the first line. The script
   re-execs itself under bash when it can, which covers `sh setup_env.sh`, but it
   cannot rescue a body piped to `sh` on stdin.

   An earlier draft of this spec used a small repo-agnostic wrapper that called
   `.config/utils/setup_env.sh` from the checkout. That does not work: the setup
   script is snapshotted and shared across every repo using the environment, so a
   repo-specific path cannot be relied on to exist when it runs (research §12).
   Pasting the contents keeps the script version-controlled and locally testable
   while removing the dependency on the checkout being there.

   **What pasting does not solve, and how the script handles it.** The wrapper at
   least knew where the checkout was. A pasted copy does not — it is not inside
   one, and often there is no checkout on disk at all. So the script discovers its
   project root at runtime (script location, then `git rev-parse --show-toplevel`,
   then walking up from `$PWD`), validating each candidate against
   `pyproject.toml` + `libs/core/kiln_ai/`.

   With a checkout, every step in F1 runs. With no checkout — which is the normal
   case here, since the script runs at environment-build time — "no repo to
   configure" is a **normal outcome, not a failure**: the script still does the
   environment-level work worth snapshotting, the uv gate and
   `uv python install 3.13`, then prints one notice naming what it skipped and
   exits 0. It must not report a run of `error:` lines for work that had no target.

   That is a real reduction in what this script can promise, and it is why F8
   exists in the shape it does. Everything repo-specific — agent configuration
   included — has to be re-done per session by `setup_startup.sh`, which is the
   only component that reliably has a checkout in hand. Read the two together: this
   script prepares the *machine*, `setup_startup.sh` prepares the *checkout*.

   Re-paste when the script changes materially.

2. **MCP trust.** A project `.mcp.json` is **never** auto-trusted. Tested: neither
   `.claude/settings.local.json` nor `~/.claude.json`'s `enabledMcpjsonServers`
   works. The only mechanisms that work are `hasTrustDialogAccepted: true` in
   `~/.claude.json`, or — cleaner — `enableAllProjectMcpServers: true` in
   **user-level** `~/.claude/settings.json`.

3. **`UV_NATIVE_TLS`** is set in the image and is deprecated; modern uv prints a
   warning on every invocation. Replace with `UV_SYSTEM_CERTS`.

Note that environment variables set *inside* a setup script do not reach the
agent's later shells — each Bash call starts fresh from the profile — so items 2
and 3 must be environment configuration, not script lines.

## Dependency on upstream — resolved

`.agents/mcp.json` invoked a bare `uvx hooks-mcp`, which resolved `hooks-mcp 0.2.4`
against `mcp 2.0.0` and failed to start (`'Server' object has no attribute
'list_tools'`). The repo pinned nothing while the fix was in progress upstream,
since a local `mcp<2` pin would have held that fix back.

`hooks-mcp` 0.2.5 has shipped, so the invocation now carries a **floor**:

```json
"args": ["--from", "hooks-mcp>=0.2.5", "hooks-mcp", ".config/hooks_mcp.yaml", "--working-directory", "."]
```

A floor, not a pin: `uvx` reuses cached tool environments, so without a lower bound
it could keep serving the broken 0.2.4 + `mcp` 2.0 pair from cache, and a pin would
freeze the repo on one version of a dependency that is not ours to hold still.

Verified by driving the configured command over stdio: `initialize` returns
`HooksMCP`, and `tools/list` returns all 17 tools from `.config/hooks_mcp.yaml`.

This was never blocking: `CLAUDE.md` and skills work without MCP.

## Success Criteria

On a fresh cloud sandbox, after the environment setup script runs and the agent has
run `setup_startup.sh`:

0. `bash .config/utils/setup_startup.sh` exits 0 and reports the Python and uv
   versions. On a deliberately broken environment it exits 1 and names the repair
   command instead.
1. `uv --version` reports ≥ 0.10.
2. A plain `uv run python -c "print(1)"` completes in well under a second and
   leaves `uv.lock` unmodified.
3. `.venv` is Python 3.13 and `import tkinter` succeeds.
4. `uv run python3 -m pytest --benchmark-quiet -q -n auto .` reports **zero
   collection errors**.
5. `app/web_ui/src/lib/check_schema.sh` runs and reports the schema is up to date.
6. `uv run ./checks.sh --agent-mode` exits 0.
7. `CLAUDE.md`, `.claude/skills/`, and `.mcp.json` all exist — **written by
   `setup_startup.sh`**, not by the environment setup script, which in a sandbox
   normally runs with no checkout in reach. This criterion therefore inherits the
   precondition in the preamble: it holds only once something has caused
   `setup_startup.sh` to run at least once. See F5's known limitation — in a fresh
   sandbox nothing in the repo can deliver that instruction, because the file that
   would carry it is one of the files this step creates.
8. `git status --porcelain` is empty — setup mutates no tracked file, with one
   named exception: `setup_startup.sh` uses `npm install` (F4), which rewrites
   `app/web_ui/package-lock.json` if it disagrees with `package.json`. On a branch
   whose lock and manifest agree — which is every branch that passes CI — nothing
   changes and the criterion holds as stated. When it does not, the script says so
   on stderr and names the file, so the change is reported rather than silent.
9. Running one small test file completes in ~1 s rather than ~7 s.

Measured reference values for 4–6 on this hardware: suite 6369 passed / 10020
skipped / 0 errors in ~59 s; `checks.sh` green in ~2 m 23 s.

**On the preamble's second clause.** "the agent has run `setup_startup.sh`" is a
genuine precondition, not a formality: nothing in a fresh sandbox tells the agent to
run it. Until the `SessionStart` hook in F5 is adopted, closing that gap needs an
operator-side prompt naming the script. Criteria 0–9 are written against the state
after that has happened; before it, 7 fails and 3–6 fail or are slow depending on
what the image happened to provide.
