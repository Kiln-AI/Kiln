#!/usr/bin/env bash
# Build (or repair) a development environment for Kiln.
#
# This file doubles as the setup script for a Claude Code cloud environment:
# paste its contents into the environment's "Setup script" field and edit only
# the CONFIGURATION block below. Nothing outside that block needs to change.
#
# In that context the script does not live inside a checkout, and there may be no
# Kiln checkout on disk at all: the setup script runs once per environment, is
# then snapshotted, and is shared across every repo using the environment. So the
# project root is discovered rather than derived from this file's own path, and
# the repo-specific steps are skipped with a notice when there is nothing to
# apply them to.

# `set -o pipefail` is not POSIX. If a runner ignores the shebang and starts this
# with `sh`, the shell would die on the next line — before --best-effort could
# suppress the exit code, which as a cloud setup script means the session never
# starts. Re-exec under bash first.
if [ -z "${BASH_VERSION:-}" ]; then
  if [ -r "$0" ]; then
    exec bash "$0" "$@"
  fi
  echo "error: setup_env.sh requires bash. Re-run it as: bash setup_env.sh" >&2
  exit 1
fi

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
PYTHON_PIN=3.13     # what .python-version gets pinned to; sync with setup_startup.sh
PYTHON_MIN_MINOR=13 # the 3.x floor an existing pin is kept at or above

# ── Project root discovery ────────────────────────────────────────────────────
# Deriving the root from ${BASH_SOURCE[0]} only works when this file is running
# from the checkout. Pasted into a cloud setup field it is somewhere else
# entirely, and BASH_SOURCE is unset outright when the body is fed on stdin, so
# every candidate is validated before it is used.
is_kiln_root() {
  [ -n "$1" ] && [ -f "$1/pyproject.toml" ] && [ -d "$1/libs/core/kiln_ai" ]
}

find_kiln_root() {
  local candidate

  # The checkout this file lives in, when it is running from one.
  candidate="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)"
  is_kiln_root "$candidate" && {
    echo "$candidate"
    return 0
  }

  # The checkout we are standing in.
  candidate="$(git rev-parse --show-toplevel 2>/dev/null)"
  is_kiln_root "$candidate" && {
    echo "$candidate"
    return 0
  }

  # Or walk up from the working directory.
  candidate="$PWD"
  while :; do
    is_kiln_root "$candidate" && {
      echo "$candidate"
      return 0
    }
    [ "$candidate" = "/" ] && return 1
    candidate="$(dirname "$candidate")"
  done
}

PROJECT_ROOT="$(find_kiln_root)" || PROJECT_ROOT=""

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
  *) echo "error: --agent must be one of: all, claude, cursor, none" >&2; usage >&2; exit 2 ;;
esac

FAILED=0
fail() {
  echo "error: $*" >&2
  FAILED=1
}

finish() {
  # $1 = the closing line for a clean run; the default assumes everything ran.
  if [ "$FAILED" -ne 0 ]; then
    if [ "$BEST_EFFORT" = true ]; then
      echo "setup_env.sh: finished with errors (best effort, exiting 0)." >&2
      exit 0
    fi
    exit 1
  fi
  echo "${1:-Environment setup complete.}"
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
  if ! uv tool install --force uv; then
    fail "failed to upgrade uv"
    return 1
  fi

  # The shell has already hashed the old uv from the version check above, and the
  # new binary usually lands at a different path (~/.local/bin/uv). Without this,
  # the rest of the run would keep calling the uv we just replaced.
  hash -r
  UV_VERSION="$(uv_version)"
  if uv_too_old "$UV_VERSION"; then
    fail "uv is still ${UV_VERSION:-(not installed)} after the upgrade; the new binary is probably shadowed on PATH"
    return 1
  fi
  echo "uv is now $UV_VERSION."
}

# "uv is absent" and "uv is too old" are different problems with different fixes:
# every repair below runs uv, so none of them can help when uv is missing. Say so
# once and stop, rather than warning about a version that does not exist and then
# offering an upgrade that cannot run.
if ! command -v uv >/dev/null 2>&1; then
  fail "uv is not installed. Install it: https://docs.astral.sh/uv/getting-started/installation/"
  finish
fi

UV_VERSION="$(uv_version)"
if uv_too_old "$UV_VERSION"; then
  if [ "$UPGRADE_TOOLS" = true ]; then
    upgrade_uv
  elif [ -t 0 ]; then
    answer=""
    read -t 10 -rp \
      "uv ${UV_VERSION:-(unknown version)} is older than $UV_MIN. Upgrade? [Y/n] " \
      answer || true
    echo ""
    case "$answer" in
      [Nn]*) echo "Skipping. Expect uv.lock churn and broken imports." ;;
      *) upgrade_uv ;;
    esac
  else
    echo "warning: uv ${UV_VERSION:-(unknown version)} is older than $UV_MIN." >&2
    echo "         Re-run with --upgrade-tools, or: uv tool install --force uv" >&2
  fi
fi

# Re-read after any upgrade attempt, so the sync failure below can tell "you
# edited a pyproject.toml" apart from "required-version refused your uv".
UV_VERSION="$(uv_version)"
UV_BELOW_MIN=false
uv_too_old "$UV_VERSION" && UV_BELOW_MIN=true

