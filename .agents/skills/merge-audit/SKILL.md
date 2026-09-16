---
name: merge-audit
description: Audit a merge commit for what its conflict resolution changed, before it is pushed. Invoke after any `git merge` you run that produced a merge commit (main into a feature branch, a feature branch into an integration branch, a sync), and before pushing any merge a human will later review.
allowed-tools: Read Grep Glob Bash Write Edit
---

# merge-audit: nothing enters a branch through a merge unexplained

A merge commit can contain code that neither side wrote: a conflict resolution typed by hand, an editor re-sorting imports while a conflicted file was open, a lint config tweak made so CI passes. No PR ever shows those lines. They reach a reviewer months later as "why is half of this formatting?", and the reviewer stops trusting the whole branch. This skill makes every merge answer that question before it is pushed.

## When

After every `git merge` you run that produced a merge commit, trivial ones included. A fast-forward, a rebase and a squash have no merge commit and nothing to audit; the script says so and exits.

## The audit

1. Merge with `git merge --no-ff <source>`. Resolve conflicts by hand. Do not let an editor save or format the file during resolution; if one did, step 2 shows what it changed.
2. Run `.agents/skills/merge-audit/scripts/audit_merge.sh [sha]` (default `HEAD`) from anywhere inside the worktree. It is built on `git show --remerge-diff`: git redoes the merge automatically and diffs the committed result against it, so the output is exactly the lines the resolution added or deleted, deletions included. Three sections:
   - **Files the resolution changed**, with line counts. `none` means the merge added nothing of its own, and the audit is over.
   - **Comments the resolution added.** A comment written while resolving a conflict that narrates the resolution or explains an absence is deleted before the push. The code is the source of truth. The scanner skips test files and does not see the continuation lines of a block comment, so read the diff too.
   - **The resolution diff.** Read every line. Real resolution code is named in the notes (step 3). A block whose lines match one side in a different order is an editor or a second sorter at work: restore the block from the side that owned the file. Anything you did not intend is removed.
3. Amend the merge commit message with a `Merge-notes:` trailer (a git trailer, so `git interpret-trailers` can read it): one line per file that keeps a hit, saying what was added and why. A merge that added nothing of its own says `Merge-notes: none`. The trailer is what answers "why is this hunk here" when the branch is reviewed later, and it stays in history after a squash in a way a chat message does not.
4. Run the repo checks. Push your own branch. For a branch other people build on, hand its owner the push command together with the audit output.

## Rules

- A lint or formatter config change is never made inside a merge, and never made "to fix CI" without first finding out why CI and the local run disagree: run the tool on the base commit, read the failing log. When the cause is a local tool (an editor's organize-imports, a second import sorter in the dev dependencies), fix the tool, not the config.
- No unexplained hit is pushed. Undone or named, nothing else.

## Limits

- Needs git 2.36 or newer for `--remerge-diff`. Two-parent merges only.
- A merge made with `-s ours` or `-X theirs` shows the whole strategy divergence as resolution edits; name the strategy in the notes instead of listing lines.
- Generated files (the generated server client, lockfiles, `api_schema.d.ts`, the agent-check annotations) are left out of the audit; they are regenerated, never resolved by hand.
- The audit sees what changed during resolution. What the source branch itself brought in, churn included, is that branch's review, not the merge's.

## Scripts

- `.agents/skills/merge-audit/scripts/audit_merge.sh [sha]`: the three sections above. `CAP=<n>` changes the printed diff cap (default 400 lines; the rest is one `git show --remerge-diff` away).
- `.agents/skills/merge-audit/scripts/comment_scan.py <base> <tip> [paths...]` or `... | comment_scan.py -`: added comment lines that narrate a change, explain an absence, or carry a dated marker. Also usable on any branch diff.
