#!/usr/bin/env bash
# Build (or repair) a development environment for Kiln.
#
# This file doubles as the setup script for a Claude Code cloud environment:
# paste its contents into the environment's "Setup script" field and edit only
# the CONFIGURATION block below. Nothing outside that block needs to change.

set -uo pipefail

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Defaults for a local run. Command line flags override them.
# For a Claude Code cloud setup script use: UPGRADE_TOOLS=true BEST_EFFORT=true
HUMAN_MODE=false    # true: also offer the worktrunk/Zellij workspace tools
UPGRADE_TOOLS=false # true: upgrade uv without asking when it is too old
AGENT=all           # all | claude | cursor | none
BEST_EFFORT=false   # true: never exit non-zero (required for cloud setup scripts)
# ──────────────────────────────────────────────────────────────────────────────

UV_MIN=0.10.0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: setup_env.sh [options]

  --human             Also offer the worktrunk/Zellij workspace tools (interactive).
  --upgrade-tools     Upgrade uv without asking when it is older than the minimum.
  --agent <name>      Which agent configs to write: all|claude|cursor|none (default all).
  --best-effort       Never exit non-zero. Required when used as a cloud setup script,
                      where a non-zero exit stops the session from starting.
  -h, --help          Show this help.

The Python sync uses --frozen, so run `uv lock` first if you changed dependencies.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --human) HUMAN_MODE=true ;;
    --upgrade-tools) UPGRADE_TOOLS=true ;;
    --best-effort) BEST_EFFORT=true ;;
    --agent) AGENT="${2:-}"; shift ;;
    --agent=*) AGENT="${1#*=}" ;;
    -h | --help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$AGENT" in
  all | claude | cursor | none) ;;
  *) echo "error: --agent must be one of: all, claude, cursor, none" >&2; exit 2 ;;
esac

FAILED=0
fail() {
  echo "error: $*" >&2
  FAILED=1
}

finish() {
  if [ "$FAILED" -ne 0 ]; then
    if [ "$BEST_EFFORT" = true ]; then
      echo "setup_env.sh: finished with errors (best effort, exiting 0)." >&2
      exit 0
    fi
    exit 1
  fi
  echo "Environment setup complete."
  exit 0
}

# ── uv version ────────────────────────────────────────────────────────────────
# uv older than $UV_MIN cannot parse this repo's relative `exclude-newer`. Rather
# than failing, such a uv ignores the setting, re-resolves the whole dependency
# graph and rewrites uv.lock, which installs a broken dependency set.
uv_version() {
  command -v uv >/dev/null 2>&1 || return 0
  uv --version 2>/dev/null | awk '{print $2}'
}

uv_too_old() {
  local current="$1"
  [ -z "$current" ] && return 0
  # True when $UV_MIN does not sort first, i.e. $current is below the minimum.
  [ "$(printf '%s\n%s\n' "$UV_MIN" "$current" | sort -V | head -1)" != "$UV_MIN" ]
}

upgrade_uv() {
  # `uv self update` resolves releases through the GitHub API, whose rate limit is
  # per egress IP and is routinely exhausted on shared sandbox IPs. --force is
  # required or uv refuses with "Executables already exist".
  echo "Upgrading uv..."
  uv tool install --force uv || fail "failed to upgrade uv"
}

UV_VERSION="$(uv_version)"
if uv_too_old "$UV_VERSION"; then
  if [ "$UPGRADE_TOOLS" = true ]; then
    upgrade_uv
  elif [ -t 0 ]; then
    answer=""
    read -t 10 -rp \
      "uv ${UV_VERSION:-(not installed)} is older than $UV_MIN. Upgrade? [Y/n] " \
      answer || true
    echo ""
    case "$answer" in
      [Nn]*) echo "Skipping. Expect uv.lock churn and broken imports." ;;
      *) upgrade_uv ;;
    esac
  else
    echo "warning: uv ${UV_VERSION:-(not installed)} is older than $UV_MIN." >&2
    echo "         Re-run with --upgrade-tools, or: uv tool install --force uv" >&2
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  fail "uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/"
  finish
fi

# ── Python ────────────────────────────────────────────────────────────────────
# The system Python on many sandbox images has no tkinter, which breaks several
# test modules and both OpenAPI schema scripts. uv-managed CPython bundles Tk.
# .python-version (gitignored) is what makes the choice survive deleting .venv.
if uv python install 3.13; then
  echo "3.13" >"$PROJECT_ROOT/.python-version" || fail "could not write .python-version"
else
  fail "could not install Python 3.13"
  finish
fi

# ── Dependencies ──────────────────────────────────────────────────────────────
# Run both installs in parallel in the foreground. npm dominates, so this is a
# meaningful win. Not backgrounded past this point: `npm ci` empties node_modules
# before repopulating it, and an agent working during that window would hit
# phantom import errors.
(cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) &
py_pid=$!
(cd "$PROJECT_ROOT/app/web_ui" && npm ci) &
npm_pid=$!

py_status=0
wait "$py_pid" || py_status=$?
npm_status=0
wait "$npm_pid" || npm_status=$?

[ "$py_status" -ne 0 ] &&
  fail "uv sync failed (exit $py_status). If you changed dependencies, run: uv lock"
[ "$npm_status" -ne 0 ] && fail "npm ci failed (exit $npm_status)"

# ── Agent configuration ───────────────────────────────────────────────────────
# Everything these scripts write is gitignored, they emit identical .mcp.json and
# .worktreeinclude, and the whole copy is small and offline, so `all` is the
# default rather than privileging one editor.
run_agent_setup() {
  local script=".agents/$1/setup.sh"
  if [ -f "$PROJECT_ROOT/$script" ]; then
    bash "$PROJECT_ROOT/$script" || fail "$script failed"
  else
    echo "warning: $script not found, skipping" >&2
  fi
}

case "$AGENT" in
  all) run_agent_setup claude; run_agent_setup cursor ;;
  claude) run_agent_setup claude ;;
  cursor) run_agent_setup cursor ;;
  none) ;;
esac

# ── Optional workspace tooling ────────────────────────────────────────────────
if [ "$HUMAN_MODE" != true ]; then
  finish
fi

echo ""
read -rp "Install Kiln workspaces (worktree-based parallel dev with Zellij)? [y/N] " install_workspaces
if [[ "$install_workspaces" =~ ^[Yy]$ ]]; then
  if ! command -v brew &>/dev/null; then
    echo "Warning: Homebrew (brew) is not installed. Skipping workspace setup."
    echo "  Install it from https://brew.sh and re-run this script."
  else
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

    if ! command -v wk &>/dev/null; then
      echo "Installing worktree TUI..."
      uv tool install "git+https://github.com/scosman/worktree_tui"
    else
      echo "  worktree TUI already installed."
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
fi

finish
