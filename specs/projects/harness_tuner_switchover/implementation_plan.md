---
status: complete
---

# Implementation Plan: Harness Tuner Switchover

Four phases. Each names the docs that specify it; the detail is there, not here. Inside a phase, each listed item is its own commit, in the order given.

Component docs: [kiln_measurement_apis](components/kiln_measurement_apis.md), [kiln_smells_skills_version](components/kiln_smells_skills_version.md), [ht_skill_reading_and_roles](components/ht_skill_reading_and_roles.md), [ht_api_switch_and_removals](components/ht_api_switch_and_removals.md).

## Phases

- [ ] Phase 1: **Kiln.** Everything in the Kiln repository.
  - Pre-flight first, with no code: spec one is merged with its phases 17 and 18; every skill path this spec names exists; the costing method of `experiment-costing` is in Kiln's skill; the list of skill files to edit (architecture ruling 13) is checked again. A path that moved is corrected in these docs. If a check fails, stop and report. (functional spec section 2)
  - The routes: the significance floor; the train helper and the detectability read; scores by split and the paired comparison; the smell check; the skill bundle routes; the version route. (kiln_measurement_apis; kiln_smells_skills_version sections 2 to 5)
  - The skill text, then the contract test and its list. (kiln_smells_skills_version sections 7 and 8; the list's content is in ht_skill_reading_and_roles section 8)
- [ ] Phase 2: **Harness-tuner reads Kiln's skill.** `SkillReader`, proved first against a real Kiln; the gateway tool `kiln_skill`; the version checks, the contract checks, the start-up order and the developer switch; the role entry files in their new homes; every link re-pointed; the shared rules block; the map from endpoint to gateway tool. (ht_skill_reading_and_roles; ht_api_switch_and_removals sections 3 and 4)
- [ ] Phase 3: **Harness-tuner switches and removes.** The skill bundle tools on the gateway; model info from Kiln; the smell check from Kiln; then every removal in the doc's order, with the knowledge copy last; then the docs, the command-line reference and the packaging. (ht_api_switch_and_removals sections 2 and 5 to 7)
- [ ] Phase 4: **Proof.** The audit against the checklist of core concepts, one run on the demo project, and the fixes they lead to. (ht_api_switch_and_removals sections 8 and 9)

## Notes

- **Release point.** Phases 2 to 4 need a Kiln build that has phase 1, with a raised app version. Harness-tuner's minimum Kiln version is set to it. Nothing in the harness-tuner repository merges before that build exists.
- Each route added or changed in phase 1 comes with the regenerated web client schema and the skill's API reference in the same commit. CI checks both.
- Phases 2 to 4 are done in the harness-tuner repository, with this spec folder open from the Kiln repository.
- Harness-tuner's noise check, its detectability code, its comparison code and the gateway's statistics tool are not touched in any phase.
- `experiment-costing` is removed in phase 3 only if the pre-flight confirmed its port. If not, it stays, and the planner's pointer is not changed.
- Phase 4 needs a person and a real agent CLI, and its demo run spends money on agent tokens. A coding agent prepares the checklist and the command, and applies the fixes that come back.
