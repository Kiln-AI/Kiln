---
status: complete
---

# Phase 13: Reviews by people

## Overview

Build step 9 (architecture section 6; skill_and_content section 9, "Reviews by people"; functional spec 15). Three reviews by people, on the content as it stands after phase 12, and their changes applied before the manual sanity check (phase 14):

- **A. Sandbox wording**, by a security owner.
- **B. Public-source claims and case studies** in the knowledge, by a person.
- **C. The owner's read** of `SKILL.md`, `train_val_test.md` and the two glue files (`run_an_experiment.md`, `diagnose_an_agent.md`).

A coding agent cannot do these reviews. This plan is the packet the reviewers work from: for each review, the files, the passages and the questions. It also carries the help-URL check that phase 7 left open (section D) and the open backlog items that are owner decisions on the same files (cross-referenced, not resolved). Section E records that the human-facing error wording of phase 12 is not one of step 9's reviews.

Nothing reviewed here is edited, and no owner decision is taken, before the answers come back. Line numbers are those of commit `0855bcd` (phase 12).

`skill/` below stands for `app/mcp/kiln_mcp_server/skill/`, and `K/` for `skill/references/knowledge/`.

## Outcome

The owner's answers. The changes for review A are not applied in this phase; they are backlog B30. Review C is backlog B31.

- **A. Sandbox wording.** Questions 1, 2, 4 and 5: yes. Question 3: "just say 'no sandbox'. Don't need to specify resource sandbox vs sandbox, a subprocess isn't for security and isn't a sandbox." Question 6: "yes remove anything saying there's a sandbox. The sub-process isn't a sandbox." To apply: backlog B30.
- **B. Public-source claims and case studies.** "these were reviewed previously, not your job to re-review." Closed, no changes.
- **C. The owner's read of four files.** Not completed; moved to backlog B31.
- **D. Help URLs.** Done: all 37 URLs returned 200.
- **E. Human-facing error wording of phase 12.** Not a step 9 review; no change.

## Steps

### 1. Review A: sandbox wording (security owner)

Functional spec 15: two Assistant knowledge files say that user code runs with no network or filesystem sandbox. It is a fact about the public app; a security owner sees the wording before it ships. Phase 7 (batch 5) kept the statement as the Assistant's source has it. Phase 8 (batch 8) changed the lever `new_tool.md` to match: it said Kiln runs a code tool "in a sandbox", and the description said "Sandboxed Python code tools". Backlog B12 records that the architecture's list for this review lacks `new_tool.md`; it is reviewed here with the other two.

Files and passages:

| File | Lines | Passage |
|---|---|---|
| `K/code_tools.md` | 10 | "Both are user-authored Python in the same sandbox and share the same trust gate." |
| `K/code_tools.md` | 16 | "User-authored Python runs with no resource sandbox (network + filesystem are open, only crash isolation + a timeout), so the project needs code trust ...; trust is per project, per app session." |
| `K/code_tools.md` | 29 | Step 1 of the workflow: ask the user first, "say that the code will run on the machine where Kiln runs, with no sandbox". |
| `K/judge_types.md` | 51 | "Kiln runs it in a subprocess per eval item ... same sandbox and trust gate, different purpose." |
| `K/judge_types.md` | 55, 60 | "the sandbox has real gotchas ..."; a returned object "fails to serialize out of the sandbox". |
| `K/judge_types.md` | 78 | "There is no resource sandbox (network and filesystem are open; only crash isolation + the timeout) — hence the trust gate ... say that the code runs on the machine where Kiln runs, with no sandbox ..." |
| `skill/references/levers/new_tool.md` | 3, 20–21 | Description "Python code tools for the subject task ..." (was "Sandboxed Python code tools ..."); "Kiln runs it with no resource sandbox (`references/knowledge/code_tools.md`)" (was "in a sandbox"). |

Related wording that states the same fact, for consistency (written in phases 7, 9 and 10 from the files above):

