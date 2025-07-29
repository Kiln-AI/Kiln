# Contributing to Kiln

## Issues and Bug Tracking

We use [GitHub issues](https://github.com/Kiln-AI/Kiln/issues) for tracking issues, bugs, and feature requests.

## Contributing

New contributors must agree to the [contributor license agreement](CLA.md).

## Development Environment Setup

We use [uv](https://github.com/astral-sh/uv) to manage the Python environment and dependencies, and npm to manage the web UI.

```
# First install uv: https://github.com/astral-sh/uv
uv sync
cd app/web_ui
# install Node if you don't have it already
npm install
```

### Running Development Servers

Running the web-UI and Python servers separately is useful for development, as both can hot-reload.

To run the API server, Studio server, and Studio Web UI with auto-reload for development:

1. In your first terminal, navigate to the base Kiln directory:

   ```bash
   uv run python -m app.desktop.dev_server
   ```

2. In a second terminal, navigate to the web UI directory and start the dev server:

   ```bash
   cd app/web_ui
   npm run dev --
   ```

3. Open the app: http://localhost:5173/run

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

Copy contents of util/pre-commit-hook to your existing hook to run Kiln checks before each commit.

## Optional Setup

### IDE Extensions

We suggest the following extensions for VSCode/Cursor. With them, you'll get compliant formatting and linting in your IDE.

- Prettier
- Python
- Python Debugger
- Type checking by pyright via one of: Cursor Python if using Cursor, Pylance if VSCode
- Ruff
- Svelte for VS Code
- Vitest
- ESLint

### llms.txt

Vibing? Here are some [llms.txt](https://llmstxt.org) you may want to add.

Usage: `@docs Svelte` in cursor lets the LLM read the docs of the specified library. Most popular libraries added by Cursor automatically, but here are some to add manually:

- daisyUI’s: https://daisyui.com/docs/editor/cursor/
