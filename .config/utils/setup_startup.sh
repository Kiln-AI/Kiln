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

# Written by setup_env.sh outside any checkout, so it survives into a VM snapshot.
# Keep these paths identical to that script's — they are the interface between the
# two, and the scripts cannot share code because setup_env.sh gets pasted whole
# into a cloud setup field.
VM_SETUP_DIR="${KILN_VM_SETUP_DIR:-/opt/kiln-vm-setup}"
VM_SETUP_MARKER="$VM_SETUP_DIR/.setup_for_kiln_repo_v1"
WARM_NODE_MODULES="$VM_SETUP_DIR/node_modules"

# No options. Take arguments anyway so a mistyped flag is not silently swallowed
# into a full sync — `setup_startup.sh --help` used to just run.
usage() {
  cat <<'EOF'
Usage: setup_startup.sh

Prepares the current checkout to build and test: verifies the environment can
build Kiln, writes agent configuration, pins the Python version, and syncs Python
and Node dependencies for the branch you are on. Takes no options other than
--help.

Only does anything inside a container or VM, where each session starts from a
fresh filesystem. Elsewhere it prints a line and exits 0: a local environment is
already set up and shared between checkouts, and this script would spend a session
of yours re-doing work that is already done. Set IS_CONTAINERIZED=true to run it
anyway.

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

# ── Containers only ───────────────────────────────────────────────────────────
# This script exists because a cloud session starts on a fresh filesystem: nothing
# repo-aware has run there, and the checkout may have no .venv or node_modules at
# all. On a development machine none of that is true — the environment is set up
# once and shared across every checkout — and the steps below would re-do that work
# every session, seed node_modules from a machine-global tree, and rewrite files a
# contributor deliberately configured.
#
# CLAUDE_CODE_REMOTE is set to true by Claude Code in cloud sessions.
# IS_CONTAINERIZED is the manual escape hatch for every other containerized setup.
#
# The rule is "non-empty and not falsy". The falsy list covers the spellings people
# actually type — someone who sets IS_CONTAINERIZED=no means no, and reading it as
# yes would be the one failure mode of this gate that is impossible to notice.
is_flag_set() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    "" | false | f | 0 | no | n | off) return 1 ;;
    *) return 0 ;;
  esac
}

if ! is_flag_set "${CLAUDE_CODE_REMOTE:-}" && ! is_flag_set "${IS_CONTAINERIZED:-}"; then
  echo "Not running in a VM/container, will not run custom setup."
  echo "  To set up or repair this environment: bash .config/utils/setup_env.sh --human"
  echo "  Or, for just the dependencies: uv sync, and npm install in app/web_ui."
  echo "  Set IS_CONTAINERIZED=true to run this script here anyway."
  exit 0
fi

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

# ── Was this machine provisioned by setup_env.sh? ─────────────────────────────
# Checked before the hard dependencies below, because a missing marker is usually
# the reason they are about to fail, and knowing that first saves reading the
# repair line for a machine that simply never got set up.
#
# Not fatal on its own: an unprovisioned machine with a working uv and npm can
# still run everything below, just slower. What it does forbid is the node_modules
# hardlink — without the marker, a tree at that path was not put there by this
# repo's setup script, and linking an unknown 600 MB of JavaScript into a checkout
# is not a risk worth a few seconds.
VM_WAS_PROVISIONED=true
if [ ! -f "$VM_SETUP_MARKER" ]; then
  VM_WAS_PROVISIONED=false
  cat >&2 <<EOF

  ! This VM was not set up for Kiln: $VM_SETUP_MARKER is missing.

    The environment's VM setup script — the contents of
    .config/utils/setup_env.sh — should have run when this machine was built,
    and either did not run, or was an older version of the script.

    Continuing anyway. Expect this to be slow, and expect the checks below to
    report anything the setup script was supposed to provide.

EOF
fi

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
# pyenv writes into this same file, so clobbering it would be resetting exactly
# the pin most likely to be deliberate.
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

# ── Seed node_modules from the VM's warm tree ─────────────────────────────────
# npm copies out of ~/.npm where uv hardlinks out of its cache, so even a warm npm
# cache costs ~21 s to fill an empty node_modules. setup_env.sh leaves a pristine
# tree outside the checkout for exactly this: `cp -al` of the 601 MB tree takes
# ~0.5 s and shares inodes rather than copying bytes.
#
# This only pre-fills; the npm install below is still what reconciles the tree with
# this branch's package.json. So every failure here is a note and a fall-through to
# the behavior we had before: an image where the tree is on another filesystem, or
# a filesystem without hardlinks, loses the speedup and nothing else.
#
# Staging is a sibling of the target so the mv is a rename on the same filesystem.
# Staging inside VM_SETUP_DIR would put the copy on the warm tree's filesystem, and
# the mv would then copy 601 MB and drop every link it just made.
WEB_UI_DIR="$PROJECT_ROOT/app/web_ui"

