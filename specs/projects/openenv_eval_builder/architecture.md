---
status: complete
---

# Architecture: Eval Builder cases grounded in an OpenEnv server

The UI is in `ui_design.md`; "Product integration" below is the backend and frontend code
behind it.

## Components

| Component | Where | New or changed |
|---|---|---|
| Server metadata, including the readme | `libs/core/kiln_ai/openenv/session_manager.py` | Changed: `metadata()` |
| Reset arguments brief | `libs/core/kiln_ai/openenv/reset_schema_brief.py` | New |
| Grounding agent | `libs/core/kiln_ai/eval_grounding/` | New package |
| Prototype command | `app/desktop/studio_server/dev/ground_cases.py` | New |
| MCP wrapper for `claude -p` | `app/desktop/studio_server/dev/grounding_mcp.py` | New |
| Tool capabilities without an episode | `app/desktop/studio_server/utils/copilot_utils.py` | Changed |
| Brief endpoint | `app/desktop/studio_server/openenv_server_api.py` | Changed |
| Grounding route | `app/desktop/studio_server/eval_builder_api.py` | New route |
| Judge guidance renderer | `libs/core/kiln_ai/eval_grounding/judge_guidance.py` | New |
| Episode scope, shared with the eval runner | `libs/core/kiln_ai/openenv/episode_scope.py` | New, extracted |
| Driving cases in their episode | `libs/core/kiln_ai/synthetic_user/runner.py`, `case.py` | Changed |
| Judge, review and save | `eval_builder_utils.py`, `eval_builder_api.py`, `copilot_api.py`, `copilot_utils.py` | Changed |
| Datamodel | `Eval.openenv_server_id`, `TaskRun.reference`, `EvalTaskInput.from_trace` | Changed |
| Simulated-user driver prompt | `libs/core/kiln_ai/synthetic_user/prompt.py` | Changed: grounded flag |
| Builder UI | `app/web_ui/.../builder/` (`+page.svelte`, `batch_plan_guidance.ts`, `builder_draft.ts`, `progress_count.svelte`), `create_eval_config` page | Changed |

The grounding agent lives in `libs/core` because it needs only the adapters and the OpenEnv
session manager, and both the studio server and the prototype call it.

## Server metadata

`OpenEnvSessionManager` reads only `name` and `version` from `GET /metadata` today. Add:

```python
@dataclass(frozen=True)
class OpenEnvMetadata:
    name: str
    version: str
    description: str | None
    readme_content: str | None

async def metadata(self, openenv_server: OpenEnvServer) -> OpenEnvMetadata
```

Same transport and errors as `openenv_version`. Missing or non-string `description` and
`readme_content` become `None`. `openenv_version` keeps its behavior.

## Reset arguments brief

`reset_schema_brief.py`, pure functions over the dict `OpenEnvSessionManager.reset_schema()`
returns.

```python
@dataclass(frozen=True)
class ResetArgument:
    path: str                    # "fixture", "startup.acting_user"
    description: str | None
    values: list[JsonValue] | None   # from enum, when the argument has a fixed set

def reset_arguments(schema: dict[str, JsonValue]) -> list[ResetArgument]
def reset_arguments_brief(schema: dict[str, JsonValue] | None) -> str | None
```

`reset_arguments`:
- Walks `properties` in order. Skips `seed` and `episode_id` at the top level.
- Resolves local refs (`#/$defs/<name>`) itself; the session manager returns the schema unresolved.
  A non-local or missing ref is treated as an argument with no further structure.
