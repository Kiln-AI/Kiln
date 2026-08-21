#!/usr/bin/env bash
# Start a Kiln dev server for an agent to drive with playwright-cli.
#
#   .agents/scripts/playwright_server.sh start|stop|status|reset|snapshot
#
# This is not for running the e2e suite: playwright.config.ts starts its own
# servers and would refuse to share these. It exists so an agent can look at the
# UI it is changing — open a page, click through it, take a screenshot — which
# needs a server that outlives a single command, where the suite's servers live
# and die inside one `playwright test` run.
#
# See the playwright skill: .agents/skills/playwright/.

if [ -z "${BASH_VERSION:-}" ]; then
  if [ -r "$0" ]; then
    exec bash "$0" "$@"
  fi
  echo "error: playwright_server.sh requires bash. Re-run it as: bash playwright_server.sh" >&2
  exit 1
fi

set -uo pipefail

# Deliberately not the e2e suite's 6534-6537. Sharing them would make this script
# and a `npm run tests:e2e` run fight over a port, and the suite sets
# reuseExistingServer:false, so whichever started second would simply fail.
FRONTEND_PORT="${KILN_DEV_FRONTEND_PORT:-6544}"
BACKEND_PORT="${KILN_DEV_BACKEND_PORT:-6545}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
WEB_UI_DIR="$PROJECT_ROOT/app/web_ui"

# Same trick the e2e suite uses: Kiln reads and writes its projects under $HOME,
# so an isolated HOME keeps whatever an agent clicks through here away from the
# real Kiln data of whoever is running it. KILN_DEV_HOME chooses *where the
# sandbox lives* — not whose data it operates on. This directory is seeded and
# `reset` deletes it, so it must be disposable; pointing it at a real home is
# refused outright.
RUN_DIR="${KILN_DEV_HOME:-$WEB_UI_DIR/.agent_dev_home}"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"

FRONTEND_URL="http://localhost:$FRONTEND_PORT"
BACKEND_URL="http://localhost:$BACKEND_PORT"

# The committed fixture project, and where a copy of it lands in the sandbox.
# The destination directory name is the fixture's basename: it is cosmetic — the
# name the UI shows comes from project.kiln — and taking it from the source means
# it cannot drift from the fixture.
FIXTURE_DIR="$PROJECT_ROOT/.agents/playwright_project"
PROJECTS_DIR="$RUN_DIR/Kiln Projects"
SEEDED_PROJECT_DIR="$PROJECTS_DIR/playwright_project"
SEED_STAMP="$RUN_DIR/.playwright_seed"
SETTINGS_FILE="$RUN_DIR/.kiln_ai/settings.yaml"
SEED_CONTACT="playwright@example.com"

# An OpenRouter key seeded into the sandbox's settings, so the app comes up with a
# provider connected and live model calls work. Optional: without it the sandbox
# behaves exactly as it always has, with nothing connected.
#
# Deliberately not named OPENROUTER_API_KEY. That name is Config's env fallback for
# open_router_api_key (libs/core/kiln_ai/utils/config.py) and litellm's too, so
# under it every `pytest --runpaid` run and every stray script on the machine would
# start spending against the key without anyone choosing to. Under this name the
# only thing that spends it is a sandbox seeded on purpose.
#
# See .config/utils/claude_cloud_setup.md for where it comes from and the spending
# limit it must have.
OPENROUTER_KEY="${OPENROUTER_QA_KEY:-}"

