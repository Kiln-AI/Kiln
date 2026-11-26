---
status: complete
---

# Phase 17: Revert and revisit phase 8

## Overview

Batch 8 of phase 8 (`919fb6a`) reworded the knowledge trees (`references/levers/`, `references/improving_agents/`) under the spec's `LOOP_WORDS` table and section 4.5. Its procedural rows turned descriptions of Kiln Harness Tuner (HT) into instructions: "ask the user", "measure it yourself", "applies when running Kiln Harness Tuner", and HT's record strings and check names went. This phase reverts the trees to batch 7 (`b4b066e`, byte-identical to HT's normalised text at `b49f159`), re-applies only the changes on the owner's keep list, and adds one section to `references/improving_agents/index.md` that tells an agent on the MCP how to read HT's words.

The design is [phase_8_revisit.md](../phase_8_revisit.md). The owner's answers to its section 7 (2026-11-24) are recorded there and in [harness_tuner_alignment_decisions.md](../harness_tuner_alignment_decisions.md) section 12. Backlog items closed: B7, B11, B12.

Kiln paths are from `app/mcp/kiln_mcp_server/skill/`. `KT-` is an item of `research/harness_tuner_alignment_audit/knowledge_tree.md`.

## Steps

### 1. Record the owner's answers

- `phase_8_revisit.md`: front matter `status: approved`; replace the "requires the owner's approval" banner with a dated "Approved" note; add section 8, "Owner answers (2026-11-24)", one line per question of section 7, and the decisions given with them (noise and detectability, screening and skill bundles, read-only record lines, B7, B11, B12).
- `harness_tuner_alignment_decisions.md`: new section 12 with the same answers; the header line names the new date; section 8's "still wait on the owner's approval" line and the "Related" line are updated.
- `implementation_plan.md`: the Phase 17 line loses "requires owner approval" (its checkbox is toggled at commit).

### 2. Fix the spec first (`components/skill_and_content.md`)

- Section 4.5, bullets 2 and 3: the rewording is vocabulary only (roles, gateway operation names, run-folder paths, the loop words of `LOOP_WORDS`). HT's rules apply to every agent as HT states them; HT's inputs, outputs, code checks, tools and record strings are named plainly as HT's; a rule keeps its case for an absent input, and that case is the rule for an agent without the input; no document branches on "when running Kiln Harness Tuner"; how an agent on the MCP reads these words is said once, in the section "How to read these documents over MCP" of `references/improving_agents/index.md`.
- Section 4.5, the fixed point "Noise": HT has a run-to-run noise check (`--noise-check N`) and a pre-run detectability check; Kiln measures neither. HT's rule for an absent `train_noise` (a flip rate of 10%) and the floor of 6 changed items for an absent `train_detectability` apply to every agent. The skill still adds no noise guidance of its own and no second identical run config.
- Section 7, the `smell-detectors` row: a smell names HT's code detection and states its threshold.
- Section 8: the `tree-banned-term` row and the allowed exceptions name the HT record strings that hold a banned loop word (step 5).
- Section 9: the "later fixes" paragraph uses the rules of step 6; row 8's work list and rule for hard cases are replaced with the vocabulary-only rule, marked as revised by Phase 17; the knowledge-tree row of `BANNED_TERMS` loses HT's input and output names, `install_skill_bundle` and `REJECTED AT VAL`; `LOOP_WORDS` keeps its six vocabulary rows (arm, the val gate, a probe, a screening round, the owner, "the guidance") and loses the five procedural rows.
- `architecture.md` build step 9: the sandbox review lists `levers/new_tool.md` beside `code_tools.md` and `judge_types.md` (the second half of B12, independent of the revert).

### 3. Revert the trees

`git checkout b4b066e -- app/mcp/kiln_mcp_server/skill/references/levers app/mcp/kiln_mcp_server/skill/references/improving_agents`. The generated index blocks are rebuilt with `skill_checks build` at the end.

### 4. Re-apply the keep list, file by file

Each later commit is a checklist, applied by hand to the reverted text:

| Change | Source | Rule |
|---|---|---|
| Gateway operation → endpoint doc path | `919fb6a` | The path batch 8 used for each operation. Where the sentence states what HT's gateway does that the Kiln endpoint does not (the model policy refused at create), the subject becomes "Code", HT's own word for its code (`working-inside-restrictions.md` already says it) |
| Role → "you" | `919fb6a` | The planner, the builder, the analyzer, "the tuner" as the actor. Where the source names a role's skill or entry file as the holder of a procedure ("the planner's skill", "the planner's entry file"), the holder is named plainly: Kiln Harness Tuner, or the Kiln file that now holds the table (`references/improving_agents/index.md`) |
| arm → candidate (or experiment); the val gate → the confirmation on val; a probe → a quick check; a screening round → a screening; the owner (of the agent or an eval) → the user; "the guidance" → what the user asked | `919fb6a` | The kept `LOOP_WORDS` rows. "The project's owners" (the authors of the knowledge) becomes "the authors of this knowledge", because a Kiln project is the user's |
| Other banned words (`gateway`, `scratch folder`, the names of HT skills that are not ported, paths into HT's skills) | `919fb6a` | The smallest rewording that keeps the sentence's rule |
| Each lever's "See also" | `919fb6a`, `c9ff717`, `d98217b` | As at `0e999b9` |
| The two size shortenings | `919fb6a` | `levers/output_mode.md` and `smells/tools-on-a-live-server.md` are shortened in wording until they pass `size`; no rule, input, check, verdict or record string goes |
| Leak-rule pointers to `references/knowledge/train_val_test.md` | `4d0ec7e` | As at `0e999b9` |
| Code-tool template paths, `code_tool_authoring.md` pointers, the uniqueness rule of `levers/new_tool.md` (`KT-B18`) | `c9ff717` | As at `0e999b9` |
| "See also" `references/knowledge/run_an_experiment.md` | `d98217b` | 7 levers |
| "No sandbox" (B30) and the code-trust steps (B23) | `de0ceb8` | `levers/new_tool.md` (description, body, step 1, `api_docs`) |

Everything else that batch 8 changed stays as HT wrote it: HT's inputs and outputs, its code checks and verdicts, its record strings, "smoke", "promotion", "wave", "drive", "objective", "this run".

### 5. Apply the approved decisions in the trees

- **Index section** (`references/improving_agents/index.md`, after "How to read these documents"): "How to read these documents over MCP", the text of `phase_8_revisit.md` 5.4. The role line names the roles as Kiln Harness Tuner's ("its planner, builder or analyzer"), because "the planner" stays a banned term. It adds the playbook-step flow (M11, from HT's `planner.md` 13–42, in Kiln's words) and the `KT-B14` line: the stop rules and the confirmation on val of "A clear measurement outranks a document" are judged with `references/knowledge/run_an_experiment.md`.
- **Noise and detectability** (`dealing-with-a-noisy-eval.md`, `dealing-with-a-saturated-eval.md`, `spending-the-budget.md`): one plain sentence that Kiln Harness Tuner has a run-to-run noise check (`--noise-check N`, result `train_noise`) and a pre-run detectability check (result `train_detectability`). HT's rule for an absent `train_noise` stays as written. Where `train_detectability` is used, one sentence gives the case for an absent input: the floor is 6 changed items, all one way.
- **The five detector smells:** HT's text, with the threshold number added where HT names only the reference (200,000 characters; 4,096; 1,024; 40 tools; 8 months).
- **`KT-B13`:** "train" is added to the item-reading steps that name no split (`dealing-with-a-wrong-eval.md`, `dealing-with-an-eval-near-zero.md`, `add-the-missing-requirement.md`, `state-the-output-contract.md`, `missing-context-the-agent-could-be-given.md`).
- **`KT-B19`:** the commissioning rules go back into `dealing-with-a-saturated-eval.md` and `dealing-with-a-wrong-eval.md` step 5 and 4 (a new eval is the rare exception, none for a closed issue, close won't-fix when it cannot reproduce, never reopen a fixed issue), stated on HT's commission sentence. The "no number, no item id and no trace" recording rule is not re-added.
- **B11:** `levers/skill.md` `api_docs` gets `post_api_projects_project_id_skills.md`. The revert restores `levers/output_mode.md`'s "The model preflight does not show this: its test call attaches no tools" and HT's `params` wording (`overrides` with the three settings); both are checked after the revert.

### 6. Code: `tree_check.py`

- `BANNED_TERMS["knowledge"]` keeps the 54 operation names, `gateway`, `the tuner`, `harness-tuner`, `kiln-harness-tuner`, the role names, `the probe`, `scratch folder` and the loop words; it drops `install_skill_bundle`, `open_questions`, `rejected_summary`, `allowed_models`, `model_policy`, `train_noise`, `train_detectability`, `measurement_prices`, `eval_sizes`, `lever_attempts`, `should_wrap_up`, `measure_issue_baseline`, `eval_only`, `eval_building`, `probe_results` and `REJECTED AT VAL`.
- New `HARNESS_TUNER_RECORD_STRINGS` (knowledge scope): the record strings that HT's code writes and that hold a banned loop word (`- rejected at the val gate`, `- blocked at the val gate`, `- held at the val gate`). The scan blanks them out of a line before it matches the knowledge-scope terms, so that a playbook can quote HT's record exactly. A comment gives the reason and the source (`memory_formats/experiment_records.md`).

### 7. Glue and maintenance docs

- `.agents/skills/knowledge-maintenance/SKILL.md` 4.6 step 2: HT's text is ported as written with only the mechanical changes (root paths, endpoint doc paths, the kept `LOOP_WORDS` rows, role → you); HT's inputs, outputs, code checks, tools and record strings are named as HT's; no "when running Kiln Harness Tuner" branch; the index section explains them to MCP agents. The check bans only the operation names, the role names and the loop words.
- `app/mcp/knowledge_backlog.md` (B7), with the backlog procedure: "Smell: an old model" goes; "A repeat measurement on request" and "A quick check for room to improve" each get one example line about Kiln Harness Tuner.
- `backlog.md`: B7, B11, B12 closed with a "Closed:" line each (B12: moot after the revert, with the replacement work named).
- Any glue file whose link into the trees must change (found by the checks).

### 8. Build and verify

- `uv run python -m kiln_mcp_server.skill_checks build`, then the skill checks, the tests of `app/mcp`, and `uv run ./checks.sh --agent-mode`.
- **Diff check (5.5).** Re-run the audit's normalisation and sentence diff with HT's normalised text replaced by the batch 7 export (they are byte-identical): export `b4b066e` and the working tree's two trees to the scratchpad, split each file into sentence groups (the audit's `units()` of `sent.py`, front matter blanked except `description`), and `difflib` the groups. Every changed group is classified by hand into one row of the step 4 table or one item of step 5; a group that fits none is fixed or listed in the phase report. The diff of the working tree against `b4b066e` is kept in the scratchpad for review.

## Tests

- `test_tree_check.py::test_banned_terms_by_scope`: still finds an operation name, `gateway` and `arm` in the knowledge scope.
- `test_tree_check.py::test_harness_tuner_inputs_and_outputs_are_allowed_in_the_knowledge`: `train_noise`, `open_questions`, `install_skill_bundle`, `— REJECTED AT VAL` in a lever give no problem.
- `test_tree_check.py::test_role_names_stay_banned_in_the_knowledge`: `the planner`, `the builder`, `the analyzer` and "the planner's skill" each give a problem.
- `test_tree_check.py::test_harness_tuner_record_strings_may_hold_a_loop_word`: `` `- rejected at the val gate <MM-DD> vs baseline <rc> — ` `` passes; "the val gate" elsewhere on the same line still fails.
- `test_shipped_skill.py::test_the_knowledge_trees_have_no_harness_tuner_branch`: no file of the two trees contains "applies when running" or "when running Kiln Harness Tuner".
- `test_shipped_skill.py::test_the_index_explains_harness_tuner_words_to_mcp_agents`: `references/improving_agents/index.md` has the section "How to read these documents over MCP", which names `references/knowledge/run_an_experiment.md` and `references/knowledge/memory.md`.
- `test_shipped_skill.py::test_the_record_strings_in_the_knowledge_are_harness_tuner_formats`: each backticked HT record line quoted in `dealing-with-train-wins-rejected-at-val.md` is one of `HARNESS_TUNER_FORMATS`.
- Any existing test that pinned batch-8 text is adjusted to the restored text.
