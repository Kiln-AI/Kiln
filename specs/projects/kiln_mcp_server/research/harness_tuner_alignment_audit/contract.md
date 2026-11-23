---
status: complete
---

# Harness Tuner alignment audit: the contract between HT and the Kiln skill and API (HT b49f159 vs Kiln 25157f3)

This is the contract audit of Kiln Harness Tuner (HT, b49f159) against Kiln at 25157f3. I read 25157f3 from a throwaway worktree, which I have removed. My working files are in `/tmp/claude-0/-home-user-Kiln/2d94edc9-cf88-595e-ad22-306868b3911d/scratchpad/audit/contract/`: `ht_calls.tsv` holds every REST call in HT's code, found with an AST scan, and `kiln_paths.txt` lists Kiln's routes at 25157f3.

**Bottom line**
- **API:** all of HT's REST calls still work. None is MCP-blocked, and none of the phase 12 changes breaks a check HT makes.
- **Skill:** the break is in the skill contract. HT's role prompts name files, a skill and a layout that are not in Kiln's skill. The ported knowledge was also reworded to send the agent to REST endpoints, where HT's loop agents have only gateway operations.
- **Memory:** a few format differences already hurt when HT and a Kiln agent work on the same task.
- **Fencing spec:** none of the items in `specs/projects/kiln_mcp_fencing/project_overview.md` exists at 25157f3, though its front matter says `status: complete`. That means no fence, no `/version`, no `min_supported_harness_tuner_version` and no "create skill from a folder" route.

HT paths below are under `src/kiln_harness_tuner/`. Kiln paths are under `app/mcp/kiln_mcp_server/skill/` unless they are given in full.

---

## 1. Ranked breaking items