usage() {
  cat <<EOF
Usage: playwright_server.sh [start|stop|status|reset|snapshot]

  start     Start the backend and frontend, wait until both answer, print the URL.
            Seeds the sandbox with .agents/playwright_project on first start.
            Already running is success, not an error.
  stop      Stop both.
  status    Report whether both are answering.
  reset     Stop, delete the sandbox, start again — a freshly seeded sandbox.
  snapshot  Capture the running sandbox's project back into
            .agents/playwright_project, to update the seed for future sessions.

Frontend $FRONTEND_URL, backend $BACKEND_URL. Override the ports with
KILN_DEV_FRONTEND_PORT / KILN_DEV_BACKEND_PORT, and the data directory with
KILN_DEV_HOME (default $WEB_UI_DIR/.agent_dev_home).

If OPENROUTER_QA_KEY is set when a sandbox is seeded, it is written into that
sandbox's settings as a connected OpenRouter provider, and live model calls work.
Without it nothing is connected. Every call spends real money against a key that
must carry a hard limit — see .config/utils/claude_cloud_setup.md.
EOF
}

# The sandbox's home is seeded, written into, and deleted by `reset`. Doing any of
# that to the invoking user's real home would destroy their settings and projects.
# $HOME here is the invoking shell's and stays that way: the script never exports
# HOME, it only passes `env HOME="$RUN_DIR"` to the backend child.
#
# cd + pwd -P rather than realpath, which is not dependably present across the
# Linux containers and macOS machines this repo is developed on. Falling back to
# the literal string keeps the comparison meaningful before the directory exists.
#
# That fallback is also this check's one weak spot, and the reason every caller
# re-checks once the directory exists: `cd` fails on a path with a missing
# component, so `$HOME/sandbox/..` — which resolves to the real home the moment
# `sandbox` is created — compares as the literal string and passes. Called again
# after `mkdir -p`, `cd` always succeeds and the comparison is real.
#
# Called by start, reset, and snapshot. Not by stop or status: those two are how
# you recover from a misconfigured KILN_DEV_HOME, so refusing them would leave a
# server you cannot stop. Between them they write only `rm -f` of the two pid
# files this script created itself.
guard_not_real_home() {
  local resolved_run resolved_home home="${HOME:-}"

  # Without HOME there is nothing to compare against, and this guard is the last
  # thing that should fail open.
  if [ -z "$home" ]; then
    echo "error: HOME is not set, so this script cannot tell whether $RUN_DIR is" >&2
    echo "       your real home. Export HOME and re-run." >&2
    return 1
  fi

  resolved_run="$(cd "$RUN_DIR" 2>/dev/null && pwd -P)" || resolved_run="$RUN_DIR"
  resolved_home="$(cd "$home" 2>/dev/null && pwd -P)" || resolved_home="$home"
  if [ "$resolved_run" = "$resolved_home" ]; then
    echo "error: KILN_DEV_HOME is your real home ($resolved_home)." >&2
    echo "       This sandbox writes settings and a fixture project into the home it" >&2
    echo "       is given, and reset deletes it. Point it somewhere disposable." >&2
    return 1
  fi
}

# A pid file outlives the process it names, and after a reboot that pid can
# belong to something else entirely. Checking the port instead asks the question
# that actually matters — is something serving? — and is what the readiness wait
# below already does.
is_up() {
  # $1 = url
  [ "$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 2 "$1" 2>/dev/null)" = "200" ]
}

backend_up() { is_up "$BACKEND_URL/openapi.json"; }
frontend_up() { is_up "$FRONTEND_URL/"; }

# `uv run` and `npm run dev` both start the real server as a child, so killing
# only the pid we recorded leaves the process actually holding the port alive.
# There is no portable `pkill --tree`, and process groups do not help: a
# background job in a non-interactive shell shares the script's own group, so
# killing that group would kill this script too. Walking ps is portable across
# the Linux containers and macOS machines this repo is developed on.
descendants() {
  # $1 = pid. Prints the whole tree below $1, deepest first, then $1 — so a
  # parent is never killed before the child whose pid we still need to read.
  local pid="$1" child
  for child in $(ps -eo pid=,ppid= | awk -v parent="$pid" '$2 == parent {print $1}'); do
    descendants "$child"
  done
  echo "$pid"
}