- Unwraps `anyOf` with one non-null member (Pydantic's `X | None`). An `anyOf` with several non-null
  members is listed with its description and no values.
- An object with `properties` is walked into; its children get dotted paths. The object itself is
  listed too when it has a description. Depth is capped at 4.
- `values` comes from `enum` on the unwrapped member. `const`, `oneOf` and the rest are not
  read: Kiln's reset form refuses them.

`reset_arguments_brief` renders the planner's "reset arguments" section: the framing text from the
plan page's "Prompt changes" tab, then one block per argument (path, description, values). It
returns `None` when there is no schema or no arguments, and the caller leaves the section out.
The framing text is a module constant, so the prototype and the product use the same words.

## Grounding agent

### Package layout

```
libs/core/kiln_ai/eval_grounding/
  models.py      # EvalContext, GroundingCase, GroundedReference, GroundingOutcome, DropReason
  prompt.py      # system prompt and the per-case user message
  session.py     # GroundingSession: the agent's tools, episode lifecycle, limits, call log
  agent.py       # ground_case(): one case, end to end
  batch.py       # ground_cases(): many cases, concurrently, with progress
```

### Models

```python
class EvalContext(BaseModel):        # the same for every case in a run
    specification: str               # the eval's specification text
    target_task_prompt: str          # the target task's prompt (task.instruction)
    data_guide: str | None

class GroundingCase(BaseModel):
    scenario: str                    # the approved plan item's prompt
    seed_prompt: str
    synthetic_user_info: str         # kiln_server's <persona>/<goal>/<behavior_guidance> blob

class Evidence(BaseModel):
    tool: str
    args: dict[str, JsonValue]
    result_excerpt: str

class Fact(BaseModel):
    text: str
    evidence: Evidence

class GroundedReference(BaseModel):  # rendered to markdown, saved as reference["judge_guidance"]
    starting_point: str
    facts: list[Fact]
    expected_outcome: str  # one paragraph of facts: correct answer and end-state change

class DropReason(str, Enum):
    no_fit = "no_fit"                # nothing fits after a reasonable search
    unrepresentable = "unrepresentable"
    rehearsal_failed = "rehearsal_failed"
    limit = "limit"                  # calls, resets or time ran out
    invalid_output = "invalid_output"

class GroundingOutcome(BaseModel):
    status: Literal["grounded", "dropped"]
    drop_reason: DropReason | None
    drop_detail: str | None          # one sentence, shown to the user
    openenv_reset: OpenEnvReset | None
    seed_prompt: str | None          # filled in
    synthetic_user_info: str | None  # filled in
    reference: GroundedReference | None
    call_log: list[LoggedCall]       # every tool call, for the prototype and debugging
    usage: Usage | None              # tokens and cost, summed over the run
    usage_complete: bool             # False when a stop, timeout or rejected answer left model calls out of usage
```

The model returns a smaller JSON (`status`, `drop_reason`, `drop_detail`, `seed_prompt`,
`synthetic_user_info`, `reference`) through structured output. `openenv_reset` is **not** taken
from the model: it is the `reset_kwargs` of the last `start_episode` call in the session. That is
the state the agent searched and rehearsed in, so the saved reset can't disagree with what the
reference describes.

### Tools (`session.py`)

`GroundingSession` holds the server, the session manager, the current `OpenEnvEpisode`, the reset
and call counters, and the call log. It builds the agent's tools as `UnmanagedKilnTool`
subclasses, passed through `AdapterConfig.unmanaged_tools`:

- `start_episode(reset_kwargs: object)`: releases the current episode, if any, then
  `session_manager.start_episode(server, reset_kwargs)`. Returns the reset metadata, or the
  server's rejection message as a tool error (the agent can fix its arguments).
- `read_state()`: `session_manager.read_state(current)`. Gives a side-effect-only environment a
  way to see what changed.
- One tool per server tool, from `list_tools`, with the server's name, description and input
  schema. `run` calls `session_manager.call_tool(current, name, kwargs)`. A server tool named
  `start_episode` or `read_state` is exposed as `env_<name>`.

Rules enforced in the tools, not the prompt:
- A server tool or `read_state` before any `start_episode` returns a tool error: "Call
  start_episode first."
- Limits: 40 tool calls (server tools and `read_state`) and 10 resets. Past a limit every tool
  returns an error telling the agent to return its result now. Five calls after that, the session
  raises `GroundingLimitReached`, which `ground_case` turns into a `limit` drop.
- `OpenEnvTransientError` (including capacity) from `start_episode` is retried twice with backoff,
  then raised. On a server tool or `read_state` the session manager has already dropped the
  session, so a retry can't succeed: the episode is cleared and the error raised. Either way it is
  not shown to the model as a tool error, because it is not the case's fault.
- A session-ending error (`tool_call_error_ends_session`) clears the current episode; the next
  server tool call returns "The environment closed. Call start_episode again."

Server tools run through `session_manager.call_tool` directly, not the `kiln_tool::openenv::`
ids and the episode ContextVar. The agent changes episodes mid-run, and the ContextVar is bound
for one episode per run.

### One case (`agent.py`)

```python
async def ground_case(
    case: GroundingCase,
    *,
    eval_context: EvalContext,
    openenv_server: OpenEnvServer,
    session_manager: OpenEnvSessionManager,
    model_name: str,
    model_provider: ModelProviderName,
    target_tools: list[ToolCallDefinition],  # what the agent under test can call
    reset_schema: dict[str, JsonValue] | None,
    metadata: OpenEnvMetadata,
    time_limit_s: float = 900,
) -> GroundingOutcome
```

1. Builds an in-memory `Task` (no path, so nothing is saved) with the system prompt from
   `prompt.py` and an output JSON schema for the model's result. Same pattern as
   `SyntheticUserDriver`.
2. Builds a `KilnAgentRunConfigProperties` for the given model with
   `structured_output_mode=StructuredOutputMode.default` and no configured tools, and an
   `AdapterConfig(allow_saving=False, unmanaged_tools=session.tools(),
   open_openenv_session=False, automatic_prompt_caching=True)`. Caching matters here: every
   tool round re-sends the whole conversation. The follow-up uses the same adapter.
3. The user message holds the eval context (specification, target task prompt, Data Guide), the
   case, the reset schema (JSON), the readme, and the target tools' names and descriptions. The
   eval context is in the message, not the system prompt, so the system prompt stays fixed.
4. Runs `adapter.invoke(...)` under `asyncio.timeout(time_limit_s)`.
5. Parses the result. On a parse or validation failure it asks once more in the same trace, then
   drops with `invalid_output`.
6. A `grounded` result with no `start_episode` call in the log is turned into an `invalid_output`
   drop.
7. `finally`: releases the current episode. Nothing is left open, on success, drop, timeout,
   error or cancel.

Errors that are not the case's fault (`OpenEnvTransientError` after retries, an unreachable
server, a model provider error) are raised, not turned into drops. The caller fails the step.

