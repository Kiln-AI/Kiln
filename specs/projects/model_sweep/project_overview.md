---
status: draft
---

# Model Sweep

A morning routine that keeps Kiln's model list current without a human driving it. This is my productivity hackathon project (October 2026). Buy over build if there are cheap tools giving things away for free.

It will run in the morning, pull from the #models Slack channel to see any hints from anybody, then check if there are new models, run the tests, check for deprecations, and put up PRs.

The skill should post to the #models Slack channel as Claude as well, for example saying a PR is up when it is up. Then users can comment on those PRs for feedback and the Claude session will fix it.

In addition, this will also look at ALL models used in Kiln-AI projects, and track how stale those models are.

## Caveats

- Sometimes the PR has some breaking change. For example, in order to make a test pass we need to add a new param. These should trigger discussion. So the PR goes up and the discussion happens there. I don't want discussion to be on Slack. I want Claude to post on the PR as Claude, not as me.
- The assumption is: an easy model add / remove is one where there is simply a model change to `ml_model_list`. If we need to touch other files, or rejig things, then this needs some discussion.

## Context

- Today the flow is manual: someone posts a model link in #models and tags me, I tag the cloud @Claude with "read `.agents/skills/claude-maintain-models/SKILL.md` and follow its instructions", and the cloud session cannot run the paid tests, so the PR is finished locally.
- Steve is doing a Slack bot for the hackathon: a general one we can add to, plus PR staleness/velocity. This project should hand him the Slack side rather than build a second bot.
- The building blocks exist in the repo: `claude-maintain-models`, `kiln-check-deprecation`, `kiln-check-finetune-deprecation`, and `open-pr` under `.agents/skills/`.
