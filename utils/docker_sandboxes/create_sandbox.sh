#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR/../../..")"
cd "$REPO_ROOT"

CURRENT_DIR_NAME="$(basename "$PWD")"
SANDBOX_NAME="claude-$CURRENT_DIR_NAME"

for arg in "$@"; do
  if [[ "$arg" == "--rebuild-all" ]]; then
    echo "Removing sandboxes and template images (--rebuild-all)..."
    docker sandbox rm kiln_base_sandbox 2>/dev/null || true
    docker sandbox rm "$SANDBOX_NAME" 2>/dev/null || true
    docker rmi -f kiln_sandbox_base_template:latest 2>/dev/null || true
    docker rmi -f kiln_deps_installed_template:latest 2>/dev/null || true
    break
  fi
  if [[ "$arg" == "--rebuild" ]]; then
    echo "Removing only the sandbox ($SANDBOX_NAME) (--rebuild)..."
    docker sandbox rm "$SANDBOX_NAME" 2>/dev/null || true
    break
  fi
done

if docker image inspect kiln_deps_installed_template:latest &>/dev/null; then 
  echo "Kiln template already exists. Will not rebuild. Call with --rebuild-all to rebuild templates." 
else 
  echo "Building sandbox template. Slow but one-time task."

  # Base template: just dockerfile, no deps
  if docker image inspect kiln_sandbox_base_template:latest &>/dev/null; then
    echo "Sandbox base template image already exists. Skipping docker build. Call with --rebuild-all to rebuild templates."
  else
    echo "Building sandbox base template image..."
    docker build -t kiln_sandbox_base_template -f utils/docker_sandboxes/DockerfileClaude utils/docker_sandboxes
  fi

  echo "Creating base sandbox instance..."
  docker sandbox create -t kiln_sandbox_base_template --name kiln_base_sandbox claude .

  echo "Installing dependencies into base sandbox..."
  docker sandbox exec kiln_base_sandbox bash -c "cd $PWD && uv sync"
  docker sandbox exec kiln_base_sandbox bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && npm i"

  echo "Saving template with deps..."
  docker sandbox save kiln_base_sandbox kiln_deps_installed_template
fi

if docker sandbox ls --json 2>/dev/null | jq -e --arg name "$SANDBOX_NAME" '(.vms // []) | any(.[]; .name == $name)' >/dev/null 2>&1; then
  echo "Sandbox $SANDBOX_NAME already exists. Will not recreate it unless you use --rebuild or --rebuild-all."
else
  echo "Creating sandbox $SANDBOX_NAME..."
  docker sandbox create -t kiln_deps_installed_template --name "$SANDBOX_NAME" claude .

  echo "Installing dependencies into sandbox..."
  docker sandbox exec "$SANDBOX_NAME" bash -c "cd $PWD && uv sync"
  docker sandbox exec "$SANDBOX_NAME" bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && npm i"
  echo "Created sandbox named $SANDBOX_NAME with dependencies installed."
fi

echo "To run agent: docker sandbox run $SANDBOX_NAME"
echo "To use bash: docker sandbox exec -it $SANDBOX_NAME bash -c \"cd $PWD && exec bash\""
echo "To delete sandbox: docker sandbox rm $SANDBOX_NAME"
