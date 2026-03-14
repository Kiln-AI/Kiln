#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
uv sync

cd "$PROJECT_ROOT/app/web_ui"
npm install

# Setup worktrunk config
WT_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/worktrunk"
WT_CONFIG="$WT_CONFIG_DIR/config.toml"
WT_PROJECT_CONFIG="$PROJECT_ROOT/.config/wt/config.toml"
if [ ! -e "$WT_CONFIG" ] && [ -f "$WT_PROJECT_CONFIG" ]; then
  mkdir -p "$WT_CONFIG_DIR"
  ln -sf "$WT_PROJECT_CONFIG" "$WT_CONFIG"
  echo "Linked worktrunk config: $WT_CONFIG -> $WT_PROJECT_CONFIG"
fi

