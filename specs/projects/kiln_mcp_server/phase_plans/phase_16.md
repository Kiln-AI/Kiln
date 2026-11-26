---
status: in_progress
---

# Phase 16: Backlog

## Overview

Close the backlog items the owner approved for this batch: B1, B2, B4, B5, B6, B10, B16, B17, B18, B20, B21, B22, B23, B28, B29 and B30, each as its decision line in `backlog.md` says. B7, B11, B12, B13 and B19 are out of this batch (the owner is re-aligning how the skill relates to Kiln Harness Tuner); their files and entries are not touched, and no Harness Tuner wording changes anywhere.

The largest item is B23: granting code trust leaves the MCP surface. The agent reads the trust state with `GET .../add_code_trust`, and the user grants it on a new app page that only an agent's link leads to.

## Status

This batch is done: B1, B2, B4, B5, B6, B10, B16, B17, B18, B20, B21, B22, B23, B28, B29 and B30 are closed, and so are B32 and B33, found in this batch's review. Phase 16 stays open: B7, B11, B12, B13 and B19 wait on the owner's re-alignment with Kiln Harness Tuner.

## Steps

1. **B1, PyInstaller dotfiles.** `app/desktop/pyinstaller_hooks/hook-kiln_mcp_server.py`: `collect_data_files("kiln_mcp_server", excludes=["**/.*", "**/.*/**"])` (check the glob on a hidden file and a hidden folder). Test in `app/desktop/test_pyinstaller_hooks.py`: a dotfile and a file in a dot-folder of a temp copy are not collected.
2. **B2, texts 7 and 8.** `api_tool/messages.py`: `_as_sentence(core_text)` adds a full stop when the core text has no closing `.`, `!` or `?`; `request_failed` and `response_unusable` join with one space after it. Spec table rows 7 and 8 of `mcp_server_and_api_tool.md` say so. Tests in `test_pipeline.py` (timeout text on POST reads "…30.0s. The POST may…"; a core text with a full stop gets no second one).
3. **B4, `./` and `../` outside link targets.** `tree_check.py`: `_DOT_RELATIVE_PATH = (?<![\w.-])\.\.?/(?:references/[A-Za-z0-9_\-./]*|SKILL\.md\b)`; `check_relative` flags code spans that start with it and prose matches. Cases in `test_relative_link_fails`. Section 8 of `skill_and_content.md`.
4. **B5, placeholders and angle brackets in `tree-relative`.** `_scan` unwraps a CommonMark `<…>` link target before it is used; `check_relative` skips placeholder targets (C5). Tests: `[x](<name>.md)` passes; `[x](<references/modes/a.md>)` resolves (and an angle-bracket target that names no file fails `tree-path`). Section 8 says so.
5. **B6, self-links.** `knowledge_check._links_only_to` skips a link whose `resolved == doc.path`. Tests: a playbook whose only step is a self-link (anchor and full path) fails `playbook-steps`; a technique's self-link in `Alternatives` is not counted.
6. **B10, imported counts.** `test_the_knowledge_was_imported_whole` asserts `>=` per kind.
7. **B16, overlap groups from the tree.** `test_shipped_skill.py`: groups 7, 10 and 12 are built from the knowledge base by the rules of skill_and_content 9.1 (the techniques `cheaper-or-faster.md` links; the techniques whose `levers` hold `tool_config` or `new_tool`, less groups 3, 9 and 11, and the smells whose `applies_to` lists `tools`, less group 11; every lever file). Section 4.3 of the `knowledge-maintenance` skill says to update the "See also" lines when the test names one.
8. **B17, fine-tuning.** `references/knowledge/fine_tuning.md` "Try First": keep the pointer; add that a fine-tune comes only with the user's sign-off, after the downsides are explained and the other options are tried, with the four downsides and "mostly for expert users".
9. **B18, B29, server instructions.** `texts.py`: `WHAT_KILN_COVERS = "projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools, skills and RAG"`, used in `SERVER_INSTRUCTIONS`; the same list in the `SKILL.md` description and line 8. `SERVER_INSTRUCTIONS` names `$kiln` beside `/kiln`. Tests pin the list in `SKILL.md` and `$kiln` in the opening.
10. **B20, spec alignment.** skill_and_content 9.2: `create_spec.md` and `judge_types.md` get the four eval playbooks of group 8.
11. **B21, README emoji.** `README.md`: 🔌 on "Use Kiln from your own agent"; remove the TODO comment.
12. **B22, Claude Code by hand.** `agent_install.md` Claude Code note: the by-hand form is user level, in `~/.claude.json` (top-level `mcpServers`), to match step 2.
13. **B23, code trust leaves MCP.**
    - `eval_api.py`: `POST /api/projects/{project_id}/add_code_trust` gets `with_mcp_deny(DENY_AGENT)`; `GET` stays allowed. `test_mcp_block_list.py`: the POST moves from `EXPECTED_MCP_ALLOWED` to `EXPECTED_MCP_BLOCKED`. Spec: block list 6.3 gains row 30 (30 operations), architecture section 5, the test row of section 10, skill_and_content 4.4 gains a row, `research/mcp_block_list_review.md` records the new ruling.
    - `code_tool_api.py`: the two route descriptions and the `not_trusted` fields (with a `Field` description) tell the agent: explain what will run and that there is no sandbox, give the user `http://localhost:8757/settings/trust_code/{project_id}`, ask them to say when they approved, then confirm with `GET .../add_code_trust`. The `ToolCallLogEntryResponse` docstring drops "sandboxed" (B30).
    - New page `app/web_ui/src/routes/(app)/settings/trust_code/[project_id]/+page.svelte`, linked from nowhere in the app. On load it reads the trust state. Question state: the trust question of the existing dialogs and one button that grants trust. Success state (also when already trusted): "Return to your agent and tell it code trust was granted." Loading and error states. The question body is shared with the two trust dialogs through a new `lib/components/code_tools/code_trust_question.svelte`, which both dialogs render unchanged. Page logic in `trust_code.ts` with a test; a page test of the states.
    - Skill: `SKILL.md` ask-first rule and the blocked-capability table; `code_tools.md`, `judge_types.md`, `code_tool_authoring.md`, `levers/new_tool.md`: the same steps, with the link; no `post_api_..._add_code_trust.md` path remains.