kill_tree() {
  # $2 = signal, default TERM.
  local pid="$1" signal="${2:-TERM}" victim
  for victim in $(descendants "$pid"); do
    kill -"$signal" "$victim" 2>/dev/null
  done
  return 0
}

# True when the pid file names a live process that looks like something this script
# started — which is as close as we get to "this sandbox owns the running server".
#
# A pid file can outlive its process, and the number in it can by then belong to
# something else entirely — on a developer's machine, plausibly their editor. The
# command filter is what makes the answer worth acting on, whether the caller is
# about to send a signal or about to tell an agent whose app it is looking at.
pidfile_process_alive() {
  # $1 = pid file
  local file="$1" pid command
  [ -f "$file" ] || return 1
  pid="$(cat "$file" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  command="$(ps -o args= -p "$pid" 2>/dev/null)"
  case "$command" in
    *dev_server* | *"npm run dev"* | *vite* | *node*) return 0 ;;
  esac
  return 1
}

stop_from_pidfile() {
  # $1 = pid file, $2 = signal.
  local file="$1" pid
  pidfile_process_alive "$file" || return 0
  pid="$(cat "$file" 2>/dev/null)"
  kill_tree "$pid" "${2:-TERM}"
}

do_stop() {
  stop_from_pidfile "$FRONTEND_PID" TERM
  stop_from_pidfile "$BACKEND_PID" TERM

  local waited=0
  while [ "$waited" -lt 10 ]; do
    backend_up || frontend_up || break
    sleep 1
    waited=$((waited + 1))
  done

  # A vite dev server that is mid-request can sit on SIGTERM long enough to look
  # stuck. Escalate rather than report a failure the caller cannot act on.
  if backend_up || frontend_up; then
    stop_from_pidfile "$FRONTEND_PID" KILL
    stop_from_pidfile "$BACKEND_PID" KILL
    waited=0
    while [ "$waited" -lt 5 ]; do
      backend_up || frontend_up || break
      sleep 1
      waited=$((waited + 1))
    done
  fi

  rm -f "$FRONTEND_PID" "$BACKEND_PID"

  if backend_up || frontend_up; then
    echo "warning: something is still answering on $FRONTEND_PORT/$BACKEND_PORT." >&2
    echo "         If it was not started by this script, stop it yourself." >&2
    return 1
  fi
  echo "Dev server stopped."
}

do_status() {
  local backend=stopped frontend=stopped
  backend_up && backend=running
  frontend_up && frontend=running
  echo "backend  $BACKEND_URL  $backend"
  echo "frontend $FRONTEND_URL $frontend"
  [ "$backend" = running ] && [ "$frontend" = running ]
}

# The first indentation-tolerant `"KEY": "value"` in a .kiln file. .kiln files are
# pretty-printed JSON where a model's own scalars always precede any nested object
# carrying the same key — `id` is the second top-level key, `name` precedes
# `requirements` — so head -1 is the model's own value. Indentation-tolerant so a
# change to how the datamodel serializes cannot break it.
#
# Every caller must treat empty output as failure.
json_field() {
  # $1 = file, $2 = key
  sed -n "s/^[[:space:]]*\"$2\": *\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -1
}

fixture_present() { [ -f "$FIXTURE_DIR/project.kiln" ]; }
is_seeded() { [ -f "$SEED_STAMP" ]; }

