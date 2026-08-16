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
#   UPGRADE_TOOLS=true BEST_EFFORT=true WARM_CACHE=true CREATE_STARTUP_SCRIPT=true
#   ADD_PLAYWRIGHT=true
HUMAN_MODE=false    # true: also offer the worktrunk/Zellij workspace tools
UPGRADE_TOOLS=false # true: upgrade uv without asking when it is too old
AGENT=all           # all | claude | cursor | none
BEST_EFFORT=false   # true: never exit non-zero (required for cloud setup scripts)
WARM_CACHE=false    # true: warm the machine's caches from a throwaway clone (cloud VMs)
CREATE_STARTUP_SCRIPT=false # true: run setup_startup.sh from a Claude Code SessionStart hook (cloud VMs)
ADD_PLAYWRIGHT=false # true: install browsers for the e2e suite, and the playwright-cli agent tool
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

# The SessionStart hook of --create-startup-script, and the file it is registered
# in. The shim's basename is deliberately repo-specific: it is what makes the
# registration idempotent, and what keeps this from ever matching someone else's
# hook. CLAUDE_CONFIG_DIR is the variable Claude Code itself honors for the user
# settings location, so respecting it is both correct and what makes this testable
# without writing to a real ~/.claude.
STARTUP_HOOK_SHIM="$VM_SETUP_DIR/kiln_session_start_hook.sh"
CLAUDE_USER_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"

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
  --create-startup-script
                      Register a Claude Code SessionStart hook that runs
                      setup_startup.sh in every session on this machine. For cloud
                      VMs; off by default so a local run never edits your Claude
                      Code settings. Merges into ~/.claude/settings.json.
  --add-playwright    Install the Chromium build app/web_ui's @playwright/test
                      pins, so `npm run tests:e2e` can launch a browser, plus the
                      playwright-cli agent tool and its own browser. Off by
                      default: it is ~800 MB and most work needs neither.
                      See .agents/USING_PLAYWRIGHT.md.
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
    --create-startup-script) CREATE_STARTUP_SCRIPT=true ;;
    --add-playwright) ADD_PLAYWRIGHT=true ;;
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
# Set only once the SessionStart hook is both written and registered. Declared
# here, with the other marker inputs, because the marker is what reports it.
STARTUP_HOOK_INSTALLED=false

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

  # Before the move below, because this is the only moment in the no-checkout
  # case when a real app/web_ui with its node_modules exists to read the pinned
  # browser revision out of. That is also the whole cloud environment-build case:
  # the setup script runs with nothing checked out.
  if [ "$ADD_PLAYWRIGHT" = true ]; then
    # Set whether or not it worked: a failure has already gone through `fail`,
    # and the message this gates is about never having tried.
    PLAYWRIGHT_REPO_BROWSER_ATTEMPTED=true
    install_playwright_repo_browser "$clone/app/web_ui"
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

