---
status: complete
---

# Phase 22: Deep review fixes, part 2

## Overview

A deep review of the branch found code, skill and record fixes. The owner approved each one on 2026-11-25 ([decisions](../harness_tuner_alignment_decisions.md) section 17). This phase applies them exactly; where the owner gave text, the text is used as given. Skill paths are from `app/mcp/kiln_mcp_server/skill/`.

**The owner's rule for conditions** (every item, and the sweep). Text that applies only to Kiln Harness Tuner is labelled with HT ("Kiln Harness Tuner …"). Unlabelled text is the default and serves every other client (chat clients today, others later). A branch that is truly chat-only (a link into `references/client_guidance/chat/`, asking the user) keeps its chat label ("In a chat with a user"). Never write "MCP client", "MCP agent" or "over MCP" for the chat client. HT's sentences stay word for word; adding an HT label is a mechanical change.

Not in this phase (owner decisions): the `.kiln` costing branch is dropped; the placeholder ids, `tools.md` tool id forms, "MCP tools ARE UI-visible", the `default_run_config_id` chat clause, the `# experiment-costing` heading, the costing endpoint doc links, the `cache_hit` lines and the mode-step references are left for later; the other code and spec findings are dropped or left for later; the owner runs the end-to-end review after this lands. Not edited (specs are point in time): `project_overview.md`, the functional spec and architecture stories, `deep_pr_goals.md` section 8, the phase 16 and requirements statuses, `AGENTS.md`, and the `harness_tuner_switchover/` and `harness_tuner_port/` projects.

## Steps

### Code

1. **A1. The `trusted` parameter of `import_project`** (`libs/server/kiln_server/project_api.py`). Its description says that callers set `trusted=true` only after the user confirms they trust the project: it is the importer's confirmation and grants no code trust. Regenerate the OpenAPI schema (`app/web_ui/src/lib/generate_schema.sh`) and the skill's API reference (`make api_docs`).

2. **A2. The code trust link from the bound address.** The code trust texts hard-code `http://localhost:8757`. The runtime messages are built from the app's address as users see it, with the rule of `kiln_skill` (architecture section 3, decision 11): `kiln_mcp_server.addresses.app_origin(host, port)`.
   - `app/desktop/studio_server/services/code_trust.py`: `CODE_TRUST_PAGE_PATH = "/settings/trust_code/{project_id}"`; `not_trusted_message(lead, project_id, app_origin)` builds the link from `app_origin`. The published API texts (route docstrings and the `not_trusted` field description) are static, so they keep the default address, as `CODE_TRUST_PAGE_DOC`; `kiln_skill` already rewrites it to the bound address when it serves the API reference.
   - `app/desktop/studio_server/eval_api.py`: `connect_evals_api(app, *, app_origin: str)`; `run_v2_eval_test(..., app_origin)`; the two untrusted answers pass it.
   - `app/desktop/desktop_server.py`: `connect_evals_api(app, app_origin=app_origin(bound_host, bound_port))`.
   - If this needs plumbing through many layers, stop and report instead.

3. **A3. Git sync stays blocked over MCP.** `app/desktop/studio_server/test_mcp_block_list.py`: a test that every route under `/api/git_sync/` is MCP-denied, so a new git sync route fails it until it is blocked.

4. **F2. The pre-commit run checks the skill.** `checks.sh --staged-only` runs pytest only when a `.py` file is staged, so a Markdown-only change under `app/mcp/` skips the skill's checks. When no `.py` file is staged and a file under `app/mcp/` is, run the tests of `app/mcp` (they include the tree check of the shipped skill).

### Skill

5. **B1.** `references/improving_agents/playbooks/know-the-agent-before-you-plan.md`: replace "When the task has no eval for an issue, you do not write one unless the run turned eval building on. The report then sends the user to the eval builder in the Kiln app." with the owner's text:
   ```
   When the task has no eval for an issue, Kiln Harness Tuner does not
   write one unless its run turned eval building on; its report then sends
   the user to the eval builder in the Kiln app. Other agents: when the user
   asks for an eval, build it with `references/knowledge/create_spec.md`.
   ```
   Set `reviewed` to 2026-11-25.

6. **B2.** `references/client_guidance/chat/running_an_experiment_from_chat.md`: delete "Kiln has a prompt optimization API; it is not a lever of this procedure." Kiln's prompt optimization API was removed; the rule stays.

7. **B3.** `references/knowledge/train_val_test.md`, eval inputs first, then older evals:
   - Opening paragraph: "Each eval of a task can have three splits, `train`, `val` and `test`. A split's items are EvalInputs, selected by an eval-input filter, most often a tag. The eval's `splits` gives each split's `source` and `filter_id`. The splits must not share an item, …" (the rest of the paragraph stays).
   - A new short section near the end, "## Which items each way of making an eval saves": the guided Eval Builder (Kiln Pro) saves eval-input splits; the form for a template, the form for a check and the API save task-run splits (a dataset filter); `train_set_filter_id` of `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_evals_eval_id.md` adds a task-run split, even when the test split holds EvalInputs (`eval_api.py`, `set_split("train", TaskRunSplit(...))`). Read each split by its `source` and `filter_id`. The PATCH bullet of "An eval with only a test split" points to it. No "older" framing.
   - Evidence: `libs/core/kiln_ai/datamodel/eval.py` (`TaskRunSplit`, `EvalInputSplit`, `SplitRef`); only the guided builder makes `eval_input` splits (`copilot_api.py`, `builder_save`); `POST /specs` (`spec_utils.build_spec_eval`, the template form) and `create_evaluator` (the check form) make `task_run` splits.
   - Owner guidance on creating evals, in `references/knowledge/create_spec.md` as unlabelled default text: never create eval data through the connection (no eval inputs, dataset items or synthetic data; send the user to the app, for example `http://localhost:8757/generate/{project_id}/{task_id}/synth`); the agent may create the eval or the spec itself through the API, and is particularly good at code, regex and conditional checks; it creates the eval only, never its dataset. The guided Eval Builder stays the recommendation where it fits. `specs_and_evals.md` and `judge_types.md` point to it; `benchmark_eval_inputs.md` says not to create EvalInputs.