# ── Python ────────────────────────────────────────────────────────────────────
# The system Python on many sandbox images has no tkinter, which breaks several
# test modules and both OpenAPI schema scripts. uv-managed CPython bundles Tk.
# Installing the interpreter is not repo-specific, so it happens either way — it
# is exactly the kind of work worth baking into an environment snapshot.
if ! uv python install "$PYTHON_PIN"; then
  fail "could not install Python $PYTHON_PIN"
  finish
fi

# ── Everything below here needs a checkout ────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  echo "No Kiln checkout found, so dependency install and agent configuration"
  echo "were skipped."
  if [ "$FAILED" -ne 0 ]; then
    # This is the one line a cloud operator reads in the setup log; do not claim
    # the tools are ready when a step above just failed.
    echo "Resolve the errors above, then run .config/utils/setup_startup.sh"
    echo "from a checkout to finish setup."
  else
    echo "uv and Python $PYTHON_PIN are ready; run"
    echo ".config/utils/setup_startup.sh from a checkout to finish setup."
  fi
  finish "Environment tools ready. Repo-specific setup was skipped."
fi

# .python-version (gitignored) is what makes the choice survive deleting .venv:
# uv consults it on every later sync.
#
# Same floor rule as setup_startup.sh — keep the two in sync. A pin at or above
# PYTHON_MIN_MINOR is a deliberate choice (3.13.1 is what pyenv writes), and this
# script is the one CONTRIBUTING.md sends people to for ordinary setup, so it must
# not quietly reset it and trigger a venv rebuild on their next sync.
pinned="$(cat "$PROJECT_ROOT/.python-version" 2>/dev/null)"
IFS=. read -r pin_major pin_minor _ <<<"$pinned"
if ! [[ "${pin_major:-}" =~ ^[0-9]+$ ]] ||
  ! [[ "${pin_minor:-}" =~ ^[0-9]+$ ]] ||
  [ "$pin_major" -lt 3 ] ||
  { [ "$pin_major" -eq 3 ] && [ "$pin_minor" -lt "$PYTHON_MIN_MINOR" ]; }; then
  echo "$PYTHON_PIN" >"$PROJECT_ROOT/.python-version" || fail "could not write .python-version"
fi

# ── Dependencies ──────────────────────────────────────────────────────────────
# Run both installs in parallel in the foreground. npm dominates, so this is a
# meaningful win. Not backgrounded past this point: `npm ci` empties node_modules
# before repopulating it, and an agent working during that window would hit
# phantom import errors.
(cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) &
py_pid=$!
# --no-fund --no-audit to match setup_startup.sh, and because the funding block and
# the audit's vulnerability tally read like failures to anyone scanning a cloud
# setup log. Neither affects what gets installed.
(cd "$PROJECT_ROOT/app/web_ui" && npm ci --no-fund --no-audit) &
npm_pid=$!

py_status=0
wait "$py_pid" || py_status=$?
npm_status=0
wait "$npm_pid" || npm_status=$?

if [ "$py_status" -ne 0 ]; then
  if [ "$UV_BELOW_MIN" = true ]; then
    fail "uv sync failed (exit $py_status). uv ${UV_VERSION:-(not installed)} is below $UV_MIN, which required-version refuses: uv tool install --force uv"
  else
    fail "uv sync failed (exit $py_status). If you changed dependencies, run: uv lock"
  fi
fi
if [ "$npm_status" -ne 0 ]; then
  fail "npm ci failed (exit $npm_status)"
fi

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
    # This block predates the rewrite, when the script ran under `set -e` and the
    # first failure aborted it. There is no `set -e` now — --best-effort has to own
    # the exit code — so each install routes its failure through `fail` instead.
    # workspace_failed tracks just this section: an earlier unrelated failure (a
    # flaky npm ci, say) must not suppress a workspace summary that is true.
    workspace_failed=0
    workspace_fail() {
      fail "$*"
      workspace_failed=1
    }

    if ! command -v wt &>/dev/null; then
      echo "Installing worktrunk..."
      if brew install worktrunk; then
        wt config shell install || workspace_fail "wt config shell install failed"
        echo "  Restart your shell (or open a new tab) for 'wt' completions to take effect."
      else
        workspace_fail "brew install worktrunk failed"
      fi
    else
      echo "  worktrunk already installed."
    fi

    if ! command -v zellij &>/dev/null; then
      echo "Installing zellij..."
      brew install zellij || workspace_fail "brew install zellij failed"
    else
      echo "  zellij already installed."
    fi

    if ! command -v wk &>/dev/null; then
      echo "Installing worktree TUI..."
      uv tool install "git+https://github.com/scosman/worktree_tui" ||
        workspace_fail "could not install the worktree TUI"
    else
      echo "  worktree TUI already installed."
    fi

    WT_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/worktrunk"
    WT_CONFIG="$WT_CONFIG_DIR/config.toml"
    WT_PROJECT_CONFIG="$PROJECT_ROOT/.config/wt/config.toml"
    if [ ! -e "$WT_CONFIG" ] && [ -f "$WT_PROJECT_CONFIG" ]; then
      if mkdir -p "$WT_CONFIG_DIR" && ln -sf "$WT_PROJECT_CONFIG" "$WT_CONFIG"; then
        echo "  Linked worktrunk config: $WT_CONFIG -> $WT_PROJECT_CONFIG"
      else
        workspace_fail "could not link the worktrunk config into $WT_CONFIG_DIR"
      fi
    else
      echo "  Worktrunk config already present."
    fi

    if [ "$workspace_failed" -eq 0 ]; then
      echo "Workspaces ready! See .config/wt/README.md for usage."
    fi
  fi
fi

finish
