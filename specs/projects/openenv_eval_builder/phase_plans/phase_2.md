---
status: complete
---

# Phase 2: Prompt iteration with `claude -p`

## Overview

The prototype command's two stages, with the `claude` engine. `prepare` reads the server's reset
schema and metadata, builds the planner guidance, and calls kiln_server's batch planner and
simulated-user generation once, writing every result to a folder. `ground --engine claude` grounds
the prepared cases by running `claude -p` once per case, with the grounding tools served by a
stdio MCP server that wraps one `GroundingSession`. `--engine kiln` is accepted by the parser and
stops with a "not implemented yet" message; it is phase 3. No test makes a paid call: the
kiln_server clients and the `claude` process are stubbed.

Nothing in the command names a world, a server or a reset argument.

## Steps

1. `libs/core/kiln_ai/eval_grounding/models.py`
   - `GroundingOutcome.dropped(reason, detail, *, call_log, usage) -> GroundingOutcome`.
   - `GroundingOutcome.from_result(result, *, openenv_reset, call_log, usage) -> GroundingOutcome`:
     a grounded result takes `openenv_reset` from the caller (the session's last reset); a grounded
     result with no reset becomes an `invalid_output` drop; a dropped result keeps its reason and
     detail. Phase 3's `ground_case` builds its outcome the same way.

2. `app/desktop/studio_server/dev/__init__.py` (new, docstring only).

3. `app/desktop/studio_server/dev/grounding_mcp.py` (new). Imports only `kiln_ai` and `mcp`, so
   `claude` can start it by file path from any working directory.
   - `GroundingRunLog(BaseModel)`: `call_log: list[LoggedCall]`, `last_reset: OpenEnvReset | None`,
     `stopped: Literal["limit", "environment_error"] | None`, `stop_detail: str | None`. The file
     `ground` reads after each case.
   - `load_openenv_server(project_path, openenv_server_id) -> OpenEnvServer`, raising
     `GroundingSetupError` when the project or server is missing. Shared with `ground_cases`.
   - `GroundingMcpServer(session, log_path)`: builds a low-level `mcp.server.lowlevel.Server` named
     `grounding` whose `list_tools` returns the session's tools (name, description, parameters as
     `inputSchema`) and whose `call_tool` runs them with input validation off (the session and the
     OpenEnv server judge arguments). A `ToolCallError` or an error result becomes `isError`.
     `GroundingLimitReached` sets `stopped="limit"`; an `OpenEnvError` raised by a tool sets
     `stopped="environment_error"`. After a stop every call is refused with a "return your result
     now" error. The log file is rewritten after every call (under a lock, off the event loop) and
     on exit, so it is current even if `claude` is killed.
   - `serve(project_path, openenv_server_id, log_path)`: list the server's tools, build the session,
     run over stdio, and on exit close the session, write the log, shut the session manager down.
   - `main(argv)`: `--project`, `--openenv-server-id`, `--log-out`.