| # | Severity | What HT relies on | Where in HT | Kiln at 25157f3 | Why it breaks |
|---|---|---|---|---|---|
| 1 | breaks on re-point | The five role entry files and the technique index of `kiln-harness-tuner-knowledge`: `references/planner.md`, `builder.md`, `analyzer.md`, `smells.md`, `report.md`, `technique-index.md` | `agents/batch_plan.md:8`, `analyze_experiment_results.md:5`, `baseline_review.md:5`, `create_experiment_rc.md:7-8`, `report_writer.md:6`; role skills `kiln-harness-tuner-baseline-review/SKILL.md:46,50`, `-batch-selection/SKILL.md:463,471,627,1163`, `-experiment-analysis/SKILL.md:337`, `-experiment-build/SKILL.md:323` | Not ported (`specs/projects/kiln_mcp_server/components/skill_and_content.md:590`). Only two indexes exist: `references/improving_agents/index.md` and `references/levers/index.md`. | Each role prompt's first instruction points at a file that does not exist. The hand-written role procedures are gone. Only planner step 3's outcomes survive, in `references/knowledge/run_an_experiment.md` ("Measure on train, and judge"). Lost: planner "How to use the knowledge" steps 4–5 (technique = lever id, "not in the knowledge"), the smells.md review procedure and its "Detected by" column, analyzer "How to name a failure pattern", builder "How to use the knowledge", and what report.md selects. |
| 2 | breaks on re-point | HT code loads the knowledge tree from disk (smell ids and titles) | `knowledge/load.py:27,123,145-155`; `knowledge/schema.py:28,44-45,83-91,175-194`; `smells/run.py:440-452` → `known_smells` (`smells/run.py:144`) | `skill_checks/knowledge_schema.py:18-23`: techniques, playbooks and smells live under `references/improving_agents/`. `gateway_ops` became `api_docs`. Smells lost `detected_by` and `detectors`. The lever heading "How the tuner changes it" became "How to change it". Links are root-relative, not file-relative. | Pointed at Kiln's tree, `_kind()` returns None for every technique, playbook and smell, so `known_smells` is empty. The baseline reviewer is then told to use `references/smells.md`, which does not exist. `LeverMeta` (extra=forbid) rejects `api_docs`, `SmellMeta` requires `detected_by`, and `resolve_link` resolves no link. The `smell-detectors` check rule cannot pass. If HT deletes its copy, `load()` raises and `_smell_titles` returns None: degraded, not a crash. |
| 3 | breaks on re-point | Loop sessions reach Kiln only through gateway operations: "no generic Kiln API tool… a refusal is final" | `agents/describe_eval.md:23-31`, `agents/eval_build.md:19-27`, `gateway/ops.py:1-19` | `SKILL.md:8` ("you reach it through the `call_kiln_api` tool"). The lever front matter `api_docs` and the steps in 13 lever and knowledge files are endpoint docs. Also `references/knowledge/memory.md:20-36` and `references/knowledge/code_tool_authoring.md` ("The calls"). | A re-pointed loop agent gets two sets of instructions that contradict each other: call REST endpoints, and use only gateway operations. The gateway operation names are banned from the knowledge trees (`skill_and_content.md:626`). |
| 4 | breaks on re-point | A fenced way to hand loop agents the skill | `install_agents.py` (copies skills per agent CLI); `gateway/` | `server.py:142-143` registers `kiln_skill` and `call_kiln_api` on every connection. `api_tool/policy.py:43-51` always returns `OPEN_SCOPE`. No fence, no `/api/version`, no `min_supported_harness_tuner_version`. | HT cannot give loop sessions the Kiln MCP to read the skill without also giving them an unfenced `call_kiln_api`. That breaks HT's train-only guarantee. Until spec two is built, HT must keep its gateway and copy Kiln's skill files into its agents folder. |
| 5 | breaks on re-point | The knowledge names the loop's inputs and words | `agents/batch_plan.md:111-118` (`train_detectability`, `train_noise`), `:101-109` (`measurement_prices`), `:13` (`lever_attempts`), `:27-39` (`eval_only`), `:24` (`open_questions`) | Banned in the knowledge trees (`skill_and_content.md:611,626`). Replaced with "Kiln Harness Tuner measures it… the rule applies when running it", for example `dealing-with-a-noisy-eval.md:28-36`, `dealing-with-a-saturated-eval.md:17,24`, `spending-the-budget.md:27,86`, `cheaper-or-faster.md:20`. | The documents no longer tie a rule to the input that feeds it. The val-rejection playbook (`dealing-with-train-wins-rejected-at-val.md:29-30`) says HT "gives the reason in the same words", but it no longer quotes HT's lines, and HT writes `- rejected at the val gate <date> vs baseline <rc> — no gain at val: …` (`memory_schema.py:853,1003-1013`). HT's copy quoted those strings (`:21-28`). |
| 6 | breaks today (HT and a Kiln agent on one task) | The startup janitor marks every `— RUNNING` experiment in the task scope as abandoned | `memory.py:1183-1199` | `references/knowledge/run_an_experiment.md:75` and `memory.md:131` tell Kiln agents to open experiments ending `— RUNNING`. | When HT starts, a live Kiln-agent experiment in another session is overwritten to `— ABANDONED (orchestrator restart MM-DD)`. |
| 7 | breaks today (minor) | `OPEN: ` dedupe by a `question:` content line | `memory.py:1822-1866`; `memory_schema.py:1368-1410` | `memory.md:123-128` gives no content keys: "the question, the default you assumed, its source (the user, or an assumption)". | HT cannot match a Kiln-agent `OPEN: ` record, so it posts a duplicate of the same question. The source vocabulary also differs: HT uses `human`/`assumption`, Kiln says "the user, or an assumption". |
| 8 | risk | Verdict shape: the label is kept and `(technique)` is dropped; an opening shape with no suffix reads `UNKNOWN` | `memory_schema.py:835,880-893,896-900` | `memory.md:66-68`: `EXP 0715-1 (prompt): no-refetch rule — accuracy: +12pp…` keeps `(prompt)`; `:132-133` says only "replaces the suffix". | HT's code reads a Kiln-format verdict as UNKNOWN (lost state), never as a verdict. Today HT acts only on its own records, so the harm is latent. |
| 9 | risk | Stamp dates in `MM-DD` | `memory_schema.py:814-815,822` (`\s+— PROMOTED \d{2}-\d{2}$`…) | `memory.md:136-137` gives `<date>` with no format. `run_an_experiment.md:231` gives bare `— PROMOTED` / `— REJECTED AT VAL`. | A Kiln-written `— PROMOTED 2026-11-23` or a bare `— PROMOTED` fails HT's `is_promoted` and `is_rejected_at_val`. |
| 10 | risk | Strings HT writes that `memory.md` does not document | `memory_schema.py:169,173,240-250,462,751-761,822,853-860,1169-1205`; `memory.py:893,945` | Missing: `— REFUTED`; `— DEAD END (<why>)`; the `(…)` details of `— NOT LANDED` and `— CAPPED`; the form `— HELD (constraint <id>) MM-DD`; `SCREEN CAPPED: `; `PROBE <item>: <q> → YES/NO/UNCLEAR` with the `probe` tag; the issue lead `issue: `; the tags `smell`, `smell_<id>`, `baseline_audit`, `baseline_judge_copy`, `audited_rc_<id>`; every `key: value` line HT reads back. | A Kiln agent cannot read these states. Nothing tells it not to edit the content lines HT parses. `memory.md:140-145` lists only the bare suffixes. |
| 11 | risk | Smell and audit issues are deliberately bound to no eval | `memory_schema.py:240-251`; `smells/run.py` | `memory.md:157-159`: "An issue ends up bound… When none does, the eval is missing: tell the user". | A Kiln agent may try to bind HT's smell and audit issues, or tell the user an eval is missing. |
| 12 | risk | Priority tags are owned by the source (re-sync replaces them) | HT memory skill table row `issue`; `setup.py` re-sync | `memory.md:109-112`: "change one by an update". | HT's re-sync reverts a priority change a Kiln agent made. |
| 13 | risk | Train-side roles never read the `baseline` record | `agents/batch_plan.md:21-22`, `create_experiment_rc.md:27`, `probe.md:19-20`, `baseline_review.md:19-20` | `memory.md:52`: orientation reads it (`tags=baseline`). | `memory.md` tells the agent to do what the role prompt forbids. |
| 14 | risk | "Never ask a human"; a failed memory write is disclosed in the return | `agents/batch_plan.md:23-25`; HT memory skill, write discipline | `SKILL.md:45-47`; `memory.md:33` (ask the user before a delete), `:86-87` ("tell the user the finding once"), `:121`, `:158`. | User-dialogue rules that loop agents cannot follow. |
| 15 | risk | Delimiter matched as a whole line | `memory_schema.py:473,488-491` | Same characters (em dashes U+2014), but the code span is wrapped across two source lines (`memory.md:161-162`: "lines⏎  below"). | An agent that copies the raw markdown gets a newline in the delimiter. Low risk, because Kiln tells agents never to write above it. Put it on one line. |
| 16 | risk (cosmetic) | Val line with bare rc ids | `memory_schema.py:1467-1484`; `memory.py:1350` | `memory.md:107`: `rc_<new> (07-16, EXP 0716-2) ← rc_<old> — …` | The `rc_` prefix differs. HT does not parse val content. |
| 17 | risk (no break) | Provider-not-connected answer, 500 → 400 `{"message": "…\nConnect it in the Kiln app…"}` | `kiln.py:175-187` (retries 5xx only); `model_preflight.py:310-357`; `kiln.py:41-58` reads only `error_messages`/`detail` | `libs/server/kiln_server/custom_errors.py:148-155`; `libs/core/kiln_ai/adapters/provider_tools.py:72,91`. It is raised by `adapter_for_task` in `POST …/run`. | No more pointless 5xx retries. The preflight still classifies the failure as "unclear" and marks the model "untested", as before. The reason text becomes a repr of the body because HT ignores the `message` key, which HTTPException bodies have always used. |
| 18 | risk (no break) | `POST /api/jobs/wait` with `{ids, timeout}` | `analysis.py:1566`, `job_drives.py:363`, `gateway/ops.py:1397`; default 3600 at `analysis.py:98` | `app/desktop/studio_server/jobs/api.py:83-104`: `extra="forbid"` (new in phase 12, commit 0855bcd); `timeout ≤ 3600` (`jobs/models.py:32-33`). | HT sends no extra fields. A timeout above 3600 would get a 422, but that cap is older than phase 12. |
| 19 | risk (no break) | 404 status, and the 400 text containing "V2 judge" | `setup.py:342-346,790`; `gateway/ops.py:937`; `onboarding/openenv_check.py:225`; `job_drives.py:346` | 404 texts are now "`<Kind> not found. ID: <id>. Check the ID, or list…`" (`not_found_error`); the status is unchanged. `libs/core/kiln_ai/adapters/eval/eval_runner.py:484` still says "…is not a V2 judge with an adapter…" with a 400. | Still matches. |
| 20 | risk | Feature detection through `GET /openapi.json` (`EvalJobParams.judge`, `CreateTaskRunConfigRequest.provenance`) | `onboarding/kiln_check.py:44-50,166`; `job_drives.py:236-262` | Both fields are present. The MCP route index accepts only `/ping` and `/api/*`. | Fine over REST. It would fail if HT ever moved its code's calls onto Kiln's MCP. |
| 21 | risk | HT's own `kiln-api` reference (290 docs) | `agent_files/skills/kiln-api/` | 49 HT docs are for routes that are gone, MCP-blocked or changed. Examples: `put_…_data_gen_guide.md` (now POST), `prompt_optimization_*`, `git_sync_*`. Kiln adds model_info, eval_inputs and openenv docs. | Stale, but harmless: HT's `kiln_api_mcp/tool.py:171` refuses PUT anyway. Re-pointing to `references/knowledge/api_docs/` fixes it. |
| 22 | breaks on re-point | Skill bundles with reference files | `skill_installer/` | `POST /api/projects/{project_id}/skills` takes only `name`, `description`, `body`, `provenance` (`app/desktop/studio_server/skill_api.py:25-39,158-183`). `GET …/skills/{id}/content` returns only `skill_md` and `body`. | Section 5. |

