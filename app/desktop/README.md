# Desktop Apps

## MacOS Environment Setup

UV python doesn't include TK/TCL [yet](https://github.com/astral-sh/uv/issues/7036). Instead, we install system python including TK/TCL, and tell UV venv to use system python.

```
# Install python 3.14 and python-tk 3.14 with homebrew
brew install python-tk@3.14
brew install python@3.14

# check uv can see it hoembrew version
uv python list --python-preference only-system

# setup 3.14 uv-managed venv with system (homebrew) python 3.14
uv venv --python 3.14 --python-preference only-system

# Check it worked
uv run python --version

# Run desktop
uv run python -m app.desktop.desktop
```

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
