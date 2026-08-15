#!/usr/bin/env bash
# Get the current checkout ready to build and test, and fail fast if the
# environment itself is wrong.
#
# Run this before your first build or test run: on a new branch, and at the start
# of a cloud sandbox session. It is cheap and safe to re-run — with a warm cache
# both installs are close to no-ops.
#
# It does not build an environment. That is `.config/utils/setup_env.sh`.

# `set -o pipefail` is not POSIX, so `sh setup_startup.sh` would die on the next
# line. Same guard as setup_env.sh.
if [ -z "${BASH_VERSION:-}" ]; then
  if [ -r "$0" ]; then
    exec bash "$0" "$@"
  fi
  echo "error: setup_startup.sh requires bash. Re-run it as: bash setup_startup.sh" >&2
  exit 1
fi

set -uo pipefail

UV_MIN=0.10.0
PYTHON_PIN=3.13     # what .python-version gets pinned to when it is missing or too old
PYTHON_MIN_MINOR=13 # the 3.x floor; PYTHON_PIN must meet it

REPAIR_SETUP="bash .config/utils/setup_env.sh --upgrade-tools"

# No options. Take arguments anyway so a mistyped flag is not silently swallowed
# into a full sync — `setup_startup.sh --help` used to just run.
usage() {
  cat <<'EOF'
Usage: setup_startup.sh

Prepares the current checkout to build and test: verifies the environment can
build Kiln, writes agent configuration, pins the Python version, and syncs Python
and Node dependencies for the branch you are on. Takes no options other than
--help.

To build or repair an environment from scratch, see setup_env.sh --help.
EOF
}

case "${1:-}" in
  "") ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    echo "error: setup_startup.sh takes no arguments (got: $*)" >&2
    usage >&2
    exit 2
    ;;
esac

bad_environment() {
  # $1 = what is wrong, $2 = the one thing to do about it.
  cat >&2 <<EOF

  ✗ $1

    To fix:

        $2

    In a Claude Code cloud sandbox, seeing this usually means the environment's
    VM setup script did not run, or ran against a different image.

EOF
  exit 1
}

# ── Locate the checkout ───────────────────────────────────────────────────────
# Deriving this from ${BASH_SOURCE[0]} alone is the bug class setup_env.sh was
# fixed for: BASH_SOURCE is unset when the body is fed on stdin, `cd ""` then
# succeeds as a no-op, and the script would sync and write files two directories
# above the working directory. Unlike setup_env.sh, this script has nothing
# useful to do without a checkout, so a miss is fatal rather than a skip.
is_kiln_root() {
  [ -n "$1" ] && [ -f "$1/pyproject.toml" ] && [ -d "$1/libs/core/kiln_ai" ]
}

find_kiln_root() {
  local candidate

  candidate="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." 2>/dev/null && pwd)"
  is_kiln_root "$candidate" && {
    echo "$candidate"
    return 0
  }

  candidate="$(git rev-parse --show-toplevel 2>/dev/null)"
  is_kiln_root "$candidate" && {
    echo "$candidate"
    return 0
  }

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

PROJECT_ROOT="$(find_kiln_root)" || bad_environment \
  "no Kiln checkout found from $PWD, so there is nothing to set up." \
  "cd into a Kiln checkout and re-run this script"

# ── Hard dependencies ─────────────────────────────────────────────────────────
# Check uv before syncing, not after. uv older than $UV_MIN cannot parse this
# repo's relative `exclude-newer`; instead of failing it re-resolves the whole
# dependency graph and rewrites uv.lock with a broken dependency set. Running a
# sync first would do the damage this check exists to prevent.
#
# The two "tool is absent" cases get their own repair line: setup_env.sh needs uv
# in order to upgrade uv, and it never installs npm at all, so pointing at it
# would send the reader somewhere that cannot help.
command -v uv >/dev/null 2>&1 || bad_environment \
  "uv is not installed." \
  "install uv: https://docs.astral.sh/uv/getting-started/installation/"

