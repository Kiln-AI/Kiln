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
# For a Claude Code cloud setup script use:
#   UPGRADE_TOOLS=true BEST_EFFORT=true WARM_CACHE=true
HUMAN_MODE=false    # true: also offer the worktrunk/Zellij workspace tools
UPGRADE_TOOLS=false # true: upgrade uv without asking when it is too old
AGENT=all           # all | claude | cursor | none
BEST_EFFORT=false   # true: never exit non-zero (required for cloud setup scripts)
WARM_CACHE=false    # true: warm the machine's caches from a throwaway clone (cloud VMs)
# ──────────────────────────────────────────────────────────────────────────────

UV_MIN=0.10.0
PYTHON_PIN=3.13     # what .python-version gets pinned to; sync with setup_startup.sh
PYTHON_MIN_MINOR=13 # the 3.x floor an existing pin is kept at or above

# Where this script records that it provisioned the machine, and where it parks
# the warm node_modules tree. Both live outside any checkout so they survive into
# a VM snapshot; setup_startup.sh reads both and must use the same paths.
#
# The _v1 in the marker name is a contract version, not decoration: when what this
# script provides changes incompatibly, bump it, so machines provisioned by the
# older script are correctly reported as not set up rather than as ready.
#
# The two overrides exist so the behavior can be exercised without writing to /opt
# or cloning over the network.
VM_SETUP_DIR="${KILN_VM_SETUP_DIR:-/opt/kiln-vm-setup}"
VM_SETUP_MARKER="$VM_SETUP_DIR/.setup_for_kiln_repo_v1"
WARM_NODE_MODULES="$VM_SETUP_DIR/node_modules"
KILN_REPO_URL="${KILN_REPO_URL:-https://github.com/Kiln-AI/Kiln.git}"

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
  --warm-cache        When there is no checkout, clone Kiln to a throwaway directory
                      and sync it, to warm this machine's uv and npm caches and keep
                      a pristine node_modules for later sessions. For cloud VMs whose
                      disk is snapshotted after setup; a no-op with a checkout.
  -h, --help          Show this help.

The Python sync uses --frozen, so run `uv lock` first if you changed dependencies.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --human) HUMAN_MODE=true ;;
    --upgrade-tools) UPGRADE_TOOLS=true ;;
    --best-effort) BEST_EFFORT=true ;;
    --warm-cache) WARM_CACHE=true ;;
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

# ── Warm this machine's caches ────────────────────────────────────────────────
# A cloud VM runs this script once, then snapshots the disk, so anything cached
# here is free for every later session. Without it a fresh session downloads ~300
# MB of wheels, fetches a git dependency and builds an sdist before it can run a
# test: measured 14.67 s of `uv sync`, against 428 ms once the cache is warm.
#
# npm is the reason a warm ~/.npm is not enough on the Node side. uv hardlinks out
# of its cache; npm copies, so filling an empty node_modules still costs ~21 s of
# the 24 s it took cold. So the tree itself is kept, outside any checkout, and
# setup_startup.sh hardlinks it into the session's checkout in ~0.5 s.
#
# Only with no checkout, which is the cloud environment-build case. With a
# checkout the sync below warms the same caches against the code actually in hand,
# and copying that checkout's node_modules — mid-branch, possibly patched — into a
# machine-global tree would be seeding later sessions from an unknown state.
WARM_TREE_CREATED=false
WARM_TREE_COMMIT=""

# Failures here are warnings, not `fail`s. This is an optimization: the machine is
# still usable without it, and marking the run failed would flip the closing line
# to "Resolve the errors above" for a VM whose uv and Python are fine. Everything
# that actually has to be true is re-checked per session by setup_startup.sh.
warm_from_throwaway_clone() {
  local clone py_status npm_status py_pid npm_pid

  if ! mkdir -p "$VM_SETUP_DIR"; then
    echo "warning: warm cache: could not create $VM_SETUP_DIR; skipping" >&2
    return 1
  fi

  # Clone inside VM_SETUP_DIR so the node_modules move below is a rename on one
  # device rather than a 600 MB copy across two.
  clone="$VM_SETUP_DIR/throwaway-clone"
  rm -rf "$clone"

  echo "Warming caches from a throwaway clone of $KILN_REPO_URL..."
  if ! git clone --depth 1 "$KILN_REPO_URL" "$clone"; then
    echo "warning: warm cache: could not clone $KILN_REPO_URL; skipping" >&2
    rm -rf "$clone"
    return 1
  fi
  WARM_TREE_COMMIT="$(git -C "$clone" rev-parse HEAD 2>/dev/null)"

  # Before the sync, so the cached wheels are the ones a session on this snapshot
  # will actually use. Without the pin uv builds the clone's .venv on the system
  # Python and caches a different interpreter's wheels — so a failed write here is
  # not cosmetic, it warms the cache for the wrong interpreter.
  if ! echo "$PYTHON_PIN" >"$clone/.python-version"; then
    echo "warning: warm cache: could not pin Python in the throwaway clone;" >&2
    echo "         skipping rather than caching wheels for the system Python" >&2
    rm -rf "$clone"
    return 1
  fi

  (cd "$clone" && uv sync --frozen --all-packages) &
  py_pid=$!
  (cd "$clone/app/web_ui" && npm ci --no-fund --no-audit) &
  npm_pid=$!

  py_status=0
  wait "$py_pid" || py_status=$?
  npm_status=0
  wait "$npm_pid" || npm_status=$?

  [ "$py_status" -ne 0 ] &&
    echo "warning: warm cache: uv sync in the throwaway clone failed (exit $py_status); the uv cache may be cold" >&2

  if [ "$npm_status" -ne 0 ] || [ ! -d "$clone/app/web_ui/node_modules" ]; then
    echo "warning: warm cache: npm ci in the throwaway clone failed (exit $npm_status); no warm node_modules was kept" >&2
    rm -rf "$clone"
    return 1
  fi

  rm -rf "$WARM_NODE_MODULES"
  if ! mv "$clone/app/web_ui/node_modules" "$WARM_NODE_MODULES"; then
    echo "warning: warm cache: could not move node_modules to $WARM_NODE_MODULES" >&2
    rm -rf "$clone"
    return 1
  fi

  rm -rf "$clone"
  echo "Warm node_modules kept at $WARM_NODE_MODULES."
}

