---
status: complete
---

# Harness Tuner alignment: owner decisions

Recorded 2026-11-23 in three rounds (sections 1–7 first; sections 8 and 9, then section 10, the same day), and on 2026-11-24 (section 11), on branch `claude/kiln-mcp-server-impl` at `7af37d1`, after the three Harness Tuner alignment audits in `research/harness_tuner_alignment_audit/` (`knowledge_tree.md`, `ht_skills.md` with `ht_skills_maps/`, `contract.md`). The audits compare Kiln Harness Tuner (HT) at `b49f159` with Kiln at `25157f3`.

These decisions override the audits where the two differ. An audit "Fix" line that adds a branch, a lane, or a write step for a code-owned record is overridden by the decisions below.

The decisions are copied as the owner gave them. Lines marked *Where it goes* are bookkeeping added when they were recorded.

## 1. Goal

> This project ports Kiln Harness Tuner's (HT) skill content into the Kiln skill. HT re-points to it later in a separate **switchover project**, which updates HT. This project's bar is: once HT switches over, its agents do not get incorrect guidance from the Kiln skill. HT switching over without changes on its side is not expected.

*Where it goes:* [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md) lists what the switchover project must do on HT's side.

## 2. Handled by the switchover project, not blocking here

> - HT's loader and prompts adapting to the Kiln skill's layout and front matter (audit "layout" items);
> - the fence (HT keeps its gateway until then);
> - HT's role skills and role entry files stay in HT, for HT only, and were rightly not ported;
> - HT's own tools (noise, detectability, screening, etc.) "are coming over in the next project";
> - the skill-bundle ("create skill from a folder") API.

*Where it goes:* [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md). This project does not work on any of these.

## 3. Branches

> Minimize them; branch only when necessary. Share as much of HT's work as possible; most rules are shared, and the rules HT invented apply to MCP agents too.

*Where it goes:* Phase 17 (the knowledge trees) and Phase 18 (the glue files). One consequence: a rule that says it "applies when running Kiln Harness Tuner" is a branch, and it is removed wherever the rule can apply to every agent.

## 4. Memory

> `references/knowledge/memory.md` stays a reference for both HT and MCP agents. Records that HT's code writes with strict formats (baseline, val, `FIXED:`/`WONT_FIX:`/reopen, `OPEN:`, experiment states and suffixes, screening, etc.) are listed as read-only, with their formats given for readers, not for writing. MCP agents may write some records — lessons, dead ends, new issues — and more in future. HT already knows how to write, so the doc's formats must match HT's code exactly (the contract audit lists the strings). Write steps for code-owned records are removed from other skill files (e.g. `run_an_experiment.md`).

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), items 1 and 2.

## 5. Lanes

> Cut. Do not add an MCP narrow/broad lane. HT enforces its lanes in code. In a follow-up project the owner removes MCP read access to val/test, so MCP agents cannot read them.

*Where it goes:* no work. Audit items `ht_skills.md` M2 and `knowledge_tree.md` C4 (the missing train lane) are closed by this decision. Backlog B13 is proposed for closing in Phase 18 on this basis, and the owner confirms it.

## 6. Batch 8 (commit `919fb6a`, "loop vocabulary in the knowledge trees")

> It put procedural instructions ("ask the user", "measure it yourself", "applies when running Kiln Harness Tuner", dropped HT record strings and check names) into the levers, techniques, playbooks and smells, following the spec's `LOOP_WORDS` table and §4.5. The fix needs a new spec phase: **"Revert and revisit phase 8"**, which requires the owner's approval before any work. Likely approach (to be approved): revert the knowledge trees to batch 7 (`b4b066e`, byte-identical to HT's normalised text), keep only the mechanical changes (root-relative links, `api_docs`) and changes the owner already approved (e.g. the B30 "no sandbox" wording), re-apply better rules, and add one short "how MCP agents read these documents" section to `references/improving_agents/index.md` instead of rewriting 74 files.

*Where it goes:* Phase 17 ([phase_8_revisit.md](phase_8_revisit.md)). No work starts before the owner approves it. Backlog B7, B11 and B12 move there.

## 7. Shared method rules that lived only in HT's role skills

> Audit `ht_skills.md` M-items: keep rule on val, exact cost/speed rule, integrity checks at keep, leak/judge-copy definitions, costing lanes and the third-party-operator rule, the quick-check definition, reading results/report wording, the lean-target guard default, merging, build hygiene, playbook-step flow, and the smaller ones. Decided **case by case** by the owner.

*Where it goes:* superseded by decision 9 below. The case-by-case table is replaced by one guide for MCP clients.

## 8. Confirmations (2026-11-23, second round)

The owner answered "ok" to three of the decisions above:
- **Memory** (section 4): read-only code-written records; writable lessons, dead ends and issues: "ok".
- **The Phase 8 revert-and-revisit phase** (section 6), which needs the owner's approval before any work: "ok". The approach itself, and the questions in [phase_8_revisit.md](phase_8_revisit.md) section 7, still wait on the owner's approval.
- **Lanes cut** (section 5): "ok".

## 9. One guide for MCP clients in place of the case-by-case table (2026-11-23, second round)

The owner's words:

> Let's make a new doc for MCP clients integrating most of these? Something like 'on_off_experimetnation_guide.md' or something like that. It heavily pushes user to harness tuner for advanced optimization (saying it enforces the loop and these principals in code, and is much more robust), but carries the key lessons for more one-off ideas from MCP. It also says 'if you are harness tuner, follow your system prompt. It has similar concepts, but better enforcement.'

The manager's proposal to the owner, confirmed by the owner in section 10:
- Make this guide by reshaping `references/knowledge/run_an_experiment.md`, rather than by adding a second file. Then one file owns the method (C12), and the 25 or so existing links to it stay.
- Rename it to `one_off_experimentation_guide.md` only if the owner prefers.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), item 5. The table of shared method rules, with each rule's HT source and audit id, becomes the guide's content list. Each row is marked "include" by default, for the owner to adjust. The exact cost/speed rule (M1) is one of the rows. Including it removes the "applies when running Kiln Harness Tuner" branch from the file, which replaces the Phase 16 batch 3 decision on B14 ("keep as is").

