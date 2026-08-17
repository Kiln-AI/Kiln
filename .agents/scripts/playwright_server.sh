#!/usr/bin/env bash
# Start a Kiln dev server for an agent to drive with playwright-cli.
#
#   .agents/scripts/playwright_server.sh start|stop|status
#
# This is not for running the e2e suite: playwright.config.ts starts its own
# servers and would refuse to share these. It exists so an agent can look at the
# UI it is changing — open a page, click through it, take a screenshot — which
# needs a server that outlives a single command, where the suite's servers live
# and die inside one `playwright test` run.
#
# See .agents/USING_PLAYWRIGHT.md.

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
# real Kiln data of whoever is running it. Override to work against real projects.
RUN_DIR="${KILN_DEV_HOME:-$WEB_UI_DIR/.agent_dev_home}"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"

FRONTEND_URL="http://localhost:$FRONTEND_PORT"
BACKEND_URL="http://localhost:$BACKEND_PORT"

usage() {
  cat <<EOF
Usage: playwright_server.sh [start|stop|status]

  start   Start the backend and frontend, wait until both answer, print the URL.
          Already running is success, not an error.
  stop    Stop both.
  status  Report whether both are answering.

Frontend $FRONTEND_URL, backend $BACKEND_URL. Override the ports with
KILN_DEV_FRONTEND_PORT / KILN_DEV_BACKEND_PORT, and the data directory with
KILN_DEV_HOME (default $WEB_UI_DIR/.agent_dev_home).
EOF
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

stop_from_pidfile() {
  # $1 = pid file, $2 = signal.
  local file="$1" pid command
  [ -f "$file" ] || return 0
  pid="$(cat "$file" 2>/dev/null)"
  [ -n "$pid" ] || return 0

  # A pid file can outlive its process, and the number in it can by then belong
  # to something else entirely — on a developer's machine, plausibly their
  # editor. Kill only a pid that still looks like what this script starts.
  command="$(ps -o args= -p "$pid" 2>/dev/null)"
  case "$command" in
    *dev_server* | *"npm run dev"* | *vite* | *node*) ;;
    *) return 0 ;;
  esac

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

do_start() {
  if backend_up && frontend_up; then
    echo "Dev server already running at $FRONTEND_URL"
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
      echo ""
      echo "  Kiln dev server ready: $FRONTEND_URL"
      echo ""
      echo "    playwright-cli open $FRONTEND_URL"
      echo "    .agents/scripts/playwright_server.sh stop"
      echo ""
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

case "${1:-start}" in
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
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