### Many cases (`batch.py`)

```python
async def ground_cases(
    cases: list[GroundingCase], *, concurrency: int = CONCURRENCY, **ground_case_kwargs
) -> AsyncIterator[GroundingProgress]
```

Runs `ground_case` through `AsyncJobRunner` with the same `CONCURRENCY` as
`synthetic_user/runner.py`. Yields a progress event per finished case (index, outcome) and a final
summary. A raised error cancels the remaining cases and, after they release their episodes, is raised as
`GroundingCaseError(case_index, error)`, chained from the original error (`.error` and `__cause__`),
so callers that map error types must unwrap it. The reset schema, metadata and tool list are read once, before the first case.

## Prototype command

`app/desktop/studio_server/dev/ground_cases.py`, run as
`uv run python -m app.desktop.studio_server.dev.ground_cases <subcommand>`. It has two stages, so
the expensive planning step runs once and the grounding step can be rerun while the prompt
changes.

**`prepare`** writes the inputs every grounding run reuses:

```
--project <path to project.kiln>
--task-id <id>                    # the target task: its prompt and schemas go to the planner
--openenv-server-id <id>          # a saved OpenEnvServer in that project
--spec <file>                     # the eval's specification text
--base-guidance <file>            # multiturn_plan_guidance output for that spec, from the UI
--data-guide <file>               # optional
--count <n>
--out <dir>
```