14. **B28, `agent_install.md` to `docs/`.** `git mv`; update `BASE_PROMPT` (`connect_agent.ts`), `README.md` (prompt copy and link), `libs/server/kiln_server/mcp/README.md`, `test_texts.py`, `connect_agent.test.ts`, and the specs (`architecture.md`, `components/connect_page_and_install.md`, `functional_spec.md` 9.1, `ui_design.md`). The future URL `https://kiln.tech/agent_install.md` stays.
15. **B30, "no sandbox".** `code_tools.md`, `judge_types.md`, `levers/new_tool.md`, and `code_tool_authoring.md` if needed: say only "no sandbox"; no "resource sandbox", no "the same sandbox" or "out of the sandbox". The Pydantic "Run Python" mentions stay.
16. **Regenerate** `make api_docs`, `make skill_index` (`build`), the web schema (`generate_schema.sh`). No annotation changes (`x-mcp-policy` is not an annotation).
17. **Backlog.** Mark the sixteen items closed in `backlog.md`, with a `Closed:` line for B13-style items that need one (B21).

## Tests

- `test_the_bundled_data_skips_dotfiles`: the hook's data set holds no dotfile or dot-folder file.
- `test_pipeline.py`: a POST timeout reads "… timed out after 30.0s. The POST may have taken effect. …"; a core text ending in `.` is not doubled.
- `test_relative_link_fails`: `` `../references/nope.md` ``, `` `./references/modes/a.md` ``, prose `see ../references/nope.md`, `` `./SKILL.md` `` are `tree-relative`.
- `test_placeholder_is_skipped`: `[x](<name>.md)` passes; `test_angle_bracket_link_resolves`: `[x](<references/modes/a.md>)` is a reference.
- `test_knowledge_check.py`: a self-link does not satisfy `playbook-steps`, `smell-remedies` or count in `Alternatives`.
- `test_shipped_skill.py`: groups built from the tree equal the spec's lists today (the existing See-also test).
- `test_texts.py`: `SKILL.md` description and line 8 hold `WHAT_KILN_COVERS`; the instructions' opening names `$kiln`; the guide is read from `docs/agent_install.md`.
- `test_mcp_block_list.py`: the POST is blocked; the GET is allowed.
- Code tool routes: `not_trusted` responses unchanged; the descriptions name the trust page and the GET.
- `trust_code.test.ts`: the state machine (loading → question / trusted / error; grant → trusted; grant error kept on the question).
- `page.test.ts` for the trust page: question state renders the question and the button; success state renders the return message; the button calls the POST.
- `connect_agent.test.ts`: reads `docs/agent_install.md`; the prompt names the new URL.