# Keep this comparison in sync with setup_env.sh, which cannot share code with
# this file: its whole contents get pasted into a cloud setup script field.
UV_VERSION="$(uv --version 2>/dev/null | awk '{print $2}')"
if [ -z "$UV_VERSION" ]; then
  bad_environment \
    "uv is on PATH but 'uv --version' printed nothing, so its version cannot be checked." \
    "$REPAIR_SETUP"
fi
if [ "$(printf '%s\n%s\n' "$UV_MIN" "$UV_VERSION" | sort -V | head -1)" != "$UV_MIN" ]; then
  bad_environment \
    "uv $UV_VERSION is older than $UV_MIN, and would corrupt uv.lock." \
    "$REPAIR_SETUP"
fi

command -v npm >/dev/null 2>&1 || bad_environment \
  "npm is not installed." \
  "install Node.js, which provides npm: https://nodejs.org/en/download"

# ── Agent configuration ───────────────────────────────────────────────────────
# First, because it is offline, costs a fraction of a second, and is what makes
# the repo's own instructions readable at all — so it must not sit behind a sync
# that might fail. setup_env.sh does this too, but in a cloud sandbox that script
# usually runs with no checkout in reach (it is snapshotted once per environment
# and shared across repos), which leaves this as the only thing that writes
# CLAUDE.md, .claude/skills/ and .mcp.json into a session's working copy.
# Everything written is gitignored.
#
# This deliberately differs from setup_env.sh's run_agent_setup, which warns about
# a missing script and treats a failing one as a `fail`. Here a missing script is
# silent — this runs every session and has no --agent selector, so it has no way to
# know the absence was unexpected — and a failure only warns, because aborting a
# startup check over agent config would be worse than the stale config it leaves.
for agent in claude cursor; do
  agent_setup="$PROJECT_ROOT/.agents/$agent/setup.sh"
  [ -f "$agent_setup" ] || continue
  if ! agent_output="$(bash "$agent_setup" 2>&1)"; then
    echo "warning: .agents/$agent/setup.sh failed:" >&2
    echo "$agent_output" >&2
  fi
done

# ── Pin the Python version ────────────────────────────────────────────────────
# Written here, not just in setup_env.sh, for the same reason as above: without
# the pin the sync below would build .venv on the system Python, which on many
# images has no tkinter, and the only recovery would be the round trip through
# this script's own failure message. uv reads the file on every sync, so writing
# it before the sync is what matters.
#
# PYTHON_MIN_MINOR is a floor, so a pin at or above it is a deliberate choice and
# is left alone; only a missing, malformed, or too-old pin gets rewritten.
#
# Compare major and minor only, ignoring any patch component: `3.13.1` is the form
# pyenv writes, and AGENTS.md tells pyenv users this file is shared with their
# shims, so clobbering it would be resetting exactly the pin most likely to be
# deliberate.
pinned="$(cat "$PROJECT_ROOT/.python-version" 2>/dev/null)"
IFS=. read -r pin_major pin_minor _ <<<"$pinned"
if ! [[ "${pin_major:-}" =~ ^[0-9]+$ ]] ||
  ! [[ "${pin_minor:-}" =~ ^[0-9]+$ ]] ||
  [ "$pin_major" -lt 3 ] ||
  { [ "$pin_major" -eq 3 ] && [ "$pin_minor" -lt "$PYTHON_MIN_MINOR" ]; }; then
  echo "$PYTHON_PIN" >"$PROJECT_ROOT/.python-version" ||
    bad_environment \
      "could not write $PROJECT_ROOT/.python-version." \
      "check the checkout is writable, then re-run this script"
fi

# ── Sync this branch ──────────────────────────────────────────────────────────
branch="$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null)"
echo "Syncing dependencies for ${branch:-this checkout}..."

