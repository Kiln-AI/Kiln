---
status: approved
---

**Approved by the owner on 2026-11-24.** The owner answered the questions of section 7 and approved the approach of section 5. The answers are in section 8 and in [harness_tuner_alignment_decisions.md](harness_tuner_alignment_decisions.md) section 12. The plan of the work is [phase_plans/phase_17.md](phase_plans/phase_17.md).

# Phase 17: Revert and revisit phase 8

Batch 8 of phase 8 (commit `919fb6a`, "loop vocabulary in the knowledge trees") is the batch that reworded the knowledge trees: the levers, techniques, playbooks and smells. The Harness Tuner alignment audits found that it changed what those documents tell an agent. This phase revisits that work.

The owner's decision is in [harness_tuner_alignment_decisions.md](harness_tuner_alignment_decisions.md), section 6. This file sets out the evidence, the approach and the owner's answers.

**Citations.** All audits are in `research/harness_tuner_alignment_audit/`:
- `KT-` is an item of `knowledge_tree.md`.
- `HS-` is an item of `ht_skills.md`.
- `CT-n` is row n of the table in section 1 of `contract.md`.

Kiln paths are from `app/mcp/kiln_mcp_server/skill/`, and the knowledge trees are `references/levers/` and `references/improving_agents/`. HT is Kiln Harness Tuner, at `b49f159`.

## 1. What batch 8 did

The spec gave batch 8 this job (skill_and_content section 9, row 8): reword the 74 imported documents from HT's loop vocabulary into words that a general agent understands, under C11 ("vocabulary only"). `919fb6a` changed 69 knowledge files and the two indexes. It also touched the tree check and its test, and added the phase 8 notes. It did these things:
- **Mechanical work, still wanted:**
  - 83 gateway operation names in the text became endpoint doc paths;
  - role names ("the planner", "the builder") became "you";
  - the `LOOP_WORDS` vocabulary: arm → candidate, val gate → the confirmation on val, probe → a quick check, screening round → a screening, owner → the user;
  - each lever's "See also" got the Kiln files of the table in section 4.5;
  - `levers/output_mode.md` and `smells/tools-on-a-live-server.md` were shortened to pass the size limit.
- **Procedural work, which is the damage:** the `LOOP_WORDS` rows that replace an HT input, output or check, and the section 4.5 rule for loop-only inputs, turned descriptions of HT into instructions. "Ask the user", "measure it yourself", "report it to the user" and "applies when running Kiln Harness Tuner" replaced HT's inputs and code checks. HT's record strings and check names went with them, because the banned terms forbid them.

The knowledge audit normalised HT's text mechanically (root links; `gateway_ops`, `detected_by` and `detectors` dropped; the lever heading renamed). It then diffed that text against batch 7 (`b4b066e`): all 74 files are byte-identical, so batch 7 was purely mechanical. Against `25157f3` there are 416 changed sentence groups. About 330 are vocabulary only, of which a script confirmed 189. The rest are the findings below.

## 2. The change in each file

The columns are:
- **Sentence groups:** the sentence groups that differ between HT's normalised text and `25157f3`. These include the small later edits of batches 9, 11 and 13a (section 5.2), so they are not all from batch 8.
- **Batch 8 lines:** the lines that `919fb6a` added and removed.
- **Findings:** the knowledge-audit items, plus `HS-L1` for the "when running Kiln Harness Tuner" branches that the HT-skills audit lists. "Vocabulary only" means the audit read every changed sentence of the file and found only vocabulary changes.

The group counts come from the audit's working files, in the scratchpad of the session that ran it, which may since have been cleared. The findings come from `knowledge_tree.md` section 1. `KT-B13` on a file that batch 8 did not touch is a gap that HT's text already had, not damage from batch 8.

