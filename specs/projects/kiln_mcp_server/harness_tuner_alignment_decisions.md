---
status: complete
---

# Harness Tuner alignment: owner decisions

Recorded 2026-11-23 in two rounds (sections 1–7 first; sections 8 and 9 the same day), on branch `claude/kiln-mcp-server-impl` at `7af37d1`, after the three Harness Tuner alignment audits in `research/harness_tuner_alignment_audit/` (`knowledge_tree.md`, `ht_skills.md` with `ht_skills_maps/`, `contract.md`). The audits compare Kiln Harness Tuner (HT) at `b49f159` with Kiln at `25157f3`.

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

The manager's proposal to the owner, pending the owner's confirmation:
- Make this guide by reshaping `references/knowledge/run_an_experiment.md`, rather than by adding a second file. Then one file owns the method (C12), and the 25 or so existing links to it stay.
- Rename it to `one_off_experimentation_guide.md` only if the owner prefers.

*Where it goes:* Phase 18 ([phase_plans/phase_18.md](phase_plans/phase_18.md)), item 5. The table of shared method rules, with each rule's HT source and audit id, becomes the guide's content list. Each row is marked "include" by default, for the owner to adjust. The exact cost/speed rule (M1) is one of the rows. Including it removes the "applies when running Kiln Harness Tuner" branch from the file, which replaces the Phase 16 batch 3 decision on B14 ("keep as is").

## Related

- [phase_8_revisit.md](phase_8_revisit.md): Phase 17. It needs the owner's approval before any work.
- [phase_plans/phase_18.md](phase_plans/phase_18.md): Phase 18, the fixes outside the knowledge trees, including the one-off experimentation guide.
- [harness_tuner_switchover_requirements.md](harness_tuner_switchover_requirements.md): what the switchover project must do in HT.
