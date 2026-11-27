---
status: draft
---

# Architecture: Harness Tuner in Kiln

This document fixes the technical decisions for the [functional spec](functional_spec.md). It is written from three studies of the code as it is now: Kiln at `c05ba31ba` (main, with the MCP server merged) and harness-tuner at `d6a9534`.

**HT** is Kiln Harness Tuner. **A role** is a role of section 5 of the functional spec. "HT's roles" are the jobs of its agents.

A line marked **Proposed** is a call made while drafting. Section 10 lists the decisions that are the owner's. Section 11 lists the places where the functional spec is wrong and must be corrected.

Component docs will add the detail of each part. They are written after the owner has answered section 10, so that they are written once:

- `components/move_and_packaging.md`: phases 1 and 7.
- `components/kiln_apis.md`: phase 2.
- `components/roles.md`: phase 3.
- `components/ht_on_kiln_mcp.md`: phases 4, 5 and 6.

A component doc may add detail. It may not change a decision made here.

## 1. Shape

```
Today, and through phase 3:
  loop agent ──stdio MCP──> HT gateway ──REST, no role──> Kiln API
  HT loop code ──REST, no role──────────────────────────> Kiln API
  chat client ──MCP /mcp──> call_kiln_api ──REST──> Kiln API        (phase 3 adds: header "role = chat")

After phase 4:
  loop agent ──MCP /mcp/<tuner role>──> call_kiln_api ──REST + role header──> guard ──> handler ──> shared helper
  HT loop code ──REST, no role──────────────────────────────────────────────> Kiln API
```

Three facts shape everything:

1. **The role is enforced in the REST API, in one guard.** The MCP server only names the role. So there is one enforcement, and a REST caller that sends the header gets the same result as an MCP client.
2. **Loop code stays a REST client.** It sends no role. Where Kiln and HT share a calculation, the function is a plain Python function in a library package that both import.
3. **Each phase merges on its own.** Phases 2 and 3 change only Kiln. Phase 1 changes no behaviour. Phase 4 is one change that can be taken back.

## 2. Phase 1: the move

### 2.1 Where the code goes

- **Proposed:** a new workspace member `app/harness_tuner/`, added the way `app/mcp/` was. The owner decides the folder (section 10, D1), because the folders of this repository carry different licence files.
- **HT keeps its own layout inside the folder**: `src/kiln_harness_tuner/`, `tests/`, `docs/`, `examples/`, its `pyproject.toml`. This is the "minimal rewrites" rule. About 20 of its tests read these paths, and they keep working.
- The distribution in the workspace is named `kiln-harness-tuner`. The name `harness-tuner` is kept for the launcher of phase 7, and a workspace cannot hold two packages with one name. HT reads its own version from that distribution; the version is Kiln's.
- HT's contributor rules (Simplified Technical English, nothing measured in `agent_files/`, fences without a language) become an `AGENTS.md` in its folder. Kiln's root `AGENTS.md` applies as well.
- HT's `specs/` folder is not moved. Its open backlog entries move to one file in HT's folder.
- `.gitattributes` pins LF for `agent_files/`, as it does for Kiln's skill: HT compares those files byte for byte at the start of each run.

### 2.2 Python version

Kiln's workspace and CI support Python 3.10. HT's code needs 3.11, at six places in the source and four test files (`StrEnum`, `datetime.UTC`, `asyncio.timeout`, `logging.getLevelNamesMapping`, `tomllib`).

- **Proposed:** HT's code is lowered to 3.10 at those places. It is a small mechanical change, and the workspace keeps one lock file and one floor. See D2.

### 2.3 Kiln's checks on HT's code

