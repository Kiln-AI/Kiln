---
status: complete
---

# Architecture: Eval Builder cases grounded in an OpenEnv server

Backend only. The UI (the project's multi-turn synthetic user guide, progress line, Review Cases, dropped cases, the judge lane's tool filter)
is designed after the phase 1 prototype, in `ui_design.md`, and added here then.

## Components

| Component | Where | New or changed |
|---|---|---|
| Server metadata, including the readme | `libs/core/kiln_ai/openenv/session_manager.py` | Changed: `metadata()` |
| Reset arguments brief | `libs/core/kiln_ai/openenv/reset_schema_brief.py` | New |
| Grounding agent | `libs/core/kiln_ai/eval_grounding/` | New package |
| Prototype command | `app/desktop/studio_server/dev/ground_cases.py` | New |
| MCP wrapper for `claude -p` | `app/desktop/studio_server/dev/grounding_mcp.py` | New |
| Brief endpoint | `app/desktop/studio_server/openenv_server_api.py` | Changed (after prototype) |
| Builder pipeline: ground, drive, judge, save | `multiturn_sdg_api.py`, `eval_builder_api.py`, `eval_builder_utils.py`, `copilot_utils.py` | Changed (after prototype) |
| Simulated-user driver prompt | `libs/core/kiln_ai/synthetic_user/prompt.py` | Changed: grounded flag |

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
    expected_outcome: list[str]
    allowed: list[str]
    must_not_happen: list[str]

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

## After the prototype (outline, finished with `ui_design.md`)

- **Brief endpoint.** `GET /api/projects/{project_id}/openenv_servers/{id}/reset_arguments_brief`
  returns `reset_arguments_brief(...)` or null. `batch_plan_guidance.ts` appends it, the
  synthetic user guide section and, on a Retry after drops, the dropped cases section (each
  dropped scenario with its `drop_detail`).
- **Grounding in `generate_cases`.** `GenerateCasesApiInput` gains `target_run_config_id`. When
  the run config reaches one OpenEnv server (`single_openenv_server_id`), the route runs
  `ground_cases` after kiln_server returns and streams progress. The case dict gains
  `openenv_reset`, `reference` (the typed form, rendered at save) and `drop`.
- **Driving.** Today's multi-turn pipeline leaves `open_openenv_session` on, so on an OpenEnv run
  config each case's first turn opens its own episode with `{}` reset arguments and nothing ends
  it. The pipeline takes the episode over, as `eval_runner._run_v2_job_in_openenv` does: start the
  case's episode with its `openenv_reset`, `set_episode(...)` around the drive, then
  `end_episode` and store `openenv_episode` with `final_state`. Drive with
  `open_openenv_session=False`, as `synthetic_user/eval_drive.py` does. The shared helper is
  extracted from `eval_runner` so both paths start, bind and end episodes the same way.
- **Judge.** `build_judge_prompt_template(judge_prompt, multi_turn)` adds
  `{{ reference_data.judge_guidance }}` and `openenv_episode.final_state` blocks, which the Jinja
  namespace already carries, and the judge's `reference_keys` is `["judge_guidance"]`.
  `run_judge_for_trace` and `build_claims_for_trace` take the `openenv_episode`.
- **Save.** `build_multi_turn_eval_inputs` writes `openenv_reset` and
  `reference={"judge_guidance": render_judge_guidance(grounded_reference)}`. The renderer is in
  `eval_grounding/judge_guidance.py`, with a test per section and for empty lists. The builder sets
  `Eval.openenv_server_id` (new, `ID_TYPE | None`) from the step 1 run config's server, and
  `Eval` validates nothing more about it in v1.
- **Step 2.** `_collect_task_capabilities` uses `list_tools` for OpenEnv tool ids.
- **Driver prompt.** `synthetic_user/prompt.py` renders without the accept-not-found bullet when
  the case has a reference.

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

## Open technical questions

1. **Prototype command location.** A dev module under `app/desktop/studio_server/dev/` can use the
   kiln_server clients and Kiln's config directly. It ships in the repo but not in any UI. Keep it
   after the prototype as a debugging tool, or delete it once the builder is wired?
2. **Structured output on the user's model.** `StructuredOutputMode.default` lets each provider
   pick. Some models are weak at tool calling followed by a JSON final answer. The measured run
   tries both this and a final `submit_result` tool.
