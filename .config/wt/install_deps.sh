#!/usr/bin/env bash
set -e

echo "Installing dependencies..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/user_settings.sh" ]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/user_settings.sh"
fi

if [ "${USE_DOCKER_SANDBOX:-}" = "true" ]; then
    echo "Skipping uv sync and npm install (USE_DOCKER_SANDBOX=true)."
    echo "Creating Docker Sandbox..."
    utils/docker_sandboxes/create_sandbox.sh
else
    uv sync
    cd app/web_ui && npm install && cd ../..
fi