- `skill/SKILL.md:49`: always ask first before granting code trust or adding a local MCP server; "Say what will run and that it has no sandbox."
- `app/mcp/kiln_mcp_server/texts.py:17` (`SERVER_INSTRUCTIONS`): ask "always before one that runs code on the machine where Kiln runs: granting code trust, or adding a local MCP server". No sandbox claim.
- `K/code_tool_authoring.md:156–158`: trust comes first, ask the user, as `code_tools.md` says.

Not the same subject (third-party Pydantic "Run Python" MCP server, which runs in Deno): `K/tools.md:80` ("Sandboxed Python interpreter") and the copied help article `skill/references/docs/tools-and-mcp/README.md:40`. Listed so the reviewer can confirm they may stay.

Context for the reviewer: the code runs in a `multiprocessing` spawn child (`libs/core/kiln_ai/sandbox/worker.py`, `spawn.py`); the app's own trust dialog says "This project wants to run Python code on your machine" (`app/web_ui/src/lib/components/code_tools/code_trust_dialog.svelte:53–57`, `eval_types/trust_code_dialog.svelte:42`); the web UI calls the child process "the sandbox" (`eval_test_run_pane.svelte:224`).

Questions:

1. Is "no resource sandbox: network and filesystem are open, only crash isolation and a timeout" accurate for the current code, for both code tools and code evals?
2. May the skill tell an agent this, and in these words? It is in the knowledge an agent reads and may repeat to a user.
3. The files use "sandbox" in two senses: "no resource sandbox" and "the same sandbox" / "out of the sandbox" for the child process (`code_tools.md:10`, `judge_types.md:51, 55, 60`). Keep both, or one word for the child process?
4. Is "trust is per project, per app session" correct?
5. Is the ask-first sentence agents say to users ("the code runs on the machine where Kiln runs, with no sandbox") enough, or should it say more (for example what the code can reach)?
6. `new_tool.md`: approve the batch 8 change (sandbox claim removed from the description and the text).

### 2. Review B: public-source claims and case studies (a person)

Skill_and_content 9: the knowledge's priors are all marked `Source: public`, and the tree holds no link. The rule of the `knowledge-maintenance` skill, section 8 (and `AGENTS.md:50`): a person approves a case study or a prior before it is committed, unless it is clearly public, with its link; before a number from a public source is written, the source is opened and the number checked, and a line whose numbers do not match is corrected or dropped. The priors came over in batch 7 from harness-tuner at `b49f159`, unchanged except for batch 8's vocabulary.

