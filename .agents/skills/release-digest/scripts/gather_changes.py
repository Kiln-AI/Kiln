#!/usr/bin/env python3
"""Gather merged PRs that are on main but not yet in the latest release tag.

Outputs JSON to stdout (the authoritative change set for the next release) and a
human-readable summary to stderr. Uses the git commit RANGE (last_tag..origin/main)
as the source of truth, not merge dates -- a PR merged the same day a tag was cut
may already be in that release.
"""

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


def display_name(author: dict) -> str:
    login = author.get("login", "unknown")
    return TEAM.get(login) or author.get("name") or login


def login_from_email(email: str) -> str | None:
    """Extract the GitHub login from a github.com noreply commit email.

    Handles both `1234567+login@users.noreply.github.com` and the older
    `login@users.noreply.github.com` form. Returns None for other emails.
    """
    m = re.match(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", email or "")
    return m.group(1) if m else None


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR running {' '.join(cmd)}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main() -> None:
    # Make sure tags and remote main are current.
    subprocess.run(
        ["git", "fetch", "--tags", "--quiet", "origin"],
        capture_output=True,
        text=True,
    )

    last_tag = run(["git", "describe", "--tags", "--abbrev=0"])

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
    # constituent commit inside each PR -- otherwise "unmatched" balloons with commits
    # that are already itemized via their PR. PR numbers live in these subjects for both
    # merge-commit ("Merge pull request #N from ...") and squash ("Title (#N)") workflows.
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
        m = re.search(r"#(\d+)", subject)
        if m:
            num = int(m.group(1))
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

    prs = []
    for num in pr_numbers:
        view = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(num),
                "--json",
                "number,title,author,url,labels,mergedAt,additions,deletions,body",
            ],
            capture_output=True,
            text=True,
        )
        if view.returncode != 0:
            # PR number referenced but not viewable (e.g. from a fork / different repo).
            continue
        data = json.loads(view.stdout)
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
                "author_login": author.get("login", "unknown"),
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
    }
    print(json.dumps(output, indent=2))

    # Human summary to stderr.
    print(
        f"\nChanges since {last_tag} on {head_ref}: "
        f"{len(prs)} PRs + {len(direct_commits)} direct commits "
        f"across {len(commit_lines)} mainline commits.",
        file=sys.stderr,
    )
    if excluded:
        print(
            f"Excluded {len(excluded)} PR(s) from non-teammates: "
            + ", ".join(f"#{e['number']} ({e['author_login']})" for e in excluded),
            file=sys.stderr,
        )
    if not prs and not direct_commits:
        print(
            "Nothing unreleased -- main is even with the latest tag.", file=sys.stderr
        )


if __name__ == "__main__":
    main()