# The marker is how setup_startup.sh tells a machine this script provisioned from
# one that never ran it — and so whether the warm tree beside it has known
# provenance. Its contents are for a human reading a broken VM, not for parsing.
previous_marker_value() {
  # $1 = key. Empty when the marker is absent or does not carry that key.
  [ -f "$VM_SETUP_MARKER" ] || return 0
  sed -n "s/^$1=//p" "$VM_SETUP_MARKER" 2>/dev/null | tail -1
}

write_vm_setup_marker() {
  if ! mkdir -p "$VM_SETUP_DIR"; then
    echo "note: could not create $VM_SETUP_DIR, so no provisioning marker was" >&2
    echo "      written. That only matters on a VM whose disk is snapshotted." >&2
    return 0
  fi

  # Describe the tree that is on disk now, not what this particular run did. The
  # two come apart on a re-run: `setup_env.sh --upgrade-tools` is what AGENTS.md
  # tells an agent to run to repair an environment, it carries no --warm-cache, and
  # the warm tree it does not touch outlives it. A marker rewritten as
  # "created=false, commit=none" would then be lying about the provenance of the
  # 601 MB every session on this machine inherits — the one fact it exists to
  # record. So carry the previous commit forward whenever the tree survives.
  local tree_present=false tree_commit=none
  [ -d "$WARM_NODE_MODULES" ] && tree_present=true

  if [ "$WARM_TREE_CREATED" = true ]; then
    tree_commit="${WARM_TREE_COMMIT:-unknown}"
  elif [ "$tree_present" = true ]; then
    tree_commit="$(previous_marker_value warm_node_modules_commit)"
    # A tree with no marker to explain it: present, provenance unrecoverable.
    tree_commit="${tree_commit:-unknown}"
  fi

  # Write beside the marker and rename over it. A redirect onto the marker itself
  # truncates before it writes, so a failed write would leave a zero-byte file —
  # and setup_startup.sh only tests that the marker exists. That would turn the one
  # check standing between a session and an unattributable 601 MB tree into a false
  # positive, with every field it reads back empty from then on.
  local staged_marker="$VM_SETUP_MARKER.$$"
  if ! cat >"$staged_marker" <<EOF
# Written by .config/utils/setup_env.sh. Its presence means this machine was
# provisioned for the Kiln repo. Delete it to force setup to be re-run.
setup_version=1
written_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
uv_version=${UV_VERSION:-unknown}
python_pin=$PYTHON_PIN
warm_node_modules=$WARM_NODE_MODULES
warm_node_modules_present=$tree_present
warm_node_modules_commit=$tree_commit
warm_node_modules_created_this_run=$WARM_TREE_CREATED
EOF
  then
    rm -f "$staged_marker"
    echo "note: could not write $VM_SETUP_MARKER; the previous marker, if any," >&2
    echo "      was left as it was." >&2
    return 0
  fi

  mv -f "$staged_marker" "$VM_SETUP_MARKER" ||
    echo "note: could not move the new marker into $VM_SETUP_MARKER." >&2
}

if [ "$WARM_CACHE" = true ]; then
  if [ -n "$PROJECT_ROOT" ]; then
    echo "Warm cache requested, but this run has a checkout at $PROJECT_ROOT;"
    echo "the sync below warms the same caches, so no throwaway clone was made."
  elif warm_from_throwaway_clone; then
    WARM_TREE_CREATED=true
  fi
fi

write_vm_setup_marker

# ── Everything below here needs a checkout ────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  echo "No Kiln checkout found, so dependency install and agent configuration"
  echo "were skipped."
  # Two readers land here. On a cloud VM this is the setup log, and the next step
  # is setup_startup.sh in the session's checkout. Locally it is someone who ran
  # this from the wrong directory — and setup_startup.sh would tell them only that
  # they are not in a container, so pointing them there would be a dead end.
  if [ "$FAILED" -ne 0 ]; then
    # Do not claim the tools are ready when a step above just failed.
    echo "Resolve the errors above, then finish setup from inside a checkout:"
  else
    echo "uv and Python $PYTHON_PIN are ready. To finish setup, from a checkout:"
  fi
  echo "  in a container or cloud sandbox: .config/utils/setup_startup.sh"
  echo "  on a development machine:        .config/utils/setup_env.sh"
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
