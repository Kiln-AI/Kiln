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

1. In your first terminal:

   ```bash
   uv run python -m app.desktop.dev_server
   ```

2. In a second terminal, navigate to the web UI directory and start the dev server:

   ```bash
   cd app/web_ui
   npm run dev --
   ```

3. Open the app: http://localhost:5173/run

### Running the Desktop App

See the [desktop README](app/desktop/README.md) instructions for running the desktop app locally.

### Building the Desktop App

Typically building desktop apps are done in a CI/CD pipeline, but if you need to build the desktop app locally, you can do so with:

```bash
cd app/desktop
uv run ./build_desktop_app.sh
```

## Tests, Formatting, and Linting

We have a large test suite, and use [ruff](https://github.com/astral-sh/ruff) for linting and formatting.

Please ensure any new code has test coverage, and that all code is formatted and linted. CI will block merging if tests fail or your code is not formatted and linted correctly.

To confirm everything works locally, run:

```bash
./checks.sh
```
