---
status: complete
---

# Implementation Plan: Code Conventions Skills

## Phases

- [x] Phase 1: Kiln — `kiln-conventions` skill: `conventions_gate.py` + tests + `gate_config.json` + `gate_allow.txt`, gate calibration and history-comment baseline, `rules.md`, `SKILL.md`, references (`core.md`, `server_desktop.md`, `web_ui.md`), wiring (`AGENTS.md`, code review guidelines, `kiln-ui` pointer). Branch `leonard/code-conventions-skills` → Kiln PR.
- [x] Phase 2: kiln_server — `kiln-server-conventions` skill: its own copy of the rules and gate (started from Kiln's), `gate_config.json` + `gate_allow.txt`, `SKILL.md`, references (`api.md`, `jobs_pipelines.md`), wiring (`AGENTS.md`, code review guidelines, `utils/setup_claude.sh`). Separate kiln_server worktree and branch `leonard/code-conventions-skills` → kiln_server PR.
- [ ] Phase 3: Kiln comment sweep — fix every `history-comment` hit from the baseline plus the audit's listed restating comments; comments only. Separate branch → Kiln PR.
- [ ] Phase 4: kiln_server comment sweep — same, in kiln_server. Separate branch → kiln_server PR.
- [ ] **Phase 5: Backlog.** Decide each open backlog item with the user, then close or dismiss them all.