# Written whole, never merged: the sandbox's settings are ours to define. The path
# is a single-quoted YAML scalar with internal quotes doubled, which is safe
# whatever it contains — `Kiln Projects` has a space, and a checkout path can hold
# `#` or `:`, either of which would change the meaning of a plain scalar.
#
# user_type + personal_use_contact is what clears the app's registration check.
#
# open_router_api_key is the same setting the Settings UI writes when you connect
# OpenRouter by hand — connect_openrouter() sets that one value and nothing else —
# so a sandbox seeded with it is indistinguishable from one where a provider was
# connected through the app.
write_seed_settings() {
  # $1 = path to project.kiln
  local escaped key_line=""
  escaped="$(printf '%s' "$1" | sed "s/'/''/g")"
  if [ -n "$OPENROUTER_KEY" ]; then
    key_line="open_router_api_key: '$(printf '%s' "$OPENROUTER_KEY" | sed "s/'/''/g")'"
  fi
  mkdir -p "$(dirname "$SETTINGS_FILE")" || return 1
  # Created empty and made private *before* the key goes in, so it is never briefly
  # readable by anyone else on the machine. chmod rather than a umask, because the
  # file may already exist from a seed that failed after this point, and truncating
  # an existing file keeps whatever mode it already had.
  : >"$SETTINGS_FILE" || return 1
  chmod 600 "$SETTINGS_FILE" 2>/dev/null
  cat >"$SETTINGS_FILE" <<EOF
projects:
- '$escaped'
user_type: personal
personal_use_contact: $SEED_CONTACT
EOF
  # Appended rather than interpolated as an empty line, so a sandbox with no key
  # gets the same file it has always had.
  [ -n "$key_line" ] && echo "$key_line" >>"$SETTINGS_FILE"
  return 0
}

# Seeding never fails the server: an agent that asked for a browser gets one, and a
# warning explains why the app looks emptier than expected.
#
# Must run before the backend launches. Config is a process-lifetime singleton that
# caches settings on first read, so a backend started against an unseeded home holds
# empty settings until it dies.
do_seed() {
  if ! fixture_present; then
    echo "warning: no fixture at $FIXTURE_DIR, starting with an empty app." >&2
    return 0
  fi

  echo "Seeding the sandbox from .agents/playwright_project..."

  if ! mkdir -p "$SEEDED_PROJECT_DIR"; then
    echo "warning: could not create $SEEDED_PROJECT_DIR, starting with an empty app." >&2
    return 0
  fi
  # `$FIXTURE_DIR/.` into an existing directory, not `$FIXTURE_DIR` into it: cp
  # would nest a second copy inside on the second attempt, and a second attempt is
  # exactly what the stamp-written-last retry produces. The nested copy is
  # invisible in the app and gets captured by the next snapshot.
  if ! cp -R "$FIXTURE_DIR/." "$SEEDED_PROJECT_DIR/"; then
    echo "warning: could not copy the fixture into $SEEDED_PROJECT_DIR." >&2
    return 0
  fi
  if ! write_seed_settings "$SEEDED_PROJECT_DIR/project.kiln"; then
    echo "warning: could not write $SETTINGS_FILE, the app will send you to /setup." >&2
    return 0
  fi

  # Last, so a failure at any step above leaves it absent and the next start
  # retries. Its contents are informational only — nothing ever reads them back.
  {
    echo "seeded_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "repo_head: $(cd "$PROJECT_ROOT" && git rev-parse --short HEAD 2>/dev/null)"
  } >"$SEED_STAMP" 2>/dev/null
}

