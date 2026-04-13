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

echo "Claude Code setup complete"
