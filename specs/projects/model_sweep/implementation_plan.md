---
status: draft
---

# Implementation Plan: Model Sweep

## Phases

- [x] Phase 1 (2026-10-01, PRs #1849, #1850, #1851): Cloud routine smoke in the operator's cloud environment. A self-contained prompt (`routine_prompt.md`) that runs the three existing skills with the consent gates pre-answered, paid tests on. Create disabled, run once by hand, read the run log. Record: did it finish, PR author identity, Slack connector available or not, duration, cost.
- [x] Phase 2 (2026-10-01): prompt fixes applied (GitHub MCP tools, targeted checks, local model list for deprecations, uv upgrade), connectors trimmed to Slack, schedule enabled. Still open on the operator's side: paste the team's VM setup script into the operator's cloud environment and add `remote-config.getkiln.ai` and `api.together.ai` to its allowlist.
- [ ] Phase 3: Identity and announcement: PR author as Claude, one line in #models per PR. Through the team Slack bot and an org GitHub App when they exist; otherwise the fallbacks in the functional spec.
- [ ] Phase 4: Staleness report as a living GitHub issue over Kiln and kiln_server.
- [ ] Phase 5: Feedback loop: a 13:00 comments-only run that answers PR comments and pushes in-scope fixes.
- [ ] Phase 6: Move the prompt into a repo skill, `.agents/skills/kiln-model-sweep/`, with the deterministic scripts from the architecture doc, so the local host and the v2 Actions host run the same code. Local scheduled task as the fallback host.
- [x] Added 2026-10-01: remote-config publish check in every run (head `main` into base `remote_config`, human merges, routine never merges). Pending first real exercise once #1810 is merged.
- [x] 2026-10-02: the routine fetches the skill from the PR branch at run time; the inline copy is gone. On merge, point it at `main`.
