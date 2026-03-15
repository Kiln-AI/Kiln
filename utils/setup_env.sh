#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
uv sync

cd "$PROJECT_ROOT/app/web_ui"
npm install

echo ""
read -rp "Install Kiln workspaces (worktree-based parallel dev with Zellij)? [y/N] " install_workspaces
if [[ "$install_workspaces" =~ ^[Yy]$ ]]; then
  if ! command -v wt &>/dev/null; then
    echo "Installing worktrunk..."
    brew install worktrunk
    wt config shell install
    echo "  Restart your shell (or open a new tab) for 'wt' completions to take effect."
  else
    echo "  worktrunk already installed."
  fi

  if ! command -v zellij &>/dev/null; then
    echo "Installing zellij..."
    brew install zellij
  else
    echo "  zellij already installed."
  fi

  WT_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/worktrunk"
  WT_CONFIG="$WT_CONFIG_DIR/config.toml"
  WT_PROJECT_CONFIG="$PROJECT_ROOT/.config/wt/config.toml"
  if [ ! -e "$WT_CONFIG" ] && [ -f "$WT_PROJECT_CONFIG" ]; then
    mkdir -p "$WT_CONFIG_DIR"
    ln -sf "$WT_PROJECT_CONFIG" "$WT_CONFIG"
    echo "  Linked worktrunk config: $WT_CONFIG -> $WT_PROJECT_CONFIG"
  else
    echo "  Worktrunk config already present."
  fi

  echo "Workspaces ready! See .config/wt/README.md for usage."
fi

