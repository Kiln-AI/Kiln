# Desktop Apps

## MacOS Environment Setup

UV python doesn't include TK/TCL [yet](https://github.com/astral-sh/uv/issues/7036). Instead, we install system python including TK/TCL, and tell UV venv to use system python.

```
# Install python 3.13 and python-tk 3.13 with homebrew
brew install python-tk@3.13
brew install python@3.13

# check uv can see it hoembrew version
uv python list --python-preference only-system

# setup 3.13 uv-managed venv with system (homebrew) python 3.13
uv venv --python 3.13 --python-preference only-system

# Check it worked
uv run python --version

# Run desktop (see below)
make dev_desktop
```

## Run Desktop App for Development

`make dev` runs the API server alone, without Tk, so it can't exercise the tray icon, the macOS dock reopen handler or native file dialogs. To test those, run the real desktop app from the repo root:

```bash
make dev_desktop
```

- It serves the built web UI from `app/web_ui/build`. Build it first with `cd app/web_ui && nvm use && npm run build`, and rebuild after UI changes.
- It uses port 8757 by default (`KILN_LOCAL_API_PORT`), the same as `make dev`. Stop `make dev` first. If the port is taken, the app assumes another copy is running, opens the browser and exits.
- For UI hot reload, run `make ui` alongside it and use the Vite URL (http://localhost:5173). The Vite UI calls the desktop app's API on port 8757.
- Python changes need a restart; there is no hot reload.
- It skips the remote model list fetch by default. Set `KILN_SKIP_REMOTE_MODEL_LIST=false` to fetch it.

## Building the Desktop App

Typically building desktop apps are done in a CI/CD pipeline, but if you need to build the desktop app locally, you can do so with:

```bash
cd app/desktop
uv run ./build_desktop_app.sh
```

## MacOS Code Signing

Easy way, but just signs with personal ID for local development: `codesign --force --deep -s - kiln.app`

Sign with a developer ID (should only be done for official releases by Kiln team):

1. Get developer ID name: `security find-identity -v -p codesigning`
2. Run `codesign --force --deep -s "Developer ID Application: YOUR NAME (XXXXXXXX)" kiln.app`
