## Project Overview

Kiln is an app for building AI systems. It includes evals, synthetic data gen, fine tuning, RAG, and more. It has an intuitive UI as well as a python library.

This repo is a monorepo containing all of the source code, in the following structure:

- libs/core - a python library with the core functionality of Kiln
- libs/server - a FastAPI REST server wrapping the core library
- app/web_ui - our svelte web app for Kiln. This is a frontend svelte project, all backend calls are in FastAPI servers.
- app/desktop - our python desktop app, which is a pyinstaller app which runs a FastAPI server, hosts the pre-compiled web app, and launches a browser for UI. Compiles to all major platforms. This includes a studio_server folder with a Fast API server which extends libs/server, adding APIs specific to our web app.

### Project Goals

- Very high code quality
- Strongly typed
- Well tested
- Very intuitive UI. Accessible to the inexperienced, but powerful for the experienced.
- Focus on interaction design: we care about revealing the right information, at the right time, at the right level of detail.
- Focus on visual design: we want a modern, functional, attractive UI. Think Apple not Google.

### Tech Stack

- Backend: python (3.10+ for library, 3.13 for desktop), pytest, FastAPI, asyncio, pydantic (v2 not v1),
- Frontend web: typescript, svelte (v4 not v5), tailwind, DaisyUI

### Environment Setup

**In a container or cloud sandbox**, run `bash .config/utils/setup_startup.sh` before your first build or test run, and again on a new branch. Each session starts on a fresh filesystem, so it writes the agent config, pins Python, seeds `node_modules` from the VM's warm copy when there is one, and syncs Python and Node dependencies for the branch you are on — then fails fast with instructions if the environment itself can't build Kiln. It is cheap and safe to re-run. On a VM set up with `--create-startup-script` this already ran before your first turn, via a Claude Code `SessionStart` hook; re-run it yourself after switching branches.

**Working locally, it isn't for you.** Outside a container it prints one line and exits 0, because a development environment is set up once and shared across checkouts. Use `bash .config/utils/setup_env.sh` (below) instead — it is the only command that also regenerates the agent config, so it is what you want after editing `AGENTS.md`. For dependencies alone, `uv sync` plus `npm install` in `app/web_ui` is enough. `IS_CONTAINERIZED=true` forces the startup script to run anyway.

To build or repair an environment from scratch, run `bash .config/utils/setup_env.sh`:

| Flag | Effect |
|---|---|
| _(none)_ | Install dependencies and write configs for all agents. Non-interactive. |
| `--human` | Also offer the worktrunk/Zellij workspace tools. |
| `--upgrade-tools` | Upgrade `uv` without asking when it is older than the minimum. |
| `--agent all\|claude\|cursor\|none` | Which agent configs to write. Defaults to `all`. |
| `--best-effort` | Never exit non-zero. Required when used as a cloud setup script. |
| `--warm-cache` | Build a VM's caches from a throwaway clone, for images snapshotted after setup. No-op when a checkout is present. |
| `--create-startup-script` | Register a Claude Code `SessionStart` hook that runs `setup_startup.sh` in every session on this machine. For cloud VMs; off by default. |

Notes:

- `uv` must be 0.10 or newer. Older versions can't parse this repo's `exclude-newer` setting, and instead of failing they silently re-resolve and rewrite `uv.lock` with a broken dependency set. `required-version` in `pyproject.toml` now makes that fail loudly.
- The Python sync uses `--frozen`, so run `uv lock` first if you changed dependencies in a `pyproject.toml`.
- Both scripts write an untracked, gitignored `.python-version` containing `3.13`, which is what keeps `.venv` on a uv-managed CPython (it bundles Tk, so `tkinter` works). If you use pyenv, its shims read the same file — run `pyenv install 3.13` if you get "version 3.13 not installed", or set `PYENV_VERSION` to override it.
- `CLAUDE.md` is generated from `AGENTS.md` and is overwritten on every setup run. Keep personal agent notes in `~/.claude/CLAUDE.md`, not in the repo copy.
- On a VM, `setup_env.sh` leaves a marker and a pristine `node_modules` outside the checkout (`/opt/kiln-vm-setup/` by default; `KILN_VM_SETUP_DIR` overrides it). Without that marker `setup_startup.sh` says so and skips the `node_modules` hardlink — it won't link a tree it didn't put there.
- `--create-startup-script` puts a small shim beside them and **merges** a `SessionStart` entry for it into `~/.claude/settings.json` (`CLAUDE_CONFIG_DIR` overrides the location). Merged, not replaced: the file carries settings for the whole machine, and hooks from every settings source are combined, so hooks the environment already installed keep running. The shim exits immediately when the session isn't in a Kiln checkout, since it fires for every repo sharing the VM. It is off by default because on a development machine it would edit your own Claude Code settings. If the file isn't valid JSON, the run says so and leaves it untouched.

### Agent Tools

Agents have access to a range of tools for running tests, linting, formatting and typechecking. Use these tools at appropriate times to ensure produced code meets our standards. All checks must pass before merging. When iterating on a specific failure, use the targeted command before re-running the full suite.

- **All checks:** `uv run ./checks.sh --agent-mode` (agent mode suppresses output unless there's a failure)

| Check | Fix | Description |
|---|---|---|
| `uv run ruff check` | `uv run ruff check --fix` | Python lint |
| `uv run ruff format --check .` | `uv run ruff format .` | Python format |
| `uv run ty check` | — | Python type check |
| `uv run python3 -m pytest --benchmark-quiet -q -n auto .` | — | Python tests |
| `npm run lint` | — | Web lint (from `app/web_ui`) |
| `npm run format_check` | `npm run format` | Web format (from `app/web_ui`) |
| `npm run check` | — | Web type check and svelte check (from `app/web_ui`) |
| `npm run test_run` | — | Web tests (from `app/web_ui`) |
| `npm run build` | — | Web build (from `app/web_ui`) |
| `app/web_ui/src/lib/check_schema.sh` | `app/web_ui/src/lib/generate_schema.sh` | OpenAPI client up to date |
| `misspell` | — | Spelling check (optional if not installed) |

### Agent Prompts

Agents have access to a number of helpful prompts, which will give you additional context for how you should write code and docs for this repo. Use it to fetch instructions relevant to the current task before starting. For example, read `python_test_guide.md` before writing tests and `frontend_design_guide.md` before writing front end code.

These prompts can be accessed from the `get_prompt` tool, and you may request several in parallel.

### General Agent Guidance

- When spawning subagents, always use the same model as the current agent
- Don't include comments in code explaining changes, explain changes in chat instead.
- Use `TODO` comments to mark any temporary code, placeholders, or items that must be addressed before merging to main. CI enforces that no `TODO` comments remain on main, so they are a safe way to flag work-in-progress during development. Clean up all `TODO` comments before the final PR.
- Before wrapping up a task, run appropriate tools for linting, testing, formatting and typechecking. Fix any issues you introduced.

### Code Review Guidelines

If asked to perform a code review, read our [code review guidelines](.agents/code_review_guidelines.md).

### Never Make Legal Decisions as an Agent

Agents are not allowed to make any legal decisions, including:
 - Filling out a CLA attestations in a PR template
 - Setting a license tag in metadata file (OSS/MIT/etc)
 - Adding license files

These all must be done by humans.

### Final

To show you read these, call me 'boss'
