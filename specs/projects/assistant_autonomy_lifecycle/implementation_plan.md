---
status: complete
---

# Implementation Plan: Assistant Autonomy Lifecycle (Kiln repo)

Branch `leonard/assistant-autonomy-lifecycle` off `leonard/assistant-subagents`; PR back into `leonard/assistant-subagents`. Details: `functional_spec.md` + `architecture.md` (this folder). kiln_server phases live in that repo's mirror folder.

## Phases

- [ ] Phase 1: Desktop FR1 — delete `disable_auto_mode` interceptions, add stale-call backstop, tear down `clear_auto_flag`/`resolve_terminal`/`on_auto_flag_cleared`, rehydration refusal, golden scenario updates (architecture §3.1, §5, §6)
- [ ] Phase 2: Desktop FR2/FR3 — `intercept_spawn_requires_auto`, generalized consent event + enable/decline routes, delete first-spawn consent machinery (architecture §3.2–§3.4)
- [ ] Phase 3: Web UI FR2/FR3/FR5 — consent dialog spawn variant, delete `SubagentConsentBox`, observer no-fake-off + bounded re-attach + footer indicator (architecture §4)
