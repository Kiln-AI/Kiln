#!/usr/bin/env python3
"""Gather merged PRs that are on main but not yet in the latest release tag.

Outputs JSON to stdout (the authoritative change set for the next release) and a
human-readable summary to stderr. Uses the git commit RANGE (last_tag..origin/main)
as the source of truth, not merge dates -- a PR merged the same day a tag was cut
may already be in that release.
"""

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys

# The five teammates whose work goes in the recap, keyed by GitHub login. The value
# is the preferred display name (takes priority over the GitHub profile name, which
# some leave unset or lowercased). PRs from any login NOT in this map are excluded
# from the recap (reported separately as excluded_prs). Add new teammates here.
TEAM = {
    "sfierro": "Sam Fierro",
    "leonardmq": "Leonard Q. Marcq",
    "chiang-daniel": "Daniel Chiang",
    "tawnymanticore": "Mike Chatzidakis",
    "scosman": "Steve Cosman",
}

# PR-number markers in a mainline commit subject. Anchored so we only match a real
# merged-PR reference -- a squash subject `Title (#456)` or a merge subject
# `Merge pull request #456 from ...` -- rather than any `#123` issue ref that might
# also appear mid-subject (which would pick the wrong number or misclassify a
# direct-to-main commit as a PR).
MERGE_RE = re.compile(r"^Merge pull request #(\d+)\b")
SQUASH_RE = re.compile(r"\(#(\d+)\)\s*$")

# Fields requested from `gh pr view` for each PR.
PR_FIELDS = "number,title,author,url,labels,mergedAt,additions,deletions,body"


def display_name(author: dict) -> str:
    """Return the preferred display name for a PR/commit author dict."""
    login = author.get("login", "unknown")
    return TEAM.get(login) or author.get("name") or login


