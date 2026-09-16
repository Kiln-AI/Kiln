#!/usr/bin/env bash
# Audit one merge commit (default HEAD) for what its resolution changed, compared with git's own
# automatic merge of the same two parents. Needs git 2.36+ (--remerge-diff).
# usage: .agents/skills/merge-audit/scripts/audit_merge.sh [merge-sha]
#        CAP=<n> caps the printed diff (default 400 lines).
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
cd "$(git rev-parse --show-toplevel)"
REF="${1:-HEAD}"
M="$(git rev-parse --verify --quiet "${REF}^{commit}")" || { echo "not a commit: ${REF}" >&2; exit 2; }
SHORT="$(git rev-parse --short "${M}")"
NP="$(git rev-list --parents -n 1 "${M}" | wc -w | tr -d ' ')"; NP=$((NP - 1))
if [ "${NP}" -lt 2 ]; then echo "${SHORT} has one parent: not a merge commit, nothing to audit"; exit 0; fi
if [ "${NP}" -gt 2 ]; then echo "${SHORT} has ${NP} parents: this audit covers two-parent merges only" >&2; exit 2; fi
# Generated files are left out: they are regenerated, never resolved by hand.
# The client path matches the ruff exclude in pyproject.toml; the annotations are rewritten by CI.
EXCL=(
  ':!**/kiln_ai_server_client/**'
  ':!*.lock'
  ':!**/package-lock.json'
  ':!**/api_schema.d.ts'
  ':!libs/server/kiln_server/utils/agent_checks/annotations/*.json'
)
# Fixed prefixes and no colour, so a user's diff config cannot change what the scanner parses.
SHOW=(git show --remerge-diff --format= --no-color --src-prefix=a/ --dst-prefix=b/)
CAP="${CAP:-400}"
echo "== merge ${SHORT} ($(git log -1 --format='%s' "${M}"))"
echo "-- files the resolution changed (lines added/deleted against the automatic merge):"
STAT="$("${SHOW[@]}" --numstat "${M}" -- . "${EXCL[@]}")"
if [ -z "${STAT}" ]; then echo "   none: the merge added nothing of its own"; exit 0; fi
printf '%s\n' "${STAT}" | awk -F'\t' '{printf "   %s +%s/-%s\n", $3, $1, $2}'
DIFF="$("${SHOW[@]}" "${M}" -- . "${EXCL[@]}")"
echo "-- comments the resolution added:"
printf '%s\n' "${DIFF}" | python3 "${D}/comment_scan.py" -
echo "-- the resolution diff (read every line):"
printf '%s\n' "${DIFF}" | awk -v cap="${CAP}" -v sha="${SHORT}" \
  'NR <= cap { print } END { if (NR > cap) print "   ... " NR - cap " more lines: git show --remerge-diff " sha }'
