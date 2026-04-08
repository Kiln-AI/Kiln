#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RESTART=false
if [ "${1:-}" = "--restart" ] || [ "${1:-}" = "-r" ]; then
    RESTART=true
    shift
fi

BRANCH="${1:-$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "main")}"
SESSION_NAME="${BRANCH//\//-}"

hash_port() {
    printf '%s' "$1" | cksum | awk '{print ($1 % 10000) + 10000}'
}
PORT=$(hash_port "$BRANCH")

export KILN_PORT="$PORT"
export KILN_FRONTEND_PORT="$((PORT + 1))"
export VITE_API_PORT="$PORT"
export VITE_BRANCH_NAME="$BRANCH"

export KILN_WEB_URL="http://localhost:$KILN_FRONTEND_PORT"

export KILN_CODER_CMD="claude"
if [ -f "$REPO_ROOT/.config/wt/user_settings.sh" ]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.config/wt/user_settings.sh"
fi

export PATH="$REPO_ROOT/.config/wt/bin:$PATH"

printf '\e]0;FEAT: %s\a' "$BRANCH"

cd "$REPO_ROOT"

LAYOUT="$REPO_ROOT/.config/wt/layout.user.kdl"
if [ ! -f "$LAYOUT" ]; then
    LAYOUT="$REPO_ROOT/.config/wt/layout.kdl"
fi

SESSION_STATUS=$(zellij list-sessions --no-formatting 2>/dev/null \
    | awk -v name="$SESSION_NAME" '{ n=$1; gsub(/[[:space:]]/, "", n); if (n == name) { print (/EXITED/ ? "exited" : "active"); exit } }') || true

if $RESTART; then
    zellij kill-session "$SESSION_NAME" 2>/dev/null || true
    zellij delete-session "$SESSION_NAME" 2>/dev/null || true
    exec zellij -s "$SESSION_NAME" -n "$LAYOUT"
fi

if [ -n "$SESSION_STATUS" ]; then
    exec zellij attach "$SESSION_NAME"
else
    exec zellij -s "$SESSION_NAME" -n "$LAYOUT"
fi
