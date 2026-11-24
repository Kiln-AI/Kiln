---
status: draft
---

# Architecture: Harness Tuner Switchover

This document fixes the technical decisions for the [functional spec](functional_spec.md). The detail of each part is in a component doc:

- [components/kiln_measurement_apis.md](components/kiln_measurement_apis.md): the significance floor, detectability, the noise check, scores by split, and the paired comparison.
- [components/kiln_smells_skills_version.md](components/kiln_smells_skills_version.md): the smell check, the skill bundle routes, the version route, and the additions to Kiln's skill.
- [components/ht_skill_reading_and_roles.md](components/ht_skill_reading_and_roles.md): how harness-tuner reads Kiln's skill, and what changes in its role skills and prompts.
- [components/ht_api_switch_and_removals.md](components/ht_api_switch_and_removals.md): the harness-tuner code that switches to Kiln's APIs, the removals, the tests and the proof.

**HT** is Kiln Harness Tuner. A component doc may add detail. It may not change a decision made here.

## 1. Shape

Two repositories change, in this order:

1. **Kiln**: new REST routes and skill text. All additive. Nothing here needs HT.
2. **Harness-tuner**: reads Kiln's skill, calls the new routes, and removes its copies. This needs a Kiln build that has step 1.

```
loop agent ──stdio MCP──> HT gateway ──REST──────────> Kiln API   (as today, plus the new routes)
                              │
                              └────MCP client call───> Kiln /mcp  (kiln_skill only)
HT loop code ──REST──> Kiln API        HT loop code ──MCP client call──> Kiln /mcp (kiln_skill only)
```

The one new kind of connection is the call to `kiln_skill`. Everything else is the REST client HT has today.

## 2. Where the code goes

### 2.1 Kiln

| Part | Location |
|---|---|
| `significance_floor` operation | `libs/server/kiln_server/statistics_api.py` (request and route) and `statistics_lib.py` (the arithmetic), beside the four existing operations |
| Detectability read, noise-check estimate | New package `app/desktop/studio_server/eval_power/`: `detectability.py`, `noise_sample.py`, `api.py` (`connect_eval_power_api(app)`) |
| Noise-check job | New worker `app/desktop/studio_server/jobs/workers/noise_check.py`, registered like the eval worker, with its own create path |
| Scores by split, paired comparison | `app/desktop/studio_server/eval_api.py`, beside the routes they extend |
| Smell check | New `app/desktop/studio_server/smell_check.py` (the five checks and their limits) and `smell_check_api.py` |
| Skill bundle routes | `app/desktop/studio_server/skill_api.py` (routes) and new `skill_bundle.py` (the folder rules and the staged write) |
| Version route | New `app/desktop/studio_server/version_api.py`; the constant `MIN_SUPPORTED_HARNESS_TUNER_VERSION` in new `app/desktop/studio_server/compat.py` |
| Skill text | `app/mcp/kiln_mcp_server/skill/` |
| Contract test | `app/mcp/kiln_mcp_server/skill_checks/test_harness_tuner_contract.py`, with its list in `harness_tuner_contract.json` beside it |

Each new `connect_*_api(app)` is called from `desktop_server.make_app()` before `connect_webhost`.

### 2.2 Harness-tuner

Paths are under `src/kiln_harness_tuner/`.

| Part | Location |
|---|---|
| The `kiln_skill` client | New `kiln_skill.py` |
| The new gateway tools | `gateway/ops.py` (`OPS`, `ROLE_OPS`), `gateway/models.py` |
| Calls to the new routes | `kiln.py` (the REST client), and the callers: `detectability.py`, `noise.py`, `smells/run.py`, `gateway/model_info.py`, `onboarding/kiln_check.py`, `contract.py` |
| Role entry files | Inside each role skill, as a reference file (section 5.3) |
| Fakes for tests | `tests/fake_kiln.py` |

## 3. Decisions that cross components

