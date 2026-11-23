---
status: complete
---

# Implementation Plan: Kiln MCP Server

The order follows [architecture.md](architecture.md) section 6. Each phase names the docs that specify it; the detail is there, not here. Batch numbers are those of the content plan in [skill_and_content](components/skill_and_content.md) section 9.

## Phases

- [x] Phase 1: The `app/mcp` project, the server mounted in the desktop app at `/mcp`, and `kiln_skill` serving a placeholder skill tree. PyInstaller hook, workspace and CI wiring. ([mcp_server_and_api_tool](components/mcp_server_and_api_tool.md) sections 1–2; [skill_and_content](components/skill_and_content.md) sections 2–3; architecture section 9)
- [x] Phase 2: `call_kiln_api`. The `KilnApiCallTool` refactor in `libs/core`, the MCP tool and its pipeline, the route index, the policy seam and the `x-mcp-policy` tag, `body_limit`, `save_to_tmpfile`, progress updates. The end-to-end test on the real desktop app. (mcp_server_and_api_tool sections 3–6.2, 9–10)
- [x] Phase 3: The block list annotations and their tests, and the data guide route from `PUT` to `POST` with its web UI call sites and regenerated files. (mcp_server_and_api_tool sections 6.3 and 7; [mcp_block_list_review](research/mcp_block_list_review.md))
- [x] Phase 4: Model info endpoints and the models.dev cache. ([model_info](components/model_info.md))
- [x] Phase 5: The API reference pipeline, its freshness check, and the skill-tree check. The API reference is generated for the first time. (skill_and_content sections 5, 6 and 8)
- [x] Phase 6: The knowledge tooling port, the `knowledge-maintenance` skill and the knowledge backlog, with the new `using_harness_tuner` entry. (skill_and_content section 7)
- [x] Phase 7: Content, part 1: import the Assistant's skill and adapt it. Batches 1–6: references, model info wording, link templates, identity and on-demand loading, blocked-capability wording, help-article URLs. (skill_and_content sections 4 and 9)
- [x] Phase 8: Content, part 2: import the knowledge and reword it. Batches 7–9: import and link rewrite, loop vocabulary, `train_val_test.md`. (skill_and_content sections 4.5 and 9)
- [x] Phase 9: Content, part 3: the new and rewritten guides. Batches 10–12 and 13a: `memory.md`, code tools and MCP wiring, the project-files guide, `run_an_experiment.md`, `diagnose_an_agent.md`, and the improve-task router. (skill_and_content sections 9.1–9.4)
- [x] Phase 10: Content, part 4: wire the knowledge into the Assistant's files, turn on every remaining check, and tune the server and tool texts. Batches 13b and 14. (skill_and_content section 9; mcp_server_and_api_tool section 2.4)
- [x] Phase 11: The Settings callout, the Connect page, `agent_install.md`, the README section, and the rename of the `kiln_mcp` help text. ([connect_page_and_install](components/connect_page_and_install.md); [ui_design](ui_design.md))
- [x] Phase 12: Probe the real API through the MCP for unclear errors and missing route descriptions; fix them at the endpoint. (architecture section 10; functional spec section 11)
- [x] Phase 13: Reviews by people: the sandbox wording, the knowledge's public-source claims and case studies, and the owner's read of `SKILL.md`, `train_val_test.md` and the two new guides. Apply their changes. (architecture section 6, step 9)
- [x] Phase 14: Manual sanity check with real agents, and the fixes it leads to. Decide whether phase 15 is needed. (functional spec section 16)
- [x] Phase 15 (optional): a "load the endpoint doc first" check that keeps the server stateless. Only if phase 14 shows agents calling endpoints wrongly because they skipped the docs. (functional spec section 5.9) Not needed: owner decision after phase 14.
- [ ] Phase 17: Revert and revisit phase 8 — requires owner approval. ([phase_8_revisit](phase_8_revisit.md))
- [ ] Phase 18: Harness Tuner alignment fixes outside the knowledge trees. ([phase_18 plan](phase_plans/phase_18.md); [decisions](harness_tuner_alignment_decisions.md))
- [ ] **Phase 16: Backlog.** Review open backlog items with the user, then close or dismiss each through the standard phase flow.

## Notes

- Phases 13 and 14 need people and real agent CLIs. A coding agent prepares what they need (the list of files to read, the scenario list, a seeded test project) and applies the changes that come back.
- Phases 7–10 are large. Each batch inside them is its own commit, verified by the check its row names.
- The Assistant export stays outside the repository in every phase. The content phases record the two source versions they port from (skill_and_content section 9).