# created_at<TAB>id<TAB>name per task, sorted. created_at is ISO-8601 with a Z
# suffix and so sorts correctly as text, which makes the earliest-created task
# first — the primary one, and the one whoever authors the fixture controls by
# creating it first.
seeded_task_lines() {
  local dir kiln created id name
  for dir in "$SEEDED_PROJECT_DIR"/tasks/*/; do
    kiln="${dir}task.kiln"
    [ -f "$kiln" ] || continue
    id="$(json_field "$kiln" id)"
    # No readable id, no row. ID_FIELD mints a fresh id when the datamodel loads a
    # file without one, so the value on disk is unknowable and no ui_state can name
    # this task — listing it could only produce a hint that lands on the task picker.
    [ -n "$id" ] || continue

    created="$(json_field "$kiln" created_at)"
    name="$(json_field "$kiln" name)"
    # An unreadable created_at is a weaker defect: the field has a default_factory,
    # so the task loads and the id above still addresses it. Sorting it last keeps
    # both properties — an empty sort key would sort *first* and crown a malformed
    # task "primary", while dropping the row would hide an id that works.
    [ -n "$created" ] || created="9999-12-31T23:59:59Z"

    printf '%s\t%s\t%s\n' "$created" "$id" "$name"
  done | sort
}

# Set by verify_seed_loaded, read by print_seed_hint: the seeded project's id when
# the backend confirmed it loaded, and empty otherwise. Sharing it is what keeps the
# two from disagreeing — the check warning that nothing loaded while the hint
# confidently names a project was the exact failure this replaced.
loaded_project_id=""

# get_projects catches every per-project load exception and continues, so a project
# that fails to load produces an app with zero projects and an agent redirected to
# /setup — visually identical to seeding never having run, and the hardest possible
# thing to diagnose from the outside. One assertion against a server we already
# waited for turns it into a sentence naming the cause.
#
# Reads the id from the *installed* copy rather than the committed fixture, because
# the question is whether the thing in this sandbox loaded. Against the fixture it
# would also fire after a branch switch, where the sandbox is perfectly healthy and
# the answer is `reset`, not "re-author the fixture".
#
# Matches the quoted id rather than checking for a non-empty array, so it also
# catches the case where some *other* project loaded. Never fails the server.
verify_seed_loaded() {
  local id body
  loaded_project_id=""

  # Nothing was installed in this sandbox, so there is nothing to assert about.
  [ -f "$SEEDED_PROJECT_DIR/project.kiln" ] || return 0

  id="$(json_field "$SEEDED_PROJECT_DIR/project.kiln" id)"
  body="$(curl -fsS --max-time 5 "$BACKEND_URL/api/projects" 2>/dev/null)"

  if [ -n "$id" ]; then
    case "$body" in
      *"\"$id\""*)
        loaded_project_id="$id"
        return 0
        ;;
    esac
  fi

  echo "warning: the seeded project is not loaded, so the app will show no projects" >&2
  echo "         and send you to /setup. Three things cause this:" >&2
  echo "           - you removed the project through the UI — expected, nothing to fix" >&2
  echo "           - this sandbox was seeded from an older fixture: run 'reset'" >&2
  echo "           - .agents/playwright_project is stale against this branch's" >&2
  echo "             datamodel: re-author it through the UI and run 'snapshot'" >&2
  echo "         No ui_state hint is printed below, because it would name a project" >&2
  echo "         the app does not have and land you on /setup anyway." >&2
}

# The app's setup gate has two steps disk cannot satisfy: the selected project and
# task live in localStorage, and the layout redirects to a task picker on mount
# without them, whatever URL you asked for. This prints the write that gets past it.
#
# All three commands, in this order, because playwright-cli's storage commands are
# fussier than they look: `localstorage-set` fails outright with no browser open,
# and re-running `open` against an already-open browser starts a fresh context that
# discards what was just written. So: open, write, then navigate again — and with
# `goto` rather than `reload`, since by then the page is sitting on the task picker
# it was redirected to, and reloading that stays there.
#
# Gated on verify_seed_loaded having confirmed the project with the backend, not on
# files being on disk: removing a project through the UI only unregisters it from
# settings and leaves project.kiln where it was, so disk presence would still print
# a hint that lands the agent on /setup — the exact symptom of an unseeded sandbox,
# and a confident wrong answer costs more than an admitted unknown.
#
# Printed on every start, seeded or not, because the browser profile is independent
# of the sandbox — an agent on a fresh profile needs this whether or not this
# particular start did the seeding.
print_seed_hint() {
  local project_name="" primary_id="" primary_name="" lines="" others=""

  if [ -n "$loaded_project_id" ]; then
    project_name="$(json_field "$SEEDED_PROJECT_DIR/project.kiln" name)"
    lines="$(seeded_task_lines)"
    primary_id="$(printf '%s' "$lines" | head -1 | cut -f2)"
    primary_name="$(printf '%s' "$lines" | head -1 | cut -f3)"

    if [ -z "$primary_id" ]; then
      echo "warning: the seeded project has no readable task, so no ui_state hint" >&2
      echo "         below. Without it the app redirects to a task picker." >&2
    fi
  fi

  # No hint to give. Still print the bare open command, which is all this script
  # printed before it seeded.
  if [ -z "$loaded_project_id" ] || [ -z "$primary_id" ]; then
    echo "    playwright-cli open $FRONTEND_URL"
    echo ""
    return 0
  fi

  echo "  Seeded project: ${project_name:-unknown} / ${primary_name:-unknown}"
  echo ""
  echo "  Land in the app (the layout redirects to a task picker without this):"
  echo "    playwright-cli open $FRONTEND_URL"
  echo "    playwright-cli localstorage-set ui_state '{\"current_project_id\":\"$loaded_project_id\",\"current_task_id\":\"$primary_id\",\"selected_model\":null}'"
  echo "    playwright-cli goto $FRONTEND_URL"
  echo ""

  others="$(printf '%s\n' "$lines" | tail -n +2 |
    awk -F'\t' 'NF { printf "%s%s (%s)", sep, $2, $3; sep = ", " }')"
  if [ -n "$others" ]; then
    echo "  Other tasks: $others"
    echo ""
  fi
}

# Whether this sandbox can make a live model call, said out loud on every start.
# An agent that has to infer it ends up either reporting a missing provider as a
# bug or assuming a key it does not have, and both cost a whole test lane.
#
# Reads settings.yaml rather than the environment, because the file is the answer:
# the app writes a key there when someone connects a provider through Settings, and
# the seed only writes one on the start that seeded. Which is also the one case
# this cannot fix silently — a sandbox seeded before OPENROUTER_QA_KEY was set
# keeps what it was seeded with, and rewriting the file behind the app's back would
# throw away a key pasted in by hand.
report_openrouter_key() {
  if grep -q '^open_router_api_key:' "$SETTINGS_FILE" 2>/dev/null; then
    echo "  OpenRouter is connected in this sandbox — live model calls will work,"
    echo "  and will spend real money against a key with a hard limit on it. Prefer"
    echo "  GPT-5.6 Luna and keep runs small. See .agents/skills/playwright/."
    echo ""
    return 0
  fi

  if [ -n "$OPENROUTER_KEY" ]; then
    echo "  OPENROUTER_QA_KEY is set, but this sandbox was seeded without it, so no"
    echo "  provider is connected. 'reset' reseeds with it (deleting this sandbox),"
    echo "  or connect OpenRouter through the app's Settings."
    echo ""
  fi
}

# Printed once both servers answer, from the cold-start path and the
# already-running path alike. They were drifting apart: an agent that ran `start`
# twice got a different set of instructions the second time.
print_ready_hints() {
  print_seed_hint
  report_openrouter_key
  echo "    .agents/scripts/playwright_server.sh stop"
  echo ""
}

do_start() {
  guard_not_real_home || return 1

  if backend_up && frontend_up; then
    # Something is serving, but not necessarily this sandbox's server, and seeding
    # only ever runs on the path below — so a KILN_DEV_HOME whose server somebody
    # else's `start` is holding would otherwise report success in silence and leave
    # the agent driving a different sandbox's app.
    #
    # Ownership is the question, so ask it directly. The stamp cannot answer it: it
    # is absent after any do_seed bail-out — no fixture on this branch, a failed copy
    # — and a sandbox that skipped seeding still owns the server it started, so a
    # stamp test accuses this sandbox of being someone else's while the hint below
    # correctly names its project.
    if ! pidfile_process_alive "$BACKEND_PID"; then
      echo "warning: something is already serving these ports and this sandbox" >&2
      echo "         ($RUN_DIR) did not start it — so the app you are about to" >&2
      echo "         drive belongs to a different sandbox, and anything you do in" >&2
      echo "         it lands there. Stop it, or point" >&2
      echo "         KILN_DEV_FRONTEND_PORT/KILN_DEV_BACKEND_PORT elsewhere." >&2
    fi
    verify_seed_loaded
    echo "Dev server already running at $FRONTEND_URL"
    echo ""
    print_ready_hints
    return 0
  fi

  # A half-up state — one port answering, the other not — is the leftover of a
  # crashed or partially stopped run. Starting the missing half on top of it
  # tends to produce a frontend talking to a backend from a previous session, so
  # clear both and start clean.
  if backend_up || frontend_up; then
    echo "Clearing a partially running dev server..."
    do_stop >/dev/null 2>&1
  fi

  if ! mkdir -p "$RUN_DIR"; then
    echo "error: could not create $RUN_DIR" >&2
    return 1
  fi

  # Again, now that the directory exists and `cd` inside the guard cannot fail. A
  # KILN_DEV_HOME whose missing component resolves back to the real home passes the
  # first check on the literal string, and the mkdir above is what makes it
  # resolvable — so this is the call that catches it, before anything is written.
  guard_not_real_home || return 1

  # Before the backend launches, and only once per sandbox. A sandbox an agent has
  # made a mess in is never quietly reverted — `reset` is how you ask for that.
  is_seeded || do_seed

  echo "Starting Kiln dev server (data in $RUN_DIR)..."

  env HOME="$RUN_DIR" KILN_PORT="$BACKEND_PORT" KILN_FRONTEND_PORT="$FRONTEND_PORT" \
    uv run python -m app.desktop.dev_server >"$BACKEND_LOG" 2>&1 &
  echo $! >"$BACKEND_PID"

  # `exec` so the recorded pid is npm itself rather than a subshell that npm
  # outlives — the kill walk starts from this pid, and a wrong root would leave
  # the server running.
  (cd "$WEB_UI_DIR" && exec env VITE_API_PORT="$BACKEND_PORT" VITE_BRANCH_NAME="" \
    npm run dev -- --port "$FRONTEND_PORT" --strictPort) >"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PID"

  # The backend builds its model list and imports a large dependency tree on
  # first start, so this is slower than a bare web server would suggest.
  local waited=0
  while [ "$waited" -lt 120 ]; do
    if backend_up && frontend_up; then
      verify_seed_loaded
      echo ""
      echo "  Kiln dev server ready: $FRONTEND_URL"
      echo ""
      print_ready_hints
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  echo "error: dev server did not come up within ${waited}s." >&2
  echo "       backend  $(backend_up && echo ok || echo down), see $BACKEND_LOG" >&2
  echo "       frontend $(frontend_up && echo ok || echo down), see $FRONTEND_LOG" >&2
  do_stop >/dev/null 2>&1
  return 1
}

# The only path that re-seeds. There is deliberately no drift detection on `start`:
# an agent has to be free to make a mess across many start/stop cycles without the
# next start quietly reverting it, and pulling in an updated fixture is a rare,
# deliberate act.
do_reset() {
  guard_not_real_home || return 1

  # The backend holds the run directory open, so stopping comes first — and a
  # failure to stop aborts before anything is deleted, rather than wiping the home
  # out from under a live server.
  if ! do_stop; then
    echo "error: not resetting while something is still answering." >&2
    return 1
  fi

  # Only delete something that is there, and re-check the guard first — with the
  # directory known to exist, `cd` inside the guard cannot fail, so the literal
  # string fallback that a missing component would trigger cannot let a path
  # resolving to the real home through. Nothing to delete is not an error: `reset`
  # on a never-started sandbox is just a seeded `start`, which re-checks the guard
  # for itself after its mkdir.
  if [ -d "$RUN_DIR" ]; then
    guard_not_real_home || return 1
    echo "Deleting $RUN_DIR..."
    if ! rm -rf "$RUN_DIR"; then
      echo "error: could not delete $RUN_DIR" >&2
      return 1
    fi
  fi

  do_start
}

# Capture the running sandbox's project back into the repo, for when you have built
# better initial state through the UI and want future sessions to start from it.
do_snapshot() {
  local count=0 first="" listing="" kiln src_dir

  # One guard call is enough here, unlike start and reset: snapshot writes nothing
  # into $RUN_DIR, and the missing-component path that defeats the guard's `cd` also
  # defeats `find`, which cannot traverse a component that does not exist either. So
  # the worst a bypass reaches is "no project found".
  guard_not_real_home || return 1

  # -print0 and read -d '' because project directory names contain spaces by
  # construction ("Kiln Projects/<name>"). A read loop rather than `mapfile -d ''`,
  # which needs bash 4.4 — stock macOS /bin/bash is 3.2, and under `set -u` the
  # resulting unset array aborts with "unbound variable" instead of a message.
  while IFS= read -r -d '' kiln; do
    count=$((count + 1))
    [ "$count" -eq 1 ] && first="$kiln"
    listing="$listing         $kiln
"
  done < <(find "$PROJECTS_DIR" -mindepth 2 -maxdepth 2 -name project.kiln -print0 2>/dev/null)

  if [ "$count" -eq 0 ]; then
    echo "error: no project found under $PROJECTS_DIR, nothing to capture." >&2
    return 1
  fi
  # Picking one silently would be a coin flip over which state gets committed.
  # Sorted, so whoever is deciding which project to delete sees a stable list
  # rather than whatever order the filesystem handed back.
  if [ "$count" -gt 1 ]; then
    echo "error: found $count projects under $PROJECTS_DIR:" >&2
    printf '%s' "$listing" | sort >&2
    echo "       Delete the ones you do not want through the UI, then re-run." >&2
    return 1
  fi

  src_dir="$(dirname "$first")"

  # An assertion on the shape of the path, because the next statement is rm -rf on
  # a variable and a mistake there deletes something that is not this fixture.
  case "$FIXTURE_DIR" in
    */.agents/playwright_project) ;;
    *)
      echo "error: refusing to mirror into $FIXTURE_DIR" >&2
      return 1
      ;;
  esac

  echo "Capturing $src_dir into $FIXTURE_DIR..."

  # Delete-then-copy rather than a merge: a run deleted through the UI must
  # disappear from the repo, and a merge would strand it there forever.
  rm -rf "$FIXTURE_DIR" || return 1
  mkdir -p "$FIXTURE_DIR" || return 1
  cp -R "$src_dir/." "$FIXTURE_DIR/" || return 1

  # A .git anywhere inside would be committed as a gitlink and break the fixture for
  # everyone who checks it out. No -type filter: `git worktree add` and submodules
  # make .git a regular *file* holding `gitdir: …`, which git treats as a repository
  # boundary exactly as it does a directory. Nothing this script does creates either
  # — git-sync clones live in ~/.git-projects, outside the searched "Kiln Projects",
  # so a git-synced project can never be the source here — but someone experimenting
  # by hand inside the sandbox project can, and the scrub costs one find.
  #
  # settings.yaml is never read or written here: it lives outside the project
  # directory, which is what keeps an authoring API key out of the repo by
  # construction rather than by anyone remembering.
  find "$FIXTURE_DIR" -name .git -prune -exec rm -rf {} + 2>/dev/null
  find "$FIXTURE_DIR" -name .DS_Store -delete 2>/dev/null

  echo ""
  (cd "$PROJECT_ROOT" && git status --short -- "$FIXTURE_DIR")
  echo ""
  echo "  Review that diff before committing: a snapshot captures whatever was in"
  echo "  the sandbox, including files you did not mean to create."
}

case "${1:-start}" in
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
  reset) do_reset ;;
  snapshot) do_snapshot ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    echo "error: unknown command: $1" >&2
    usage >&2
    exit 2
    ;;
esac