---

## 2. Contract list: skill paths and names HT references

**Skills loaded by name**

| HT name | Status | Location in Kiln (skill `kiln`) |
|---|---|---|
| `kiln-harness-tuner-knowledge` | missing as a skill | Its content is in `references/improving_agents/` and `references/levers/` |
| `memory` | moved | `references/knowledge/memory.md` (front matter `name: memory`) |
| `kiln-api` | moved | `references/knowledge/api_docs/`, with `api_index.md` in place of the SKILL.md routing index |
| `kiln-harness-tuner-code-tool-authoring` | moved | `references/knowledge/code_tool_authoring.md` plus `references/knowledge/code_tool_wrappers/*.md`. The 8 `references/wrappers/*.py` became `.md`; `wrappers/README.md` is gone. |
| `-gateway`, `-batch-selection`, `-experiment-build` (and its `references/merging.md`, `references/skill-authoring.md`), `-experiment-analysis`, `-baseline-review`, `-probe`, `-promote`, `-report`, `kiln-task-setup`, `experiment-costing` | missing | Not ported; HT keeps them |

**Entry files**

| HT file | Status | Nearest file in Kiln |
|---|---|---|
| `references/planner.md` | missing | `references/improving_agents/index.md`, sections Smells / Goals / Order of work / Failure patterns / Eval problems / Design |
| `references/builder.md` | missing | `index.md` Techniques and `references/levers/index.md` |
| `references/analyzer.md` | missing | `index.md` Failure patterns and Eval problems |
| `references/smells.md` | missing | `index.md` Smells, without the "Detected by" column |
| `references/report.md` | missing | none |
| `references/technique-index.md` | missing | `index.md` Techniques and Dormant techniques |

