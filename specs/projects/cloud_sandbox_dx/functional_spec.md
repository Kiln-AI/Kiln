---
status: draft
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

**Command contract:**

| Invocation | Behavior |
|---|---|
| `setup_env.sh` | Deps + all agent configs. No prompts except the uv check (F2). |
| `setup_env.sh --human` | Adds the interactive worktrunk/zellij install offer. |
| `setup_env.sh --upgrade-tools` | Upgrades a too-old uv without asking. |
| `setup_env.sh --agent <all\|claude\|cursor\|none>` | Which agent configs to write. Default `all`. |
| `setup_env.sh --help` | Usage. |

Unknown flags are an error with usage and a non-zero exit.

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

No repo source changes for `tkinter`. The imports in `desktop_server.py` and
`import_api.py` stay exactly as they are.

### F4 — Dependency installation

- Python: `uv sync --frozen --all-packages`. `--frozen` guarantees the lockfile is
  used as-is and never rewritten.
- Node: `npm ci` in `app/web_ui`, not `npm install`. `npm ci` cannot rewrite
  `package-lock.json` — the same class of bug as the uv problem — and measured
  faster (25.6 s vs 27.3 s).
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

### F6 — Python test startup cost

The root `conftest.py` imports `litellm` at module scope. pytest imports the root
conftest on **every** invocation, so every run pays ~4 s even when no test touches
litellm. This is the tax on the most common agent action: iterating on one test
file.

The import becomes lazy. Measured effect:

| | before | after |
|---|---|---|
| single test file (42 tests, 0.14 s of testing) | 7.40 / 7.73 / 6.86 s | **0.96 / 0.91 / 2.03 s** |
| full suite `-n auto` | 63.3 s | **58.9 s** |
| pass / skip counts | 6369 / 10020 | **identical** |

Behavior that must not change: every test that currently gets a flushed litellm
client cache must still get one, and litellm logging must still be configured
exactly once per session for runs that use litellm.

### F7 — Documentation

`AGENTS.md` gains a short environment-setup section: `setup_env.sh` is the way to
set up an environment, what the flags do, the `uv lock` caveat from F4, and a note
that `CLAUDE.md` is generated from `AGENTS.md` and overwritten on every run — so
personal agent notes belong in user-scope `~/.claude/CLAUDE.md`, not the repo copy.

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

1. **Setup command** — a deliberately dumb, repo-agnostic wrapper, since the same
   command is shared across repos:

   ```bash
   #!/usr/bin/env bash
   set -uo pipefail
   cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
   if [ -f .config/utils/setup_env.sh ]; then
     bash .config/utils/setup_env.sh --upgrade-tools \
       || echo "cloud-setup: WARNING setup_env.sh exited $?"
   fi
   ```

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

## Dependency on upstream

`.agents/mcp.json` invokes `uvx hooks-mcp`, which currently resolves
`hooks-mcp 0.2.4` against `mcp 2.0.0` and fails to start
(`'Server' object has no attribute 'list_tools'`). A fix is in progress upstream.
The repo pins nothing now, since a local `mcp<2` pin would hold that fix back.
Once 0.2.5 ships, set a floor — `--from "hooks-mcp>=0.2.5"` — because `uvx` reuses
cached tool environments and could otherwise keep serving the broken pair.

This is not blocking: `CLAUDE.md` and skills work without MCP.

## Success Criteria

On a fresh cloud sandbox, after the environment setup command runs:

1. `uv --version` reports ≥ 0.10.
2. A plain `uv run python -c "print(1)"` completes in well under a second and
   leaves `uv.lock` unmodified.
3. `.venv` is Python 3.13 and `import tkinter` succeeds.
4. `uv run python3 -m pytest --benchmark-quiet -q -n auto .` reports **zero
   collection errors**.
5. `app/web_ui/src/lib/check_schema.sh` runs and reports the schema is up to date.
6. `uv run ./checks.sh --agent-mode` exits 0.
7. `CLAUDE.md`, `.claude/skills/`, and `.mcp.json` all exist.
8. `git status --porcelain` is empty — setup mutates no tracked file.
9. Running one small test file completes in ~1 s rather than ~7 s.

Measured reference values for 4–6 on this hardware: suite 6369 passed / 10020
skipped / 0 errors in ~59 s; `checks.sh` green in ~2 m 23 s.
