---
status: complete
---

# Phase 7: Content, part 1: import the Assistant's skill and adapt it

## Overview

The placeholder `SKILL.md` is replaced by the Assistant's skill: `SKILL.md`, 4 modes, 23 of its 26 knowledge files and 34 help articles with their index (skill_and_content sections 4 and 9, batches 1–6). The files are adapted to this MCP: plain skill paths in place of skill-tool calls, the model info endpoints in place of the Assistant's model tools, app links with the app address, a `SKILL.md` for on-demand loading in place of the always-present system prompt, the C10 wording for MCP-blocked capabilities, and `online_url` on every help article. Each batch turns its rules on in `PENDING_RULES` and adds its tests, so the shipped-tree tests hold after every batch.

The help-article import uses a one-off script that is not kept in the repository (C8). No file of the source is added beyond the 63 skill files, and no committed file names where the source is kept.

## Steps

1. **Batch 1: import and normalise references.**
   - Copy into `app/mcp/kiln_mcp_server/skill/` the source's `SKILL.md`, `references/modes/*.md`, `references/knowledge/*.md` except `experiment_batch.md`, `optimize_quality.md` and `optimize_performance.md`, and `references/docs/**`. The placeholder `SKILL.md` is replaced; `references/knowledge/api_docs/` is kept as generated.
   - `SKILL.md` gets the front matter of 4.2 (`name: kiln`, `description`). The front matter `name` of each mode and knowledge file becomes its file stem.
   - Every `skill(name="kiln-chat", resource="X")` becomes the plain path `X` ("read `X`"); a bare `skill()` verb becomes "read"; the access-rule section of `SKILL.md` goes. The two `skill()` mentions of the Kiln product feature (a user's own skill) stay, reworded so that `skill(name=` does not occur.
   - Bare skill-file names and bare API-doc names become full paths. A `../` link of a help article that leaves the copied set becomes its public URL; one that stays inside becomes a root path.
   - The references to the three files that are not imported become `references/modes/improve_task.md`.
   - Endpoint doc paths that the generated reference names differently (the data guide save is `post_…_data_gen_guide.md` here) are fixed; a path to an endpoint with no doc here is left for batch 5, which owns the blocked-endpoint wording.
   - `test_shipped_skill.py`: `PENDING_RULES` holds every rule this batch does not satisfy; add `test_example_paths_exist` (every skill path in `SKILL_TOOL_DESCRIPTION`, `PATH_DESCRIPTION` and `HINT` is a file of the shipped tree).
2. **Batch 2: model info.** The mentions of `model_info_featured`, `model_search` and `model_info` become the model info endpoints through `call_kiln_api`, with their endpoint doc paths: list and search → `GET /api/model_info/models`, details → `GET /api/model_info/model_details`, providers → `GET /api/model_info/providers`. The defining section of `references/knowledge/model_work.md` is rewritten; the model info section of `references/modes/improve_task.md` is removed. "MCP tool" stays only where it means Kiln's tool-server feature. The model info terms of `tree-banned-term` hold after this batch.
3. **Batch 3: link templates.** Every app path in backticks or as a link target gets `http://localhost:8757`; `{pid}` and `{tid}` become `{project_id}` and `{task_id}` (C4). The rule statements, the per-file link tables and the "external URL" definitions are rewritten for absolute links. API paths (`/api/…`) are left as they are. `tree-app-link` leaves `PENDING_RULES`; add `test_address_replacement_covers_every_app_link`.
4. **Batch 4: identity and on-demand loading.** `SKILL.md` is rewritten to 4.3: the eight parts in order, at most 300 lines and 20,000 characters, no persona, no session start, no always-in-a-mode rule, the table of main pages (checked against `app/web_ui/src/routes/(app)/`). The routing summary of the Assistant's `SKILL.md` moves into the routing table and `references/modes/establish_intent.md`, which keeps only the steps for an unclear request. The Session Start and Per-Turn Intent Check sections of the three modes are rewritten: rules apply "while you do Kiln work"; a rule that only makes sense for an always-present system prompt is deleted. The `SKILL.md` banned terms hold after this batch. Add `test_skill_md_has_the_required_parts` and `test_skill_md_size`.
5. **Batch 5: blocked-capability and approval wording.** Each statement that a capability is UI-only, or that a call needs approval, is checked against the block list. Where the endpoint has a doc in `api_docs/`, the text gives the API workflow: running an eval (written once in `references/knowledge/specs_and_evals.md` as the job calls: start, wait, read the errors), MCP server wiring, RAG setup and indexing, code tools, judges, task from a tool, dataset download. Where it has none, the C10 wording with the app link of the table in 4.4. The two "not connected" texts (Kiln Pro, provider) are written. "requires approval" becomes "ask the user first", or goes. Paths to endpoint docs that do not exist are removed. The destructive-action rule and product advice stay. The approval terms of `tree-banned-term` hold; `tree-banned-term` and `tree-path` leave `PENDING_RULES`. Add `test_no_skill_file_names_a_blocked_endpoint` to `app/desktop/test_skill_api_reference.py` (section 10).
6. **Batch 6: help-article URLs.** The one-off script adds `online_url` (`online_url_for(path)`) to the 34 articles and removes `<figure>`, `<img>` and Markdown images whose file is not in the tree. `docs_index.md` is regenerated with `skill_checks build`. Each URL is requested once. `tree-front-matter` and `docs-index` leave `PENDING_RULES`; add `test_docs_index_is_current`. `misspell` runs over the tree.

After batch 6 the rules still pending are those owned by later phases: `tree-split-pointer` (batch 9) and `tree-test-split` (batch 13a), plus any rule whose remaining problems need content of a later batch, each with a comment naming that batch.

## Tests

- `test_example_paths_exist`: every skill path written in the tool texts and `HINT` is a file of the shipped tree.
- `test_address_replacement_covers_every_app_link`: no shipped file holds `127.0.0.1:8757`, `https://localhost:8757`, or `localhost:8757` without `http://`.
- `test_skill_md_has_the_required_parts`: the served `SKILL.md` has the eight parts of 4.3 in order, names the routing table's mode paths, the entry points of part 7 and every app page of the main-pages table.
- `test_skill_md_size`: `SKILL.md` has at most 300 lines and 20,000 characters.
- `test_no_skill_file_names_a_blocked_endpoint`: no shipped file outside `api_docs/` names the path of an MCP-blocked endpoint (with the `/api/settings` same-line rule), plus synthetic cases of the matcher.
- `test_docs_index_is_current`: `docs_index.md` equals `render_docs_index` of the shipped tree.
- The existing shipped-tree tests (`test_the_shipped_tree_passes_every_check`, `test_the_full_check_passes`, `test_no_file_over_body_limit`, the PyInstaller bundling test) pass after every batch with the batch's `PENDING_RULES`.

## Notes for the reviews by people

- Sandbox wording (functional spec 15), for the security owner: batch 5 touched the statement that user code runs with no network or filesystem sandbox in `references/knowledge/code_tools.md` and `references/knowledge/judge_types.md`. The statement is kept as the source has it.
- Still open: the public help URLs were not requested. This environment's network blocks `docs.kiln.tech`, so neither the 34 `online_url` values nor the `https://docs.kiln.tech/developers/...` links of batch 1 were checked. Request each one in phase 13 or 14.