- **Knowledge SKILL.md "How to read these documents":** moved to the same heading in `references/improving_agents/index.md`.

**Folders**

| HT folder | Status | Kiln folder |
|---|---|---|
| `references/levers/` | OK | same |
| `references/techniques/` (with the `guide-skill-for-a-tool-set/` sub-files) | moved | `references/improving_agents/techniques/` |
| `references/playbooks/` | moved | `references/improving_agents/playbooks/` |
| `references/smells/` | moved | `references/improving_agents/smells/` |

- **Cited paths:** `references/playbooks/dealing-with-train-wins-rejected-at-val.md` (batch-selection:1069) and `references/playbooks/dealing-with-a-noisy-eval.md` (planner.md) both moved under `references/improving_agents/playbooks/`.
- **Memory skill links:** `../kiln-api/references/api_docs/{post,get,get…summary,get…by_ids,patch,delete}_…memories….md` moved to `references/knowledge/api_docs/` with the same file names.
- **Link convention:** HT links are file-relative; Kiln links are relative to the skill root (`SKILL.md:12`).

**Ids** (diffed file by file: identical)
- **Levers (OK):** model, new_tool, output_mode, params, prompt, skill, tool_config. The `technique` field still maps to these.
- **Techniques (OK):** 27, plus 3 sub-files.
- **Playbooks (OK):** 23.
- **Smells (OK):** 15, including the five detector smells very-long-prompt, very-long-skill-description, very-long-tool-description, too-many-tools and old-model.
- **Front-matter titles:** identical.
- **Descriptions:** reworded in places. For example, the 5 detector smells now say "measure it yourself" with the number.

