---
status: draft
---

# Architecture: Harness Tuner in Kiln

This document fixes the technical decisions for the [functional spec](functional_spec.md). It is written from three studies of the code: Kiln at `c05ba31ba` (the MCP server merged) and harness-tuner at `d6a9534`. Main has moved since: it dropped Python 3.10. The work starts from current main.

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

- A new workspace member in the folder `app/harness-tuner/`, added the way `app/mcp/` was. (Decided by the owner.)
- **HT keeps its own layout inside the folder**: `src/kiln_harness_tuner/`, `tests/`, `docs/`, `examples/`, its `pyproject.toml`. This is the "minimal rewrites" rule. About 20 of its tests read these paths, and they keep working.
- The distribution in the workspace is named `kiln-harness-tuner`. The name `harness-tuner` is kept for the launcher of phase 7, and a workspace cannot hold two packages with one name. HT reads its own version from that distribution; the version is Kiln's.
- HT's contributor rules (Simplified Technical English, nothing measured in `agent_files/`, fences without a language) become an `AGENTS.md` in its folder. Kiln's root `AGENTS.md` applies as well.
- HT's `specs/` folder is not moved. Its open backlog entries move to one file in HT's folder.
- `.gitattributes` pins LF for `agent_files/`, as it does for Kiln's skill: HT compares those files byte for byte at the start of each run.

### 2.2 Python version

HT's code needs Python 3.11. Main requires 3.11 since it dropped 3.10, so nothing changes in HT for this.

### 2.3 Kiln's checks on HT's code

| Check | What it finds in HT today | Decision |
|---|---|---|
| ruff lint | 269 findings with Kiln's rules. 165 are "ambiguous unicode character" for `×`, `−` and `–`, which HT prints on purpose | HT's own ruff section is removed, so Kiln's rules apply. The three unicode rules are turned off for HT's folder. The other 104 are fixed in this phase |
| ruff format | Clean, if HT's agent files stay excluded | The exclude moves to Kiln's root config. Seven wrapper templates are copied by agents exactly as they are, so they are not formatted |
| ruff import order | About 120 findings in `tests/` without a first-party setting | A `src` setting for HT's folder |
| ty type check | 143 diagnostics in `src` at 3.11, 49 of them imports of `textual` that go away when the dependency is in the lock | **One phase of its own, directly after the move** (decided by the owner). The move excludes HT's `src` from ty. The next phase is one clear commit that fixes every diagnostic and removes the exclude. No behaviour changes in it |
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
- **Running a train item by id** is the eval job with `judge: false`, `split: "train"` and `item_ids`. Today that job needs a judge config of the V2 kind, because the old kind of judge runs the task and judges it in one call. **The gap is closed in this phase, as the functional spec says:** a job with `judge: false` runs the task with the drive path that V2 uses, whatever kind the named judge config is. No judge runs in such a job, so the kind of the judge does not matter to it. The component doc gives the change in the eval runner.
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

- `reserved_memory_tags` is the rule of the functional spec (a record tagged with the name of a withheld split), made a setting, so that it also covers the `baseline` record, which the gateway protects today. (Decided by the owner.)
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

1. **Check the sandbox first.** The agent CLIs' connection to Kiln's MCP server over HTTP was verified many times in the MCP project. What is new here is HT's own sandbox settings: the shell's network is off, and the session may read only named folders. So the first step runs each of the three CLIs with those settings, calls both tools, and opens a file that `call_kiln_api` saved.
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
| Check of each run config an agent made | Where the builder's output enters the loop (`items.py`), before the review step | New place for two checks that exist (the model policy, the tool lock) and one new one: the run config against its parent, with the rules of HT's `rc_inherit` |
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

**The mechanism is left open until this phase** (decided by the owner). It needs a trial and an investigation first. The candidates:

| Mechanism | For | Against, or not known |
|---|---|---|
| A sub-command or an option of Kiln's one executable | One executable to build, sign and ship. The Python code is shared with the app | The entry script runs in every child process, so the branch must be at its top and use only the standard library. On Windows the app is built as a windowed program, which is linked as a GUI program: a console program started from it has known problems with its console, its input and output, and its exit code. The Linux build shows a splash screen |
| A second executable in the same bundle | Its own entry script, and it can be a console program | Needs a build file where the build is one command line today. The Linux build is one file, so there is no shared bundle there |
| HT as a Python package beside the app | No frozen-build problem at all | The code does not ship in the app, which the owner asked for |

- The launcher (`harness-tuner` on PyPI) finds an installed Kiln, or downloads the release asset for the platform, checks its digest, and installs it. Then it starts HT by the mechanism that is chosen.
- Native Windows is a P2 for HT, in the [backlog](backlog.md). The Windows problems above still matter to the choice, because the choice should not close that door.

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

- **HT's sandbox settings with an HTTP MCP server** (5.1, step 1). The connection itself is proven; the settings are not.
- **The route map has 272 lines to get right.** A wrong `CHAT` on a route that returns eval data leaks to chat clients. The mark of 4.5 and its test are the guard, and the review of the phase reads every route that returns a run, an eval input or a score.
- **HT's suite under Kiln's set-up** (2.3). Not run yet.
- **Phase 7 inside a frozen build.** Not run yet.
- **The size of the port of the role files.** 190,000 characters, checked by a sentence diff.
- **A context variable added later** by someone who does not know the job trap (4.3). A test starts a job from a request with a role and checks that the job reads a withheld split.

## 10. Decisions

Answered by the owner on 2026-11-27:

- **The folder** is `app/harness-tuner/`.
- **Python:** main requires 3.11. No change.
- **The type check** is one phase of its own, one clear commit, directly after the move.
- **How Kiln's release runs HT** is left open until phase 7 (section 7).
- **The `baseline` memory record:** the three train-side tuner roles cannot write `baseline` or `val`.
- **Kiln's memory tool or API tool on a new run config:** no check. Nothing gives an agent those tool ids, and this spec does not guard obscure cases. It belongs with the cases of functional spec 5.7.
- **The parent's properties on a new run config:** the agent builds the whole body, the role file says how, and loop code checks the result against the parent.
- **Native Windows** stays a P2, in the backlog.

Still open:

- **The tool lock and archives.** See the note below.
- **Judged eval jobs.** The build role has the eval job route, for the run of one train item. With it, a builder or a probe could start a judged eval job, which no HT role that stays can do today. **Proposed:** one more setting of a role, "eval jobs without a judge only", and one call of the shared helper in the handler that starts an eval job. It is the same pattern as the other rules, and it keeps today's limit.

**The tool lock.** `--lock-tool` is an option of the user: it names tools of the baseline run config that must not change. HT refuses a run config that drops such a tool, replaces it, or wraps it in a new code tool. Loop code makes this check before a run config is measured or promoted, and that stays. The gateway does two more things: it makes the check at the moment an agent creates the run config, and it refuses to archive a locked skill or code tool. After the move, the first is covered by the new check of 5.4. The second is not: the build role has the two archive routes, and Kiln does not know the lock. **Proposed:** the role file names the locked tools, and loop code's check of 5.4 also confirms that no locked tool was archived by the session.

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
9. *(Removed: the gap for an old-kind judge is closed, as the functional spec says.)*
10. **Section 9:** "each platform Kiln supports" becomes "each platform HT supports". Native Windows is a P2, in the backlog.
11. **6.4:** the `baseline` tag, the check of a run config against its parent, and the tool lock are added to the list, with the owner's decisions.
12. **Section 3:** the type check is one phase of its own, not steps.
