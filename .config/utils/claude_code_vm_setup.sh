#!/usr/bin/env bash
# The setup script for a Claude Code cloud environment. Paste the contents of
# this file into the environment's "Setup script" field. The whole setup, with
# the environment's other fields and what to expect: claude_cloud_setup.md.
#
# It fetches .config/utils/setup_env.sh and runs it, rather than being a copy of
# it. That is the whole point: setup_env.sh changes, and a pasted copy of it goes
# stale the moment it does, silently, until someone notices a VM missing
# something. This file is small and its contents almost never change, so pasting
# it once is the last manual step.
#
# It runs at environment-build time, before any repo is checked out, so it cannot
# read anything from the repo — hence fetching over HTTPS rather than reading a
# path. Kiln is public, so no credentials are involved.
#
# KILN_SETUP_REF overrides the ref, to try a branch's setup_env.sh without
# editing this file.
#
# The environment this runs in needs Custom network access, with these in its
# allowed domains, or the corresponding step below fails:
#
#   raw.githubusercontent.com          this script's own fetch
#   cdn.playwright.dev                 the browsers --add-playwright installs
#   playwright.download.prss.microsoft.com   Playwright's download fallback
#
# plus "also include default list of common package managers" for npm, PyPI and
# apt. On the default Trusted policy the browser downloads get a 403.
set -u

REF="${KILN_SETUP_REF:-main}"
URL="https://raw.githubusercontent.com/Kiln-AI/Kiln/$REF/.config/utils/setup_env.sh"

# Nothing below exits non-zero. A cloud setup script that fails stops the session
# from ever starting, which is worse than a machine that comes up unprovisioned
# and says so — the same reason setup_env.sh is run with --best-effort.
script="$(mktemp)" || exit 0
trap 'rm -f "$script"' EXIT

echo "Fetching setup_env.sh from $REF..."
# --retry without --retry-all-errors on purpose: it retries timeouts and 5xx, and
# fails immediately on a 404, which is what a wrong ref deserves rather than four
# identical errors.
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$script" "$URL"; then
  echo "" >&2
  echo "  ! Could not download $URL" >&2
  echo "    This machine is NOT set up for Kiln. In a session, run:" >&2
  echo "        bash .config/utils/setup_env.sh --upgrade-tools" >&2
  echo "" >&2
  exit 0
fi

# A captive proxy or a renamed path answers 200 with an HTML error page, and
# piping that into bash produces pages of syntax errors instead of one clear line.
if ! head -1 "$script" | grep -q '^#!/usr/bin/env bash'; then
  echo "" >&2
  echo "  ! $URL did not return a shell script. First line:" >&2
  head -1 "$script" >&2
  echo "    Check that the ref '$REF' still exists." >&2
  echo "" >&2
  exit 0
fi

# --best-effort is what keeps setup_env.sh's own failures from stopping the
# session; the rest is the cloud VM profile setup_env.sh documents, plus the
# Playwright browsers and playwright-cli (see .agents/skills/playwright/).
bash "$script" \
  --upgrade-tools \
  --best-effort \
  --warm-cache \
  --create-startup-script \
  --add-playwright

exit 0