| File | Sentence groups changed (HT → 25157f3) | Batch 8 lines (+/−) | Findings |
|---|---|---|---|
| `improving_agents/index.md` | – | +22 / −22 | KT-B14 |
| `levers/index.md` | – | +3 / −3 | none (vocabulary only) |
| `levers/model.md` | 12 | +46 / −45 | KT-A4, KT-B8, KT-B9, KT-B12 |
| `levers/new_tool.md` | 13 | +35 / −27 | KT-A5, KT-B8, KT-B18 |
| `levers/output_mode.md` | 7 | +34 / −42 | KT-B8, KT-B9, KT-B10, KT-B17 |
| `levers/params.md` | 7 | +27 / −29 | KT-B8, KT-B9, KT-C2 |
| `levers/prompt.md` | 7 | +23 / −16 | KT-B7, KT-B8, KT-B16, KT-C2 |
| `levers/skill.md` | 9 | +37 / −30 | KT-B1, KT-B8, KT-B15, KT-C1 |
| `levers/tool_config.md` | 7 | +24 / −18 | KT-B7, KT-C2 |
| `smells/document-behind-a-lookup-tool.md` | 1 | +1 / −1 | none (vocabulary only) |
| `smells/faulty-inherited-skill.md` | 2 | +3 / −3 | none (vocabulary only) |
| `smells/fixed-call-chain.md` | 1 | +2 / −2 | KT-B10 |
| `smells/general-query-tool-without-a-guide.md` | 0 | not touched | none (unchanged) |
| `smells/old-model.md` | 9 | +31 / −29 | KT-A3 |
| `smells/one-file-skill-with-many-topics.md` | 0 | not touched | none (unchanged) |
| `smells/skill-too-small-to-earn-its-place.md` | 1 | +2 / −2 | none (vocabulary only) |
| `smells/too-many-tools.md` | 5 | +7 / −7 | KT-A3 |
| `smells/tool-results-flood-the-context.md` | 0 | not touched | none (unchanged) |
| `smells/tool-search.md` | 0 | not touched | none (unchanged) |
| `smells/tools-on-a-live-server.md` | 5 | +8 / −8 | KT-B11 |
| `smells/unnecessary-tools.md` | 1 | +1 / −1 | none (vocabulary only) |
| `smells/very-long-prompt.md` | 5 | +11 / −9 | KT-A3 |
| `smells/very-long-skill-description.md` | 5 | +14 / −12 | KT-A3 |
| `smells/very-long-tool-description.md` | 3 | +11 / −9 | KT-A3 |
| `playbooks/answers-not-grounded.md` | 3 | +3 / −3 | none (vocabulary only) |
| `playbooks/change-the-surface-not-the-words.md` | 7 | +13 / −14 | KT-B10, KT-B11 |
| `playbooks/cheaper-or-faster.md` | 8 | +26 / −26 | KT-B4 |
| `playbooks/dealing-with-a-noisy-eval.md` | 12 | +27 / −26 | KT-B2, KT-B3, KT-B11 |
| `playbooks/dealing-with-a-saturated-eval.md` | 7 | +24 / −20 | KT-B3, KT-B10, KT-B11, KT-B19 |
| `playbooks/dealing-with-a-wrong-eval.md` | 10 | +19 / −18 | KT-B7, KT-B10, KT-B11, KT-B13, KT-B19 |
| `playbooks/dealing-with-an-eval-near-zero.md` | 8 | +16 / −16 | KT-B11, KT-B13 |
| `playbooks/dealing-with-train-wins-rejected-at-val.md` | 14 | +54 / −53 | KT-B5, KT-B6, KT-B7, KT-B10, KT-B19 |
| `playbooks/failure-at-a-tool-call.md` | 2 | +4 / −6 | none (vocabulary only) |
| `playbooks/fit-the-tool-layer-to-the-agent.md` | 7 | +9 / −8 | none (vocabulary only) |
| `playbooks/know-the-agent-before-you-plan.md` | 11 | +19 / −19 | KT-A4, KT-B10 |
| `playbooks/lost-in-long-instructions.md` | 9 | +15 / −14 | none (vocabulary only) |
| `playbooks/malformed-tool-calls.md` | 0 | not touched | none (unchanged) |
| `playbooks/missing-context-the-agent-could-be-given.md` | 0 | not touched | KT-B13 |
| `playbooks/ordering-work.md` | 10 | +24 / −23 | none (vocabulary only) |
| `playbooks/output-contract-not-met.md` | 5 | +22 / −19 | KT-B9 |
| `playbooks/requirement-missing-from-the-prompt.md` | 2 | +3 / −2 | KT-B7 |
| `playbooks/skill-is-not-read.md` | 4 | +5 / −4 | none (vocabulary only) |
| `playbooks/spending-the-budget.md` | 7 | +28 / −25 | KT-A4, KT-B2, KT-B3, HS-L1 |
| `playbooks/working-inside-restrictions.md` | 9 | +19 / −19 | KT-A4, KT-B11, KT-B12 |
| `playbooks/wrong-scope-or-refusal.md` | 1 | +4 / −4 | none (vocabulary only) |
| `playbooks/wrong-tool-chosen.md` | 2 | +2 / −2 | none (vocabulary only) |
| `techniques/add-the-missing-requirement.md` | 4 | +6 / −5 | KT-B8, KT-B13 |
| `techniques/answer-only-from-the-source.md` | 1 | +4 / −4 | none (vocabulary only) |
| `techniques/attach-the-knowledge-source.md` | 12 | +23 / −22 | none (vocabulary only) |
| `techniques/cap-and-preview-wrapper.md` | 4 | +10 / −9 | none (vocabulary only) |
| `techniques/consolidate-tools.md` | 4 | +11 / −11 | KT-B10 |
| `techniques/decision-model-for-a-classifier.md` | 11 | +25 / −25 | KT-B8 |
| `techniques/decline-rules-paragraph.md` | 4 | +9 / −8 | none (vocabulary only) |
| `techniques/directive-in-the-tool-response.md` | 4 | +9 / −9 | none (vocabulary only) |
| `techniques/document-into-a-skill.md` | 5 | +19 / −16 | KT-B1 |
| `techniques/errors-the-agent-can-act-on.md` | 4 | +11 / −10 | KT-B11 |
| `techniques/faster-provider-for-the-same-model.md` | 12 | +20 / −19 | KT-B8 |
| `techniques/guard-tool-calls-at-the-boundary.md` | 4 | +7 / −7 | none (vocabulary only) |
| `techniques/guide-skill-for-a-tool-set.md` | 5 | +12 / −6 | KT-B1 |
| `techniques/guide-skill-for-a-tool-set/sample-queries.md` | 2 | +4 / −4 | none (vocabulary only) |
| `techniques/guide-skill-for-a-tool-set/schema-as-leaf-files.md` | 1 | +4 / −4 | none (vocabulary only) |
| `techniques/guide-skill-for-a-tool-set/timestamps.md` | 0 | not touched | none (unchanged) |
| `techniques/long-prompt-into-a-skill.md` | 11 | +23 / −19 | KT-B1 |
| `techniques/model-swap-inside-a-class.md` | 12 | +35 / −34 | KT-B8 |
| `techniques/new-tool-description.md` | 5 | +10 / −9 | HS-L1 |
| `techniques/normalize-inputs-wrapper.md` | 4 | +10 / −8 | none (vocabulary only) |
| `techniques/one-general-rule-per-edit.md` | 7 | +15 / −13 | KT-B16, HS-L1 |
| `techniques/policy-as-step-by-step-procedures.md` | 3 | +10 / −9 | none (vocabulary only) |
| `techniques/prune-one-group-at-a-time.md` | 8 | +20 / −18 | KT-B7 |
| `techniques/remove-or-scope-tools.md` | 5 | +10 / −10 | KT-B7, KT-B10 |
| `techniques/rewrite-an-inherited-skill.md` | 10 | +24 / −19 | KT-B1, KT-B8 |
| `techniques/roll-up-tool.md` | 5 | +13 / −13 | KT-B10 |
| `techniques/skill-into-the-prompt.md` | 4 | +8 / −8 | none (vocabulary only) |
| `techniques/state-the-output-contract.md` | 3 | +2 / −2 | KT-B13 |
| `techniques/structure-a-long-prompt.md` | 8 | +20 / −18 | none (vocabulary only) |
| `techniques/thinking-level-ladder.md` | 16 | +33 / −33 | KT-B8 |
416