## 10. The one-off experimentation guide: its file and its content (2026-11-23, third round)

The owner approved the manager's recommendations:
- **The file.** Reshape `references/knowledge/run_an_experiment.md` into the guide, and keep that name. There is no rename to `one_off_experimentation_guide.md`. This confirms the proposal in section 9.
- **The content list.** The "Include / leave out" column of the table in Phase 18 item 5 is set as below. The row ids are the table's: `M` rows are `HS-M` items of `ht_skills.md`, and `S` rows are smaller rules from `ht_skills_maps/`.

| Decision | Rows |
|---|---|
| Include | M1, M5, M6, M7, M9, M10, M12, M18, M21, M22, S3, S5 |
| Include, short form | M4: the headline mean win rate against the baseline, plus no eval clearly down; leave out the priority-weighted gate |
| | M8: keep the third-party operator's agreement rule, the human gate and "judging is paid again on every re-score"; leave out the six-lane detail |
| | M15: keep the writing rules; leave out the provenance and `derived_from_ids` mechanics, which the levers already cover |
| | M17: leave out replicate folding |
| | M19: keep "never carry a magnitude over from another task" and the floor of 6 wins for p < .05; leave out the planning moves |
| Fold into M1 | S4 |
| Move to the "How to read" section of `references/improving_agents/index.md` (Phase 17) | M11 |
| Leave out | M16, keeping one line: "combine by hand; never combine two candidates of one head-to-head group" |
| | S1, S2 |

One question stays open, and Phase 18 asks it (question 9): does the follow-up project's removal of MCP read access to val and test cover all of val, summary metrics included, or only val rows? If all of val, the val parts of M1, M4, M6 and M21 say "confirming on val needs Kiln Harness Tuner" instead.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), item 5 and its questions. M11 goes to Phase 17 ([phase_8_revisit.md](phase_8_revisit.md)), whose files Phase 18 does not edit.

## 11. Answers to the questions of Phase 18 (2026-11-24)

The owner answered the nine questions of [phase_plans/phase_18.md](phase_plans/phase_18.md). The owner's words are quoted where the owner gave them.

1. **Writable kinds.** `constraint`: yes, for the restrictions the user states. `hypothesis`: "reserved for harness-tuner". Kiln Harness Tuner reads it, so the docs must say this clearly.
2. **`memory.md`'s size.** `memory.md` stays short. The read-only formats move out of it into a folder with one small file per format, `references/knowledge/memory_formats/`, so that an agent's context is not flooded. `memory.md` links to the files and says which file covers what. The formats are for reading, not for writing, and they must match Kiln Harness Tuner's code exactly (`contract.md` section 3).
   - **Correction (same day):** "memory.md needs to link to docs individually or an index. There's no folder list tool." `memory.md` names each file by its full path, and never tells the agent to look in or list the folder.
3. **`OPEN: ` answers.** Allowed: a `constraint` that cites the `OPEN: ` record's id. But "don't really suggest this like it's common. Not a recommended flow, don't want to write a bunch about it and make it happen." At most one short line, phrased as a rare case.
4. **One-off records.** No `experiment` records from MCP agents. A one-off's lasting results are `lesson`, `dead_end`, `issue` (and `constraint`).
5. **B14.** Yes: porting the exact cost/speed rule (Phase 18 item 3, row M1) replaces the earlier "keep as is".
6. **Project files** (`HS-M13`). Add the sentence now, in `working_with_project_files.md`: the project tree holds val and test items, and reading their rows counts as reading val or test data.
7. **B19.** Yes, the proposed text of Phase 18 item 6 is approved: never change the task's default run config on your own initiative, only when the user asks. Both files say so.
8. **B13.** Resolved by allowing MCP agents to read the `val` memory record, which holds only summary metrics. Close B13. No extra fence is needed for the val record.
9. **What the val fence covers.** The follow-up project's val and test fence covers only rows; val summary metrics stay readable. So the val parts of M1, M4, M6 and M21 stay as written, with no "needs Kiln Harness Tuner" wording.

**The one-off headline (2026-11-24).** Owner decision: the one-off headline is eval-level, how many evals the candidate is ahead on by summary scores, the target eval included; Kiln Harness Tuner's item-level mean win rate is the loop's version.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), items 1 to 8.

## Related

- [phase_8_revisit.md](phase_8_revisit.md): Phase 17. It needs the owner's approval before any work.
- [phase_plans/phase_18.md](phase_plans/phase_18.md): Phase 18, the fixes outside the knowledge trees, including the one-off experimentation guide.
- [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md): what the switchover project must do in HT.
