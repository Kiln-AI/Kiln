#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

BRANCH="${1:-$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "main")}"
SESSION_NAME="${BRANCH//\//-}"

hash_port() {
    printf '%s' "$1" | cksum | awk '{print ($1 % 10000) + 10000}'
}
PORT=$(hash_port "$BRANCH")

export KILN_PORT="$PORT"
export KILN_FRONTEND_PORT="$((PORT + 1))"
export VITE_API_PORT="$PORT"

export KILN_WEB_URL="http://localhost:$KILN_FRONTEND_PORT"

export KILN_CODER_CMD="claude"
if [ -f "$REPO_ROOT/.config/wt/user_settings.sh" ]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.config/wt/user_settings.sh"
fi

export PATH="$REPO_ROOT/.config/wt/bin:$PATH"

printf '\e]0;FEAT: %s\a' "$BRANCH"

cd "$REPO_ROOT"

LAYOUT="$REPO_ROOT/.config/wt/layout.kdl"

# Kill any cached/serialized session so we always get a fresh layout
zellij delete-session "$SESSION_NAME" 2>/dev/null || true

exec zellij -s "$SESSION_NAME" -n "$LAYOUT"
