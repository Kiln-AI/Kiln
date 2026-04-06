#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=sandbox_name.sh
source "$SCRIPT_DIR/sandbox_name.sh"
REPO_ROOT="$(dirname "$SCRIPT_DIR/../../..")"
cd "$REPO_ROOT"

SANDBOX_NAME="$(kiln_claude_sandbox_name)"

for arg in "$@"; do
  if [[ "$arg" == "--rebuild" ]]; then
    echo "Removing the sandbox ($SANDBOX_NAME) (--rebuild)..."
    docker sandbox rm "$SANDBOX_NAME" 2>/dev/null || true
    break
  fi
done

kiln_docker_image_exists() {
  [[ -n "${1:-}" ]] || return 1
  docker image ls --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -Fqx "$1"
}

if kiln_docker_image_exists kiln_deps_and_logged_in_template:latest; then
  echo "Kiln template already exists. Continuing..." 
else 
  echo "STEP MISSED - CAN NOT CREATE SANDBOX"
  echo "Run setup agent and login to claude code in UI: docker sandbox run kiln_base_sandbox"
  echo "then run: docker sandbox save kiln_base_sandbox kiln_deps_and_logged_in_template"
  exit 1
fi

if docker sandbox ls --json 2>/dev/null | jq -e --arg name "$SANDBOX_NAME" '(.vms // []) | any(.[]; .name == $name)' >/dev/null 2>&1; then
  echo "Sandbox $SANDBOX_NAME already exists. Will not recreate it unless you use --rebuild"
else
  echo "Creating sandbox $SANDBOX_NAME..."
  docker sandbox create -t kiln_deps_and_logged_in_template --name "$SANDBOX_NAME" claude .

  # As deps may have changed, we still reinstall. It should be much faster as the cache is already built.
  echo "Installing dependencies into sandbox..."
  docker sandbox exec "$SANDBOX_NAME" bash -c "cd $PWD && uv sync"
  docker sandbox exec "$SANDBOX_NAME" bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && npm i"
  echo "Created sandbox named $SANDBOX_NAME with dependencies installed."
fi

echo "To run agent: docker sandbox run $SANDBOX_NAME"
echo "To use bash: docker sandbox exec -it $SANDBOX_NAME bash -c \"cd $PWD && exec bash\""
echo "To delete sandbox: docker sandbox rm $SANDBOX_NAME"
