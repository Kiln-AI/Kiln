#!/usr/bin/env bash
# Sourceable env setup for wk workspace windows.
# Sets ports, env vars, and PATH for the current worktree.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../.." && pwd))"

BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null)"
[ -n "$BRANCH" ] || BRANCH="main"

hash_port() {
    printf '%s' "$1" | cksum | awk '{print ($1 % 10000) + 10000}'
}

if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    export KILN_PORT=8757
    export KILN_FRONTEND_PORT=5173
else
    PORT=$(hash_port "$BRANCH")
    export KILN_PORT="$PORT"
    export KILN_FRONTEND_PORT="$((PORT + 1))"
fi
export VITE_API_PORT="$KILN_PORT"
export VITE_BRANCH_NAME="$BRANCH"
export KILN_WEB_URL="http://localhost:$KILN_FRONTEND_PORT"
export KILN_CODER_CMD="claude"

if [ -f "$REPO_ROOT/.config/wt/user_settings.sh" ]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.config/wt/user_settings.sh"
fi

export WK_BIN_DIR="$REPO_ROOT/.config/wt/bin"
[[ ":$PATH:" != *":$WK_BIN_DIR:"* ]] && export PATH="$WK_BIN_DIR:$PATH"