1. The specification, the target task's prompt (`task.instruction`, as sent to simulated-user
   generation) and the Data Guide, when given → `specification.txt`, `task_prompt.txt`,
   `data_guide.txt`. `ground` reads them as the `EvalContext`.
2. `reset_schema()` and `metadata()`; `reset_arguments_brief(...)` → `brief.txt`, `schema.json`,
   `metadata.json`.
3. Guidance = base guidance + brief + Data Guide section → `guidance.txt` →
   `_run_batch_plan_kiln_server(...)` → `plan.json`.
4. `SyntheticUserClient.generate(...)` on the plan prompts, in the same chunks as
   `generate_cases`, with plan-relative `scenario_index` → `users.json`.

The base guidance file is used as given: the OpenEnv version of the rule-12 line is not swapped in.

**`ground`** grounds the prepared cases. A prepare folder without `specification.txt` or
`task_prompt.txt` is refused with the missing names, rather than grounded without them.

```
--project <path> --openenv-server-id <id> --in <prepare's dir> --out <run dir>
--engine claude | kiln
--model <name> [--provider <provider>]    # provider for --engine kiln only
--prompt <file>                            # optional: a grounding prompt to try instead of prompt.py's
--cases <indices>                          # optional: a subset, e.g. 0,3-5, for quick iteration
--claude-bin <path>                        # optional: the claude executable (default: claude)
--claude-bare                              # optional: run claude with --bare
```

Writes `outcomes.json` (every outcome with its call log) and `summary.json`: grounded and dropped
counts, drops by reason, failed cases with their errors, each grounded case's reset arguments (so a
person can see which ones used a setup argument; the command doesn't guess which argument is setup),
and tokens and cost where the engine reports them.

A case that fails for a reason that is not its fault (an environment error, a `claude` failure, an
MCP server that never started) is listed under `failed_cases`; the other cases carry on, and the
command exits 1. The product's `ground_cases` instead fails the whole step.

The planner guidance is composed in the web UI for the product. The prototype reads the base part
from a file so it doesn't port `batch_plan_guidance.ts`; the Data Guide framing is a constant in
the prototype until the product's version is written. `prepare` needs the Kiln Copilot API key from
Kiln's config, as the studio server does.

### Engine `claude`: prompt iteration with `claude -p`

For cheap iteration on the prompt and tool descriptions with a frontier model, before spending on
the user's model. It tests the approach, not Kiln's adapter loop.