1. **HT reads `kiln_skill` with an MCP client call, not a new REST route.** Kiln is not changed for it. HT already depends on the `mcp` package. One call opens a Streamable HTTP client session to `<kiln host>/mcp`, calls the tool `kiln_skill` with a `path`, and closes. This is the same tool and the same text every MCP client gets.
2. **One reader, one interface.** `kiln_skill.py` holds `SkillReader` with `async read(path: str) -> str`, and raises `KilnSkillError` with a plain message. The gateway and the loop code both use it. Tests replace it with a fake that reads a small folder of fixture files. Nothing else in HT knows about MCP client code.
3. **Caching.** A `SkillReader` caches each file for the life of its process. A gateway process lives for one agent session. Loop code holds one reader per run.
4. **The gateway tool returns plain text.** The `kiln_skill` gateway tool returns the file's text as its content, not wrapped in JSON, so markdown is not escaped. The gateway's size cap on an answer still applies. Kiln's own check keeps every skill file under 30,000 characters, which is under the cap.
5. **The noise job reuses the eval job's machinery and then removes what it made.** It does the check the way HT does today: a temporary copy of the run config for the second drive, and a temporary copy of each judge config for the second judgment. It then deletes those copies, their eval runs and the task runs it drove. It does not add a "store nothing" path to the eval runner. Reasons: the method stays HT's exactly, and the core eval runner is not changed.
6. **Left-overs are found by name.** Every temporary object's name starts with `NOISE-CHECK `. The job deletes its objects in a `finally` step on success, failure and cancel. If the app dies mid-job, objects are left; the next noise job on the task, and app start, sweep any object with that prefix that no live job owns. While a job runs, its temporary run config is visible in the app. This is accepted.
7. **"Train" in the three train-only routes** is one helper, used by all three: the items of the eval's train split, minus any item that is also in a val or test split of any eval of the task. It lives in `eval_power/` and uses Kiln's existing split resolution. The response of each route carries `left_out_held_out`, the count removed.
8. **The arithmetic is not copied.** `significance_floor` calls the functions `statistics_lib.py` already has (the exact McNemar test, the Wilcoxon test, the Wilson and Newcombe intervals). The one exception is deliberate: the bootstrap rule stays HT's closed form, `((n − k) / n)^n < alpha / 2`, and does not call the server's seeded draw. A comment and a test say so, so that nobody "fixes" it.
9. **Rounding.** New routes return unrounded p values, and their `significant` flag reads the unrounded value, as the statistics route does today. HT keeps its own rounding where its own code decides.
10. **Model release dates** for the old-model smell come from the model info module that spec one built. The smell check does not fetch anything itself. If model info has no data yet, the smell check waits for it under that module's own rules, and reports the model as "release date not known" when there is none.
11. **Skill bundle writes go through Kiln's datamodel**, staged in a folder beside the skills and moved into place in one rename, with the skill's model file written last. Ids, `created_by`, provenance checks and git sync are then Kiln's own. `SKILL.md` is written as the bytes given, not rebuilt from the name and description.
12. **The version constant is hand-edited.** `MIN_SUPPORTED_HARNESS_TUNER_VERSION` is in `compat.py`, which the packaging script does not rewrite. The app version comes from the existing `_version.py`.
13. **Policies.** Every new route is allowed for MCP (the default). For the Kiln Assistant's policy: the free reads are allowed; the noise job needs approval, with the same kind of text as the eval job; the skill bundle create follows the existing skill create route.
14. **Generated files.** New routes change the OpenAPI document. The web client schema and the skill's generated API reference are regenerated and committed in the same phase as each route, because CI checks both.
15. **Tool names in HT.** The two skill tools keep their names, `install_skill_bundle` and `export_skill_bundle`, and move from the separate installer server to the gateway. Role skills change only the server prefix they name.
16. **HT's old-version behaviour.** Every Kiln change here is additive, so an HT from before the switch still runs against the new Kiln. `MIN_SUPPORTED_HARNESS_TUNER_VERSION` therefore starts at the lowest HT version that works today. HT's own minimum Kiln version is raised to the first Kiln release that has all of this spec.

## 4. The contract between the two repositories

After the switch, three things tie HT to Kiln. Each has one owner and one check.

| What | Owner | Check |
|---|---|---|
| The new routes: paths, fields, meanings | Kiln (the component docs) | Kiln's tests. HT's `contract.py` start-up check reads the OpenAPI document for each route and field it uses, and stops with the name of what is missing |
| The skill paths, ids, front matter keys and headings HT names | Kiln (`harness_tuner_contract.json`) | Kiln's contract test fails when the skill no longer has an entry of the list. HT's start-up check reads each path through `SkillReader` and stops with the path's name |
| Versions | Each side holds its own minimum | The version route, checked both ways at HT's start (functional spec 5.8) |

`harness_tuner_contract.json` is written once, from what HT names after its links are re-pointed. When HT starts to name something new, the list grows in the same Kiln release that HT's minimum version points at.

## 5. Harness-tuner design points

### 5.1 The gateway tool `kiln_skill`

- Input: `path` (required; a call with no path is refused with "give a path", because the root file is written for a chat agent and the role skill already tells the role which file to read).
- Output: the text. On an error from Kiln (unknown path, Kiln not reachable), the tool returns Kiln's message as a tool error.
- Roles: every role whose skill or entry file names a path in Kiln's skill.
- The gateway skill documents it, as HT's tests require for every gateway tool.

Note: the functional spec passes the whole skill through. Refusing a call with no path does not limit which files can be read; every file has a path.

### 5.2 Loop code that reads the knowledge