# npm install rather than npm ci: it is incremental, so a warm node_modules makes
# it near-free, where npm ci would empty and refill the directory every time — and
# on a snapshotted filesystem that cached state is the whole point of this script
# being cheap.
#
# The cost of that choice is real: unlike `uv sync --frozen`, `npm install` will
# rewrite package-lock.json when it disagrees with package.json. That is a tracked
# file, so the run can leave the working tree dirty. Rather than give up the
# incremental behavior, detect it and say so — see the check after the wait.
#
# The braces matter: `cksum <"$NPM_LOCK" 2>/dev/null` lets bash report the failed
# input redirect on its own stderr, before the redirection applies.
NPM_LOCK="$PROJECT_ROOT/app/web_ui/package-lock.json"
npm_lock_before="$({ cksum <"$NPM_LOCK"; } 2>/dev/null)"

(cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) &
py_pid=$!
(cd "$PROJECT_ROOT/app/web_ui" && npm install --no-fund --no-audit) &
npm_pid=$!

py_status=0
wait "$py_pid" || py_status=$?
npm_status=0
wait "$npm_pid" || npm_status=$?

# Report the lock before the failure guards, not after: npm rewrites the file and
# *then* fails often enough that this is the case the check matters most for, and
# exiting first would leave a modified tracked file with nothing said about it.
# Not a failure itself — the change may be what the branch intended.
if [ "$({ cksum <"$NPM_LOCK"; } 2>/dev/null)" != "$npm_lock_before" ]; then
  echo "" >&2
  echo "  ! npm install rewrote app/web_ui/package-lock.json." >&2
  echo "    It does that when the lock and package.json disagree. Review the diff:" >&2
  echo "    keep it if you meant to change dependencies, otherwise" >&2
  echo "    'git checkout -- app/web_ui/package-lock.json' and re-run." >&2
  echo "" >&2
fi

if [ "$py_status" -ne 0 ]; then
  echo "" >&2
  echo "  ✗ uv sync failed (exit $py_status)." >&2
  echo "    If you changed dependencies in a pyproject.toml, run: uv lock" >&2
  echo "" >&2
  exit 1
fi

if [ "$npm_status" -ne 0 ]; then
  echo "" >&2
  echo "  ✗ npm install failed (exit $npm_status)." >&2
  echo "" >&2
  exit 1
fi

# ── Verify what the environment setup was supposed to provide ─────────────────
# Checked after the sync because both live in .venv. The system Python on many
# sandbox images is older and has no tkinter, which breaks several test modules
# and both OpenAPI schema scripts.
probe_errors="$(mktemp)"
trap 'rm -f "$probe_errors"' EXIT
probe=$(
  cd "$PROJECT_ROOT" && uv run --frozen python -c \
    'import sys, importlib.util as u; print(sys.version_info[0], sys.version_info[1], u.find_spec("tkinter") is not None)' \
    2>"$probe_errors"
)
# Read the last line: anything uv decides to print on stdout lands ahead of the
# Python output, and feeding that to an arithmetic test below would produce a raw
# bash error and then a misleading "no tkinter" verdict.
read -r py_major py_minor has_tk <<<"$(printf '%s\n' "$probe" | tail -1)"

if ! [[ "${py_major:-}" =~ ^[0-9]+$ ]] || ! [[ "${py_minor:-}" =~ ^[0-9]+$ ]]; then
  # Print what uv actually said; "could not run Python" on its own gives the
  # reader nothing to act on.
  cat "$probe_errors" >&2
  [ -n "$probe" ] && echo "    probe printed: $probe" >&2
  bad_environment \
    "could not read a Python version from .venv." \
    "$REPAIR_SETUP"
fi

if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt "$PYTHON_MIN_MINOR" ]; }; then
  bad_environment \
    "the virtualenv is Python $py_major.$py_minor, but 3.$PYTHON_MIN_MINOR or newer is required." \
    "$REPAIR_SETUP"
fi

if [ "$has_tk" != "True" ]; then
  bad_environment \
    "this Python has no tkinter, so some tests and the OpenAPI schema scripts cannot run." \
    "$REPAIR_SETUP"
fi

echo "Ready. Python $py_major.$py_minor, uv $UV_VERSION, agent config written."
