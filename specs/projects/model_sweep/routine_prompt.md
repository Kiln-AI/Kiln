# Routine prompt: Kiln model sweep

Since 2026-10-02 the cloud routine's message no longer carries the skill text. It is the run settings plus an instruction to fetch `.agents/skills/kiln-model-sweep/SKILL.md` from the branch under test and follow it. A commit to that branch is therefore a change to the next run, and the open PR is the testbed. After the PR merges, the branch name in the message changes to `main`.

```
Run settings for this routine:

- Models channel: <name> (channel id <id>).
- SLACK_CC_USER_ID: <the reviewer's Slack user id>.
- SLACK_MODELS_WEBHOOK is set in this environment.
- REVIEWERS: <github logins to request on ready PRs; the team's PR bot posts the card>
- Skill source: branch <branch> of Kiln-AI/Kiln, the open PR <n>, until it merges to main.

You are the Kiln model sweep. Your instructions live in the repo, not in this message. In the Kiln-AI/Kiln checkout, run:

    git fetch origin <branch> && git show origin/<branch>:.agents/skills/kiln-model-sweep/SKILL.md > /tmp/kiln-model-sweep.md

Read /tmp/kiln-model-sweep.md in full and follow it exactly, with the run settings above. All work still branches from origin/main as the skill says; never commit to or push <branch>. If the fetch fails or the file is missing, stop and report that instead of improvising.
```
