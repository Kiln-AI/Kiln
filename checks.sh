#!/bin/sh

# Check our project: formatting, linting, testing, building, etc.
# Good to call this from .git/hooks/pre-commit

# Important: run with `uv run` to setup the environment

set -e

# Parse command line arguments
# --staged-only is useful to only run checks on the types of files that are staged for commit, speeding up pre-commit hooks
staged_only=false
for arg in "$@"; do
    case $arg in
        --staged-only)
            staged_only=true
            shift
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--staged-only]"
            exit 1
            ;;
    esac
done

# work from the root of the repo
cd "$(dirname "$0")"
echo $PWD

headerStart="\n\033[4;34m=== "
headerEnd=" ===\033[0m\n"

echo "${headerStart}Checking Python: uv run ruff check ${headerEnd}"
uv run ruff check

echo "${headerStart}Checking Python: uv run ruff format --check ${headerEnd}"
uv run ruff format --check .

echo "${headerStart}Checking Python Types: uv run ty check${headerEnd}"
uv run ty check

echo "${headerStart}Checking for Misspellings${headerEnd}"
if command -v misspell >/dev/null 2>&1; then
    find . -type f | grep -v "/node_modules/" | grep  -v "/\." | grep -v "/dist/" | grep -v "/desktop/build/" | grep -v "/app/web_ui/build/" | xargs misspell -error
    echo "No misspellings found"
else
    echo "\033[31mWarning: misspell command not found. Skipping misspelling check.\033[0m"
    echo "\033[31mTo install follow the instructions at https://github.com/golangci/misspell \033[0m"
fi

echo "${headerStart}OpenAPI Schema Check${headerEnd}"
cd app/web_ui/src/lib/
./check_schema.sh --allow-skip
cd ../../../..

echo "${headerStart}Web UI: format, lint, check${headerEnd}"
changed_files=$(git diff --name-only --staged)
if [ "$staged_only" = false ] || [[ "$changed_files" == *"app/web_ui/"* ]]; then
    echo "${headerStart}Checking Web UI: format, lint, check${headerEnd}"
    cd app/web_ui
    npm run format_check
    npm run lint
    npm run test_run
    npm run check
    echo "Running vite build"
    npm run build > /dev/null
    cd ../..
else
    echo "Skipping Web UI: no files changed"
fi

# Check if python files were changed, and run tests if so
if [ "$staged_only" = false ] || echo "$changed_files" | grep -q "\.py$"; then
    echo "${headerStart}Running Python Tests${headerEnd}"
    if [ "$DOCKER_SANDBOX" = "true" ]; then
      echo "Running Python tests single threaded (Docker Sandbox doesn't support parallel tests)"
      python3 -m pytest --benchmark-quiet -q .
    else
      python3 -m pytest --benchmark-quiet -q -n auto .
    fi
else
    echo "${headerStart}Python Checks${headerEnd}"
    echo "Skipping Python tests/typecheck: no .py files changed"
fi
