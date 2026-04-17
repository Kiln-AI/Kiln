#!/bin/bash
# Setup Claude Code for this worktree

set -e

# Copy AGENTS.md to CLAUDE.md
cp AGENTS.md CLAUDE.md

# Copy skills if they exist
if [ -d ".cursor/skills" ]; then
    mkdir -p .claude
    cp -r .cursor/skills .claude/
fi

# copy .cursor/mcp.json to .mcp.json
if [ -f ".cursor/mcp.json" ]; then
    mkdir -p .claude
    cp .cursor/mcp.json .mcp.json
fi

echo "Claude Code setup complete"
