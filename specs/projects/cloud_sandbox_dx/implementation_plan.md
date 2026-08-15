---
status: draft
---

# Implementation Plan: Cloud Sandbox Developer Experience

## Phases

- [x] Phase 1: uv floor and Python 3.13 pin — `required-version` in
      `pyproject.toml`, `.python-version` in `.gitignore`. Small, independent, and
      the foundation everything else assumes.
- [x] Phase 2: `setup_env.sh` rewrite — `CONFIGURATION` block, flags, uv version
      gate, Python 3.13, parallel `uv sync --frozen --all-packages` + `npm ci`,
      agent config, `--human` extras, `--best-effort`.
- [x] Phase 2b: `setup_startup.sh` — per-session hard-dependency gate plus
      `uv sync` / `npm install` top-up. Added after research §12 showed the setup
      script runs once per environment and is then snapshotted and skipped, so
      nothing repo-aware runs per session.
- [x] Phase 3: `conftest.py` deferred litellm import, including the log-path
      verification called out in the architecture.
- [x] Phase 4: `AGENTS.md` environment-setup section.

Phases 2 and 3 are independent and can be reviewed separately. Phase 4 depends on
Phases 2 and 2b being settled, since it documents that interface.

## Validation

Each phase ends with `uv run ./checks.sh --agent-mode` green and
`git status --porcelain` empty.

Final validation for the project must happen in a **fresh** cloud sandbox against
the nine success criteria in the functional spec. Re-running in an already-repaired
session proves nothing — the current session has had uv upgraded and the venv
rebuilt on Python 3.13 by hand during research.

## Environment-side work (not code, tracked here so it isn't lost)

Outside the repo, in the Claude Code cloud environment configuration:

- [ ] Setup script set to the **contents** of `.config/utils/setup_env.sh`, with
      `UPGRADE_TOOLS=true` and `BEST_EFFORT=true` in its `CONFIGURATION` block
      (functional spec, "Environment-side changes"). Not a wrapper that calls the
      repo copy — see research §12 for why that cannot work.
- [ ] Remove the now-deprecated `UV_NATIVE_TLS` variable. Adding `UV_SYSTEM_CERTS`
      is not enough on its own: with both set, uv still prints the deprecation
      warning on every invocation, as it does throughout this session's logs.
- [ ] `enableAllProjectMcpServers: true` in user-level `~/.claude/settings.json`,
      so the project `.mcp.json` is trusted. Nothing repo-side can do this.
- [x] Replace `UV_NATIVE_TLS` with `UV_SYSTEM_CERTS` in the environment variables.
      Done. Takes effect in new sessions.

## Follow-up, blocked on upstream

- [ ] Once `hooks-mcp` 0.2.5 ships, set a floor in `.agents/mcp.json`:
      `--from "hooks-mcp>=0.2.5"`. Not a pin — a floor — because `uvx` reuses
      cached tool environments and could otherwise keep serving the broken
      0.2.4 + mcp 2.0 pair.
