---
status: complete
---

# Phase 21: One skill, many kinds of client

## Overview

The owner approved this design on 2026-11-24 ([decisions](../harness_tuner_alignment_decisions.md) section 15).

**The principle.** The Kiln skill is one body of knowledge, read by more than one kind of client. Two today, and more may come:

- **Chat clients**: interactive agents working with a user (Claude Code, Claude Desktop, Codex, OpenCode).
- **Non-interactive agents with their own instructions**: Kiln Harness Tuner (HT), whose role prompts deep-link into the skill.

Shared files serve every client. A branch states its real condition ("In a chat with a user: …", "if you have the `call_kiln_api` tool"), never a client's name. Guidance only for chat clients lives in `references/client_guidance/chat/`. "MCP client", "MCP agent" and "over MCP" never mean the interactive client: HT is an MCP client too.

This is mostly a move, not a rewrite. Moved files keep their content, apart from path fixes and the opening line of the chat files. Content ported from HT stays word for word. Skill paths below are from `app/mcp/kiln_mcp_server/skill/`.

The phase also does the records left over from the Phase 20 code review (step 9).

## Steps

1. **Move the chat files** with `git mv` into `references/client_guidance/chat/`:
   - `references/modes/{establish_intent,project_operations,improve_task,learn_about_kiln}.md`, same names. `references/modes/` goes.
   - `references/knowledge/freeform_help.md`, same name.
   - `references/knowledge/run_an_experiment.md` → `running_an_experiment_from_chat.md` (front matter `name` follows).

   Each file opens, after its front matter, with: "For chat clients working with a user. A non-interactive agent with its own instructions does not need this file." In `running_an_experiment_from_chat.md` this line replaces "If you are Kiln Harness Tuner, follow your system prompt. It has similar concepts, but better enforcement.", which named a client where the real condition works.

   Path fixes inside them: "the routing table of `SKILL.md`" and "the section "Working with the user" of `SKILL.md`" name `references/client_guidance/chat/using_kiln_from_chat.md`; "the section "Calling the Kiln API" of `SKILL.md`" names `references/knowledge/api_docs/calling_the_kiln_api.md`. `learn_about_kiln.md` loses its feature table and points to the table "Kiln's features" of `SKILL.md`; no second copy.

2. **Write `references/client_guidance/chat/using_kiln_from_chat.md`** (front matter `name`, `description`; the chat line), from text that moves unchanged:
   - from `SKILL.md`: "Routing" (mode paths fixed), "Working with the user" with the reply rules, "Links into the app", "What you cannot do over this connection", and "Keep the user in the loop" from the API section;
   - from `references/improving_agents/index.md`: the section "How to read these documents over MCP", under the heading "How to read the shared documents". Its first sentence names the shared documents, and its last bullet names the index for "A clear measurement outranks a document". "How to work through a playbook" stays in the index;
   - a closing table "The files of this folder", which names every chat file, so each is reachable.

3. **Move the API rules.** `SKILL.md`, "Calling the Kiln API", minus "Keep the user in the loop", becomes `references/knowledge/api_docs/calling_the_kiln_api.md`, word for word, under `# Calling the Kiln API`. It opens with "These rules apply if you have the `call_kiln_api` tool. If you do not, you need not read them." The endpoint docs carry no such line.

   The folder is generated and replaced whole, so the pipeline keeps this one hand-written file:
   - `skill_files.py`: `API_RULES_PATH = "references/knowledge/api_docs/calling_the_kiln_api.md"`; the not-found listing of the folder names it beside the catalogues.
   - `skill_checks/api_reference.py`: `HAND_WRITTEN_NAMES = frozenset({PurePosixPath(API_RULES_PATH).name})`. `write_folder(files, target)` copies a hand-written file of `target` into the staging folder; `diff_folder(files, target)` leaves them out.
   - `app/desktop/test_skill_api_reference.py`: `test_committed_docs_match_the_block_list` leaves them out.
   - `tree_check.py`: `_is_api_reference(key)` is true for the API folder except `API_RULES_PATH`, so the rules file meets the wording rules of a hand-written file (banned terms, bare names, app links, the test split).