| Check | What it finds in HT today | Decision |
|---|---|---|
| ruff lint | 269 findings with Kiln's rules. 165 are "ambiguous unicode character" for `×`, `−` and `–`, which HT prints on purpose | HT's own ruff section is removed, so Kiln's rules apply. The three unicode rules are turned off for HT's folder. The other 104 are fixed in this phase |
| ruff format | Clean, if HT's agent files stay excluded | The exclude moves to Kiln's root config. Seven wrapper templates are copied by agents exactly as they are, so they are not formatted |
| ruff import order | About 120 findings in `tests/` without a first-party setting | A `src` setting for HT's folder |
| ty type check | 143 diagnostics in `src` at 3.11, 49 of them imports of `textual` that go away when the dependency is in the lock | **In steps.** Phase 1: HT's `src` is excluded from ty, by area, and the areas with few findings are fixed and taken out of the exclude. Each later phase that touches an area fixes it. The exclude list is empty at the end of phase 6 |
| Debug detector (`print(`) | 35 hits, which are the command line's output | HT's output goes through one small function in one file, and that file is exempt, as one Kiln file is today |
| pytest | Not run under Kiln's set-up yet. Known differences: Kiln runs tests in parallel; HT's `conftest` module name clashes with Kiln's; HT's tests import `fcntl` and `pty` | HT's suite runs as its own pytest call, from HT's folder, in `checks.sh` and in a CI job of its own. It is skipped on Windows. Whether it runs in parallel is found in this phase |

- The lock gains `textual` and moves `rich` from 13 to 14 for the whole app. That starts the desktop build workflow on the pull request, which is the check that the app still builds.
- **The first thing this phase does** is run HT's suite inside the workspace. Nothing else is planned until that is green.

### 2.4 What does not change

- HT talks to a running Kiln app over REST, as today. It imports nothing new from Kiln in this phase.
- Its five commands exist when it is installed from the repository (`uv run harness-tuner`).
- The PyPI package `harness-tuner` is not touched. It keeps being the old repository's release until phase 7.
- No release of HT is made from the Kiln repository before phase 7. So users change over once.

## 3. Phase 2: Kiln APIs

### 3.1 Where the code goes