# Staging is per-PID, and no run ever touches a path that is not its own. A shared
# name loses badly here: two runs racing on one name corrupt each other silently —
# one `rm -rf` unlinks entries out of the other's tree mid-`cp -al` and the survivors
# get renamed into place, or the `rm -rf` fails against a directory still being
# created and the second `cp -al` copies *into* it, nesting a whole tree. Measured
# 57 corruptions in 60 races, every one of them reporting a successful seed.
#
# That is not a supported scenario — two of these in one checkout also collide on
# the npm install below, destructively and unconditionally — but a name that cannot
# collide costs nothing and keeps the failure to the one place it is already known.
#
# The price of per-PID names is that a killed run leaks its staging under a name no
# later run will reuse, so a sweep reclaims what is left behind. It runs
# unconditionally, because the seed block below is skipped as soon as node_modules
# exists — exactly the state a leaked 601 MB directory would otherwise sit in
# forever.
#
# What makes deleting someone else's staging path safe here is that in every
# supported configuration there is no one else: this runs before this run creates
# its own staging, and a second concurrent process is already unsupported and
# already destructive at the npm install below.
#
# It is specifically *not* safe because of the age filter. `cp -al` implies
# --preserve=all, which stamps the warm tree's mtime onto the staging directory the
# moment the copy finishes — on a snapshot-restored VM that is the image build date,
# so a live staging directory can read as days old the instant it is complete. The
# -mmin filter is a coarse guard against deleting a directory another run is still
# filling (that one does bump its mtime per top-level entry), not a liveness proof.
warm_staging="$WEB_UI_DIR/.node_modules.warm.$$"
# No dot before the wildcard: it must also match the fixed `.node_modules.warm`
# name a previous version of this script used, or a tree left by a run of that
# version is orphaned permanently and invisibly, since the name is gitignored. The
# leading dot is what keeps this from ever matching node_modules itself.
find "$WEB_UI_DIR" -maxdepth 1 -name '.node_modules.warm*' -mmin +60 \
  -exec rm -rf {} + 2>/dev/null

# Everything happens in the staging directory, and node_modules only ever appears
# by a single rename of a finished tree. A partially copied — or still fully
# shared — tree must never be visible under that name: the next run would see
# node_modules already present, skip seeding, and let npm install write straight
# through the hardlinks into the pristine tree.
seed_warm_node_modules() {
  # Only this run's own path — a PID can be reused after a reboot, and cp -al onto
  # a surviving directory of that name would copy into it rather than replace it.
  rm -rf "$warm_staging"
  cp -al "$WARM_NODE_MODULES" "$warm_staging" || return 1

  # Hardlinks mean a write through one path is a write to the other, so a tool
  # that edits a file in place edits the pristine tree every later checkout is
  # seeded from. `npm install` does exactly that to node_modules/.package-lock.json
  # — same inode, new mtime, measured — and that file is npm's record of what is
  # installed, so drift there is what could make a later npm install skip a package
  # that is genuinely missing.
  #
  # Measured on this repo's current toolchain: after a seed, an npm install and a
  # full npm run build, that file was the only changed inode out of 46,375, and
  # everything else npm and vite wrote landed on new inodes in this checkout's own
  # directory entries. So unsharing the regular files at the root of the tree — a
  # few hundred KB — was enough, and the ~46,000 package files below stay linked.
  # A failure here is a failed seed, not a cosmetic problem: it would leave the
  # baseline exposed to exactly the write above.
  #
  # Collect the whole list before touching anything. Streaming `find` into the loop
  # would have it reading the directory while `cp -p` and `mv -f` create and remove
  # `X.unshared` names in it: a transient entry landing in find's readdir buffer
  # makes the next `cp -p` fail on a file that no longer exists, and the seed aborts
  # for no reason.
  local shared_file
  local -a warm_root_files
  mapfile -t warm_root_files < <(find "$warm_staging" -maxdepth 1 -type f)
  for shared_file in "${warm_root_files[@]}"; do
    cp -p "$shared_file" "$shared_file.unshared" || return 1
    mv -f "$shared_file.unshared" "$shared_file" || return 1
  done

  # -T so a node_modules that appeared since the guard above makes this fail rather
  # than silently swallow staging as a subdirectory, which is the one outcome worse
  # than not seeding. (-T does not make the rename always succeed; it makes it
  # refuse the wrong thing.)
  mv -T "$warm_staging" "$WEB_UI_DIR/node_modules" || return 1
}

# A warm tree on another filesystem fails once per file — 46,436 lines, 15 MB,
# measured — and this is the graceful path, whose reader is usually an agent.
# Neither its context nor this shell should have to hold that, so the output goes to
# a file and only its first lines are ever printed.
print_seed_output() {
  # $1 = file, $2 = how many lines to show.
  #
  # grep -c '' rather than wc -l: wc counts newlines, so a single error line without
  # a trailing one would count as zero and print nothing — silence in the function
  # that exists to break silence.
  local total
  total="$(grep -c '' <"$1")"
  [ "$total" -eq 0 ] && return 0
  head -"$2" "$1" | sed 's/^/      /'
  [ "$total" -gt "$2" ] && echo "      ...and $((total - $2)) more lines like that."
  return 0
}

