---
status: draft
---

# Phase 9: Content, part 3: the new and rewritten guides

## Overview

Batches 10, 11, 12 and 13a of the content plan (skill_and_content sections 9 and 9.1–9.4). The skill gets the guides that neither source had in the form a coding agent needs: memory, code tools and their authoring, the project's files on disk, and the two glue files that turn harness-tuner's method into a by-hand procedure (`run_an_experiment.md`, `diagnose_an_agent.md`). `references/modes/improve_task.md` becomes the router into the knowledge. After batch 13a, `PENDING_RULES` is empty.

Sources, as recorded for the content phases:

- Harness-tuner at commit `b49f1594620862876d1e515cdda2f2deff018e95`: the `memory` skill (batch 10); the `kiln-harness-tuner-code-tool-authoring` skill with its `references/wrappers/` (batch 11); the knowledge skill's `SKILL.md`, the planner's entry file, and the promote, batch-selection, experiment-build and experiment-analysis skills, as the sources of the method of the glue files (batch 13a). Reference only; no code is copied except the eight wrapper templates, which are content (section 3).
- The Assistant's skill as delivered: the three files that are not imported (`experiment_batch`, `optimize_quality`, `optimize_performance`) are read for the content that 9.2 moves (batch 13a). Their content is written anew in its destination. Their names do not appear in the tree (banned terms).

Rules for every batch: C11 (a port, not a redesign), C12 (one owner per question), C13 (no test split), and the private-source hygiene of section 9. Backlog B8 and B9 are open owner decisions: the files are written consistently with `references/knowledge/train_val_test.md` as it stands, and rule on neither. Each batch is its own commit; a patch of the whole working tree is saved in the scratchpad after each batch.

## Steps

1. **Batch 10: memory.**
   - New `references/knowledge/memory.md` (front matter `name`, `description`; at most 12,000 characters) from the `memory` skill: what memory is for (knowledge that outlives a session, not working state); the discipline (check first, record as you go, assume interruption); the six endpoints, each with its doc path under `references/knowledge/api_docs/`; scopes `project` and `task::<task_id>`, given on every call; orientation at the start of Kiln work; write discipline (one finding per memory, the 280/4,000 caps, the overview as a load decision, check before writing, corrections as updates, no negative platform claims, a failed write is reported to the user, what is not memory-worthy); the tag vocabulary (`issue`, `hypothesis`, `experiment`, `dead_end`, `constraint` with `OPEN:`, `lesson`, `baseline`, `val`, priorities `p0`–`p3`), with the overview prefixes and suffixes that a by-hand session writes; issues bound to evals with `eval_<eval_id>`; memory vs provenance.
   - Gone, by the batch rule "run and loop scopes go": the gateway operations, the orchestrator's code-owned writes, the setup phase, the screening, generality and reference-check lines, the frozen format of the loop's analysis, the train-side lane rules. Where a rule names a loop-only actor, the by-hand session follows the same format itself. The `val` record keeps its access rule: only summary numbers; it is read when confirming on val and when reporting, and names `references/knowledge/train_val_test.md`.
   - Listed in `SKILL.md` part 7 and in the knowledge tables of the three modes.