4. **Rewrite `SKILL.md`** as a short router for every client:
   1. Intro: "This is the Kiln skill: an agent-skill-shaped tool for Kiln, served over MCP.", then what Kiln is, then "while you do Kiln work".
   2. "Reading skill files": paths from the skill root; give the path to the tool that returned this text; the tool cannot list a folder, so every file is reached by a path some file names; read it again when it drops out of context.
   3. "Who reads this skill": chat clients always read `references/client_guidance/chat/using_kiln_from_chat.md` at session start. A non-interactive agent with its own instructions (such as Kiln Harness Tuner) follows them on any conflict, ignores "ask the user" instructions, and does not read `references/client_guidance/chat/`; if it reads a file there, it fits any lesson to its own process.
   4. "The parts of the skill", each with a link to the next file of its chain:
      - "Kiln's features": the feature table moved from `learn_about_kiln.md`, with a row for every knowledge file directly in `references/knowledge/` that another part does not name (adds `create_task`, `fine_tuning`, `prompt_rewrite`, `project_status`, `model_create_configs`, `prompt_audit`, `local_private_on_prem`, `create_spec`, `benchmark_eval_inputs`, `diagnose_an_agent`, `code_tool_authoring`, `adding_skills`); then one line: the help articles (`references/docs/docs_index.md`) rank below the knowledge files.
      - "Improving agents": levers, smells, playbooks, techniques and how they connect (smell or playbook → technique → lever), with `references/levers/index.md`, `references/improving_agents/index.md`, `references/knowledge/train_val_test.md` and `references/knowledge/experiment_costing.md`.
      - "Memory": `references/knowledge/memory.md`.
      - "The Kiln API": `references/knowledge/api_docs/calling_the_kiln_api.md` (if you have `call_kiln_api`) and `references/knowledge/api_docs/api_index.md`.
      - "Chat client guidance": `using_kiln_from_chat.md`, for chat clients.

   The term definitions fit in "Improving agents", so there is no `references/glossary.md`. `SKILL.md` names no chat file but `using_kiln_from_chat.md`.

5. **Path fixes in the shared files.** Every link to a moved file, in the levers, the techniques, the knowledge files and `memory.md`, gets its new path. No shared file may need a chat file to make sense, so each such path sits in a sentence for a chat with a user ("In a chat with a user: …"), the condition the Phase 20 ports use. In the levers' "See also" the line is "- In a chat with a user: `<path>`.": `output_mode.md` would pass its 6,000-character limit otherwise. `one-general-rule-per-edit.md` step 3 reads "Apply "Text you add" of your build instructions (in a chat with a user: "Build the candidate" of `<path>`)". `prompt_rewrite.md` and `working_with_project_files.md` name the API rules file and the chat guide in place of `SKILL.md`'s sections.

6. **Texts.** `texts.py`: the skill tool's "They name the modes and the entry points" becomes "They list the parts of the skill"; `CALL_KILN_API_DESCRIPTION` names `references/knowledge/api_docs/calling_the_kiln_api.md` to read before the first call.

7. **Checks** (`tree_check.py`):
   - `CLIENT_GUIDANCE_FOLDER = "references/client_guidance/"` in place of `MODES_FOLDER`: the split-pointer rule and the `name`/`description` front matter rule cover it.
   - A banned-term scope `guidance` for every file outside the help articles and the API reference: `MCP client`, `MCP clients`, `MCP agent`, `MCP agents`. `BANNED_TERM_EXCEPTIONS` allows the first two in `references/knowledge/tools.md`, where they mean the protocol's role.

8. **Upkeep.** `.agents/skills/knowledge-maintenance/SKILL.md`: who reads the knowledge; a table of where each kind of content lives; 4.6 names the moved section. `app/mcp/knowledge_backlog.md`: the review entry names the new path. `AGENTS.md` names no moved path.

