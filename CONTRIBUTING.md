# Contributing to Kiln

## Issues and Bug Tracking

We use [GitHub issues](https://github.com/Kiln-AI/Kiln/issues) for tracking issues, bugs, and feature requests.

## Contributing

New contributors must agree to the [contributor license agreement](.config/CLA.md).

## Development Environment Setup

We use [uv](https://github.com/astral-sh/uv) to manage the Python environment and dependencies, and npm to manage the web UI.

The quickest path is the setup script, which does all of the below and also pins the Python version and writes editor/agent config:

```
# First install uv: https://github.com/astral-sh/uv
# and Node if you don't have it already: https://nodejs.org
bash .config/utils/setup_env.sh --human
```

Run `bash .config/utils/setup_env.sh --help` for the flags. `--human` adds an optional offer to install the [worktree workspace tools](.config/wt/README.md); without it the script is non-interactive.

Or do it by hand. Write the Python pin first — `uv sync` on its own builds `.venv` against whatever Python it finds, and many system Pythons are built without `tkinter`, which several tests and both OpenAPI schema scripts need:

```
echo 3.13 > .python-version   # gitignored; uv reads it on every sync
uv python install 3.13
uv sync
cd app/web_ui
npm install
```

**uv must be 0.10 or newer.** The repo sets `required-version = ">=0.10"` in `pyproject.toml`, so an older uv refuses to run rather than silently rewriting `uv.lock` with a broken dependency set — which is what it did before the floor existed. If you hit that refusal, upgrade with `uv tool install --force uv`, or let `setup_env.sh --upgrade-tools` do it for you.

The setup script also writes a gitignored `.python-version` containing `3.13`. uv reads it on every sync, which is what keeps the virtualenv on a Python that bundles Tk (several tests and both OpenAPI schema scripts need `tkinter`). If you use pyenv, its shims read the same file — run `pyenv install 3.13` if you get "version 3.13 not installed".

There is a second script, `.config/utils/setup_startup.sh`, but it is for containers and cloud sandboxes, where every session starts on a fresh filesystem. On a development machine it prints one line and exits 0 — your environment is already set up and shared across checkouts. After switching to a branch that changed a lockfile, re-run `bash .config/utils/setup_env.sh`, which also refreshes the generated editor and agent config; `uv sync` plus `npm install` covers the dependencies alone.

### Environment Variables

The web UI has optional dev-only environment variables. See [`app/web_ui/.env.example`](app/web_ui/.env.example) for details.

### Running Development Servers

Running the web-UI and Python servers separately is useful for development, as both can hot-reload.

To run the API server, Studio server, and Studio Web UI with auto-reload for development:

1. In your first terminal, navigate to the base Kiln directory:

   ```bash
   uv run python -m app.desktop.dev_server
   ```

2. In a second terminal, start the web UI dev server:

   ```bash
   make ui
   ```

3. Open the app: http://localhost:5173/run

### Makefile

The root `Makefile` provides convenient shortcuts for commonly used scripts (`make dev`, `make ui`, `make package`, ...).

### Running and Building the Desktop App

See the [desktop README](app/desktop/README.md) instructions for running the desktop app locally.

## Tests, Formatting, and Linting

We have a large test suite, and use [ruff](https://github.com/astral-sh/ruff) for linting and formatting.

Please ensure any new code has test coverage, and that all code is formatted and linted. CI will block merging if tests fail or your code is not formatted and linted correctly.

To confirm everything works locally, run:

```bash
uv run ./checks.sh
```

4. Setup pre-commit hook.

In your base Kiln directory, run the following command to setup a pre-commit hook which will run the Kiln checks locally before each commit.

```bash
cp .config/utils/pre-commit-hook .git/hooks/pre-commit
```

5. Spec Skill

We use the spec from this project for planning: https://github.com/scosman/vibe-crafting

To install (adapt to your tooling):

```bash
# Outside of the project
git clone git@github.com:scosman/vibe-crafting.git

# Claude Code
mkdir -p ~/.claude/skills
ln -s "$(pwd)/vibe-crafting/skill" ~/.claude/skills/spec
# Optional: add Read access to your skills path to ~/.claude/settings.yaml

# Cursor
mkdir -p ~/.cursor/skills
ln -s "$(pwd)/vibe-crafting/skill" ~/.cursor/skills/spec
```

## Optional Setup

### IDE Extensions

We suggest the following extensions for VSCode/Cursor. With them, you'll get compliant formatting and linting in your IDE.

- Prettier
- Python
- Python Debugger
- Ty - language server and type checker for Python
- Ruff
- Svelte for VS Code
- Vitest
- ESLint

### HooksMCP

We have a [hooks_mcp.yaml](./.config/hooks_mcp.yaml) file, which defines how coding agents can interact with our developer tools (formatting, linting, etc).

To use it, [setup HooksMCP](https://github.com/scosman/hooks_mcp?tab=readme-ov-file#running-hooksmcp) for your agents.

### llms.txt

Vibing? Here are some [llms.txt](https://llmstxt.org) you may want to add.

Usage: `@docs Svelte` in cursor lets the LLM read the docs of the specified library. Most popular libraries added by Cursor automatically, but here are some to add manually:

- daisyUI’s: https://daisyui.com/docs/editor/cursor/