def login_from_email(email: str) -> str | None:
    """Extract the GitHub login from a github.com noreply commit email.

    Handles both `1234567+login@users.noreply.github.com` and the older
    `login@users.noreply.github.com` form. Returns None for other emails.
    """
    m = re.match(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", email or "")
    return m.group(1) if m else None


def pr_number_from_subject(subject: str) -> int | None:
    """Return the merged-PR number from a mainline commit subject, or None.

    Matches squash subjects (`... (#N)`) and merge-commit subjects
    (`Merge pull request #N ...`) only; a bare `#N` elsewhere is ignored.
    """
    m = SQUASH_RE.search(subject) or MERGE_RE.match(subject)
    return int(m.group(1)) if m else None


def run(cmd: list[str]) -> str:
    """Run a command and return its stdout, exiting with its stderr on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(f"ERROR running {' '.join(cmd)}:\n{result.stderr}\n")
        sys.exit(1)
    return result.stdout.strip()


def require_gh() -> None:
    """Exit early with a clear message if `gh` is missing or unauthenticated."""
    try:
        status = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True
        )
    except FileNotFoundError:
        sys.stderr.write(
            "ERROR: GitHub CLI (gh) is not installed. Install it from https://cli.github.com.\n"
        )
        sys.exit(1)
    if status.returncode != 0:
        sys.stderr.write(
            "ERROR: GitHub CLI (gh) is not authenticated. Run 'gh auth login'.\n"
        )
        sys.exit(1)


def fetch_pr(num: int) -> tuple[int, dict | None, str]:
    """Fetch one PR's metadata via `gh pr view`. Returns (num, data|None, error)."""
    view = subprocess.run(
        ["gh", "pr", "view", str(num), "--json", PR_FIELDS],
        capture_output=True,
        text=True,
    )
    if view.returncode != 0:
        return num, None, view.stderr.strip()
    try:
        return num, json.loads(view.stdout), ""
    except json.JSONDecodeError as e:
        return num, None, str(e)


def resolve_base_tag(args: argparse.Namespace) -> str:
    """Pick the tag to compare against, honoring --since / --pre-release overrides.

    Default: the newest tag reachable from HEAD (`git describe`). But when the newest
    tag is a just-cut pre-release (main is already even with it), that baseline yields
    an empty range -- so `--pre-release` steps back one tag to recap what went INTO the
    pre-release, and `--since TAG` lets the caller name the baseline explicitly.
    """
    latest = run(["git", "describe", "--tags", "--abbrev=0"])
    if args.since:
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{args.since}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            sys.stderr.write(f"ERROR: --since tag {args.since!r} does not exist.\n")
            sys.exit(1)
        return args.since
    if args.pre_release:
        # The newest tag is a pre-release still being QA'd; baseline is the tag before
        # it, so the range covers exactly what the pre-release contains.
        prior = run(["git", "describe", "--tags", "--abbrev=0", f"{latest}^"])
        sys.stderr.write(
            f"Pre-release mode: newest tag {latest} treated as the release being "
            f"QA'd; comparing against the prior tag {prior}.\n"
        )
        return prior
    return latest


def main() -> None:
    """Compute the unreleased change set and print it as JSON to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pre-release",
        action="store_true",
        help="Treat the newest tag as a just-cut pre-release and compare against the "
        "tag before it (recaps what the pre-release contains).",
    )
    group.add_argument(
        "--since",
        metavar="TAG",
        help="Explicit base tag to compare against, overriding auto-detection.",
    )
    args = parser.parse_args()

    require_gh()

    # Refresh tags + origin/main. A fetch failure isn't fatal (offline runs with
    # recent refs are still useful), but warn loudly since the digest could be stale.
    fetch = subprocess.run(
        ["git", "fetch", "--tags", "--quiet", "origin"],
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        sys.stderr.write(
            "WARNING: 'git fetch' failed -- digest may be based on stale refs/tags.\n"
        )

    last_tag = resolve_base_tag(args)

    # Prefer origin/main; fall back to local main if there's no remote-tracking ref.
    head_ref = "origin/main"
    check = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", head_ref],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        head_ref = "main"

    rng = f"{last_tag}..{head_ref}"

    # Subjects on the mainline only. --first-parent gives one node per merged PR
    # (the merge/squash commit) plus genuine direct-to-main commits, instead of every
    # constituent commit inside each PR -- otherwise direct commits would balloon with
    # commits that are already itemized via their PR.
    subjects = run(
        ["git", "log", rng, "--first-parent", "--format=%H%x1f%an%x1f%ae%x1f%s"]
    )
    commit_lines = [line for line in subjects.splitlines() if line.strip()]

    pr_numbers: list[int] = []
    direct_commits = []
    excluded = []
    seen: set[int] = set()
    for line in commit_lines:
        sha, an, ae, subject = (*line.split("\x1f", 3), "", "", "")[:4]
        num = pr_number_from_subject(subject)
        if num is not None:
            if num not in seen:
                seen.add(num)
                pr_numbers.append(num)
            continue
        # A direct-to-main commit (no PR). Attribute it to its author and list it
        # under that person, same as a PR but with no PR number. Apply the team filter.
        login = login_from_email(ae)
        if login in TEAM:
            direct_commits.append(
                {
                    "sha": sha[:9],
                    "title": subject,
                    "author_login": login,
                    "author_name": TEAM[login],
                }
            )
        else:
            excluded.append(
                {"number": None, "title": subject, "author_login": login or an}
            )

    # Fetch PR metadata in parallel (network-bound), then process in PR-number order
    # so output is deterministic regardless of completion order.
    fetched: dict[int, tuple[dict | None, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for num, data, err in executor.map(fetch_pr, pr_numbers):
            fetched[num] = (data, err)

    prs = []
    unresolved = []
    for num in pr_numbers:
        data, err = fetched[num]
        if data is None:
            # Don't silently drop a PR -- surface it so the digest is visibly partial.
            unresolved.append({"number": num, "error": err})
            sys.stderr.write(f"WARNING: could not load PR #{num}: {err}\n")
            continue
        author = data.get("author") or {}
        login = author.get("login", "unknown")
        if login not in TEAM:
            # Not one of the five teammates -- excluded from the recap, but reported
            # so the omission is visible rather than silent.
            excluded.append(
                {
                    "number": data["number"],
                    "title": data["title"],
                    "author_login": login,
                }
            )
            continue
        prs.append(
            {
                "number": data["number"],
                "title": data["title"],
                "author_login": login,
                "author_name": display_name(author),
                "url": data["url"],
                "labels": [label["name"] for label in data.get("labels", [])],
                "merged_at": data.get("mergedAt"),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
                "body": (data.get("body") or "")[:600],
            }
        )

    output = {
        "last_tag": last_tag,
        "head_ref": head_ref,
        "range": rng,
        "commit_count": len(commit_lines),
        "pr_count": len(prs),
        "prs": prs,
        "direct_commits": direct_commits,
        "excluded_prs": excluded,
        "unresolved_prs": unresolved,
    }
    sys.stdout.write(json.dumps(output, indent=2) + "\n")

    # Human summary to stderr.
    sys.stderr.write(
        f"\nChanges since {last_tag} on {head_ref}: "
        f"{len(prs)} PRs + {len(direct_commits)} direct commits "
        f"across {len(commit_lines)} mainline commits.\n"
    )
    if excluded:
        sys.stderr.write(
            f"Excluded {len(excluded)} change(s) from non-teammates: "
            + ", ".join(
                f"#{e['number']} ({e['author_login']})"
                if e["number"] is not None
                else f"{e['title']!r} ({e['author_login']})"
                for e in excluded
            )
            + "\n"
        )
    if unresolved:
        sys.stderr.write(
            f"WARNING: {len(unresolved)} PR(s) could not be loaded: "
            + ", ".join(f"#{u['number']}" for u in unresolved)
            + "\n"
        )
    if not prs and not direct_commits:
        sys.stderr.write("Nothing unreleased -- main is even with the latest tag.\n")


if __name__ == "__main__":
    main()