4. `app/desktop/studio_server/dev/ground_cases.py` (new). `main(argv) -> int`, subcommands
   `prepare` and `ground`.
   - `prepare`: `--project`, `--task-id`, `--openenv-server-id`, `--spec`, `--base-guidance`,
     `--data-guide` (optional), `--count`, `--out`.
     1. `reset_schema()` and `metadata()` → `schema.json`, `metadata.json`;
        `reset_arguments_brief(...)` → `brief.txt` (empty when the server publishes none).
     2. `compose_guidance(base, brief, data_guide)`: base guidance, then the brief, then
        `DATA_GUIDE_FRAMING` with the text in `<data_guide>` tags, each left out when empty →
        `guidance.txt`. `_run_batch_plan_kiln_server(...)` with the task's runtime prompt and
        schemas and no `input_data_guide` → `plan.json`.
     3. `SyntheticUserClient.generate(...)` on the plan prompts, in chunks of `SU_CASES_PER_CALL`,
        with `scenario_index` made plan-relative → `users.json`.
   - `ground`: `--project`, `--openenv-server-id`, `--in`, `--out`, `--engine claude|kiln`,
     `--model` (default `claude-opus-5-5` for `claude`), `--provider` (kiln only), `--prompt`,
     `--cases`, `--claude-bin` (default `claude`), `--claude-bare`.
     - `load_prepared_cases(in_dir) -> list[GroundingCase]`: each user joined to its plan prompt by
       `scenario_index`; reads `schema.json` and `metadata.json` for the case message.
     - Target tools: the server's own tools from `list_tools`, as `ToolCallDefinition`s.
     - `--engine kiln`: prints that it is not implemented yet and returns exit code 2 before any
       work.
     - Engine `claude`, per case (at most `CONCURRENCY` at once), in `<out>/case_<n>/`: writes
       `mcp_config.json` (one stdio server `grounding`: `sys.executable` + the `grounding_mcp.py`
       path + its arguments, log file in the case folder) and `message.txt`; runs `claude -p
       --model <m> --output-format json --mcp-config <file> --strict-mcp-config --tools ""
       --allowedTools "mcp__grounding__*" --permission-mode dontAsk --system-prompt <text>`
       (`--bare` when asked) with the message on stdin, under the case's time limit; saves the raw
       output. Then: a timeout or a `limit` stop → `limit` drop; an `environment_error` stop →
       the case fails; otherwise the reply's `result` is parsed into `GroundingResult`. On a parse
       or validation failure it resumes the same `claude` session once with no MCP servers and no
       tools, asking for the JSON only, then drops with `invalid_output`. The outcome comes from
       `GroundingOutcome.from_result` with the log's `last_reset` and call log, and the usage
       summed over both calls.
     - `run_claude(argv, *, stdin, cwd, timeout_s) -> ClaudeReply`: async subprocess, kill on
       timeout; a non-zero exit, unparseable output or `is_error` raises `ClaudeRunError`.
     - A case that raises (environment error, `claude` failure) is recorded as failed and the
       others carry on; the command exits 1 when any case failed.
     - Writes `outcomes.json` (`case_index` + outcome per case), `summary.json` (engine, model,
       grounded and dropped counts, drops by reason, failed cases, each grounded case's
       `reset_kwargs`, summed tokens and cost) and `system_prompt.txt`.

## Tests

- `eval_grounding/test_models.py`
  - `from_result`: grounded takes the given reset; grounded without a reset becomes an
    `invalid_output` drop; dropped keeps reason and detail; call log and usage carried
  - `dropped`: builds a valid drop
- `dev/test_grounding_mcp.py` (fake OpenEnv server, in-memory MCP client)
  - lists `start_episode`, `read_state` and the server's tools with their schemas
  - a server tool call reaches the fake server after `start_episode`; a call before it is an error
  - a rejected reset comes back as `isError`
  - limits apply; after the hard stop the log says `limit` and later calls are refused
  - an environment error sets `environment_error`
  - the log is written after each call, and on exit with the episode released
  - `load_openenv_server`: missing project file, missing server
- `dev/test_ground_cases.py`
  - `compose_guidance`: all parts in order; brief and data guide left out when empty
  - `prepare` with stubbed batch planner, simulated-user client and API key against the fake server
    with a `/schema` route: writes `schema.json`, `metadata.json`, `brief.txt`, `guidance.txt`,
    `plan.json`, `users.json`; chunked generation with plan-relative `scenario_index`; the
    guidance carries the brief and the data guide
  - `load_prepared_cases`: joins users to plan prompts; `--cases` subset
  - `parse_grounding_result`: plain JSON, fenced JSON, prose around the object, invalid
  - `ground --engine claude` with a stub `claude` runner that writes the MCP log and returns a fixed
    reply: grounded outcome takes `openenv_reset` from the log, not the reply; argv carries the
    model, MCP config, strict config, no built-in tools, allowed tools and system prompt; MCP config
    points at `grounding_mcp.py` with the case's log path
  - drop reply, limit stop, timeout → `limit` drop, invalid reply retried once via resume then
    `invalid_output`, retry that succeeds, environment error → failed case and exit 1
  - `summary.json` counts, drops by reason, reset kwargs, usage; `outcomes.json` contents
  - `--engine kiln` exits 2 with the not-implemented message and writes nothing
  - `run_claude` against a small fake `claude` script: parses the JSON reply, raises on a non-zero
    exit and on `is_error`, kills the process on timeout