2. **Batch 11: code tools and MCP wiring.**
   - Rewrite `references/knowledge/code_tools.md` for the API: read the trust state; ask the user before granting code trust; draft; test the code on your own machine first (what a coding agent can do that the Assistant could not: run the tool's own tests); dry-run with `test_code_tool`; create; attach on a new run config; iterate as a new tool. It names `references/knowledge/code_tool_authoring.md` and the lever `references/levers/new_tool.md`.
   - `references/knowledge/tools.md` and `references/knowledge/subagents.md`: the wiring parts state the same sequence (read the state, ask the user before adding a local MCP server, connect, check the tools it exposes, iterate by edit).
   - New `references/knowledge/code_tool_authoring.md` from the authoring skill: when a code tool is the right change, the four families, the wrapper templates table, the allowlist rule in full, the contract, the calls (endpoint doc paths in place of gateway operations), the build rules for an experiment, and the worked example. Loop words and roles go (`build_notes` → what you report).
   - New `references/knowledge/code_tool_wrappers/`: one Markdown file per template (8), front matter `name` and `description`, a short text (the README's row and the template's docstring), and the module in a ```` ```python ```` fence, unchanged. The README's shared rules move into `code_tool_authoring.md`.
   - Known difference from the source: the module code of every template is unchanged, but the docstrings of three are reworded for this MCP (`actionable_errors`: the code tool GET endpoint and "the tool definition call" in place of two gateway operations; `context_on_tool_surface`: "arms" becomes "candidates"; `readonly_guard`: "rc" becomes "run config"). A later diff against harness-tuner's `references/wrappers/*.py` shows these lines; they are not drift. The port procedure of the `knowledge-maintenance` skill diffs only the knowledge folder, so it needs no note.
   - The six techniques that name `*.py` templates name the wrapper file paths; `references/levers/new_tool.md` gets the pointer to the full allowlist rule and its "See also" names `code_tool_authoring.md` and the wrapper templates.
   - Test `test_wrapper_templates_compile` in `skill_checks/test_shipped_skill.py`: each file of `code_tool_wrappers/` has exactly one `python` fence, which compiles and defines a module-level `run`.
3. **Batch 12: project files guide.**
   - New `references/knowledge/working_with_project_files.md` with the three rules of functional spec 7.4 (read directly when faster; write through the API; respect immutability: a new copy, never a change in place). It says nothing about val or test data.
   - Listed in `SKILL.md` part 7 and in the three modes.
4. **Batch 13a: the glue files and the router.**
   - New `references/knowledge/run_an_experiment.md` with the eleven parts of 9.3 in order (`## ` headings): Two paths, Words, Before you start, The hypothesis, Cost before you spend, Build the candidate, Measure on train and judge, Confirm on val, Keep or discard, Record and report, Variants. Part 1 is the owner's ruling (Kiln Harness Tuner for experimentation at scale, recommended to the user with no CLI steps; the by-hand procedure for a one-off). Part 8 reads val by the summary numbers of `train_val_test.md`, and states the keep rule of the promote step.
   - New `references/knowledge/diagnose_an_agent.md` with the five parts of 9.3: the agent as it is, what the smells measure (the rendered prompt call), the scores on train, the failing train items, where to go next.
   - Rewrite `references/modes/improve_task.md` as the router of 9.4 (about 8,000 characters): the owners, the two paths, task context (discovery and the snapshot call kept), the usual path, the routing table, reporting, the knowledge table in four groups.
   - Partial rewrites of 9.2 in `prompt_audit.md`, `prompt_rewrite.md`, `model_work.md`, `model_create_configs.md`, `eval_scores.md`, `specs_and_evals.md`, `benchmark_eval_inputs.md`, `adding_skills.md`; the content that only the three files had, in its destination (`run_an_experiment.md`, `improve_task.md`, `create_spec.md`, `prompt_audit.md`, `diagnose_an_agent.md`, `model_work.md`); the references that batch 1 pointed at the mode are refined where a glue file is the better target.
   - Each file that names a call or page of `TEST_SPLIT_READERS` says which split it reads, or names `references/knowledge/train_val_test.md`; no file asks for `split=test`.
   - Each lever's "See also" names `references/knowledge/run_an_experiment.md`. `SKILL.md` part 7 lists it.
   - Test `test_the_glue_files_have_their_parts`. `tree-test-split` leaves `PENDING_RULES`, which is then empty.
5. **Checks** after each batch: `skill_checks check`, the `app/mcp` tests; at the end the full `checks.sh`.

## Tests

- `test_wrapper_templates_compile`: each wrapper template file holds one Python block that compiles and defines `run`; there are 8 of them.
- `test_the_glue_files_have_their_parts`: `run_an_experiment.md` has the parts of 9.3 in order, and its first part names Kiln Harness Tuner and the one-off path; `diagnose_an_agent.md` has its five parts in order.
- The shipped-tree tests (`test_the_shipped_tree_passes_every_check`, `test_the_shipped_knowledge_passes_every_check`, `test_the_full_check_passes`, `test_skill_md_has_the_required_parts` with the entry points `memory.md`, `working_with_project_files.md` and `run_an_experiment.md`, `test_no_file_over_body_limit`, `test_no_skill_file_names_a_blocked_endpoint`, the bundling test) pass after every batch with its `PENDING_RULES`, and with none after batch 13a.