if [ ! -d "$WEB_UI_DIR/node_modules" ] &&
  [ "$VM_WAS_PROVISIONED" = true ] &&
  [ -d "$WARM_NODE_MODULES" ]; then
  seed_errors="$(mktemp)"
  if seed_warm_node_modules 2>"$seed_errors"; then
    echo "Seeded node_modules by hardlink from $WARM_NODE_MODULES."
    # A seed can succeed and still have had something to say — a `cp` that skipped
    # an entry, say. Silence about it would be the same class of quiet as the note
    # below exists to avoid.
    print_seed_output "$seed_errors" 3 >&2
  else
    rm -rf "$warm_staging"
    {
      echo "note: could not seed node_modules from $WARM_NODE_MODULES, so"
      echo "      npm install below will populate it from scratch."
      print_seed_output "$seed_errors" 3
    } >&2
  fi
  rm -f "$seed_errors"
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
NPM_LOCK="$WEB_UI_DIR/package-lock.json"
npm_lock_before="$({ cksum <"$NPM_LOCK"; } 2>/dev/null)"

(cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) &
py_pid=$!
(cd "$WEB_UI_DIR" && npm install --no-fund --no-audit) &
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

# ── Playwright ────────────────────────────────────────────────────────────────
# playwright-cli's global config, which selects the browser it launches. Without
# it the first `playwright-cli open` tries to launch a branded Google Chrome that
# a container does not have.
#
# setup_env.sh writes this at VM-build time, so on a machine it provisioned this
# is a no-op. It is repeated here as the safety net for the case that is easy to
# miss: an image built before --add-playwright existed, or one where the home
# directory is not the one the setup script wrote to.
#
# Only when absent, so anyone's own defaults survive. A failure is a warning: it
# costs an agent a `--browser=chromium` flag, not a broken checkout.
write_playwright_cli_config() {
  local config="$HOME/.playwright/cli.config.json"

  [ -f "$config" ] && return 0

  if ! mkdir -p "$HOME/.playwright" || ! cat >"$config" <<'JSON'
{
  "browser": {
    "browserName": "chromium",
    "launchOptions": {
      "channel": "chromium"
    }
  }
}
JSON
  then
    echo "warning: could not write $config; playwright-cli will need --browser=chromium." >&2
  fi
  return 0
}

# Only a check, and deliberately a pure-bash one: this runs at the start of every
# session, and shelling out to `playwright install --dry-run` to ask the same
# question costs ~1 s — about as much as the whole rest of this script warm.
#
# What makes the browser worth checking at all is that its absence is reported by
# Playwright as a browser that was never installed, pointing at `npx playwright
# install`, when the actual state is a browser of the wrong revision sitting right
# where it looked. Naming the revision here turns that into one clear line.
#
# Not fatal: most sessions never launch a browser, and the rest of the checkout is
# ready regardless. See .agents/USING_PLAYWRIGHT.md.
check_playwright() {
  local browsers_json="$WEB_UI_DIR/node_modules/playwright-core/browsers.json"
  local browsers_dir revision missing=""

  [ -f "$browsers_json" ] || return 0

  # The first "revision" after the chromium entry. The closing quote in the match
  # is what keeps this off "chromium-headless-shell", which follows it and
  # currently shares the revision — but is a separate entry that need not.
  revision="$(grep -A1 '"name": "chromium"' "$browsers_json" |
    sed -n 's/.*"revision": *"\([0-9]*\)".*/\1/p' | head -1)"
  [ -n "$revision" ] || return 0

  # Containers only, so the Linux default is the right fallback. Playwright writes
  # INSTALLATION_COMPLETE last, so a directory without it is a partial download.
  browsers_dir="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
  [ -f "$browsers_dir/chromium-$revision/INSTALLATION_COMPLETE" ] ||
    missing="chromium-$revision"

  command -v playwright-cli >/dev/null 2>&1 || missing="${missing:+$missing, }playwright-cli"

  [ -n "$missing" ] || return 0

  echo "" >&2
  echo "  ! Playwright is not fully installed here: $missing is missing." >&2
  echo "    Needed only to run the e2e tests or drive the UI in a browser:" >&2
  echo "        bash .config/utils/setup_env.sh --add-playwright" >&2
  echo "    See .agents/USING_PLAYWRIGHT.md." >&2
  echo "" >&2
}

command -v playwright-cli >/dev/null 2>&1 && write_playwright_cli_config
check_playwright

echo "Ready. Python $py_major.$py_minor, uv $UV_VERSION, agent config written."
