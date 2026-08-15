---
status: complete
---

# Cloud Sandbox Developer Experience

A meta project to improve the ability to work on the Kiln repo inside Claude Code
cloud sandboxes.

I use Claude Code's cloud sandboxes more and more, so I really value efficiency in
that environment. I've seen a bunch of issues — the list below is not complete.
The goal is to make the best fixes for working in cloud sandboxes: process
improvements, `CLAUDE.md`/`AGENTS.md` updates, setup script improvements, etc.

Issues seen so far:

- Can setup be faster? A `uv sync` cache? On another project I added an R2 cache
  for cargo. How fast is setup today? Is it worth optimizing? Are other startup
  steps costing us?
- Some code uses tkinter, which doesn't work on headless Linux. It isn't really
  needed often — we can host a web server, we can run things.
- Can't run the script to update the OpenAPI schema (tkinter issue).
- Test performance: is it fast enough? Should we add something to speed it up?
  Are we getting parallel performance?
- There may be many more.

A report from another agent that encountered and worked around some of these
issues is attached as a starting point. Its solutions may be far from optimal —
it is a starting point, not a plan.

Planning must begin with a research phase: run experiments, clear the cache and
re-run the startup script, measure times, try running things. Get data before
planning.

## Research

The research phase is complete. See [research_findings.md](research_findings.md)
for measurements taken on a live sandbox.

## Decisions

Settled during planning:

1. **Reuse `.config/utils/setup_env.sh`** rather than adding a new setup script.
   Make its default fully non-interactive; add a `--human` flag to opt into the
   worktrunk/zellij extras. Switch `uv sync` → `uv sync --frozen --all-packages`
   and `npm install` → `npm ci`. Mention the script in `AGENTS.md` as the way to
   set up an environment.

   It also runs the agent config setup, via `--agent all|claude|cursor|none`,
   **defaulting to `all`**. Everything both agent scripts write is gitignored
   (`.claude/`, `.cursor/`, `CLAUDE.md`, `.mcp.json`, `.worktreeinclude`), they
   write byte-identical `.mcp.json` and `.worktreeinclude`, and the whole copy is
   176K with no network — so running both by default is free and avoids
   privileging one editor. `--agent none` exists so the script stays usable in CI.
   Because `all` is the default, `--human` does not need to ask which agent.

   `.agents/claude/setup.sh` clobbers `CLAUDE.md` unconditionally (it is generated
   from `AGENTS.md`), which now happens on every plain `setup_env.sh` run. Note in
   `AGENTS.md` that personal agent notes belong in user-scope `~/.claude/CLAUDE.md`,
   not the repo copy.
2. **Enforce a uv floor:** add `required-version = ">=0.10"` to `[tool.uv]`, so a
   too-old uv fails loudly instead of silently rewriting `uv.lock`. (0.9.9 still
   fails to parse the relative `exclude-newer`; 0.10.0 is the first good version.)

   **Upgrading uv lives in `setup_env.sh`, behind an opt-in `--upgrade-tools`
   flag.** Not pinned to a version — always install latest. The command is
   `uv tool install --force uv` (no pip; `uv self update` fails structurally here,
   see research §8). Without the flag: detect a too-old uv and prompt
   interactively with a 10 s `read -t` timeout, defaulting to yes on timeout;
   with no TTY, warn only. The cloud env config passes `--upgrade-tools`.

   No `cloud_env_setup.sh` — the shared cross-repo wrapper stays as dumb as
   possible: check for `.config/utils/setup_env.sh` and call it with
   `--upgrade-tools`. Nothing else.
3. **Python 3.13 via a generated, gitignored `.python-version`**, written by both
   `setup_env.sh` and the cloud setup script. Preferred over a bare
   `uv sync --python 3.13` because uv consults the file on every later sync, so it
   survives deleting `.venv`. No new tracked top-level file.
4. **No source change for tkinter.** It is fixed by building the venv on
   uv-managed Python 3.13, which bundles Tk. `desktop_server.py` and
   `import_api.py` stay as they are.
5. **Restore agent config** by running the existing `.agents/claude/setup.sh` from
   the cloud setup script.

   The MCP server used to fail to start: `hooks-mcp 0.2.4` resolved against
   `mcp 2.0.0`, which dropped `Server.list_tools`. This repo pinned nothing while
   that was being fixed upstream — a local `mcp<2` pin would only have held back
   the fix. **Resolved:** `hooks-mcp` 0.2.5 shipped, and `.agents/mcp.json` now
   carries a *floor* (`--from "hooks-mcp>=0.2.5"`), not a pin, because `uvx` reuses
   cached tool environments and could otherwise keep serving the broken
   0.2.4 + mcp 2.0 pair.

   Separately, whether Claude Code on the web auto-trusts a project `.mcp.json` is
   still unverified. Verified working without a session restart: `CLAUDE.md` and
   `.claude/skills/`. If MCP turns out to need approval a cloud session cannot
   give, fall back to documenting the direct shell commands in `AGENTS.md`.