| Part | Location |
|---|---|
| Floor arithmetic, and the `significance_floor` operation | `libs/server/kiln_server/statistics_lib.py` and `statistics_api.py`, beside the four existing operations |
| The fix of `mcnemar_exact_p` | `statistics_lib.py` |
| Shared measurement code: rows by item with the replicate fold, comparable scores, room, the detectability rows, the paired comparison of two sets of rows | New `libs/server/kiln_server/eval_measure/` (pure functions over loaded models or plain values; no HTTP, no `HTTPException`) |
| The five smell checks and their limits | New `libs/server/kiln_server/smell_checks.py` (pure functions over the collected inputs) |
| Routes: detectability, smell check, `split` on the four summary routes, `paired_comparison` | `app/desktop/studio_server/`: service code under `services/`, models under `api_models/`, routes in `eval_api.py` and a new `smell_check_api.py` |
| Skill bundle routes | `app/desktop/studio_server/skill_api.py`, with the folder rules in `services/skill_bundle.py` |
| The trace as text | `libs/server/kiln_server/trace_text.py` (the renderer, moved from HT's `gateway/trace_files.py`), and a route beside the run routes |
| Skill text | `app/mcp/kiln_mcp_server/skill/` |

- **Why `libs/server`.** The shared functions must be importable by Kiln's routes, which are in `app/desktop`, and by HT's loop code. `libs/server` is the lowest package that already holds the statistics code. HT gains a dependency on `kiln-server`.
- The functions are pure. HT's loop code keeps fetching rows over REST and calls the same function on them that Kiln's route calls. No HT caller is rewritten to make a new HTTP call.
- Existing lookups (`task_run_config_from_id`, `eval_from_id`) stay in `eval_api.py` and are imported from there, as the job code does today. This follows the local pattern (conventions H24).
- Each new route is added before `connect_kiln_mcp_server` runs, because `call_kiln_api` indexes the routes once at that point. Each has a description whose first sentence is at most 100 characters; a Kiln test requires it.

### 3.2 Decisions on single routes

- **The trace as text** is one task run's trace, whole. HT's files move the system prompt and the tool definitions to a shared file, to save space across many traces; the route puts them at the top of the text. The per-run-config statistics files that HT writes are not part of the route: loop code keeps writing them for the analyst (6.4).
- **Running a train item by id** is the eval job with `judge: false`, `split: "train"` and `item_ids`. It needs a judge config of the V2 kind. The caller names the judge config, so an eval with at least one V2 config works. An eval whose configs are all of the old kind cannot be run this way. **Proposed:** this gap is not closed; the job's error already says to use a V2 config, and the role file says the same. See section 11.
- **Skill bundle create** writes with Kiln's datamodel: build the `Skill`, write `SKILL.md` with `save_skill_md`, write the reference files, and write `skill.kiln` last. On any failure the new folder is removed.
- **The old-model smell** reads the release date from the model info service of the MCP project. That service's connect function returns the service, so the smell check route can use it.

### 3.3 What HT does in this phase

Nothing. HT's copies are removed in phase 4, in the same change that makes its code import the shared functions. Phase 2 can ship alone.

## 4. Phase 3: roles

### 4.1 The definitions

One new package, `libs/server/kiln_server/access/`. It is in `libs/server` because the handlers that need it are in both `libs/server` and `app/desktop`, and `app/mcp` needs the list of names.

```
@dataclass(frozen=True)
class Role:
    name: str
    withheld_item_splits: frozenset[str]     # per-item data of these splits is withheld
    withheld_number_splits: frozenset[str]   # numbers of these splits are withheld
    reserved_memory_tags: frozenset[str]     # records with these tags are hidden and cannot be written

ROLES: dict[str, Role]   # chat, open, tuner_build, tuner_plan, tuner_review, tuner_val
NO_ROLE: Role            # withholds nothing; used when a request names no role
```

| Role | URL | Item data withheld | Numbers withheld | Reserved memory tags |
|---|---|---|---|---|
| `chat` | `/mcp` | val, test | test | — |
| `open` | `/mcp/open` | — | — | — |
| `tuner_build`, `tuner_plan`, `tuner_review` | `/mcp/<name>` | val, test | val, test | `val`, `baseline` |
| `tuner_val` | `/mcp/tuner_val` | val, test | test | — |

- `reserved_memory_tags` is the rule of the functional spec (a record tagged with the name of a withheld split), made a setting, so that it can also cover the `baseline` record. See D5.
- No code outside this package compares a role's name. A test searches the source for it.

### 4.2 The route map

- Each route declares its roles in its `openapi_extra`, beside the agent policy it declares today. New helpers in `kiln_server/utils/agent_checks/` build the value, so a route line stays one line, for example `openapi_extra=roles(ALLOW_AGENT, CHAT, TUNER_READ)`.
- Named groups keep the choice short: `NO_MCP` (in no role), `CHAT` (chat and open), `TUNER_READ` (all four tuner roles), `TUNER_WRITE` (build only), and the single names for the rest.
- Today's block list for MCP (`x-mcp-policy`, 30 routes) becomes `NO_MCP`. The old key and its helpers are removed. The generator of the skill's API reference, which leaves blocked routes out, reads the new declaration: a route that is not in `chat` gets no endpoint doc.
- All 272 operations get a declaration in this phase. Most are `CHAT`. The lists of the four tuner roles are in the component doc; they come from the gateway's lists of today (40 to 14 routes for each role).
- The new key appears in `/openapi.json` only. The web client's schema and the API reference ignore unknown keys, so they do not change.

### 4.3 The guard

- **One async dependency for the whole app**, added where the FastAPI app is made (`libs/server/kiln_server/server.py`). It covers the desktop app and the library server.
- It reads the header `X-Kiln-Role` from `request.headers`. It does not declare a header parameter, because that would add a parameter to every operation of the published API.
- No header: `NO_ROLE`, and the request goes on. An unknown name: 400.
- It reads the matched route's declaration from `request.scope["route"].openapi_extra`. A route that is not in the role: 403, with a message that names the role and the route.
- It puts the `Role` on `request.state`. **It never uses a context variable.** A job that a request starts copies the request's context variables, and would then filter its own reads; `request.state` is not copied.
- A refusal by the guard has Kiln's normal error body (`{"message": …}`).
- The guard does not run for `/mcp`, `/openapi.json` or the web UI's files. They are not API routes.
- An unknown path or a wrong method never reaches the guard. The router answers 404 or 405, as today.

### 4.4 The shared helper

`kiln_server/access/eval_access.py`. A handler gets it with `Depends(eval_access)`, which reads `request.state`. It is the only way a handler learns anything about the caller.

```
class EvalAccess:
    def require_rows(self, split: str) -> None            # raises 403 when item data of the split is withheld
    def require_numbers(self, split: str) -> None         # raises 403 when numbers of the split are withheld
    def require_item(self, task, item_key) -> None        # raises 403 when the item is in a withheld split of any eval of the task
    def require_items(self, task, item_keys) -> None      # the same for a list: fails in full
    def hidden_memory_tags(self) -> frozenset[str]
    def require_writable_tags(self, tags) -> None
```

- For `NO_ROLE` and `open` every method returns at once. So a caller with no role runs the same code and gets today's result.
- **Is an item withheld?** For each eval of the task and each withheld split name, the item is tested with the split's filter. Kiln's filters are tests on one item, so no store is read. The evals of the task are loaded once for each request.
- A task run that an eval made points at its item (`eval_source`). The helper follows it, so a trace of a withheld item is withheld.
- The helper raises a 403 with a message in three parts: what was refused, why, and what to call in its place.
- Loaders that the job workers share with the routes get no check. The check is in the route handler, after the load.

### 4.5 The handlers that call it

| Handler | Call |
|---|---|
| Eval result rows | `require_rows(split)`, from the request |
| Judge trace; one eval input; one run; a run's chain, feedback and repair; a run with a parent run | `require_item`, on the loaded record |
| Edits that return the item (`PATCH` of a run or an eval input) | `require_item`, before the edit |
| Eval-input list; the two run lists | `require_items`, on the loaded list: the request fails in full |
| Dataset download; the judge-trace stream of the eval builder | Refused for a role that withholds any item data |
| The four summary routes; the paired comparison; `run_comparison` | `require_numbers(split)`. No `split` means `test` |
| Memory: list, by ids, summary, create, update | Hidden tags go into the store's query, so pages and counts are right. Writes call `require_writable_tags` |
| Eval job start | No check: a job on a withheld split is allowed (run, then link). The docstring says so |

- Each of these routes carries a mark in its declaration (`eval_data=…`) that names its rule. A test fails for a route that is in a role that withholds data, returns eval data by its mark, and has no call.
- The calibration routes read the golden set, which is not a split. They get no rule. See section 11.
- The prompt generators get no rule, by the owner's decision.

### 4.6 The MCP side

- The MCP server stays one stateless server. The mount gains one route, `/mcp/{role}`, on the same server.
- An unknown role name is refused where the endpoint already answers 405 today, before the MCP library sees the request.
- `ConnectionScope` becomes the role's name: `chat` for `/mcp`, else the path's name.
- `KilnApiCallTool` (in `libs/core`, public code) gains an optional `headers` argument. Nothing else about it changes. The pipeline passes `{"X-Kiln-Role": <name>}`.
- The MCP server's own check of the block list is removed. The guard refuses, and the tool returns the guard's message, as it returns any error body.
- `kiln_skill` does not depend on the role.

### 4.7 Saved files

- `TmpFileStore.save` takes the role's name and writes into `kiln_mcp/<role>/`. The clean-up walks the sub-folders.
- All six folders are made when the server starts. Claude Code's file rules are built from the folders that exist when HT writes them, so a folder made later would not be covered.
- `GET /api/mcp/info` (new, in no role) returns the URL path and the saved-files folder of each role, as the running app resolves them. HT's loop code calls it at the start of a run. This answers the open point of the functional spec: HT does not have to guess the app's temp folder.

### 4.8 Tests and upkeep

- **One pytest walks every route of the real app**, in place of today's CI step that needs a live server: each route has an agent policy, a roles declaration, and a description.
- **For each role, one test walks every route**: a route that is out answers 403; a route that is in does not answer 403 from the guard.
- Each rule of 4.5 has a test on the REST API with the header, for every role from `ROLES`, and one test through the MCP URL.
- `.agents/code_review_guidelines.md` and the kiln-conventions rules for API code gain the check for val and test leaks, and the rule for choosing a new route's roles.
- `app/mcp/README.md` is new: the roles, their URLs, what each withholds, the header, and how to add a route.

## 5. Phase 4: HT on Kiln's MCP server and skill

### 5.1 The order inside the phase

1. **Prove the connection first.** Each of the three agent CLIs connects to an HTTP MCP server at `http://localhost:8757/mcp/<role>` with its shell's network off, calls both tools, and opens a file that `call_kiln_api` saved. None of this has been run. If one CLI cannot do it, the phase stops here and the owner decides.
2. Move what loop code imports out of `gateway/` (below).
3. Port the role files into Kiln's skill.
4. Switch the dispatch to the role URLs, and the prompts to the role files.
5. Make loop code import the shared functions, and remove HT's copies.
6. Remove the rest.

### 5.2 Dispatch

- HT still writes one MCP config file for each of its roles. The file holds one HTTP server, `kiln`, at the URL of the role's Kiln role. The Codex and OpenCode dispatchers translate it, as they translate the stdio entries today.
- The Kiln host comes from `--kiln-host`, as today.
- The tool allow lists name the two tools of the `kiln` server.
- **Saved files.** Each dispatcher adds the role's folder (from `/api/mcp/info`) to what the session may read. Codex and OpenCode deny what is not named, so one more entry is enough. Claude Code's file rules deny by list, so HT adds a deny for Kiln's temp folder as a whole and an allow for the one sub-folder.
- A session of a role that writes nothing has no write access to scratch, as today.

### 5.3 Role files

- Target: `references/client_guidance/harness_tuner/` in Kiln's skill. One entry file names the others; `SKILL.md` names the entry file in its section "Who reads this skill", so every file is reachable, as Kiln's check requires.
- Kiln's checks on these files, as they are now: front matter with `name` and `description`; at most 30,000 characters for each file; root-relative links; no `kiln_skill` and no `skill(name=` outside `SKILL.md`; no text that tells a reader to use the test split. The gateway's tool names are not banned in this folder, but they are replaced anyway: each becomes the endpoint doc of its call.
- Nine files move, about 190,000 characters. The planner's file has 77,000 and becomes at least three.
- The port is checked by a sentence diff against HT's text at the pinned commit, as spec one's ports were. Only the mechanical changes of the functional spec (6.1) are allowed.
- HT's prompts name the role file by path. The sentence that tells an agent how to read a path is in the prompt, which is HT's own text, because Kiln's check keeps the tool's name out of the skill's files.

### 5.4 Loop code

| What | Where | Change |
|---|---|---|
| Check of each run config an agent made | Where the builder's output enters the loop (`items.py`), before the review step | New. It checks the model policy and the tool lock. See D6 for what else |
| Allowed models in the builder's and the probe's input | `schemas.py` | New field, filled from the policy |
| Code trust | Where a builder or probe session is dispatched | Loop code calls the trust route once, with no role. The probe's own code already does this |
| The val table for the report writer | `ReportInput` in `schemas.py` | New field. The promoter's input has it already |
| Memory write feed | After each session | Loop code lists the memory records made since the session began and leaves out its own, which it knows by id. An update of an old record is not seen; see section 11 |
| Statistics files for the analyst | Loop code, with `trace_stats` | Kept. Loop code writes them into the analyst's scratch from the train rows it already reads |
| Shared calculations | `detectability.py`, `analysis.py`, `smells/`, `noise.py` | They import from `kiln_server`. Their own copies go |
| Model information, skill bundles | `kiln.py` and the callers | They call Kiln's routes |

### 5.5 What moves before the gateway can go

Loop code imports from `gateway/` today: `trainset.compute`, the trace parser and statistics, the run tag, the val summary file name, and the tool lists. Each moves to a module outside `gateway/` in step 2 of 5.1, with no change of behaviour. `quarantine.py` and `job_drives.py` are loop code and stay.

### 5.6 Tests

- HT's suite stays offline. `tests/fake_kiln.py` gains the routes that loop code newly calls.
- The tests of the role files move to Kiln, as checks of the skill.
- A test that bound a role file's text to HT's code can now do so directly: both are in one repository. The test reads the skill file from the `kiln_mcp_server` package.
- The gateway's own tests stay until phase 6.

## 6. Phases 5 and 6

- **Phase 5** is a list of searches and reads (functional spec, section 7). Its record is one file in this spec's folder, with each finding and what was done.
- **Phase 6.** The gateway's fence tests are the source of the role tests: for each, a test of the same intent on `/mcp/tuner_*`, or a line in the record that says why there is none. The runs on the demo project are done by a person with a real agent CLI. Then the `gateway/` folder, its 15 test files and its console script are deleted, and the searches of phase 5 are run again.

## 7. Phase 7: the launcher

By this phase HT starts no MCP server of its own. So one thing must run from Kiln's release: the `harness-tuner` command.

Facts that limit the design:

- Kiln's executable reads no arguments today. Started with arguments, it starts a second copy of the app.
- The builds differ: a folder bundle on macOS and Windows, one 350 MB file with a splash screen on Linux.
- HT runs on Apple silicon macOS and on Linux (WSL included). It refuses native Windows and does not support Intel macOS.
- Nothing of HT has been run inside a frozen build.

**Proposed**, to be confirmed by a trial build before the rest of the phase is planned:

- **A sub-command of Kiln's one executable.** `Kiln harness-tuner <options>` runs HT's command line in the app's Python, with the terminal attached. The branch is taken at the top of the entry script, before the app's imports.
- **The launcher** (`harness-tuner` on PyPI, in `app/harness_tuner_launcher/`) finds an installed Kiln at the usual places for the platform. If there is none, or it is too old to hold HT, it downloads the release asset for the platform from Kiln's GitHub release, checks its digest, and installs it the way Kiln's own installer does. Then it runs the sub-command with the options it was given.
- The functional spec's "each platform Kiln supports" becomes "each platform HT supports". See section 11.

The other mechanisms, and why not: a second executable in the bundle needs a new kind of build file and does not fit the one-file Linux build; shipping HT as a Python package beside the app is the simplest to build, but then the code does not ship with the app, which the owner asked for. See D4.

## 8. Build order and release points

| Order | What | Needs |
|---|---|---|
| 1 | Phase 1 | — |
| 2 | Phase 2 | — (can go before or beside phase 1) |
| 3 | Phase 3 | Phase 2, for the routes that give val results as numbers |
| 4 | **A Kiln release** with phases 2 and 3. Chat clients get the new default | |
| 5 | Phase 4, 5, 6 | Phases 1 to 3 |
| 6 | Phase 7, and **the Kiln release that holds HT** | Phase 6 passed, or its fallback is decided |

- If phase 6 fails and the gateway stays, phase 7 must also run the gateway's server from the frozen app. That is one more sub-command of the same kind.

## 9. Risks

- **The agent CLIs and an HTTP MCP server on loopback** (5.1, step 1). Not verified for any of the three.
- **The route map has 272 lines to get right.** A wrong `CHAT` on a route that returns eval data leaks to chat clients. The mark of 4.5 and its test are the guard, and the review of the phase reads every route that returns a run, an eval input or a score.
- **HT's suite under Kiln's set-up** (2.3). Not run yet.
- **Phase 7 inside a frozen build.** Not run yet.
- **The size of the port of the role files.** 190,000 characters, checked by a sentence diff.
- **A context variable added later** by someone who does not know the job trap (4.3). A test starts a job from a request with a role and checks that the job reads a withheld split.

## 10. Decisions for the owner

- **D1. The folder for HT's code.** `app/harness_tuner/` (proposed: it is an application, and the app bundles it as it bundles `app/mcp/`) or `libs/harness_tuner/`. The two folders carry different licence files today, and HT has its own. Which licence applies to HT's code in this repository is the owner's decision, and no file about it is changed without the owner.
- **D2. Python 3.10.** Lower HT to 3.10 at about ten places (proposed), or raise the floor of the whole workspace to 3.11, which drops 3.10 for the published `kiln-ai` and `kiln-server`.
- **D3. The type check in steps** (2.3): HT's code is excluded at first and brought in by area, with the exclude list empty at the end of phase 6.
- **D4. How Kiln's release runs HT** (section 7): a sub-command of the one executable (proposed), a second executable, or a Python package beside the app.
- **D5. The `baseline` memory record.** The gateway refuses an agent's write of the `baseline` tag today. The functional spec protects only `val`. Proposed: the three train-side tuner roles cannot write `baseline` or `val`, by the role's setting (4.1).
- **D6. Rules of the gateway that the functional spec does not list** (found in this study). For each, the proposal is a check in loop code's new step (5.4), not a rule in Kiln:
  - A new run config, or a code tool's allow list, must not add Kiln's memory tool or Kiln's own API tool, at any depth. The gateway refuses it today, and loop code has no copy of the check. Such a tool gives the tuned agent a way to read anything.
  - When an agent makes a run config from a parent, the gateway carries the parent's properties that the agent did not name, and sets or refuses the output mode. After, the agent builds the whole body. The role file says how; loop code checks the result against the parent.
  - The option `--lock-tool`. Loop code already checks it for run configs.
- **D7. Judged eval jobs.** The build role has the eval job route, for the run of one train item. With it, a builder or a probe can start a judged eval job on any split, which no HT role that stays can do today. Proposed: accept; the role file says not to.

## 11. Corrections to the functional spec

To be made when this document is approved:

1. **5.3 and 5.7:** the calibration route reads the golden set, not the test split. It is not a "numbers of a withheld split" route.
2. **5.2:** "the ones blocked for MCP today" is 30 routes.
3. **5.2:** "no route that edits" is too wide. The build role has three writes that change an existing record: rename a run config, archive a skill, archive a code tool.
4. **5.3:** the eval-input list has no filter by split. Its filter is by tag. The rule is: the request fails in full when the answer holds a withheld item.
5. **5.6:** "a way to learn the folder of a role" is `GET /api/mcp/info`, and the folders are made at start.
6. **6.1:** the entry files hold no hand-kept table. Both tables that the spec names are generated, and both go.
7. **6.3:** "Run a train eval" is not something an HT role that stays does today; only the removed eval-building role did. The row goes. See D7.
8. **6.4, item 6:** the memory feed reports new records only, not updates.
9. **4.8:** an eval whose judge configs are all of the old kind cannot run one item by id. Accepted, not closed.
10. **Section 9:** "each platform Kiln supports" becomes "each platform HT supports".
11. **6.4:** the rules of D5 and D6 are added to the list, with the owner's decisions.
