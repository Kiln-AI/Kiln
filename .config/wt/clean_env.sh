#!/usr/bin/env bash
set -e

echo "Cleaning environment..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/user_settings.sh" ]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/user_settings.sh"
fi

if [ "${USE_DOCKER_SANDBOX:-}" = "true" ]; then
    # shellcheck source=sandbox_name.sh
    source "$SCRIPT_DIR/../../utils/docker_sandboxes/sandbox_name.sh"
    SANDBOX_NAME="$(kiln_claude_sandbox_name)"
    echo "Cleaning Docker Sandbox $SANDBOX_NAME..."
    docker sandbox rm "$SANDBOX_NAME" 2>/dev/null || true
else
    echo "Nothing to clean in non-Docker Sandbox..."
fi