Totals: 74 imported documents and the two indexes. Batch 8 left 7 documents untouched. 44 documents have findings; two of them (`missing-context-the-agent-could-be-given.md` and `state-the-output-contract.md`) have only `KT-B13`, which is not from batch 8. 24 changed in vocabulary only, and 6 not at all.

## 3. Categories of damage

| # | Category | What batch 8 wrote | Example | Audit items |
|---|---|---|---|---|
| D1 | "Ask the user" in place of HT's inputs | An HT input (`allowed_models`, `model_policy`, `flagged_models`, `measurement_prices`, `should_wrap_up`) became a question to the user | `levers/model.md:70-71`: "Ask the user which models and providers are allowed before you create a run config" (HT: the models in `allowed_models` and the model policy). `levers/new_tool.md:42-44`: HT's "Grant trust once in the session" became "Ask the user first" | `KT-A4`, `KT-A5` |
| D2 | "Measure it yourself" or "check it yourself" in place of HT's code | A code detection, a code check or a code-built screening became a by-hand step, and the verdict words went | `smells/very-long-prompt.md`: "the code detection in your input gives …" became "measure it yourself". `levers/params.md:38`: "Code makes each candidate's run config … No agent builds them" became "Make one run config for each candidate". Lost: the verdicts `lever not applied`, `lever unverified`, `applied`, and the stop rule `invalid_output_rate` | `KT-A3`, `KT-B8`, `KT-B9` |
| D3 | "Applies when running Kiln Harness Tuner" branches | A rule with an HT input became a rule that applies only under HT, which leaves MCP agents with no rule, or a weaker one | `playbooks/dealing-with-a-noisy-eval.md:28-37`: "Kiln Harness Tuner measures it … This rule applies when running it". HT has one rule for both cases ("When `train_noise` is absent … the stop rules use a flip rate of 10%"). Also the skill bundle (`levers/skill.md:43,50,67` and four techniques), detectability, the speed/cost screening, and merge timing | `KT-B1`, `KT-B2`, `KT-B3`, `KT-B4`, `KT-B6`, `HS-L1`, `KT-C3` |
| D4 | HT's record strings and check names dropped | Exact strings that HT writes, and the names of its checks, became paraphrase. One claim about them is now wrong | `playbooks/dealing-with-train-wins-rejected-at-val.md:13-29`: HT's `— REJECTED AT VAL`, `- rejected at the val gate <MM-DD> vs baseline <rc> — `, `no gain at val: no targeted eval improved.` and others became words. The playbook says HT "gives the reason in the same words", which it does not. "The judge-copy check" became "a check for copied judge text", which implies a check MCP agents do not have | `KT-B5`, `KT-B7`, `KT-B15`, `CT-5` |
| D5 | HT's output fields became "report it to the user" | An output field of a role became a chat instruction | `open_questions` and `rejected_summary` in 11 places; `rationale` became "your report" (`dealing-with-a-noisy-eval.md:28`); `build_notes` became "the `notes` of the tool's `provenance`" (`techniques/errors-the-agent-can-act-on.md:92`), so HT's builder would now write its reasoning to another place | `KT-B11` |
| D6 | HT's input names replaced by by-hand steps | The input that feeds a rule is no longer named | `probe_results` became "do a quick check" (`levers/output_mode.md:91`); `lever_attempts` became "count from your records"; `measure_issue_baseline` and `evaluation_target` were dropped | `KT-B10` |
| D7 | Statements that are false under HT, or a rule's meaning changed | A sentence about what HT's code does was turned into its opposite, or into another rule | `playbooks/working-inside-restrictions.md:23-26`: "Nothing refuses a run config whose model the user does not allow", where HT's gateway refuses it. `improving_agents/index.md:32-34`: "as the stop rules and the val gate judge it" became "as the measurement on train and the confirmation on val judge it" | `KT-B12`, `KT-B14` |
| D8 | Small losses | A detail went with a rewording | `levers/output_mode.md` Limits lost "The model preflight does not show this: its test call attaches no tools". `levers/skill.md` `api_docs` lacks the create-skill doc. Three "See also" pointers were dropped. The "Text you add" rules of `one-general-rule-per-edit.md` were lost | `KT-B17`, `KT-C1`, `KT-C2`, `KT-B16`; backlog B11 |