- `dev/grounding_mcp.py`: a stdio MCP server on the low-level `mcp` `Server`, not FastMCP:
  FastMCP derives each tool's input schema from a Python signature, and these schemas come from
  the OpenEnv server. It imports only `kiln_ai` and `mcp`, so `claude` starts it by file path.
  On start it loads the project's `OpenEnvServer` and builds one `GroundingSession`. It exposes the
  session's tools (`start_episode`, `read_state`, one per server tool) as MCP tools, with the same
  limits, rules and call log. It writes a run log (call log, last reset, and a stop value) to a file
  named by an argument after every call and on exit, so the log is current even if `claude` is
  killed. The stop value is `limit` (the hard stop after a limit) or `error` (anything not the
  case's fault, such as an unreachable server); after a stop every call is refused. On exit it
  releases the episode.
- Per case, in `<run dir>/case_<n>/`, `ground` runs
  `claude -p --model <model> --output-format json --tools "" --permission-mode dontAsk
  --system-prompt <grounding prompt text> --mcp-config <one server, this case> --strict-mcp-config
  --allowedTools "mcp__grounding__*"` with the case message on stdin and the case folder as the
  working directory. `--tools ""` removes the built-in tools, so only the grounding tools exist: no
  file, shell or web access. `claude` has no `--system-prompt-file`, so the prompt goes as text.
- The final message must be the result JSON. `ground` parses it (code fences and prose around the
  object are tolerated), takes `openenv_reset` from the run log's last reset, and builds the
  outcome with `GroundingOutcome.from_result`, as `ground_case` will. A `limit` stop or the case's
  15 minutes running out is a `limit` drop; an `error` stop fails the case.
- An unusable reply gets one follow-up: `--resume <session>` with `--strict-mcp-config` and no MCP
  config, so the agent has no tools, can't start another episode, and no new server overwrites the
  run log. If that reply is unusable too, or `claude` rejects the follow-up, the case drops as
  `invalid_output`.
- Cases run in parallel up to `CONCURRENCY`, each with its own MCP server process. `claude` is
  killed on timeout or cancel.
- Default model: `claude-opus-5-5`.
- Limitation: without `--claude-bare`, `claude` still loads the user's own CLAUDE.md and memory, and
  any CLAUDE.md in the run folder or above it, into the agent's context. `--out` belongs outside any
  repository; `ground` warns when it finds a CLAUDE.md above the run folder. `--bare` keeps all of
  it out but authenticates only with `ANTHROPIC_API_KEY`.

### Engine `kiln`

Calls `ground_cases(...)` with `--model` and `--provider`: the real agent, on the model a user
would pick. This is the measured run. Until phase 3 it prints that it is not implemented yet and
exits 2.

Comparison against the eb3 runs is manual: same specification, same server, same count.

## Product integration

Finished after the prototype, with `ui_design.md`. Each part below is one place in the code; the
phases in `implementation_plan.md` follow the same order.

### What the builder does today on an OpenEnv run config

Read from the code (2026-11-18), not run:

- **Step 2 fails.** Clarifying questions (`question_spec`) and judge authoring both call
  `_collect_task_capabilities` (`studio_server/utils/copilot_utils.py`), which calls `tool_from_id`
  for every tool. For a `kiln_tool::openenv::…` id that raises outside an episode
  (`tools/tool_registry.py`, `_openenv_tool`).
- **Turn 2 fails.** `run_cases_batch` drives with `allow_saving=False`, so the adapter clears the
  run's id, and `openenv_for_run` releases the episode after turn 1 (`openenv/run_session.py`,
  `handle.run_id is None`). Turn 2 then raises `session_ended`.
- **Reviewed cases have no reference.** Reviewed conversations become the golden set as `TaskRun`s,
  and `EvalTaskInput.from_trace` gives a golden `TaskRun` no reference data when it is scored
  against itself. A judge with `reference_keys=["judge_guidance"]` would skip every one.

All three are fixed below.

### Tool capabilities without an episode

`_collect_task_capabilities` splits the run config's tool ids. OpenEnv ids go to
`OpenEnvSessionManager.list_tools(server)` (one call per server, no episode), and their names and
descriptions are read from that list. Other ids keep `tool_from_id`. An unreachable server raises
`OpenEnvUnreachable`, which the route turns into the existing 500 with the server's URL; the
frontend's `is_openenv_unreachable` already titles it.

### Planner guidance

- `GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_arguments_brief` in
  `openenv_server_api.py` returns `{brief: str | null}` from `reset_arguments_brief(...)`.
- `batch_plan_guidance.ts` gains three builders, all plain text:
  - `reset_arguments_section(brief)` with the framing in the functional spec, including: name kinds
    of starting states, never a starting state by name.
  - `synthetic_user_guide_section(guide)`, left out when empty. Wired once the guide's UI exists.
  - `dropped_cases_section(drops: {scenario, drop_detail}[])`.
- `compose_plan_guidance(base, steer)` becomes `compose_plan_guidance(base, sections, steer)`:
  base, then each non-empty section, then the steer last. The base stays a strict prefix.
- `multiturn_plan_guidance(spec, { openenv: boolean })` swaps the rule-12 paragraph for the OpenEnv
  wording.
- `on_plan_batch` fetches the brief once per build (cached in the draft with the server id), and
  passes `pending_retry_drops` when set. `pending_retry_drops` is set by the drop screen's Retry
  and cleared when a plan lands.