# ── Run setup_startup.sh from a Claude Code SessionStart hook ─────────────────
# This is what closes the repo's circular bootstrap. Documenting the script could
# not work: the docs an agent reads are CLAUDE.md, which setup_startup.sh itself
# writes, so in a fresh sandbox nothing has told it the script exists. A user-level
# hook runs before the agent reads anything, so it depends on nothing being said —
# which is why the repo no longer documents running it at all.
#
# ~/.claude survives into the VM snapshot and Claude Code reads it in cloud
# sessions, so no repo file and no human instruction are involved.
#
# Off by default. On a development machine this would edit a contributor's own
# Claude Code settings and make every session of theirs — in every repo — run a
# script for this one. That is not a dependency installer's business.
#
# CLAUDE_USER_SETTINGS resolves $HOME here, at VM-build time. An image that builds
# as one user and runs sessions as another would register the hook in the wrong
# home, and nothing later would notice. Set CLAUDE_CONFIG_DIR explicitly on such an
# image.
install_session_start_hook() {
  local staged_shim

  # Editing JSON with sed is how settings files get destroyed. This one holds
  # enableAllProjectMcpServers for the whole machine.
  if ! command -v python3 >/dev/null 2>&1; then
    echo "warning: startup hook: python3 is not installed, so $CLAUDE_USER_SETTINGS" >&2
    echo "         cannot be edited safely; skipping" >&2
    return 1
  fi

  if ! mkdir -p "$VM_SETUP_DIR"; then
    echo "warning: startup hook: could not create $VM_SETUP_DIR; skipping" >&2
    return 1
  fi

  # Written beside the target and renamed over it: a session starting mid-write
  # would otherwise run half a shell script.
  staged_shim="$STARTUP_HOOK_SHIM.$$"
  if ! cat >"$staged_shim" <<EOF
#!/usr/bin/env bash
# Claude Code SessionStart hook. Written by Kiln's .config/utils/setup_env.sh
# --create-startup-script, and registered in $CLAUDE_USER_SETTINGS.
#
# The hook fires at the start of every session on this machine, whatever repo the
# session is for, so this does nothing unless it can find a Kiln checkout.
set -u

# CLAUDE_PROJECT_DIR is set for SessionStart hooks, and is the session's working
# directory — not necessarily the root of the checkout, hence the walk upward.
# setup_startup.sh does its own root discovery too, so this only has to get close.
#
# Resolved to an absolute path first, so a relative one walks the real tree rather
# than up to ".". The walk then stops when a directory is its own parent, which is
# true of "/" and of "." — belt and braces against ever spinning here.
dir="\${CLAUDE_PROJECT_DIR:-\$PWD}"
dir="\$(cd "\$dir" 2>/dev/null && pwd)" || dir="\$PWD"
while [ ! -f "\$dir/.config/utils/setup_startup.sh" ]; do
  parent="\$(dirname "\$dir")"
  [ "\$parent" = "\$dir" ] && exit 0
  dir="\$parent"
done
script="\$dir/.config/utils/setup_startup.sh"

# A SessionStart hook's stdout becomes context for the session and its stderr does
# not, so both streams are captured and printed together: a failure the agent never
# sees is worse than no hook at all. Always exit 0 — this must never be the reason
# a session fails to start. stdin is the hook's event JSON; nothing below reads it.
#
# Capped, because this text is spent from the session's context window rather than
# scrolled past: the normal run is ~15 lines, but a failing uv resolution or npm
# install can be enormous, and the tail of such output is where the reason is.
output="\$(bash "\$script" 2>&1 </dev/null)"
status=\$?
if [ "\${#output}" -gt 4000 ]; then
  output="\$(printf '%s' "\$output" | head -c 1500)
[...trimmed. Re-run .config/utils/setup_startup.sh to see all of it...]
\$(printf '%s' "\$output" | tail -c 2000)"
fi
[ -n "\$output" ] && printf '%s\n' "\$output"
[ "\$status" -ne 0 ] &&
  printf '%s\n' "(\$script exited \$status. Fix the above before building or testing.)"
exit 0
EOF
  then
    rm -f "$staged_shim"
    echo "warning: startup hook: could not write $STARTUP_HOOK_SHIM; skipping" >&2
    return 1
  fi

  if ! chmod +x "$staged_shim" || ! mv -f "$staged_shim" "$STARTUP_HOOK_SHIM"; then
    rm -f "$staged_shim"
    echo "warning: startup hook: could not install $STARTUP_HOOK_SHIM; skipping" >&2
    return 1
  fi

  # A shim on disk is not a hook: nothing runs it until the registration below
  # succeeds. Only that sets the flag the marker reports.
  register_session_start_hook || return 1
  STARTUP_HOOK_INSTALLED=true
}