Not damage, and kept:
- **The vocabulary-only changes:** about 330 groups. They cover endpoint doc paths, arm → candidate, val gate → confirmation on val, probe → quick check, the "See also" lines, the leak-rule pointers and the threshold numbers, which the audit checked against HT's `thresholds.py`.
- **`KT-B18`:** the uniqueness rule in `levers/new_tool.md`, a documented change.
- **`KT-B19`:** the added rules, which tighten consistently with HT. Question 9 asks whether they stay.

Out of scope here:
- `KT-B13` (item-reading steps that name no split) is a gap in HT's own text. Question 8 asks about it.
- `KT-C4` (no train lane) is closed by the owner's decision to cut lanes.
- `KT-A1` and `KT-A2` (HT's loader and entry files) are for the switchover project ([harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md), SR1 and SR4).

## 4. The root cause is in the spec

Batch 8 did what the spec said. The fix starts in `components/skill_and_content.md`:

- **Section 4.5, the governing rule, bullet 3:** "Where a rule names a loop-only input that a general agent cannot have, the text says what the agent does to get the equivalent, or says that the rule applies when running Kiln Harness Tuner." The first half produced D1, D2 and D6. The second half produced D3.
- **Section 4.5, the fixed point "Noise":** with the `LOOP_WORDS` noise row, it required the noise and detectability branches (D3).
- **Section 9, row 8, rule for hard cases:**
  - "A loop-only input becomes what the agent does to get the equivalent; where a general agent cannot get it, the sentence says that the rule applies when running Kiln Harness Tuner."
  - "A sentence that only says what loop code does becomes 'check it yourself', or goes when it asks nothing of the reader."
  - Row 8's work list adds: "5 smells get 'how to measure this yourself' with the number" (D2).
- **`LOOP_WORDS`:** five of its eleven rows are procedural, not vocabulary:

  | Row | Damage |
  |---|---|
  | `open_questions`, `rejected_summary` → "report it to the user" | D5 |
  | `allowed_models`, "the model policy" → "the models the user allows; ask the user" | D1 |
  | "code checks …" → "check … yourself" | D2 |
  | a reason code that code writes → "the outcome in words" | D4 |
  | the noise inputs → "the rule applies when running it" | D3 |

- **`BANNED_TERMS`, the knowledge-tree scope:** it bans HT's input and output names and `REJECTED AT VAL`, so no document could name HT's inputs or quote its record strings, even plainly as HT's (D4, D6).
- **`.agents/skills/knowledge-maintenance/SKILL.md` 4.6 step 2** repeats the rewrites for every later port of an HT fix (backlog B12), so the damage would recur.

The audits' own "Fix" lines mostly add "Kiln Harness Tuner: X; otherwise Y" branches to each sentence. The owner's decision on branches ([decisions](harness_tuner_alignment_decisions.md), section 3) rules that pattern out.

## 5. Approach (approved by the owner on 2026-11-24)

### 5.1 Fix the spec first

1. Rewrite the parts of section 4.5 and section 9 row 8 that are quoted in section 4:
   - HT's rules apply to every agent as HT states them;
   - HT's inputs, outputs, checks and record strings are named plainly as HT's;
   - no document branches on "when running Kiln Harness Tuner";
   - how an MCP agent reads HT's words is said once, in the index (5.4).
2. Cut `LOOP_WORDS` to its vocabulary rows (arm, val gate, probe, screening round, owner, "the guidance"), and drop the five procedural rows.
3. Cut the knowledge-tree scope of `BANNED_TERMS` to the gateway operation names, the role names and the loop words of the kept rows. Allow HT's input and output names, `install_skill_bundle` and `REJECTED AT VAL` (question 3).
4. Rewrite `knowledge-maintenance` 4.6 step 2 to the same rules (backlog B12).

### 5.2 Revert the knowledge trees to batch 7, and keep what is mechanical or approved

Revert every file under `references/levers/` and `references/improving_agents/` to `b4b066e`. That text is HT's normalised text, with root links and `api_docs` already in place. Then re-apply, by hand, only these changes:

| Kept change | Source | Files |
|---|---|---|
| Gateway operation → endpoint doc path, in the text | `919fb6a`; the map is in that diff (`OPERATION_ENDPOINTS` was not kept in the repository) | 12 files, 72 of the 83 names in the levers |
| Role → "you" | `919fb6a` | about 38 files |
| The vocabulary rows of `LOOP_WORDS` | `919fb6a` | about 52 files |
| Each lever's "See also": the Kiln files of section 4.5 | `919fb6a` | 7 levers |
| The size shortenings of `levers/output_mode.md` and `smells/tools-on-a-live-server.md` (no rule dropped) | `919fb6a` | 2 |
| The leak-rule pointers to `references/knowledge/train_val_test.md` (`tree-split-pointer`) | batch 9, `4d0ec7e` | 18 files, including `improving_agents/index.md` |
| Code-tool template paths and `code_tool_authoring.md` pointers | batch 11, `c9ff717` | 6 techniques and `levers/new_tool.md` |
| "See also" `references/knowledge/run_an_experiment.md` | batch 13a, `d98217b` | 7 levers |
| "No sandbox" (backlog B30) and the code-trust steps (backlog B23): read the state with `GET …/add_code_trust`; only the user grants it | Phase 16, `de0ceb8` | `levers/new_tool.md`, `levers/index.md` |
| The hand-written part of `improving_agents/index.md` | batches 7 and 9 | 1 |

The later commits were made on top of batch 8's text, so their diffs may not apply cleanly to the reverted text. Each one is used as a checklist and applied by hand.

### 5.3 The better rules

Where the reverted text names something only HT has, it is stated once, plainly, for every agent. There is no branch.

- **An HT tool** is named as HT's: "Kiln Harness Tuner has a run-to-run noise check (`--noise-check N`); its result is `train_noise`."
- **A rule** keeps HT's case for an absent input. That case is the rule an MCP agent follows. For example: "When `train_noise` is absent, the noise is not known: use a flip rate of 10%."
- **A by-hand form** is added only where it is the same rule, computed by hand: the detectability room and floor (question 6).
- **A record string** is quoted exactly, as HT writes it (D4). `references/knowledge/memory.md` lists it as read-only (Phase 18).
- **The five detector smells** keep HT's text. Each states its threshold (200,000 characters; 4,096; 1,024; 40 tools; 8 months). Where HT's sentence names only the code detection, the number is added; that is a mechanical change.

### 5.4 One section for MCP agents in `references/improving_agents/index.md`

The 74 files are not rewritten for MCP agents. `index.md`, the entry point of the trees, gets one short section. A draft, for the owner to approve (question 4):

> **How to read these documents over MCP.** These documents are shared with Kiln Harness Tuner, whose agents run without a person and whose code does part of the work. Their rules apply to you as written. Read them this way:
> - A role (the planner, the builder, the analyzer) is you.
> - An input of Kiln Harness Tuner that the user decides (`allowed_models`, the model policy, `measurement_prices`): ask the user. An input that Kiln Harness Tuner measures (`train_noise`, `train_detectability`, `probe_results`, `lever_attempts`): you do not have it, so follow the document's rule for when it is absent.
> - "Code checks", "code refuses", "the code detection in your input": Kiln Harness Tuner's code does this for its agents. Check it yourself, with the same rule and threshold.
> - An output field (`open_questions`, `rejected_summary`, `rationale`): tell the user.
> - A record line that Kiln Harness Tuner writes, such as `— REJECTED AT VAL`: read it, and never write it (`references/knowledge/memory.md`).
> - A Kiln Harness Tuner tool that Kiln does not have (the skill installer, the screening): tell the user it needs Kiln Harness Tuner.

The section also gets the playbook-step flow, which the owner moved here from Phase 18's one-off guide (row M11 of its content list, `HS-M11`; HT `kiln-harness-tuner-knowledge/references/planner.md` 13–42): the smells of the present baseline first, and a smell that blocks other work before the rest; steps in order, each with a condition; Landed → the next step only if the issue is still open; Refuted → the next step; Capped → run again; Inconclusive → the step stays open and the next can run in parallel; an idea of your own is marked "not in the knowledge".

The section also fixes `KT-B14` ("as the stop rules and the val gate judge it"): it points to `references/knowledge/run_an_experiment.md` for how an MCP agent judges. HT's role prompts tell HT agents to skip it (switchover SR6).

### 5.5 Checks

`uv run python -m kiln_mcp_server.skill_checks check` (the knowledge `size`, `sections` and `index` rules, `tree-banned-term` with the new list, `tree-split-pointer`, `tree-path`), `test_shipped_skill.py` (the "See also" and overlap-group tests), and `misspell`.

A diff check like the audit's: re-run the audit's normalisation and sentence diff, HT's normalised text against the result. Every changed sentence group must fall into a row of the table in 5.2, or 5.3, or an owner-approved item. The phase report lists any that do not.

## 6. Open backlog items this phase absorbs

- **B7 (the knowledge backlog entries):**
  - drop "Smell: an old model" from `app/mcp/knowledge_backlog.md`;
  - keep the renames "A repeat measurement on request" and "A quick check for room to improve", each with an HT example as the owner wrote.
  
  It is done here because the renames follow the vocabulary of 5.1, with the `knowledge-maintenance` backlog procedure.
- **B11 (content polish):**
  - `levers/skill.md` `api_docs` gets `post_api_projects_project_id_skills.md` (`KT-C1`);
  - `levers/output_mode.md` Limits: the revert restores HT's "The model preflight does not show this: its test call attaches no tools". The owner decides whether it stays as HT's sentence or becomes "a test call with no tools attached";
  - `levers/params.md` "changes only …": the revert restores HT's wording, which is then checked against the B11 concern.
- **B12 (docs-sync):**
  - `knowledge-maintenance` 4.6 step 2 gets the rules of 5.1, not batch 8's patterns;
  - `architecture.md` step 9 lists `levers/new_tool.md` beside `code_tools.md` and `judge_types.md` for the sandbox review. That edit is independent of the revert.

## 7. Questions for the owner

1. **The approach.** Approve revert-and-re-apply (5.2) over the other way, a targeted fix of the about 86 damaged sentence groups? The targeted fix would follow the audits' "Fix" lines, which mostly add branches.
2. **The vocabulary rows.** Re-apply all of them? These are role → you, gateway operation → endpoint doc path, arm → candidate, val gate → the confirmation on val, probe → a quick check, screening round → a screening, owner → the user. Recommended: all. They keep the text readable for MCP agents and change no rule, and HT's role prompts handle the reverse (switchover SR6 b).
3. **The banned terms.** Allow HT's input and output names, `install_skill_bundle` and `REJECTED AT VAL` in the trees, and keep the gateway operation names and role names banned? Recommended: yes.
4. **The index section.** Approve the draft of 5.4, or give its wording. Is `index.md` the only place it goes, or do `SKILL.md` part 7 and `references/modes/improve_task.md` name it too?
5. **Noise.** HT's rule for an absent `train_noise` (a flip rate of 10%) then applies to MCP agents. That changes the section 4.5 fixed point "Noise" (`KT-B2`). Agree?
6. **Detectability.** Give MCP agents the by-hand form (the room is a count over the train results; the floor is 6 changed items, all one way, for p < .05 on pass/fail), or treat `train_detectability` as an absent input? (`KT-B3`)
7. **Screening and skill bundles.** HT's code builds screenings (`KT-B9`, `KT-B4`), and HT's installer builds skill bundles (`KT-B1`). Kiln has neither, and a bundle has no API until the switchover project builds one. Is the index line "tell the user it needs Kiln Harness Tuner" right for both? Or should an MCP agent build a small screening by hand, within `run_an_experiment.md`'s rule to ask before 3 or more run configs?
8. **`KT-B13`.** Add "train" to the item-reading steps that name no split (a one-word change, consistent with the leak rules)? Or leave them, since the follow-up project removes MCP read access to val and test?
9. **`KT-B19`.** The revert drops the lines that batch 8 added from HT's own role skills: "rare exception / none for a closed issue / won't fix, never reopen", and "no number, no item id and no trace". Re-add them, or leave them to Phase 18's one-off guide?
10. **The kept list.** Is the table of 5.2 the full list of changes to keep? Or did the owner approve other edits to the trees since batch 7, beyond B23 and B30?
11. **Order.** Phase 18 touches no file of the trees, except that the one-off guide may link to `index.md`. So it can run while this phase waits for approval. Agree?

## 8. Owner answers (2026-11-24)

1. **The approach:** revert the knowledge trees to batch 7 and re-apply (5.2), not a targeted patch.
2. **The vocabulary rows:** re-apply them all: role → you, gateway operation → endpoint doc path, arm → candidate, val gate → the confirmation on val, probe → a quick check, screening round → a screening, owner → the user.
3. **The banned terms:** allow HT's input and output names, `install_skill_bundle` and `REJECTED AT VAL` in the trees. Keep the gateway operation names and the role names banned. `tree_check.py` `BANNED_TERMS`, its tests and skill_and_content section 8 change with it.
4. **The index section:** approved as drafted in 5.4, in `references/improving_agents/index.md` only. It includes the M11 playbook-step flow, and the `KT-B14` fix that points to `references/knowledge/run_an_experiment.md`.
5. **Noise** and 6. **Detectability:** say plainly that Kiln Harness Tuner has a noise check and a detectability check. For MCP agents, the document's rule for an absent input applies: the flip rate of 10% for noise, and the floor of 6 wins for detectability.
7. **Screening and skill bundles:** "tell the user it needs Kiln Harness Tuner", for now. The bundle API comes in the next project.
8. **`KT-B13`:** add "train" to the item-reading steps that name no split.
9. **`KT-B19`:** re-add the commissioning rules of HT's role skills to the saturated-eval and wrong-eval playbooks: building a new eval is the rare exception; none for a closed issue; close the issue as won't fix when the new eval cannot reproduce it; never reopen a fixed issue. Do not re-add the "no number, no item id and no trace" recording rule: after Phase 18, only HT's code writes experiment records.
10. **The kept list:** the table of 5.2 is the full list of changes to re-apply after the revert: the renames; the batch 9 pointers to `train_val_test.md`; the batch 11 code-tool template paths and `code_tool_authoring.md` pointers; the batch 13a "See also" `run_an_experiment.md`; Phase 16's B30 "no sandbox" and B23 code-trust wording; the two size shortenings that dropped no rule; each lever's "See also". Nothing else since batch 7 touches the trees.
11. **Order:** Phase 18 ran first (it touches no file of the trees).

Given with the answers:
- The record lines that HT writes are read-only for MCP agents (Phase 18).
- **"The tuner"** (owner, option B, after review): where "the tuner" is the subject of a rule that limits what may be changed (the task, an eval, a fine-tune, a RAG config), the subject becomes "an experiment" or "this lever"; everywhere else, "the tuner" becomes "you". Reason: Kiln Harness Tuner's agents act only through experiments, so for them the meaning is the same; for MCP agents it limits the rule to experiments, so an agent does not refuse a user who asks it to change a task or an eval. This is an approved rename.
- **B7:** in `app/mcp/knowledge_backlog.md`, drop "Smell: an old model". Keep the renames "A repeat measurement on request" and "A quick check for room to improve", and add a Kiln Harness Tuner example line to each.
- **B11:** the revert restores the `output_mode` sentence on the test call with no tools attached and the `params` wording; check that they are back. Add `post_api_projects_project_id_skills.md` to the `api_docs` of `levers/skill.md`. Close B11.
- **B12:** close it as moot, because batch 8 is reverted. Instead, `.agents/skills/knowledge-maintenance/SKILL.md` 4.6 describes the new rules: HT's text is ported as written with only the mechanical changes and the approved renames, and the section "How to read these documents over MCP" of `references/improving_agents/index.md` explains HT's inputs, code checks, outputs and tools to MCP agents.
