# Routine prompt: Kiln model sweep

The cloud routine's message is a short run-settings block followed, verbatim, by the body of `.agents/skills/kiln-model-sweep/SKILL.md` (everything after its `---` separator). The skill is generic; the settings block is where the operator's channel id and Slack user id live. Keep the two copies of the body identical.

```
Run settings for this routine:

- Models channel: <name> (channel id <id>).
- SLACK_CC_USER_ID: <the reviewer's Slack user id>.
- SLACK_MODELS_WEBHOOK and SLACK_PRS_WEBHOOK are set in this environment.
```

Then the skill body.
