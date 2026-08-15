#!/usr/bin/env bash
# Get the current checkout ready to build and test, and fail fast if the
# environment itself is wrong.
#
# Run this before your first build or test run: on a new branch, and at the start
# of a cloud sandbox session. It is cheap and safe to re-run — with a warm cache
# both installs are close to no-ops.
#
# It does not build an environment. That is `.config/utils/setup_env.sh`.

set -uo pipefail

UV_MIN=0.10.0
PYTHON_MIN_MINOR=13

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

bad_environment() {
  cat >&2 <<EOF

  ✗ $1

    This environment cannot build Kiln. Repair it with:

        bash .config/utils/setup_env.sh --upgrade-tools

    In a Claude Code cloud sandbox, seeing this usually means the environment's
    VM setup script did not run, or ran against a different image.

EOF
  exit 1
}

# ── Hard dependencies ─────────────────────────────────────────────────────────
# Check uv before syncing, not after. uv older than $UV_MIN cannot parse this
# repo's relative `exclude-newer`; instead of failing it re-resolves the whole
# dependency graph and rewrites uv.lock with a broken dependency set. Running a
# sync first would do the damage this check exists to prevent.
command -v uv >/dev/null 2>&1 || bad_environment "uv is not installed."

UV_VERSION="$(uv --version 2>/dev/null | awk '{print $2}')"
if [ "$(printf '%s\n%s\n' "$UV_MIN" "$UV_VERSION" | sort -V | head -1)" != "$UV_MIN" ]; then
  bad_environment "uv $UV_VERSION is older than $UV_MIN, and would corrupt uv.lock."
fi

command -v npm >/dev/null 2>&1 || bad_environment "npm is not installed."

# ── Sync this branch ──────────────────────────────────────────────────────────
echo "Syncing dependencies for $(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo 'this checkout')..."

# npm install rather than npm ci: it is incremental, so a warm node_modules makes
# it near-free, where npm ci would empty and refill the directory every time.
(cd "$PROJECT_ROOT" && uv sync --frozen --all-packages) &
py_pid=$!
(cd "$PROJECT_ROOT/app/web_ui" && npm install --no-fund --no-audit) &
npm_pid=$!

py_status=0
wait "$py_pid" || py_status=$?
npm_status=0
wait "$npm_pid" || npm_status=$?

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
probe=$(
  cd "$PROJECT_ROOT" && uv run --frozen python -c \
    'import sys, importlib.util as u; print(sys.version_info[0], sys.version_info[1], u.find_spec("tkinter") is not None)' \
    2>/dev/null
)
read -r py_major py_minor has_tk <<<"$probe"

if [ -z "${py_major:-}" ]; then
  bad_environment "could not run Python from .venv."
fi

if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt "$PYTHON_MIN_MINOR" ]; }; then
  bad_environment "the virtualenv is Python $py_major.$py_minor, but 3.$PYTHON_MIN_MINOR or newer is required."
fi

if [ "$has_tk" != "True" ]; then
  bad_environment "this Python has no tkinter, so some tests and the OpenAPI schema scripts cannot run."
fi

echo "Ready. Python $py_major.$py_minor, uv $UV_VERSION."