### Grounding as its own stream

`generate_cases` stays as it is (plain JSON from kiln_server). Grounding is a new route, so it can
stream and receives what it needs.

`POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/ground_cases` in
`eval_builder_api.py`, streamed with `_sse` and `CancellableStreamingResponse` like
`multi_turn_pipeline`:

```
GroundCasesRequest
  target_run_config_id: str
  judge_model: {model_name: str, model_provider: str}
  specification: str
  synthetic_user_guide: str | None
  cases: list[GroundCaseApi]
    scenario_index: int
    scenario: str                       # the plan item text
    seed_prompt: str
    synthetic_user_info: str
```

- Resolves the run config, then the server with `single_openenv_server_id(project, tool_ids)`.
  None (no OpenEnv tools, or tools from two servers) is a 400.
- Builds `GroundingCase`s and calls `ground_cases(...)` with the judge model, the task's prompt
  as `target_task_prompt`, and the run config's tool definitions as `target_tools`.
- Events, one JSON frame each, then the terminator:
  - `grounding_started {total}`
  - `case_grounded {case_index, scenario_index, status: "grounded", openenv_reset, seed_prompt,
    synthetic_user_info, judge_guidance}`; `judge_guidance` is `render_judge_guidance(reference)`,
    so the typed reference never leaves the server.
  - `case_dropped {case_index, scenario_index, drop_reason, drop_detail}`
  - `grounding_finished {grounded, dropped, usage}`
  - `grounding_failed {code, message}` when `ground_cases` raises (`GroundingCaseError`; an
    `OpenEnvUnreachable` cause gives `code: "openenv_unreachable"` and the server URL).
- A client abort cancels the generator; `ground_cases` cancels its cases and each releases its
  episode.

### Judge guidance rendering

`libs/core/kiln_ai/eval_grounding/judge_guidance.py`:

```python
def render_judge_guidance(reference: GroundedReference) -> str
```

Headings in order: `## Starting point`, `## Facts`, `## Expected outcome`. Each fact is a bullet
with its text, then an indented line ``Checked with `tool` (args): result excerpt``. An empty field
prints "None." under its heading.

### Builder state (frontend)

- `SyntheticUserCaseWire` gains `openenv_reset?: OpenEnvReset` and `judge_guidance?: string`.
- Two case caches (`builder_draft.ts`). `cached_su_cases` holds kiln_server's generated simulated
  users, keyed on the plan and spec only, as before this project. `cached_grounded_cases` holds the
  same cases after grounding, keyed on plan, spec, OpenEnv server id and judge model, with the count
  of drops accepted with Continue. A grounding failure or a changed judge or server re-grounds the
  cached generated cases without calling `generate_cases` again.
- `on_drive_multi_turn` runs `grounding_cases` after `generating_cases` when the run config's
  server is known. The server is looked up with `lookup_run_openenv_server` when the first plan
  needs it, only when the run config has an OpenEnv tool id, and kept in the draft keyed by the
  tool set.
- Drops collect into `grounding_drops: {scenario, drop_detail}[]`. Any drop stops before driving
  and shows the drop screen (`ui_design.md`). Continue drives the grounded cases; Retry sets
  `pending_retry_drops = grounding_drops` and calls `on_plan_batch()`; Cancel clears the batch's
  cases and returns to the plan.

### Driving each case in its episode

- `SyntheticUserCase` (`synthetic_user/case.py`) gains `openenv_reset: OpenEnvReset | None` and
  `judge_guidance: str | None`. The pipeline request carries both.
