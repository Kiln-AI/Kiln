#!/bin/sh

# Check our project: formatting, linting, testing, building, etc.
# Good to call this from .git/hooks/pre-commit

# Important: run with `uv run` to setup the environment

set -e

# work from the root of the repo
cd "$(dirname "$0")"

headerStart="\n\033[4;34m=== "
headerEnd=" ===\033[0m\n"

echo "${headerStart}Checking Python: Ruff, format, check${headerEnd}"
# I is import sorting
uvx  ruff check --select I
uvx ruff format --check .

echo "${headerStart}Checking for Misspellings${headerEnd}"
if command -v misspell >/dev/null 2>&1; then
    find . -type f | grep -v "/node_modules/" | grep  -v "/\." | grep -v "/dist/" | grep -v "/desktop/build/" | xargs misspell -error
    echo "No misspellings found"
else
    echo "\033[31mWarning: misspell command not found. Skipping misspelling check.\033[0m"
    echo "\033[31mTo install: go install github.com/client9/misspell/cmd/misspell@latest\033[0m"
fi

echo "${headerStart}Web UI: format, lint, check${headerEnd}"
changed_files=$(git diff --name-only --staged)
if [[ "$changed_files" == *"app/web_ui/"* ]]; then
    echo "${headerStart}Checking Web UI: format, lint, check${headerEnd}"
    cd app/web_ui
    npm run format_check
    npm run lint
    npm run check
    npm run test_run
    echo "Running vite build"
    npm run build > /dev/null
    cd ../..
else
    echo "Skipping Web UI: no files changed"
fi

echo "${headerStart}Checking Types${headerEnd}"
pyright .

echo "${headerStart}Running Python Tests${headerEnd}"
python3 -m pytest --benchmark-quiet -q .