9. **Records.**
   - `implementation_plan.md`: the Phase 21 line.
   - `components/skill_and_content.md`: sections 1, 3, 4.1–4.5, a new 4.6 with the design, 6, 8, the note at the top of 9, 9.3, 9.4, 10.
   - `functional_spec.md` 7.1 and 7.2; `architecture.md` section 2 and owner decision 6.
   - `harness_tuner_alignment_decisions.md`: section 15; the note on owner quotes that say "MCP agents"; section 14's carried-over fixes (below).
   - `deep_pr_goals.md` section 3: the new paths and terms.
   - `harness_tuner_switchover_requirements.md`: SR4's stale reason for the planner's steps 4–5 (the Kiln index holds them since Phase 17); SR5's notes (pinned headings follow the Kiln skill; every path that Phase 21 changes); SR6 a, b and g; new SR19 for the client guidance and its acceptance line.
   - The wording sweep: "MCP client/agent" and "over MCP" meaning the interactive client become "chat client(s)" or the real condition, in the skill and in this project's living specs (`functional_spec.md`, the components, `deep_pr_goals.md`, `backlog.md`, `phase_8_revisit.md`, the decisions and requirements). Owner quotes keep their words, with a note. The phase plans and the research audits are dated records and keep theirs. `specs/projects/harness_tuner_switchover/` and `harness_tuner_port/` are not edited.

   Carried over from the Phase 20 code review:
   - SR5: the switchover's pinned contract headings (its `components/ht_skill_reading_and_roles.md:480-481`) must follow the Kiln skill's current ones: `memory.md` "Tags" → "Tags — seed vocabulary (8 + priorities)", its "Who writes" column → "Write when"; `code_tool_authoring.md` "Wrapper templates" → "Wrapper templates — bake it into code first", "The allowlist rule" → "The one hard rule: allowlist hygiene".
   - SR11 and SR12 notes and decisions section 14: "No other writer exists" becomes "the Kiln skill adds no writer of these records; HT's own interactive install (`harness-tuner-install-agents --dest`), which had one, goes in the switchover (its architecture.md decision 15)".
   - Decisions section 14's sentence-map table: the Mechanical/Decision/Correction/Dropped split was sorted by hand; the script gives verbatim/near/changed only (memory 126/23/36, code-tool authoring 58/13/17, kiln-api 13/13/21). `hypothesis` moves from the corrections to the decisions applied (memory: Decision 11, Correction 0).
   - Decisions section 14's dropped list: a "dropped under decision 11" line for "(a hand-run n=3 check has no bundle)", "elsewhere, any labelled numbers", "or this session's equivalent" after `call_kiln_api`, "One `Read`, no catalog hop." → "Read it before the first call.", "write them when you open experiments".
   - `references/knowledge/memory.md`: the save row says the `overview` has no newlines, beside the 280-character limit (`libs/core/kiln_ai/datamodel/memory.py:122`).
   - Requirements section 7, SR6 acceptance: "or reads `tags=baseline` or `tags=val` from a train-side role" again.

10. Run `uv run python -m kiln_mcp_server.skill_checks build` and `uv run ./checks.sh --agent-mode` until clean.

## Tests

- `test_shipped_skill.py::test_skill_md_has_the_required_parts`: the three `## ` sections and the five `### ` parts of `SKILL.md`, in order; the intro says what Kiln is, "served over MCP" and "while you do Kiln work"; "Who reads this skill" names the chat guide; each part names its entry points.
- `test_skill_md_names_every_knowledge_file`: every file directly in `references/knowledge/` is named in `SKILL.md`.
- `test_skill_md_names_only_the_chat_guide_of_the_chat_files`.
- `test_each_chat_file_opens_with_the_chat_line` (parametrised over the chat folder).
- `test_the_chat_guide_lists_every_chat_file`: the guide's sections, in order, and its folder table.
- `test_the_chat_guide_has_the_rules_for_working_with_the_user`: the mode paths, "Keep the user in the loop", the main app pages and the blocked-capability pages (the old `SKILL.md` assertions, moved).
- `test_a_shared_file_names_a_chat_file_only_for_a_chat_with_a_user`: each paragraph, list item or table row of a shared file that names a chat path also says "in a chat with a user".
- `test_the_chat_guide_explains_harness_tuner_words_to_chat_clients` replaces `test_the_index_explains_harness_tuner_words_to_mcp_agents`: the section names the index, the experiment guide and `memory.md`.
- `test_the_index_keeps_the_heading_harness_tuner_reads`: "How to read these documents" holds "How to work through a playbook", and the index names no chat path.
- `test_the_api_rules_keep_harness_tuners_discipline` reads the rules file; `test_the_api_rules_open_with_their_condition`.
- `test_run_an_experiment_opens_with_the_two_paths`, the glue-file, overlap-group and record-writer tests: new paths, same intent.
- `test_memory_states_kilns_overview_limits`.
- `test_tree_check.py::test_mcp_client_means_the_protocol_role_only`: the chat words fail in a knowledge file, a chat file and the API rules file; pass in `tools.md`, a help article and an endpoint doc. The fixtures use `references/client_guidance/chat/` for the old `references/modes/`.
- `test_api_reference.py`: `test_the_api_rules_are_the_hand_written_file_of_the_folder`, `test_write_folder_keeps_the_hand_written_files`, `test_diff_folder_leaves_out_the_hand_written_files`.
- `test_skill_files.py`: the folder listing names the rules file beside the catalogues.
