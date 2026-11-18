---
status: complete
---

# Phase 1: Foundations, no model calls

## Overview

The pieces the grounding agent and the prototype command stand on, with no model call anywhere:
the server's `/metadata` with its readme, the planner's reset-arguments brief built from the reset
schema, and the `eval_grounding` package's models, prompt and `GroundingSession` (the agent's
tools, limits, call log and episode lifecycle). Everything is tested against the fake OpenEnv
server in `kiln_ai/openenv/testing.py`. `agent.py` and `batch.py` come in phase 3.

## Steps

1. `libs/core/kiln_ai/openenv/session_manager.py`
   - Add a frozen dataclass `OpenEnvMetadata(name: str, version: str | None, description: str |
     None, readme_content: str | None)`. `version` is optional because Kiln already accepts a
     server whose `/metadata` has none.
   - Extract `_read_metadata(openenv_server, base_url) -> dict[str, Any]` from `_connect_remote`
     (same transport, timeout and error messages); `_connect_remote` uses it.
   - Add `async def metadata(self, openenv_server) -> OpenEnvMetadata`: reads `/metadata` fresh,
     uncached, with the no-url check. Non-string `description` / `readme_content` become `None`.

2. `libs/core/kiln_ai/tools/openenv_tool.py`
   - Extract `tool_call_result(outcome: ToolCallOutcome) -> ToolCallResult` from
     `OpenEnvToolProxy.run` so the grounding session renders server tool results the same way.

3. `libs/core/kiln_ai/openenv/reset_schema_brief.py` (new)
   - `ResetArgument` frozen dataclass: `path`, `description`, `values`.
   - `reset_arguments(schema) -> list[ResetArgument]`: walks `properties` in order, skips top-level
     `seed` / `episode_id`, resolves local `#/$defs/` refs (non-local, missing or cyclic refs are a
     leaf), unwraps a single-non-null `anyOf`, lists a multi-member `anyOf` with no values, walks
     objects with `properties` into dotted paths (the object listed too when described), caps depth
     at 4, reads `values` from `enum` only. An outer description wins over the resolved one.
   - `reset_arguments_brief(schema) -> str | None`: `RESET_ARGUMENTS_FRAMING` constant (from the
     plan page's "Prompt changes" tab) then an `<openenv_server_reset_arguments>` block with one
     `- path: description` line per argument and `Values: a | b` under it. `None` for no schema or
     no arguments.

4. `libs/core/kiln_ai/eval_grounding/__init__.py` (new, docstring only).

5. `libs/core/kiln_ai/eval_grounding/models.py` (new)
   - `GroundingCase`, `Evidence`, `Fact`, `GroundedReference`, `DropReason` (str Enum: `no_fit`,
     `unrepresentable`, `rehearsal_failed`, `limit`, `invalid_output`), `LoggedCall(tool, args,
     output, is_error, episode_id)`.
   - `GroundingResult`: what the model returns (`status`, `drop_reason` limited to the three
     model-chosen reasons, `drop_detail`, `seed_prompt`, `synthetic_user_info`, `reference`), with a
     validator: grounded needs the user fields and reference; dropped needs reason and detail; a
     grounded `synthetic_user_info` must parse with `parse_synthetic_user_info`.
   - `GroundingOutcome` as in the architecture, with the same status invariants (grounded also
     needs `openenv_reset`).

6. `libs/core/kiln_ai/eval_grounding/prompt.py` (new)
   - `SYSTEM_PROMPT`: the plan page's grounding prompt, adapted to the architecture: tools are
     `start_episode`, `read_state` and the server's own; `openenv_reset` is taken from the last
     `start_episode`, so the model is told to finish in the environment it grounded in; the return
     JSON is `GroundingResult`'s shape.
   - `case_message(case, *, reset_schema, readme, target_tools) -> str`: tagged sections
     `<case_scenario>`, `<simulated_user>` (seed prompt + the tagged blob), `<reset_schema>` (JSON,
     or a line saying there is none and to reset with `{}`), `<server_readme>`, `<target_tools>`
     (name and description per tool).

7. `libs/core/kiln_ai/eval_grounding/session.py` (new)
   - `GroundingLimits` frozen dataclass (40 tool calls, 10 resets, 5 calls after a limit).
   - `GroundingLimitReached(Exception)`.
   - `GroundingSession(openenv_server, session_manager, server_tools, limits=..., 
     transient_retry_delays_s=(1.0, 3.0))`:
     - `tools() -> list[KilnToolInterface]`: `start_episode`, `read_state`, one per server tool
       (`env_` prefix on a name collision), as `UnmanagedKilnTool` subclasses.
     - An `asyncio.Lock` serializes calls, since the adapter runs a turn's tool calls concurrently.
     - Limits as in the architecture; past a limit every tool refuses with "return your result
       now"; after five such refusals the next call raises `GroundingLimitReached`.
     - `start_episode` releases the current episode first, retries `OpenEnvTransientError` with
       backoff then raises, turns a rejection into a `ToolCallError`, records `last_reset`.
     - Server tools and `read_state` refuse before any episode; a session-ending error clears the
       episode and later calls say "The environment closed. Call start_episode again."; a transient
       error clears the episode and is raised (the session is gone, so a retry can't succeed).
     - Every call is logged. `close()` releases the current episode; idempotent.

## Tests

- `openenv/test_reset_schema_brief.py`
  - properties in order; `seed` and `episode_id` skipped at the top level only
  - `$ref` into `$defs` resolved, outer description wins; missing / non-local / cyclic ref is a leaf
  - `anyOf` with null unwrapped (values from the enum member); multi-member `anyOf` has no values
  - nested object paths; described object listed, undescribed object not; depth cap at 4
  - `const` / `oneOf` not read as values
  - `None` schema, no properties, only skipped properties → `reset_arguments_brief` returns `None`
  - a Seahaven-shaped schema (fixture enum with listing, `startup.acting_user`, `setup_sql`,
    `clock_mode` via `$ref`) renders the expected brief, starting with the framing constant
- `openenv/test_session_manager.py`
  - `metadata()` with readme and description; without them; non-string values become `None`;
    unreachable server and missing url raise `OpenEnvError`
- `tools/test_openenv_tool.py`: existing proxy tests still pass through the extracted helper
- `eval_grounding/test_models.py`
  - grounded / dropped invariants on `GroundingResult` and `GroundingOutcome`; model drop reasons
    exclude `limit` / `invalid_output`; unparseable `synthetic_user_info` rejected; reference
    round-trips through `model_dump()`
- `eval_grounding/test_prompt.py`
  - case message carries each section; no-schema line; empty readme; target tools listed
  - system prompt names the tools and every `GroundingResult` field
- `eval_grounding/test_session.py` (fake server)
  - tool list: names, server schemas, collision renamed to `env_<name>`, server without properties
    gets an empty object schema
  - server tool and `read_state` before `start_episode` refused
  - `start_episode` releases the previous episode (works on a one-session server)
  - rejected reset is a tool error; `last_reset` keeps the last successful reset
  - server tool result and server tool error rendered like the proxy
  - `read_state` returns the state JSON
  - call limit, reset limit, refusals after the limit, then `GroundingLimitReached`
  - transient capacity error retried then raised
  - session-ending error clears the episode, next call asks for `start_episode`
  - concurrent calls serialize
  - call log contents; `close()` releases and is idempotent (one-session server accepts a new one)