**Front-matter keys**

| Key | Status |
|---|---|
| `title`, `description`, `reviewed` | OK |
| technique `status`, `levers`, `applies_to`, `cost` | OK |
| playbook `kind`, `applies_to` | OK |
| lever `gateway_ops` | renamed to `api_docs` (doc paths, not operation names) |
| smell `detected_by`, `detectors` | missing |

**Section headings**

| Heading | Status |
|---|---|
| The 9 technique headings | OK |
| The 4 playbook headings | OK |
| The 5 smell headings, including "How to confirm it", "What it blocks" and "Remedies", which the role skills cite | OK |
| Lever "How the tuner changes it" | renamed to "How to change it" |
| Lever "What it is", "Limits", "See also" | OK |

**Tags and ids in role text**
- **Lever ids** (`prompt`, `skill`, `tool_config`, `new_tool`, `params`, `output_mode`, `model`): OK.
- **Smell ids** in the `smell_<id>` tag: OK.

---

## 3. Memory formats, string by string (HT code vs `references/knowledge/memory.md`)

**Same string**
- **Scopes:** `project`, `task::<task_id>` (memory.md:38-43).
- **Kind tags:** `issue`, `hypothesis`, `experiment`, `dead_end`, `constraint`, `lesson`, `baseline`, `val` (:98-107). HT's `RecordKind` has no `hypothesis`; harmless.
- **Priorities:** `p0`–`p3` (:109-112).
- **Faceted tags:** `eval_<eval_id>` (:151; HT accepts numeric ids of 6 or more digits) and `rc_<run_config_id>` (:106).
- **Issue prefixes:** `UNMEASURED: `, `UNMEASURABLE: `, `FIXED: `, `WONT_FIX: ` (:115-121, matching `memory_schema.py:411-417`).
- **Open questions:** `OPEN: ` (:123, matching `memory_schema.py:1342`).
- **Experiment suffixes:**
  - ` — RUNNING` (:131) matches `memory_schema.py:752`.
  - `— FAILED (infra: <error class>)` (:134) matches ` — FAILED (infra: {detail})`.
  - `— ABANDONED (<why>)` (:135) matches.
  - `— PROMOTED <date>` and `— REJECTED AT VAL <date>`: same words, but see the date format below.
- **Opening shape:** `EXP <id> (<technique>): <hypothesis>` (:131).
- **Screening prefixes:** `SCREEN SURVIVOR: ` and `SCREEN DEAD END: ` (:144).
- **Caps:** overview 280, content 4000, a 422 above them (:28,61-63).