# Merge, never overwrite: this file already carries settings that belong to the
# whole machine (enableAllProjectMcpServers, among others), and replacing it would
# disable them silently. Anything unexpected in there is left exactly as it is —
# repairing someone's malformed settings is not this script's business, and
# truncating them is worse than not installing the hook.
#
# The entry is identified by the shim's repo-specific basename, so re-running is
# idempotent and a moved KILN_VM_SETUP_DIR replaces its old entry rather than
# adding a second one.
register_session_start_hook() {
  python3 - "$CLAUDE_USER_SETTINGS" "$STARTUP_HOOK_SHIM" <<'PY'
import json
import os
import sys
import tempfile

settings_path, shim = sys.argv[1], sys.argv[2]
key = os.path.basename(shim)


def refuse(why):
    sys.stderr.write("warning: %s %s,\n" % (settings_path, why))
    sys.stderr.write("         so the SessionStart hook was not registered. "
                     "Nothing was written.\n")
    raise SystemExit(3)


try:
    with open(settings_path, encoding="utf-8") as handle:
        raw = handle.read()
except FileNotFoundError:
    raw = ""
except OSError as error:
    refuse("could not be read (%s)" % error.strerror)

if raw.strip():
    try:
        settings = json.loads(raw)
    except ValueError as error:
        refuse("is not valid JSON (%s)" % error)
    if not isinstance(settings, dict):
        refuse("does not hold a JSON object")
else:
    settings = {}

hooks = settings.setdefault("hooks", {})
if not isinstance(hooks, dict):
    refuse('has a "hooks" value that is not an object')
groups = hooks.setdefault("SessionStart", [])
if not isinstance(groups, list):
    refuse('has a "hooks.SessionStart" value that is not an array')

before = json.dumps(settings, sort_keys=True)

# Drop our own entry wherever it is, then append exactly one. A group left empty
# by that goes with it; a group holding anything else keeps everything else.
kept = []
for group in groups:
    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
        kept.append(group)
        continue
    others = [
        entry for entry in group["hooks"]
        if not (isinstance(entry, dict)
                and isinstance(entry.get("command"), str)
                and key in entry["command"])
    ]
    if len(others) == len(group["hooks"]):
        kept.append(group)
    elif others:
        group["hooks"] = others
        kept.append(group)

kept.append({
    # SessionStart also fires on "clear" and "compact", and this hook's output is
    # spent from the context window. Re-running it on every compaction of a long
    # session would re-inject it for no gain: the checkout is already prepared, and
    # nothing about clearing or compacting can undo that. "fork" is in because a
    # forked session can start on a filesystem this has not run on.
    "matcher": "startup|resume|fork",
    "hooks": [{
        "type": "command",
        "command": shim,
        # Seconds. Generous on purpose: a VM with no warm node_modules tree pays
        # ~32 s, and a branch that really changed dependencies pays more.
        "timeout": 600,
        "statusMessage": "Preparing the Kiln checkout",
    }],
})
hooks["SessionStart"] = kept

if json.dumps(settings, sort_keys=True) == before:
    print("SessionStart hook already registered in %s." % settings_path)
    raise SystemExit(0)

directory = os.path.dirname(settings_path) or "."
try:
    os.makedirs(directory, exist_ok=True)
except OSError as error:
    refuse("could not be created (%s)" % error.strerror)

mode = 0o600
try:
    mode = os.stat(settings_path).st_mode & 0o777
except OSError:
    pass

# Same reason as the marker: a redirect onto the file itself truncates before it
# writes, and a failed write would leave the machine's settings empty.
handle, staged = tempfile.mkstemp(dir=directory, prefix=".settings.json.")
try:
    with os.fdopen(handle, "w", encoding="utf-8") as staged_file:
        # ensure_ascii=False: the contract of this function is that it touches
        # nothing but our own entry, and the default would rewrite every non-ASCII
        # character in someone else's setting as an escape.
        json.dump(settings, staged_file, indent=2, ensure_ascii=False)
        staged_file.write("\n")
    os.chmod(staged, mode)
    os.replace(staged, settings_path)
except OSError as error:
    try:
        os.unlink(staged)
    except OSError:
        pass
    refuse("could not be written (%s)" % error.strerror)

print("Registered the SessionStart hook in %s." % settings_path)
PY
}

