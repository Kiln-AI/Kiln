#!/bin/bash
# Setup Cursor for this worktree

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Copy skills from the canonical .agents/skills/ location
if [ -d ".agents/skills" ]; then
    mkdir -p .cursor
    rm -rf .cursor/skills
    cp -r .agents/skills .cursor/skills
fi

echo "Cursor setup complete"
