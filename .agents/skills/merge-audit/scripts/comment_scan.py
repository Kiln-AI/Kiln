#!/usr/bin/env python3
"""Comment lines added in a diff that narrate the change instead of explaining the code.

usage: .agents/skills/merge-audit/scripts/comment_scan.py <base> <tip> [path ...]
       ... | .agents/skills/merge-audit/scripts/comment_scan.py -     (a unified diff on stdin)

A hit is an added line whose comment part matches a narration phrase: the change's history
("previously", "no longer", "used to", "now that", "moved from"), an absence ("no X here",
"handled elsewhere"), compatibility kept for something that never shipped, a dated marker, or
the diff talking about itself ("this change", "this PR"). The comment part is `#` or `//` to the
end of the line (also right after `;`), a `<!--`, `/*` or `{/*` opener, or a line that starts
with `*` inside a block comment. Continuation lines of a block comment that carry no marker, and
docstrings, are not scanned. Test files (by name) and docs are skipped. A hit is a candidate, not
a verdict."""

import re
import subprocess
import sys


def emit(*parts: object) -> None:
    sys.stdout.write(" ".join(str(p) for p in parts) + "\n")


PHRASES = [
    r"\bpreviously\b",
    r"\bno longer\b",
    r"\b(was|were) removed\b",
    r"\bused to\b",
    r"\bnow that\b",
    r"\bmoved (from|here|to)\b",
    r"\bno \w+ here\b",
    r"\bnot needed here\b",
    r"\bhandled (elsewhere|by|in)\b",
    r"\bkept for (backward|compat)",
    r"\bbackward[- ]compat",
    r"\bthis (change|pr|diff|commit)\b",
    r"\bas of (20\d\d|now)\b",
    r"\b20\d\d-\d\d-\d\d\b",
    r"\(\d\d-\d\d\)",
    r"\bpreview \(",
    r"\bthe old (way|code|version)\b",
    r"\blegacy path (kept|remains)\b",
    r"\bleft (in place|as is) (for|because)\b",
    r"\bwe (just|now) (added|removed|moved|renamed)\b",
    r"\bafter (this|the) (change|refactor)\b",
]
NARR = re.compile("|".join(PHRASES), re.I)
COMMENT = re.compile(r"(?:^\s*\*\s*|(?:^|[\s;])(?:#|//|<!--|/\*|\{/\*)\s*)(.*)$")
FILE_HEADER = re.compile(r'^diff --git "?a/.*?"? "?b/(.+?)"?$')
SKIP_PATH = re.compile(
    r"(^|/)(test_[^/]*|conftest\.py|[^/]*\.(test|spec)\.[jt]sx?)$|\.(md|txt|rst)$"
)


def read_diff(args: list[str]) -> str:
    if args and args[0] == "-":
        return sys.stdin.read()
    if len(args) >= 2:
        done = subprocess.run(
            [
                "git",
                "diff",
                "-U0",
                "--no-color",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                args[0],
                args[1],
                "--",
                *args[2:],
            ],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            sys.exit(done.stderr.strip() or "git diff failed")
        return done.stdout
    sys.exit(__doc__)


path = None
ln = 0
hits = []
unattributed = 0
for line in read_diff(sys.argv[1:]).splitlines():
    header = FILE_HEADER.match(line)
    if header:
        path = header.group(1)
        continue
    if line.startswith(("+++ ", "--- ", "\\ ")):
        continue
    if line.startswith("@@"):
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
        if m:
            ln = int(m.group(1)) - 1
        continue
    if line.startswith(" "):
        ln += 1
        continue
    if line.startswith("+"):
        ln += 1
        if path is None:
            unattributed += 1
            continue
        if SKIP_PATH.search(path):
            continue
        m = COMMENT.search(line[1:])
        if m and NARR.search(m.group(1)):
            hits.append((path, ln, m.group(1).strip()[:110]))
for path, ln, text in hits:
    emit(f"{path}:{ln}  {text}")
emit(f"{len(hits)} candidate narration comment(s)")
if unattributed:
    emit(
        f"{unattributed} added line(s) had no `diff --git` header and were not scanned"
    )
