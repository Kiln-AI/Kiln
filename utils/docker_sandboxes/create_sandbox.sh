#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR/../../..")"
cd "$REPO_ROOT"

for arg in "$@"; do
  if [[ "$arg" == "--rebuild" ]]; then
    echo "Removing template images (--rebuild)..."
    docker rmi kiln_sandbox_base_template 2>/dev/null || true
    docker rmi kiln_deps_installed_template 2>/dev/null || true
    break
  fi
done

# Build template. Fast if already built.
echo "Building sandbox image..."
docker build -t kiln_sandbox_base_template -f utils/docker_sandboxes/DockerfileClaude utils/docker_sandboxes

echo "\nCreating base sandbox..."
docker sandbox create -t kiln_sandbox_base_template --name kiln_base_sandbox claude .

# Slow first time. But we'll save a template which will make future runs faster.
echo "\nInstalling dependencies into base sandbox..."
docker sandbox exec kiln_base_sandbox bash -c "cd $PWD && uv sync"
docker sandbox exec kiln_base_sandbox bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && npm i"

echo "\nSaving template with deps..."
docker sandbox save kiln_base_sandbox kiln_deps_installed_template

CURRENT_DIR_NAME="$(basename "$PWD")"
SANDBOX_NAME="claude-$CURRENT_DIR_NAME"

echo "\nCreating sandbox $SANDBOX_NAME..."
docker sandbox create -t kiln_deps_installed_template --name "$SANDBOX_NAME" claude .

echo "\nInstalling dependencies into sandbox..."
docker sandbox exec "$SANDBOX_NAME" bash -c "cd $PWD && uv sync"
docker sandbox exec "$SANDBOX_NAME" bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && npm i"

echo "\nDone. Sandbox name: $SANDBOX_NAME\n"
echo "To run agent: docker sandbox run $SANDBOX_NAME"
echo "To use bash: docker sandbox exec -it $SANDBOX_NAME bash -c \"cd $PWD && exec bash\""
echo "To delete sandbox: docker sandbox rm $SANDBOX_NAME"
