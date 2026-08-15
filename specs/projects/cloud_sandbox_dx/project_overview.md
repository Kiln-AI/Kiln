---
status: draft
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
3. **Python 3.13 via a generated, gitignored `.python-version`**, written by both
   `setup_env.sh` and the cloud setup script. Preferred over a bare
   `uv sync --python 3.13` because uv consults the file on every later sync, so it
   survives deleting `.venv`. No new tracked top-level file.
4. **No source change for tkinter.** It is fixed by building the venv on
   uv-managed Python 3.13, which bundles Tk. `desktop_server.py` and
   `import_api.py` stay as they are.
5. **Restore agent config** by running the existing `.agents/claude/setup.sh` from
   the cloud setup script. This also requires fixing `.agents/mcp.json` to pin
   `mcp<2` — `hooks-mcp 0.2.4` resolves against `mcp 2.0.0`, which dropped
   `Server.list_tools`, so the MCP server currently fails to start for everyone.
   Whether Claude Code on the web auto-trusts a project `.mcp.json` is still
   unverified; if it does not, fall back to documenting direct shell commands in
   `AGENTS.md`.
6. **Test startup cost** — under investigation.
7. **Out of scope:** the `debug_detector` TODO-in-spec-markdown issue and the
   mutation-sweep scripts leaving mutated source on disk. Unrelated to sandboxes.
8. **Setup runs the two installs in parallel, in the foreground** (~37 s → ~26 s).
   Not backgrounded: `npm ci` deletes `node_modules` before repopulating it, so an
   agent acting during setup would hit intermittent phantom import errors — the
   exact failure class this project exists to remove.

A shared, repo-agnostic wrapper script (checking for the existence of both setup
scripts) is configured as the Claude Code cloud environment setup command.