**Differs or is missing in memory.md**
- **Delimiter:** HT `— setup wrote everything above; lines below belong to the loop —` (memory_schema.py:473). Kiln has the same characters and spacing, but the code span is split over two source lines (:161-162).
- **Verdict overview:** Kiln keeps `(technique)` (:66-68). HT drops it, and its code reads the kept form as UNKNOWN.
- **Stamp dates:** Kiln `<date>` (:136-137), or no date at all (run_an_experiment.md:231). HT requires `MM-DD`.
- **`— HELD`:** Kiln gives only `— HELD` (:143). HT writes `— HELD (constraint <id>) MM-DD`.
- **`— NOT LANDED`, `— CAPPED`:** Kiln gives them bare (:140-142). HT always writes ` (<detail>)` after them.
- **Missing entirely:** `— REFUTED`, `— DEAD END (<why>)`, `SCREEN CAPPED: `, `PROBE <item>: <q> → YES|NO|UNCLEAR`, and the tags `probe`, `screen`, `smell`, `smell_<id>`, `baseline_audit`, `baseline_judge_copy`, `audited_rc_<id>`.
- **Issue overview lead `issue: `** (memory_schema.py:462): not in memory.md. HT does not require it when it reads.
- **Content lines:**
  - Kiln `- eval: <eval_id>` (:152). HT writes `- eval: <id> (built <date>, reproduced)` or `(linked by kiln-harness-tuner setup <date>)`, and a head line `eval: <id> (<name>, <kind>)`.
  - Kiln `fixed 07-15 by rc_207, EXP 0715-1` vs HT `- fixed <date> by <citation>`; the reopen line differs too. HT does not parse the tail, so this is harmless.
- **`key: value` lines HT reads back:** none are in memory.md.
  - Setup head: `eval:`, `priority: p<n> (source: …)`, `status: <state> at sync · fp: <hex> · synced <date>`.
  - Open questions: `question:`, `default:`, `gates:`, `source:`, `re-ask when:`.
  - Experiments: `hypothesis`, `predicted effect`, `parent rc`, `eval`, `issue`, `technique`, `head_to_head_group`, `reused rc`, `wildcard`, `merge of`, `conflict flags`, `rc`, `change`, `generality`, `judge copy`, `reference check`.
  - Line prefixes: `- ingredient: `, `- rejected at the val gate `, `- held at the val gate `, `- blocked at the val gate `.
  - Screen records: 17 keys, including `result` (one JSON line).
- **Val line:** Kiln `rc_<new> (07-16, EXP 0716-2) ← rc_<old> — …`. HT writes bare ids.
- **Val overview:** HT re-asserts a fixed numberless sentence (memory_schema.py:1423). Kiln says only that the overview has no number; compatible.
- **Baseline record:** compatible. Both use tags `baseline` and `rc_<id>` with one rc id per line, newest first. HT fails hard on zero or two `rc_` tags (memory.py:737-755), and takes the first row if two `baseline` records exist (memory.py:789-801).

---

## 4. Tools HT has that Kiln does not

