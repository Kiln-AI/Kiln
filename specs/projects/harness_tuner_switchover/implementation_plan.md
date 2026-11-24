---
status: draft
---

# Implementation Plan: Harness Tuner Switchover

The order follows [architecture.md](architecture.md) section 8. Each phase names the doc that specifies it; the detail is there, not here. The architecture's unused build step 4 has no phase, so the phase numbers below run on from 4.

Component docs: [kiln_measurement_apis](components/kiln_measurement_apis.md), [kiln_smells_skills_version](components/kiln_smells_skills_version.md), [ht_skill_reading_and_roles](components/ht_skill_reading_and_roles.md), [ht_api_switch_and_removals](components/ht_api_switch_and_removals.md).

## Phases

### Pre-flight

- [ ] Phase 1: Check that the work can start, and write down the result. No code. Spec one is merged, with its phases 17 and 18. Every skill path this spec names exists in the merged tree. The costing method of `experiment-costing` is in Kiln's skill. The list of skill files to edit (architecture ruling 13) is checked again. A path that moved is corrected in these docs first. If a check fails, stop and report. (functional spec section 2)

### Kiln repository

- [ ] Phase 2: The `significance_floor` operation on the statistics route. (kiln_measurement_apis section 2)
- [ ] Phase 3: The train helper and the detectability read. (kiln_measurement_apis sections 1, 3 and 4)
- [ ] Phase 4: Scores by split on the four summary routes, and the paired comparison route. Needs phase 3. (kiln_measurement_apis sections 7 and 8)
- [ ] Phase 5: The smell check, with the release-date read on spec one's model info module. (kiln_smells_skills_version section 2)
- [ ] Phase 6: The skill bundle routes: create from a folder, list files, read a file. Includes `skill_name_errors`. (kiln_smells_skills_version sections 3 and 4)
- [ ] Phase 7: The version route and `compat.py`. (kiln_smells_skills_version section 5)
- [ ] Phase 8: Skill text: the statistics file, the smell documents, the skill lever and techniques, `using_harness_tuner`, and the other files of ruling 13. (kiln_smells_skills_version section 7)
- [ ] Phase 9: The contract test and its list. The list's content comes from ht_skill_reading_and_roles section 8. (kiln_smells_skills_version section 8)

### Release point

- [ ] Phase 10: A Kiln build that has phases 2 to 9, with a raised app version. Set harness-tuner's minimum Kiln version to it. Nothing in the harness-tuner repository merges before this exists.

### Harness-tuner repository

- [ ] Phase 11: `SkillReader`, proved first against a real Kiln. Then the gateway tool `kiln_skill`, the version checks both ways, the contract checks, the start-up order and the developer switch. (ht_skill_reading_and_roles sections 1 to 3; ht_api_switch_and_removals sections 3 and 4)
- [ ] Phase 12: The role entry files in their new homes, every link re-pointed, the shared rules block, and the map from endpoint to gateway tool. (ht_skill_reading_and_roles sections 4 to 7 and 9)
- [ ] Phase 13: The skill bundle install and export as gateway tools, and the loop code that reads a skill's files. The skill installer is removed. (ht_api_switch_and_removals sections 2.1 and 2.2)
- [ ] Phase 14: Model info from Kiln. The model catalogue and its option are removed. (ht_api_switch_and_removals section 2.3)
- [ ] Phase 15: The smell check from Kiln. The five detectors are removed. (ht_api_switch_and_removals section 2.7)
- [ ] Phase 16: The remaining removals, in the doc's order, with the knowledge copy last. Then the docs, the command-line reference and the packaging. (ht_api_switch_and_removals sections 5 to 7)
- [ ] Phase 17: The audit against the checklist of core concepts. Fix what it finds. (ht_api_switch_and_removals section 8)
- [ ] Phase 18: One run on the demo project, and the fixes it leads to. (ht_api_switch_and_removals section 9)

## Notes

- Phases 2 to 9 can be built in any order after phase 1, except that phase 4 needs phase 3. Phase 9 needs the list from the harness-tuner doc, which is already written.
- Each Kiln phase that adds or changes a route regenerates the web client schema and the skill's API reference in the same phase. CI checks both.
- Phases 11 to 18 are done in the harness-tuner repository, with this spec folder open from the Kiln repository.
- Harness-tuner's noise check, its detectability code, its comparison code and the gateway's statistics tool are not touched in any phase.
- `experiment-costing` is removed in phase 16 only if phase 1 confirmed its port. If not, it stays, and the planner's pointer is not changed.
- Phases 17 and 18 need a person and a real agent CLI. Phase 18 spends money on agent tokens. A coding agent prepares the checklist and the command, and applies the fixes that come back.