- New `libs/core/kiln_ai/openenv/episode_scope.py`, extracted from
  `eval_runner._run_v2_job_in_openenv`:

  ```python
  @asynccontextmanager
  async def openenv_episode_scope(
      manager: OpenEnvSessionManager, server: OpenEnvServer, reset_kwargs: dict[str, JsonValue]
  ) -> AsyncIterator[EpisodeScope]
  ```

  It starts the episode, binds it with `set_episode`, yields, then ends it and puts the ended
  episode (with `final_state`) on `scope.ended`. On error it releases instead. `eval_runner` uses
  it too, so both paths start, bind and end episodes the same way.
- `run_cases_batch` drives a case that has `openenv_reset` inside `openenv_episode_scope`, with
  `open_openenv_session=False` on the target adapter, and stores `scope.ended` as the leaf run's
  `openenv_episode`. An ended episode with no `final_state` is not saved: the case is retried in
  a fresh episode, as the eval runner refuses such a trace. A case without one is driven as today.

### Judge

- `build_judge_prompt_template(judge_prompt, multi_turn, grounded=False)`: when `grounded`, adds a
  `<judge_guidance>{{ reference_data.judge_guidance }}</judge_guidance>` block, and a
  `{% if openenv_episode and openenv_episode.final_state %}` block with the final state, before the
  transcript. The text tells the judge to grade against the specification, using the guidance as
  the facts of the environment, and to grade the end result and what the agent told the user, not
  which tools it called.
- `build_transient_judge_eval_config(..., grounded)` sets `reference_keys=["judge_guidance"]` when
  grounded. `run_judge_for_trace`, `build_claims_for_trace` and the `judge_traces` route take the
  case's `judge_guidance` and pass `reference_data={"judge_guidance": ...}`; the trace run carries
  `openenv_episode`.
- The saved judge (`spec_with_copilot`) uses the same template and `reference_keys`.

### Reference on golden runs

- `TaskRun` gains `reference: dict[str, JsonValue] | None` (default None): ground truth a judge
  reads for this run when it is a golden eval item. Same meaning as `EvalInput.reference`.
- `EvalTaskInput.from_trace`: when the source is a `TaskRun` with `reference` set, that is the
  reference data, whether or not the source is the trace. Otherwise unchanged.
- Save sets `reference={"judge_guidance": ...}` on each reviewed chain's leaf run.

### Save

- `MultiTurnSaveInfo` gains `openenv_server_id: str | None`. `DrivenSyntheticCaseApi` gains
  `openenv_reset` and `judge_guidance`.
- `build_multi_turn_eval_inputs` writes `openenv_reset` and
  `reference={"judge_guidance": ...}` on each minted `EvalInput`.
- `Eval` gains `openenv_server_id: ID_TYPE | None` (default None), set from `MultiTurnSaveInfo`.
  The save checks that every case's `openenv_reset.openenv_server_id` equals it; a mismatch is a
  400.

### Driver prompt

