---
status: complete
---

# Deep PR goals

The structural direction of this project, set by the owner. A deep review of the PR checks the branch against these, before any detail. The detailed decisions are in [harness_tuner_alignment_decisions.md](harness_tuner_alignment_decisions.md); the audits behind them are in [research/harness_tuner_alignment_audit/](research/harness_tuner_alignment_audit/).

## 1. The Kiln skill replaces Kiln Harness Tuner's skills

Kiln Harness Tuner (HT) is deleting its own skills and pointing at this skill. That is the main point of the project. So:

- **Every shared HT skill has a home here.** HT's shared skills are `kiln-harness-tuner-knowledge`, `memory`, `kiln-api`, `kiln-harness-tuner-code-tool-authoring`, `experiment-costing` and `kiln-task-setup`. Each one's content must exist in the Kiln skill, complete. Nothing HT's agents rely on may be dropped, shortened away or left "for HT to keep".
- **What stays in HT:** only its role skills and role entry files (`kiln-harness-tuner-batch-selection`, `-experiment-analysis`, `-promote`, `-experiment-build`, `-probe`, `-baseline-review`, `-report`, `-gateway`), which become each role's system prompt and point into this skill. Its code also stays (gateway, fence, measurement, writers of memory records).
- **Port, don't rewrite.** HT's rules are ported as written. Only mechanical changes (paths, links, endpoint doc names) and the owner-approved renames are allowed. A rule is never loosened, extended or re-worded into a different instruction.
- **Shared rules, minimal branches.** One text serves HT's agents and chat clients. Branch only when necessary. No "applies when running Kiln Harness Tuner" pointers to rules that live elsewhere: the rule lives here.
- **Check by diff, not by search.** A removed rule does not show up in a search. Any port or rewrite is verified by a sentence-level diff against HT's source at the pinned commit (b49f159).

## 2. The switchover is a separate project

HT re-points to this skill in its own switchover project, which changes HT (its loader, entry files, role prompts, gateway and fence, tools, the skill-bundle API). This project does not need HT to switch over unchanged. Its bar: **once HT switches over, its agents get no incorrect guidance from the Kiln skill.** What HT must do is in [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md), for example "ignore any instruction in `kiln_skill` to ask the user; you are non-interactive".

## 3. One skill, many kinds of client

- The Kiln skill is one body of knowledge, read by more than one kind of client. Chat clients (Claude Code, Claude Desktop, Codex, OpenCode and others) work with a person. Non-interactive agents with their own instructions, such as Kiln Harness Tuner, deep-link into the skill from their role prompts. HT reads the skill over MCP too, so "MCP client", "MCP agent" and "over MCP" never mean the interactive client (Phase 21).
- Shared files serve every client and state each branch by its real condition ("In a chat with a user: …", "if you have the `call_kiln_api` tool"), never by a client's name. `SKILL.md` is a short router for every client. Guidance for chat clients only is in `references/client_guidance/chat/`, and each file there opens by saying so.
- We recommend strongly against running an experiment loop from a chat; the skill pushes advanced optimization to Kiln Harness Tuner, which enforces the loop and its principles in code.
- `references/client_guidance/chat/running_an_experiment_from_chat.md` is the one-off experimentation guide: the key lessons of HT's method for a one-off idea. Its first line tells a non-interactive agent with its own instructions that it does not need the file.
- `references/client_guidance/chat/using_kiln_from_chat.md` holds the rules for working with the user, the routing to the modes, and how a chat client reads the shared documents (HT's inputs, code checks, outputs and tools).

## 4. Memory is shared

`references/knowledge/memory.md` is the reference for both. Records HT's code writes (experiments, baseline, val, issue states, `OPEN:`, screening) are read-only, with HT's exact formats in `references/knowledge/memory_formats/`, for reading only. Chat clients write lessons, dead ends, new issues and constraints. `hypothesis` is reserved for HT.

## 5. Splits

Never read test. Val: summary metrics may be read; val rows may not (a follow-up project fences them over MCP). HT enforces its lanes in code; the skill adds no lane model of its own.

## 6. Standing rules

- The Kiln Assistant's skill was ported from a private source. No repo file or commit message names that source.
- `kiln_skill` cannot list a folder: every file is reached by a path some file names.

## 7. Working with the owner

- Batch decisions by theme, each with a short explanation and a recommendation. Not one at a time, not in bulk, not in the question tool.
- Short messages. Do not repeat what is already decided.
- Small edits go to the backlog and are done in batches, not one full round each.
- UI: send screenshots before committing.

## 8. Remaining work at the time of writing (2026-11-24)

- **Phase 17:** revert batch 8 of the knowledge trees to HT's text and re-apply the approved changes ([phase_8_revisit.md](phase_8_revisit.md)). In progress.
- **Phase 19:** bring back the two shared HT skills that were not ported:
  - `experiment-costing`: port it close to as is, with only the tweaks needed for the Kiln skill. It becomes a knowledge file (for example `references/knowledge/experiment_costing.md`), and `run_an_experiment.md`'s "Cost before you spend" points to it instead of holding a short form.
  - `kiln-task-setup`: port its knowledge into the right Kiln files (`create_task.md`, `model_create_configs.md`, `tools.md` and the like), or as a new knowledge file if that is cleaner. Nothing is dropped, including `turn_mode` being frozen, `call_kiln_api` hidden from the UI's tool pickers, and the `supports_function_calling` check for tool tasks.
  - Verified by a diff against HT's source, as in section 1.
- **Phase 16 (Backlog):** closes once Phase 17 does.