One place: the known-smell list for the baseline review. It reads `references/improving_agents/index.md` once, takes the smell ids from its Smells table, then reads each smell file for its title. The result is cached for the run. On `KilnSkillError` it keeps today's fallback and logs `knowledge_unreadable`.

### 5.3 Role entry files

Each entry file moves into the role skill that uses it, as `references/knowledge.md`:

| Entry file today | New home |
|---|---|
| `planner.md` | the batch-selection skill |
| `builder.md` | the experiment-build skill |
| `analyzer.md` | the experiment-analysis skill |
| `smells.md` | the baseline-review skill |
| `report.md` | the report skill |
| `technique-index.md` | Removed. It is only a generated table, and Kiln's index has the same table |

- Hand-written text stays. Each generated table becomes one line that names the section of Kiln's index to read.
- Two tables stay, hand-kept in HT: the five smells that code detects (in the baseline-review file), and the gateway tools each lever uses (in the experiment-build file). One HT test checks the second against `gateway.ops.OPS`, in place of the removed knowledge checker.
- The generator and checker in `knowledge/` are removed. `resolve_link`, which a docs test imports, moves to the test's own helper.

### 5.4 The map from endpoint to gateway tool

A table in the gateway skill, between marker comments. A script in HT's `tests/` builds the expected table from `gateway/ops.py` (each tool's route), and a test fails when the file differs. An endpoint the knowledge names that no tool serves is listed as "not available".

### 5.5 Start-up order in HT

1. Ping Kiln.
2. Version route, both ways.
3. `contract.py`: the routes and fields HT uses, from the OpenAPI document.
4. `contract.py`: each skill path of the contract, through `SkillReader`.
5. The rest of today's start-up.

A failure in 1 to 4 stops the run before any spend, with one message that names the fix.

## 6. Error handling

- **Kiln routes** follow Kiln's existing rules: 404 for an unknown id with the "not found, check the id or list" text; 422 for a bad value with the field named; no 500 for a caller's mistake. A route that reports several problems at once (the skill bundle create) returns them as a list in one 422.
- **The noise job** never fails for one bad eval. It records the failure and goes on. It fails only when it cannot start at all. Provider error text is kept whole.
- **HT** treats a missing route, field or skill path as a start-up error, never a mid-run surprise. A `KilnSkillError` in a gateway tool goes back to the agent as a tool error. In loop code it is logged and the documented fallback is used.

## 7. Testing

- **Kiln:** pytest beside each module, as the repo does today. Where HT pins a value (the floors, the Wilcoxon p values, the interval ends, the noise-adjusted wins), the same value is pinned in Kiln's test, and the test names HT's test it came from. The noise job is tested with fake model adapters: sampling, the comparison, the cap, the clean-up on success, failure and cancel, and the sweep.
- **Kiln's contract test** reads the shipped skill tree and the JSON list.
- **HT:** the suite stays offline. `tests/fake_kiln.py` gains the new routes. `SkillReader` is faked from fixture files. Tests that read HT's knowledge copy are removed with it or rewritten against the fakes (functional spec, section 6).
- **No test in either repo calls the other repo.** The live checks are HT's start-up check and the demo run.

## 8. Build order

The implementation plan turns this into phases.

1. Pre-flight: spec one is merged; every named skill path exists; the costing method is in Kiln's skill.
2. Kiln: `significance_floor`.
3. Kiln: the train helper, detectability, the noise-check estimate.
4. Kiln: the noise-check job.
5. Kiln: the smell check.
6. Kiln: scores by split, the paired comparison.
7. Kiln: the skill bundle routes.
8. Kiln: the version route.
9. Kiln: the skill text, and the contract test.
10. HT: `SkillReader`, the gateway tool, the start-up checks.
11. HT: entry files, re-pointed links, the shared rules, the map.
12. HT: skill bundle tools; the installer is removed.
13. HT: model info; the catalogue is removed.
14. HT: detectability, noise and smells call Kiln; their code is removed.
15. HT: the remaining removals (the knowledge copy last), docs and command line.
16. The audit.
17. The demo run.

Steps 2 to 9 can be built in any order after step 1, except that 4 needs 3. Steps 10 to 15 need a Kiln build with 2 to 9.

## 9. Risks

- **The noise job deletes objects.** Kiln has no delete for a run config or a judge config today. The job deletes only objects it created, found by id, and the sweep deletes only by the reserved name prefix. The component doc lists the exact delete order and what happens when a delete fails.
- **An MCP client call per file.** If the session handshake against a stateless server misbehaves, HT cannot read the skill at all. It is the first thing step 10 proves, against a real Kiln, before any other HT work.
- **The skill moves between Kiln releases.** Guarded by section 4.
- **Two repositories, one change.** HT's switch cannot merge before a Kiln release has steps 2 to 9. The implementation plan puts a release point between the two halves.
