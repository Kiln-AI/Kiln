#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for arg in "$@"; do
  if [[ "$arg" == "--rebuild" ]]; then
    echo "Removing sandboxes and template images (--rebuild-all)..."
    docker sandbox rm kiln_base_sandbox 2>/dev/null || true
    docker rmi -f kiln_sandbox_base_template:latest 2>/dev/null || true
    docker rmi -f kiln_deps_installed_template:latest 2>/dev/null || true
    break
  fi
done

kiln_docker_image_exists() {
  [[ -n "${1:-}" ]] || return 1
  docker image ls --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -Fqx "$1"
}

if kiln_docker_image_exists kiln_deps_installed_template:latest; then
  echo "Kiln template already exists. Will not rebuild. Call with --rebuild-all to rebuild templates." 
else 
  echo "Building sandbox template. Slow but one-time task."

  # Base template: just dockerfile, no deps
  if kiln_docker_image_exists kiln_sandbox_base_template:latest; then
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
fi


echo "Next run agent and login to claude code in UI: docker sandbox run kiln_base_sandbox"
echo "then run: docker sandbox save kiln_base_sandbox kiln_deps_and_logged_in_template"