# ── Playwright ────────────────────────────────────────────────────────────────
# Two separate installs, both off by default because together they are ~800 MB
# and most work in this repo needs neither:
#
#   - The Chromium build app/web_ui's @playwright/test pins, without which
#     `npm run tests:e2e` cannot launch a browser. The pin is the whole
#     difficulty: an image that ships "a Chromium" ships some other revision, and
#     Playwright accepts only its own — reporting it as a browser that was never
#     installed, rather than as the version mismatch it is. So no revision is
#     named anywhere below. It is whatever the checkout's own playwright asks
#     for, and it moves on its own when @playwright/test is bumped.
#
#   - playwright-cli, the agent-facing browser tool, and its Claude Code skill.
#     It bundles its own playwright, so it wants its own browser revision, which
#     is not the one above and has to be installed separately.
#
# Every download here comes from cdn.playwright.dev, which a restrictive egress
# policy blocks. These route through `fail`, so --best-effort leaves a VM that
# boots and reports the problem instead of one that never starts.
PLAYWRIGHT_CLI_MIN=0.1.18
PLAYWRIGHT_REPO_BROWSER_ATTEMPTED=false

# --with-deps shells out to apt-get, and the apt mirrors are not in every egress
# allowlist that has the CDN in it. Any image that already ships a Chromium has
# the system libraries, so losing apt is not a reason to end up with no browser:
# drop the flag and retry, and only a second failure is a real one.
run_browser_install() {
  # "$@" = the command that installs a browser, without --with-deps.
  "$@" --with-deps && return 0
  echo "note: '$*' failed with --with-deps (apt is often blocked); retrying without it." >&2
  "$@"
}

# $1 = an app/web_ui directory whose node_modules is already installed.
install_playwright_repo_browser() {
  local web_ui="$1"

  # The bin, not the package: it is what the line below actually runs, and
  # `npx --no-install` reports its absence as a bare "could not determine
  # executable" with nothing about npm ci not having run.
  if [ ! -x "$web_ui/node_modules/.bin/playwright" ]; then
    fail "no playwright in $web_ui/node_modules, so the e2e browser cannot be installed"
    return 1
  fi

  echo "Installing the Chromium build app/web_ui pins..."
  # --no-install so this can only ever run the checkout's own pinned playwright.
  # Without it npx silently fetches the latest from the registry on a miss, and
  # would install a revision the suite then refuses to use.
  (cd "$web_ui" && run_browser_install npx --no-install playwright install chromium) ||
    fail "could not install the Chromium build app/web_ui pins"
}

