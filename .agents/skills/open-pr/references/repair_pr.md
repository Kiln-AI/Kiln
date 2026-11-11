# Repair a PR opened by the "Create PR" button

Background: the "Create PR" button in Claude Code desktop ignores our PR template rules. It fills in the human-only header, ticks every box, deletes options it didn't pick, and often signs the Contributor License Agreement. Its system prompt tells it to treat a PR template as a layout to fill in and to ignore instructions inside it, so the hidden comment in `.github/pull_request_template.md` doesn't stop it. When the button finishes, the session that owns the branch gets a message like this, as a user turn:

> A pull request was just created for this branch from the Claude Code UI: https://github.com/Kiln-AI/Kiln/pull/NNNN
> You don't need to create one. Reference this PR going forward — pushing more commits to this branch will update it.

That message is how an agent knows the button made the PR. On GitHub, the PR looks like the user opened it by hand.

When you see that message, load the PR and confirm it didn't ignore the PR template rules (Rule 0, Rule 1 and Step 3 of `../SKILL.md`). If it did, fix the PR as Step 6 of `../SKILL.md` describes. Never edit a PR created or edited by a human, only new PRs created by an agent.