| HT module | What it measures | Kiln equivalent | Wording for the skill |
|---|---|---|---|
| `noise.py` | Run-to-run noise: re-drive and re-judge on N train items via a clone, giving the flip rate | None. The building blocks exist (`POST run_configs`, `create_eval_config`, eval jobs with `item_ids`) | "Kiln Harness Tuner has a … tool" |
| `detectability.py` | Per (eval, score): `room` (items not at the best value) and `floor` (fewest wins for p<α: McNemar 2·0.5^k, Wilcoxon) | None. `/api/statistics` (`proportion_ci`, `compare_proportions`, `mcnemar_paired`, `compare_paired`) tests a given pair but does not compute room or floor | HT |
| Model age (`smells/detectors/old_model.py` and the model catalogue) | Model age against an 8-month reference | `GET /api/model_info/models` and `…/model_details` give `release_date`, `release_date_estimated` and `agent_notes`. The age is easy to compute; the 8-month reference is HT's default | Point to the Kiln endpoint, as the old-model smell does now |
| Screening and measurement engine (`viability.py`, `measure.py`, `stop_rules.py`, `estimate.py`) | Successive-halving screens, stratified estimates, early stops | None | HT |
| `latency.py`, `objective.py` | Paired per-request latency and cost | Partial: task runs carry `usage`, and judge-free eval jobs return `driven_runs`. No paired comparison; `compare_paired` could be fed the arrays | HT for the rule |
| `budget.py` | Spending caps and measurement prices | None | HT |
| `probes.py` | Code probes counting tool calls, skill reads, JSON validity | None (`POST …/run` plus traces by hand) | HT |
| `model_preflight.py` | One test call per allowed model | Partial: model_info `status` is `ready`/`not_connected`; `POST …/run` works for a test call | Endpoint for status; HT for the preflight |
| `levers.py` | Whether the declared lever reached the call | None | HT |
| `generality.py`, `judge_copy.py`, `integrity.py`, `reference_check.py` | Leak, judge-copy, reward-hacking and dangling-reference checks | None; `train_val_test.md` tells the agent to check by hand | HT |
| `quarantine.py`, gateway `trainset` | Train-only fence | None (spec two not built) | HT |
| 5 smell detectors | Size and count checks | None; the smells say "measure it yourself" with the threshold | Already worded that way |

---

## 5. Skill bundles

**What Kiln has today**
- **Create:** `POST /api/projects/{project_id}/skills` takes `name`, `description`, `body` (at least 1 character) and `provenance`. It writes `skill.kiln` and SKILL.md only.
- **Read:** `GET …/skills/{id}/content` returns only `skill_md` and `body`.
- **Consequence:** a new version made over the API loses its reference files, as `improving_agents/techniques/guide-skill-for-a-tool-set.md:51-54` already says.

**What HT does today** (`skill_installer/bundle.py`, `skill_installer/mcp_server.py`, `prompt_text.py`): it writes directly to disk. The "create skill from a folder" API would have to do the following.

**Input**
- **SKILL.md:** front matter with exactly `name` and `description`, no other keys, and a non-empty body.
  - **Name rules:** `^[a-z0-9-]+$`, at most 64 characters, starts with a lowercase letter, no `--`, no leading or trailing `-`, not `skill`.
  - **Description:** 1 to 1024 characters.
- **`references/**`:** nested folders allowed, UTF-8 text only.
- **`assets/**`:** any bytes.
- **Nothing else at the root.** No symlinks, no `skill.kiln` from the caller.
- **Size:** at most 512 KB per file and 2 MB per bundle.
- **Provenance:** non-empty `notes`, `derived_from_ids` (a list of strings), `origin: "agent"`.

**Semantics**
- **Install-once:** a name that already exists, in a `skill.kiln` or a folder suffix, is refused. A new version means a new name.
- **Atomic:** staged, then one rename. A skill either does not exist or exists whole.
- **Ids and files:** the id is minted with Kiln's scheme. SKILL.md is stored byte-identical. `references/` and `assets/` are always created, even when empty.
- **Errors:** every error at once (`{"ok": false, "errors": [...]}`), and nothing is written on a refusal.
- **Success returns:** `skill_id`, `skill_name` and `tool_id` = `kiln_tool::skill::<id>`.

**Transport**
- **Upload the tree:** HT agents write the bundle in a scratch folder that the Kiln server may not be able to read. The API should take the tree itself, either multipart or a JSON map of path to content with binary assets base64-encoded, not a local path.

**Also needed: a read lane**
- **Export a skill:** HT's `export_skill_bundle` returns SKILL.md, `references/**` and `assets/**`, but not `skill.kiln`, up to 4 MB.
- **Read every file of a skill:** `prompt_text.py` reads every reference file and every text asset of attached skills, and code-tool files, for the generality and integrity checks.
- **Effect:** with both, HT can stop reading the project tree from disk.