install_playwright_cli() {
  if ! command -v npm >/dev/null 2>&1; then
    fail "npm is not installed, so playwright-cli cannot be installed"
    return 1
  fi

  echo "Installing playwright-cli..."
  # A floor rather than @latest: hooks-mcp taught us that a bare latest is one
  # broken publish away from breaking every session, and a floor still picks up
  # fixes. Bump it when the tool gains something worth requiring.
  if ! npm install -g "@playwright/cli@>=$PLAYWRIGHT_CLI_MIN" --no-fund --no-audit; then
    fail "could not install @playwright/cli"
    return 1
  fi
  hash -r

  # A successful `npm install -g` still leaves nothing to run when npm's global
  # bin directory is not on PATH, which is ordinary on a machine using a Node
  # installed by Homebrew or a version manager. Saying that here beats three
  # "command not found" lines that each look like a failed install.
  if ! command -v playwright-cli >/dev/null 2>&1; then
    fail "playwright-cli installed but is not on PATH; add '$(npm prefix -g 2>/dev/null)/bin' to it"
    return 1
  fi

  # --global puts the skill in ~/.claude/skills, which survives into the VM
  # snapshot. The workspace form writes .claude/skills/playwright-cli, which
  # .agents/claude/setup.sh rebuilds from .agents/skills every session — so the
  # skill would be deleted by the next session to start.
  playwright-cli install --skills --global ||
    fail "could not install the playwright-cli agent skill"

  run_browser_install playwright-cli install-browser chromium ||
    fail "could not install playwright-cli's own Chromium"
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
  # two come apart on a re-run: repairing an environment means re-running this
  # script, which carries no --warm-cache, and the warm tree it does not touch
  # outlives it. A marker rewritten as
  # "created=false, commit=none" would then be lying about the provenance of the
  # 601 MB every session on this machine inherits — the one fact it exists to
  # record. So carry the previous commit forward whenever the tree survives.
  local tree_present=false tree_commit=none hook_shim=none playwright_cli=none
  [ -d "$WARM_NODE_MODULES" ] && tree_present=true

  # Probed rather than carried forward like the fields below: what is on PATH now
  # is the whole truth here, and a re-run without --add-playwright must not report
  # a tool that has since been uninstalled.
  command -v playwright-cli >/dev/null 2>&1 &&
    playwright_cli="$(playwright-cli --version 2>/dev/null | tr -d '\n')"
  playwright_cli="${playwright_cli:-unknown}"

  # The shim file existing proves nothing — it is written before the registration
  # that makes it a hook, and that registration refuses to touch a malformed
  # settings.json. Reporting the path there would send whoever is debugging a VM
  # with no hook looking anywhere but at the file that actually failed. So:
  # installed reports the path, a refusal reports the refusal, and a run that did
  # not try carries the previous marker's answer forward the way the warm tree does.
  if [ "$STARTUP_HOOK_INSTALLED" = true ]; then
    hook_shim="$STARTUP_HOOK_SHIM"
  elif [ "$CREATE_STARTUP_SCRIPT" = true ]; then
    hook_shim=registration_failed
  else
    hook_shim="$(previous_marker_value session_start_hook)"
    hook_shim="${hook_shim:-none}"
  fi

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
session_start_hook=$hook_shim
playwright_cli=$playwright_cli
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

# Before the marker, so the marker can record the outcome, and well before the
# "everything below needs a checkout" exit: the cloud environment-build case has no
# checkout, and is exactly the case this exists for.
[ "$CREATE_STARTUP_SCRIPT" = true ] && install_session_start_hook

# Same reason: playwright-cli is installed globally and carries its own browser,
# so unlike the e2e browser above it needs no checkout at all.
[ "$ADD_PLAYWRIGHT" = true ] && install_playwright_cli

write_vm_setup_marker

# ── Everything below here needs a checkout ────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  echo "No Kiln checkout found, so dependency install and agent configuration"
  echo "were skipped."
  # playwright-cli is installed by now either way; this is only about the browser
  # the e2e suite pins, whose revision can only be read from a checkout's
  # node_modules. --warm-cache makes one, so say so only when nothing did.
  if [ "$ADD_PLAYWRIGHT" = true ] && [ "$PLAYWRIGHT_REPO_BROWSER_ATTEMPTED" = false ]; then
    echo ""
    echo "The browser the e2e suite needs was skipped: which revision to install"
    echo "is a property of a checkout. Add --warm-cache, or from a checkout run:"
    echo "  .config/utils/setup_env.sh --add-playwright"
  fi
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

# After npm ci, which is what puts the pinned playwright in node_modules for the
# revision to be read from. Skipped when the warm clone above already did it, so
# a --warm-cache run with a checkout does not download the same browser twice.
if [ "$ADD_PLAYWRIGHT" = true ] && [ "$PLAYWRIGHT_REPO_BROWSER_ATTEMPTED" = false ]; then
  install_playwright_repo_browser "$PROJECT_ROOT/app/web_ui"
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