8. **B4.** `references/client_guidance/chat/using_kiln_from_chat.md`, "How to read the shared documents": replace
   ```
   - A Kiln Harness Tuner tool that Kiln does not have (the skill installer,
     the screening): tell the user it needs Kiln Harness Tuner.
   ```
   with
   ```
   - A Kiln Harness Tuner tool that Kiln does not have (the screening): tell
     the user it needs Kiln Harness Tuner. For the skill installer or the
     skill-authoring guide, create the skill with
     `references/knowledge/adding_skills.md`, which writes the `SKILL.md`
     body only, with no `references/` files.
   ```
   No other change for this item: no per-file clauses, no port of the guide.

9. **C1. One copy of the code trust procedure for chat clients.** In `references/knowledge/code_tools.md` (step 1 of the build) and `references/knowledge/judge_types.md` ("Trust and testing"), replace the asking steps with a pointer labelled "In a chat with a user:" to the code trust rule of `references/client_guidance/chat/using_kiln_from_chat.md` ("Working with the user"). Each file keeps its own facts: `code_tools.md` the endpoint doc, `not_trusted: true` and the end of trust at a restart; `judge_types.md` the trust gate, the endpoint doc and "never present code … as trustworthy". The HT-ported copies (`references/levers/new_tool.md`, `references/knowledge/code_tool_authoring.md`, `references/levers/index.md`) do not change.

10. **The Eval Builder links.** In the web UI, `/specs/{project_id}/{task_id}/select_template` is the entry page: with a description it opens the guided Kiln Pro builder (`/builder`), and it also offers the templates and the checks. `spec_builder` is the form the app opens after a template (`?type=`) or a check (`?judge=`) is picked (`spec_utils.ts`, `select_template/+page.svelte`). Every link labelled "Eval Builder" (guided, recommended, the eval builder) points to `select_template`; the `spec_builder?type=` and `spec_builder?judge=` links stay, labelled as the form for a template or for a check. Places: `create_spec.md`, `create_task.md`, `eval_scores.md`, `judge_types.md`, `specs_and_evals.md` (the UI deep links), `train_val_test.md`, and `client_guidance/chat/project_operations.md` (its verified deep-link prefixes gain `select_template`). A grep of `spec_builder` and "Eval Builder" finds any other.

11. **The conditions sweep.** Apply the owner's rule to every branch added in Phases 20 and 21 and to the files this phase touches: where HT's sentence is unlabelled and an "In a chat with a user:" clause follows it (`memory.md`: the failed write, the missing eval, `dead_end`, the `hypothesis` row and the like; `memory_formats/`; `code_tool_authoring.md`; `api_docs/calling_the_kiln_api.md`; any other), add the HT label to HT's sentence and make the chat clause the unlabelled default ("Other agents: …" or plain text), unless the clause is truly chat-only (asking the user, a link into `client_guidance/chat/`), which keeps its chat label. The labelled links from shared files into chat files keep their label. Tests that pin a changed phrase follow it.

### Records

12. **F3.** `app/mcp/knowledge_backlog.md`, "A manual review of four files against the port rules": the rule becomes the port rule (HT's text as written; only mechanical changes, owner-approved renames and code-evidenced corrections), within the backlog's format (one to three lines of at most 100 characters).

13. **Decisions.** `harness_tuner_alignment_decisions.md` section 17: the conditions rule; B3 (eval inputs first, no new evals in the old form); the Eval Builder link; B4 as one line; A1.

14. **Docs that state the old branch rule**: the skill component doc, section 4.6, and the knowledge-maintenance skill ("Where each kind of content lives") follow the conditions rule.

## Tests

- `test_code_trust.py`: the message links the trust page at the given address (an IPv6 address in brackets), with the project id encoded.
- `test_eval_api.py`: the app fixture passes a non-default address; the untrusted create and test answers link the page there.
- `test_kiln_mcp_mount.py::test_the_eval_routes_get_the_app_address_of_the_bind`: `make_app` passes `app_origin(host, port)` to `connect_evals_api` (a wildcard bind gives `localhost`, a specific host keeps it).
- `test_mcp_block_list.py::test_every_git_sync_route_is_blocked`: no route under `/api/git_sync/` is open over MCP.
- `test_shipped_skill.py::MEMORY_RULES`: the pinned failed-write and `dead_end` phrases follow the sweep.
- The skill tree check, the shipped skill tests, the backlog format test, the OpenAPI schema check and the API reference check pass.