The 19 priors (paths under `skill/references/improving_agents/`; each line is the `Source:` line; the prior's text is the bullet above it):

| # | File:line | Source as written |
|---|---|---|
| 1 | `playbooks/change-the-surface-not-the-words.md:97` | paper "Beyond Prompts: Measuring and Optimizing LLM Tool-Agent Harnesses", 2026-09-09 |
| 2 | `playbooks/dealing-with-a-noisy-eval.md:84` | paper "EvoSkill v2: Fully Agentic Skill Evolution from Benchmark Adaptation to a Stateful Evolver", 2026-10-23 |
| 3 | `playbooks/dealing-with-a-wrong-eval.md:79` | Shopify post "Building production-ready agentic systems: Lessons from Shopify Sidekick", 2025-08-26 |
| 4 | `playbooks/dealing-with-a-wrong-eval.md:84` | Hex post "How we built a lab to evaluate data agents", 2026-05-22 |
| 5 | `playbooks/dealing-with-train-wins-rejected-at-val.md:118` | paper "Reflective Prompt Optimization of a Deep-Research Agent: A Topic-Disjoint, Multi-Seed Protocol for Measuring Transferable Gains and Prompt-Level Overfitting", 2026-10-08 |
| 6 | `playbooks/ordering-work.md:114` | paper "Building Customer Support AI Agents at 100M-User Scale: An Evaluation-Driven Framework", 2026-06-07 |
| 7 | `playbooks/ordering-work.md:123` | paper "AutoSaddler: Automatic Harness Optimization with Durable Updates from Agent Execution Traces", 2026-08-24 |
| 8 | `playbooks/skill-is-not-read.md:73` | Vercel post "AGENTS.md outperforms skills in our agent evals", 2026-01-27 |
| 9 | `playbooks/skill-is-not-read.md:80` | paper "Harness Updating Is Not Harness Benefit: Disentangling Evolution Capabilities in Self-Evolving LLM Agents", 2026-05-28 |
| 10 | `techniques/attach-the-knowledge-source.md:123` | LinkedIn paper "Text-to-SQL for Enterprise Data Analytics", arXiv 2507.14372, 2025-07-18 |
| 11 | `techniques/model-swap-inside-a-class.md:128` | Hex post "Hill climbing to glory: using evals to improve AI error rate by 7x", 2026-10-08 |
| 12 | `techniques/model-swap-inside-a-class.md:135` | TensorZero post "We're building an automated AI engineer, and it works", 2026-03-23 |
| 13 | `techniques/policy-as-step-by-step-procedures.md:99` | Quesma post "Tau² benchmark: how a prompt rewrite boosted GPT-5-mini by 22%", 2025-09-12 |
| 14 | `techniques/prune-one-group-at-a-time.md:100` | Ramp post "Stack Benchmarking", 2026-06-03 |
| 15 | `techniques/remove-or-scope-tools.md:108` | Vercel post "We removed 80% of our agent's tools", 2025-12-22 |
| 16 | `techniques/remove-or-scope-tools.md:115` | GitHub post "How we're making GitHub Copilot smarter with fewer tools", 2025-11-19 |
| 17 | `techniques/state-the-output-contract.md:102` | paper "Prompt Optimization Is a Coin Flip", arXiv 2604.14585, 2026-04-16 |
| 18 | `techniques/state-the-output-contract.md:110` | Dropbox post "How we optimized Dash's relevance judge with DSPy", 2026-03-17 |
| 19 | `techniques/thinking-level-ladder.md:104` | LangChain post "Improving Deep Agents with harness engineering", 2026-02-17 |

The `## Confidence` sections also cite public evidence without a `Source:` line: `techniques/guide-skill-for-a-tool-set.md:111`, `one-general-rule-per-edit.md:88`, `roll-up-tool.md:130`, `errors-the-agent-can-act-on.md:125`, `attach-the-knowledge-source.md:130`, `skill-into-the-prompt.md:92`, `policy-as-step-by-step-procedures.md:104`, `long-prompt-into-a-skill.md:108`, `consolidate-tools.md:125–127`, `remove-or-scope-tools.md:120–121`, `thinking-level-ladder.md:110`, `model-swap-inside-a-class.md:140`, `guard-tool-calls-at-the-boundary.md:116`, `state-the-output-contract.md:116`, `prune-one-group-at-a-time.md:104–105`; and `improving_agents/index.md:5` ("from public sources and from other ..."). A search of the tree finds no other case study (`case stud` occurs only in `consolidate-tools.md:125`, as a claim about public cases).

Questions:

1. For each of the 19: does the source exist, is it public, are the title, publisher and date right, and do the numbers and claims in the prior's text match the source? Correct or drop a line that does not match.
2. Each is "clearly public" only "with its link", and the tree holds none. Approve them as they are, or add a link to each `Source:` line? (Adding links is a change to the knowledge format that the knowledge checker and `templates/technique.md` would need to allow.)
3. Do the "public guidance" and "public case" claims of the Confidence sections listed above hold?
4. Any prior or claim that may not ship: say which, and whether to drop it or reword it.

### 3. Review C: the owner's read of four files

Read against the rules of skill_and_content: C11 (a port, not a redesign: harness-tuner's method at `b49f159`, no rule loosened, extended or added; only vocabulary changes), C12 (one owner per question: `run_an_experiment.md` owns measure, judge and keep; `train_val_test.md` owns the split and leak rules), C13 (no file selects, compares or keeps on test).

**C1. `skill/SKILL.md`** (124 lines, 12,497 characters; limits 300 and 20,000). Written in batch 4 to section 4.3, changed in batches 9, 10, 13a.

- Line 3 (front matter `description`) and line 8: identity and the "applies while you do Kiln work" rule; no persona.
- Lines 17–29: routing table and the three routing rules.
- Lines 31–43: the API rules (endpoint doc first, non-2xx as data, narrowing, `query_params`, streams, `jq_filter`, reuse, rate limits, the five-call update).
- Lines 45–58: the ask-first rules (destructive operations; code trust and local MCP servers always) and how to reply.
- Lines 60–93: links into the app and the two page tables.
- Lines 95–104: the other entry points (part 7).
- Lines 106–124: what cannot be done over this connection, and the two "not connected" texts. Phase 12 changed the server texts these pair with: Kiln Pro not connected ("Connect it in the Kiln app under Settings > AI Providers > Kiln Pro", `app/desktop/studio_server/utils/copilot_utils.py:129`) and provider not connected (`PROVIDER_NOT_CONNECTED_NEXT_STEP`, `libs/server/kiln_server/custom_errors.py:16`).
- Backlog **B18**: the `description` (line 3) lists "projects, tasks, prompts, run configs, models, evals, synthetic data, fine-tuning, tools and RAG"; `SERVER_INSTRUCTIONS` in `texts.py` and line 8 of this file add "skills". Which list?

**C2. `K/train_val_test.md`** (104 lines). Written in batch 9: harness-tuner's rule, with "metrics only" as harness-tuner defines it at `b49f159`.

- Lines 18–45: the rule table and the three rules. Line 34 counts "whether it is significant" among the val summary numbers.
- Lines 47–65: the `TEST_SPLIT_READERS` table (which call and page reads which split). Line 53: the paired statistics call is "On train" only.
- Lines 67–89: an eval with only a test split; the two choices offered to the user.
- Lines 91–104: the leak rules.
- Backlog **B8**: significance on val needs per-item val scores sent to `post_api_statistics`, which line 53 and the metrics-only rule forbid, while skill_and_content 4.5 and 9.3 (row 8) say the paired statistics call is used on val. The file also omits harness-tuner's zero-number val-to-train channels (the rejection reason, the regressed-issue flag) that step D1 of `playbooks/dealing-with-train-wins-rejected-at-val.md` (lines 22, 63) relies on. Owner decision.
- Backlog **B9**: no endpoint and no page adds a val split to an existing eval; lines 79–89 tell the agent to offer the two choices. Accept the wording; the product gap itself is outside this project.
- Related, not on this file: **B13** (`K/memory.md:107`, the `val` record is read only when confirming on val or reporting; harness-tuner also allows it for human or interactive orientation). Keep or widen.

**C3. `K/run_an_experiment.md`** (251 lines, 13,582 characters). Written in batch 13a from harness-tuner's knowledge skill, planner entry file and the promote, batch-selection, experiment-build and experiment-analysis skills at `b49f159`. Read against C11: it restates the method by hand and must not change it.

- Lines 25–40: "Two paths", the owner's ruling (Kiln Harness Tuner for experimentation at scale, recommended with no CLI steps; the one-off by hand).
- Lines 42–96: words, before you start, the hypothesis, cost.
- Lines 98–163: build, measure on train and judge.
- Lines 165–206: confirm on val: the missing-val rule (172–179), `OPEN: ` constraints (181–186), the keep rule (188–200).
- Lines 208–251: keep or discard, record and report, variants.
- Backlog **B14** (lines 194–198): the cost or speed rule on val is in plain words, with "Kiln Harness Tuner's exact rule applies when running it". Port the exact rule instead (the rule is quoted in B14)?
- Backlog **B19** (line 217): "Never change the task's default run config" against `K/local_private_on_prem.md:94–96` ("Select New Default": offer to make the winner the default). Which holds?
- Backlog **B15**: the file is about 13.6k characters against a target of about 10,000; `skill/references/modes/improve_task.md` is about 11.5k against about 8,000; `K/memory.md` is at 11,997 of a hard 12,000. Accept, or name what to cut.
- B8 applies here too: "clearly better" and "clearly worse" on val (lines 190–193), and "confirm the best one on val" after a paired comparison (Variants, lines 242–245), depend on how significance on val is read.

**C4. `K/diagnose_an_agent.md`** (113 lines). Written in batch 13a: Kiln API steps only, five parts (lines 16, 47, 65, 86, 109). It reads train items only. Read against C11 and C12: it names the calls, and the smells and playbooks own what to look for. No backlog item is open on it.

### 4. Section D: the help-URL check (open from phase 7)

Phase 7 could not request the public help URLs: this environment's proxy refuses `docs.kiln.tech` (`CONNECT tunnel failed, response 403`, checked again for this plan). It needs no judgement, only network access, so a person or an agent on another network can do it. The 37 distinct `docs.kiln.tech` URLs are the 34 `online_url` values of `skill/references/docs/**` plus `https://docs.kiln.tech/`, `https://docs.kiln.tech/developers/kiln-datamodel` and `https://docs.kiln.tech/developers/python-library-quickstart` (from batch 1, in `skill/references/modes/learn_about_kiln.md` and `K/app_help.md`). From the repository root:

```
grep -rhoE "https://docs\.kiln\.tech[^ )\"'>\`]*" app/mcp/kiln_mcp_server/skill --include=*.md \
  | sort -u | while read -r u; do curl -s -o /dev/null -L -w "%{http_code} $u\n" "$u"; done
```

Every URL must answer 200. A failing `online_url` is fixed in the article's front matter (`online_url_for` in `skill_checks/`, then `skill_checks build` for `docs_index.md`); a failing link in a mode or knowledge file is fixed in place.

Done: the owner ran the check; all 37 URLs returned 200. Nothing to fix.

### 5. Section E: human-facing error wording of phase 12 (not a step 9 review)

Step 9 names no wording review, so these texts are not part of this phase. They are listed because a person sees them in the web UI, which shows the API's `detail`: the 404 shape `"<Kind> not found. ID: <id>. Check the ID, or list the <plural> to find the right one."` (`custom_errors.not_found_error`, 61 call sites), `dangling_reference_error`, the batch-job 404 that names `/api/jobs` (`app/desktop/studio_server/data_gen_api.py:586–588`), the provider text "Connect it in the Kiln app under Settings > AI Providers, or choose a model from a connected provider." and the Kiln Pro text above. If the owner wants them read, add it to this phase or to phase 14; otherwise they stand. Backlog B2 and B3 (MCP error texts) are owner decisions too, but on `api_tool/messages.py`, not on the reviewed files.

### 6. Apply the changes that come back

When the answers arrive: make each change in the file the reviewer named, and nothing beyond it; record each answer to a backlog item (B8, B9, B12, B13, B14, B15, B18, B19) so phase 16 can close or dismiss it; fix the architecture's list for review A if the owner agrees (B12). A change to a lever, technique, smell or playbook follows the `knowledge-maintenance` skill. A change to `SKILL.md` keeps the parts of 4.3; a change to the split or keep rule keeps one statement, in its owner file. Regenerate what a change makes stale (`skill_checks build` for an index; `make api_docs` and `make schema` only if a route text changes).

## Tests

No new test: the reviews change content, and the existing checks cover it. After the changes:

- `skill_checks check` and the `app/mcp` tests: `test_the_shipped_tree_passes_every_check`, `test_the_shipped_knowledge_passes_every_check`, `test_no_rule_is_pending`, `test_skill_md_has_the_required_parts`, `test_skill_md_size`, `test_the_split_rule_file_states_the_rule`, `test_the_glue_files_have_their_parts`, `test_no_file_over_body_limit`, `test_each_overlap_file_has_its_see_also_line`, `test_example_paths_exist`.
- `app/desktop/test_skill_api_reference.py` (`test_no_skill_file_names_a_blocked_endpoint`).
- If a prior gains a link, the knowledge checker's format rules and `test_each_template_gives_a_valid_document` must accept it.
- `misspell` over the tree, and `uv run ./checks.sh --agent-mode`.
