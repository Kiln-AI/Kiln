#!/bin/bash
# Setup Cursor for this worktree

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Copy .worktreeinclude to repo root (worktrunk/Claude Code desktop require it there)
rm -f .worktreeinclude
cp .config/wt/.worktreeinclude .worktreeinclude

# Copy skills from the canonical .agents/skills/ location
if [ -d ".agents/skills" ]; then
    mkdir -p .cursor
    rm -rf .cursor/skills
    cp -r .agents/skills .cursor/skills
fi

# Copy MCP config to root (gitignored)
cp .agents/mcp.json .mcp.json

echo "Cursor setup complete"