`synthetic_user/prompt.py` renders without the accept-not-found bullet when the case has
`judge_guidance`. Both paths that drive a case pass this flag: `run_cases_batch` in the builder
(the case's `judge_guidance`), and the eval runner's re-drive through `drive_case_for_eval`
(the saved `EvalInput.reference` has a `judge_guidance` key, `is_grounded_input`). A saved grounded
case then behaves the same in the builder and when the eval runs.

### Judge hint

The `create_eval_config` page reads the eval; when `openenv_server_id` is set, it shows the note in
`ui_design.md` above the prompt fields. No change to how `reference_keys` are derived in v1.

### Grounding prompt

The two rules from the Haiku runs (`prototype_results.md`) go into `prompt.py`: a named thing that
isn't there is replaced by one of the same kind or added with setup; the scenario's situation
(when, whose, what state) is kept, with setup if needed.

Two more keep the reference to environment truth. The reference does not restate or interpret
the specification: the judge has it, and writes only what the environment shows. Setup writes the
data the scenario calls for as the scenario describes it, never softened, masked or sanitized to
fit the specification, or the case tests something else.

## Error handling

| Error | Where | Result |
|---|---|---|
| Server rejects reset arguments | `start_episode` tool | Tool error; the agent fixes them |
| Server tool error | server tool | Tool error, as the server reported it |
| Session ended by the server | server tool | Tool error asking for a new `start_episode` |
| Transient or capacity error | `start_episode` | Retried twice, then raised; the step fails |
| Transient error | server tool, `read_state` | Episode cleared, error raised; the step fails |
| Limits reached | session | Agent told to finish; then a `limit` drop |
| Time limit | `ground_case` | `limit` drop |
| Unparseable result | `ground_case` | One retry, then an `invalid_output` drop |
| Model provider error | `ground_case` | Raised; the step fails |

Every path releases the current episode.

## Testing

All against the fake server in `libs/core/kiln_ai/openenv/testing.py` (`serve_in_thread`), with
the LLM stubbed by patching `acompletion_checking_response`, as `test_run_session.py` does.

- `reset_schema_brief`: properties in order; `seed` and `episode_id` skipped; `$ref` into `$defs`
  resolved; `anyOf` with null unwrapped; nested object paths; `enum` values; depth cap; missing
  schema and empty properties return `None`; a real Seahaven-shaped schema as a fixture.
- `metadata()`: with and without `readme_content` and `description`, via `extra_routes`.
- `GroundingSession`: server tools before `start_episode` refused; `start_episode` releases the
  previous episode; rejection returned as a tool error; call and reset limits; the hard stop
  after the limit; transient retries then raise; session-ending errors clear the episode; name
  collision renamed; call log contents.
- `ground_case`: grounded result takes `openenv_reset` from the last `start_episode`, not from the
  model; parse failure retried once then dropped; grounded with no episode becomes a drop; timeout
  drops; every exit releases the episode (assert the fake server has no open sessions).
- `ground_cases`: progress per case; concurrency bound; a raised error cancels the rest and
  releases their episodes.
- Prototype command: `prepare` with stubbed kiln_server clients, checking the files it writes;
  `ground --engine kiln` with a stubbed LLM; `ground --engine claude` with the `claude` call
  replaced by a stub that returns a fixed result.
- `grounding_mcp`: lists the session's tools; a call reaches the fake server; limits apply; the
  call log and last reset are written on exit.

- Product integration:
  - `_collect_task_capabilities` with OpenEnv ids against the fake server, no episode opened;
    unreachable server gives the existing error.
  - `reset_arguments_brief` route: brief, null for a server without a reset schema, 404.
  - `ground_cases` route: events in order for grounded and dropped cases, `judge_guidance`
    rendered, `grounding_failed` on a raised error, 400 for a run config with no OpenEnv server,
    a client abort leaves no open session on the fake server.
  - `render_judge_guidance`: each section, facts with evidence, empty lists.
  - `openenv_episode_scope`: started, bound, ended with `final_state`; released on error;
    `eval_runner` tests still pass through it.
  - `run_cases_batch`: a case with `openenv_reset` drives every turn in one episode and stores
    the ended episode on the leaf run; a case without it drives as today.
  - Judge template with and without `grounded`; transient judge passes the guidance.
  - `EvalTaskInput.from_trace` with a golden `TaskRun` that has `reference`.
  - Save: inputs carry `openenv_reset` and `judge_guidance`, golden leaves carry `reference`,
    `Eval.openenv_server_id` set, mismatched server rejected.
  - Frontend: guidance composition order; drop screen actions (Continue, Retry sets
    `pending_retry_drops`, Cancel); progress counts from the stream; judge lane settings on
    OpenEnv builds; cache key includes server and judge model.

## Open technical questions

1. **Prototype command location.** A dev module under `app/desktop/studio_server/dev/` can use the
   kiln_server clients and Kiln's config directly. It ships in the repo but not in any UI. Keep it
   after the prototype as a debugging tool, or delete it once the builder is wired?
2. **Structured output on the user's model.** `StructuredOutputMode.default` lets each provider
   pick. Some models are weak at tool calling followed by a JSON final answer. The measured run
   tries both this and a final `submit_result` tool.