6. **Test startup cost:** adopt the deferred-litellm change to the root
   `conftest.py` (research §10). Single test file goes from ~7.4 s to ~0.95 s
   (~7×), full suite 63.3 s → 58.9 s, identical pass/skip counts.

   That ~7× is the number this decision was made on, and it did not generalize:
   later measurements on other machines ranged down to ~2.3×, since litellm's
   import is far cheaper warm. The decision still holds — the direction and the
   identical counts reproduced everywhere — but see F6 for the real spread.
   **Rejected:** `--ignore`-ing the paid-heavy test files — saves only ~1.7 s and
   risks silently not running tests.

   **Dropped — not implementing.** Enough wins are banked without it. Recorded
   below for the record only:

   ~~P2, drop if the phase runs long:~~ set `LITELLM_LOCAL_MODEL_COST_MAP=True`
   via `.env`, written by `setup_env.sh`. Worth ~0.6 s of a 3.9 s litellm import,
   which is ~1 % of a full-suite run and nothing at all on the inner loop once the
   conftest change lands — so the justification is hermeticity (no HTTP request to
   GitHub at import time), not speed. Safe here because `load_dotenv()` is called
   in exactly one place (`conftest.py:34`) and nothing in `libs/` or `app/` reads
   `.env`, so it cannot reach production. Requires moving `load_dotenv()` to
   conftest module scope — the current session-scoped fixture runs after
   collection, by which time test modules have already imported litellm. That
   needs `# ruff: noqa: E402`, for which `app/desktop/desktop.py:1` is precedent.
7. **Out of scope:** the `debug_detector` TODO-in-spec-markdown issue and the
   mutation-sweep scripts leaving mutated source on disk. Unrelated to sandboxes.
8. **Setup runs the two installs in parallel, in the foreground** (~37 s → ~26 s).
   Not backgrounded: `npm ci` deletes `node_modules` before repopulating it, so an
   agent acting during setup would hit intermittent phantom import errors — the
   exact failure class this project exists to remove.

9. **The cloud setup script is a copy of `setup_env.sh`, not a wrapper around it.**
   Discovered after the first plan was written (research §12): a cloud setup script
   runs once per environment and is then snapshotted and skipped, and the
   environment is shared across repos — so it cannot depend on a particular
   checkout being on disk. The original "dumb wrapper that calls
   `.config/utils/setup_env.sh`" would have done nothing whenever that path was
   absent.

   Instead the file's contents are pasted into the environment dialog, and only a
   delimited `CONFIGURATION` block at the top is edited. The script stays in the
   repo, reviewable and testable locally.

   To be clear about what this does and does not buy: pasting removes the
   dependency on a *fixed* path, but a pasted copy still has no idea where the
   checkout is — and, run at environment-build time, usually has none to find. So
   the script has to discover its project root at runtime and treat "no checkout"
   as a normal outcome, doing the environment-level work and skipping the rest with
   a notice. Without that it is no better off than the wrapper, only noisier about
   it. The wrapper's one real advantage was that it knew the root; the replacement
   has to earn that back rather than assume it.

   This also forces `--best-effort`/`BEST_EFFORT`: a setup script that exits
   non-zero stops the session from starting, so a `set -e` script with hard
   `exit 1` paths would turn one flaky `npm` fetch into a sandbox that will not
   boot.
10. **A new `setup_startup.sh` carries the per-session work.** Because the setup
    script is snapshotted and skipped, nothing repo-aware runs per session.
    `AGENTS.md` instructs agents to run it before their first build or test. It
    verifies the hard dependencies the VM was supposed to provide — failing fast
    with the repair command if the session landed on a bad VM — then tops up
    `uv sync` and `npm install` for the current branch. Measured **22.9 s** for the
    first run of a snapshot-started session, and ~2 s for a re-run inside it. (An
    earlier "5.9 s warm" here was a hot-page-cache figure and did not survive a
    cold start.)

    It uses `npm install` where `setup_env.sh` uses `npm ci`: the working directory
    is on the snapshotted filesystem (measured — a container restart preserved
    `node_modules`, `.venv`, and a 1.4 GB uv cache), and `npm ci` would empty
    `node_modules` before refilling it, discarding exactly the cached state that
    makes the top-up cheap.
11. **A `SessionStart` hook runs `setup_startup.sh`, installed by the VM setup
    script itself.** Added late, once a live session showed that user-level hooks in
    `~/.claude/settings.json` fire in cloud sandboxes and that `~/.claude` is on the
    snapshotted filesystem. It closes the project's last circular dependency — the
    instruction to run the script lived in a file the script writes — without a
    tracked `.claude/settings.json` and without an operator-side prompt, which is
    what the earlier framing assumed were the only options.

    The registration **merges** into the user settings and was verified not to
    displace the environment's own `SessionStart` hook, whose loss would have
    broken commit signing. It costs the session's first ~23 s up front, and async
    mode was rejected because the agent's context is assembled from files the hook
    writes.
