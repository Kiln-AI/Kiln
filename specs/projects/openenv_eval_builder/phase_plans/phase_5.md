---
status: complete
---

# Phase 5: Studio server for grounded cases

## Overview

The studio server routes the builder UI (phase 6) calls for a multi-turn build on an OpenEnv run
config. Judge authoring and clarifying questions read OpenEnv tools from the server's tool list
instead of raising outside an episode. A new route returns the reset arguments brief for the
planner. A new streamed route grounds the planned cases. The review pipeline and the re-judge
stream judge a grounded case against its judge guidance and the episode's final state, and the
claim builder sees the guidance as part of the rubric. Save writes `openenv_reset` and the judge
guidance on each minted input, the guidance as `reference` on each golden leaf, the server on the
`Eval`, and the grounded judge template with `reference_keys=["judge_guidance"]`. Everything is
stubbed in tests: the fake OpenEnv server, and mocked or scripted models.

## Steps

1. New `libs/core/kiln_ai/tools/run_config_tools.py`, the tools a run config lists, read without
   an episode:

   ```python
   async def served_openenv_tools(
       project: Project, tool_ids: Iterable[str], session_manager: OpenEnvSessionManager
   ) -> dict[str, OpenEnvTool]
   async def tool_definitions_without_episode(
       task: Task, tool_ids: Iterable[str], session_manager: OpenEnvSessionManager
   ) -> list[ToolCallDefinition]
   ```

   `served_openenv_tools` maps each OpenEnv tool id to the tool its server lists, one
   `list_tools` per server. A missing server record or a tool the server doesn't serve is a
   `ValueError`; an unreachable server raises the session manager's `OpenEnvError`.
   `tool_definitions_without_episode` keeps the ids' order, skips skill ids, takes OpenEnv tools
   from `served_openenv_tools` (`openenv_toolcall_definition`) and every other tool from
   `tool_from_id(...).toolcall_definition()`.

2. `libs/core/kiln_ai/synthetic_user/runner.py`: `CaseCompletedEvent.openenv_episode:
   OpenEnvEpisode | None = None`, set to the leaf's ended episode for a grounded case, so the
   pipeline judge has the final state without reloading the leaf.
   `multiturn_sdg_api._event_to_payload` leaves it off the wire (the state can be large and the
   client never reads it).

3. `studio_server/utils/copilot_utils.py`: `task_capabilities_for_task(task, run_config_id,
   openenv_session_manager=None)` (default `shared_session_manager()`) passes the manager to
   `_collect_task_capabilities`, which reads OpenEnv ids through `served_openenv_tools` and the
   rest through `tool_from_id` as today. An unreachable server still lands in the existing 500,
   whose message carries the session manager's error with the URL.

4. `studio_server/openenv_server_api.py`:
   `GET /api/projects/{project_id}/openenv_servers/{openenv_server_id}/reset_arguments_brief`
   returns `OpenEnvServerResetArgumentsBriefResponse {brief: str | None}` from
   `reset_arguments_brief(await shared_session_manager().reset_schema(server))`. 404 for an
   unknown server, 400 without a url, 502 when unreachable (as the reset schema route). `ALLOW_AGENT`.

5. Grounding stream.
   - `api_models/eval_builder_models.py`: `GroundingModelApi {model_name, model_provider}`,
     `GroundCaseApi {scenario_index, scenario, seed_prompt, synthetic_user_info}`, and the frames
     `GroundingStartedEvent {total}`, `CaseGroundedEvent {case_index, scenario_index, status,
     openenv_reset, seed_prompt, synthetic_user_info, judge_guidance}`, `CaseDroppedEvent
     {case_index, scenario_index, drop_reason, drop_detail}`, `GroundingFinishedEvent {grounded,
     dropped, usage, usage_complete}`, `GroundingFailedEvent {code, message}`.
   - New `studio_server/services/eval_grounding.py`: `grounding_events(...) -> AsyncIterator[str]`
     takes the loaded task, the resolved run config properties, the `OpenEnvServer`, the session
     manager, the judge model, the specification, the guide and the cases. It reads the target
     tool definitions (inside `mcp_session_scope`), runs `ground_cases` under
     `contextlib.aclosing`, and maps its progress to the frames, rendering `judge_guidance` with
     `render_judge_guidance`. `GroundingCaseError` or any `OpenEnvError` becomes
     `grounding_failed`: `code "openenv_unreachable"` with the server's URL when the cause is an
     `OpenEnvError`, else `"grounding_error"` with the unwrapped provider error; anything else is
     `"internal_error"`. Then the `data: complete` terminator. Plus
     `resolve_grounding_server(project, tool_ids) -> OpenEnvServer`, raising
     `NoGroundingServerError` (a domain error) when the tools reach none, several, or a missing
     record.
   - `eval_builder_api.py`: `GroundCasesRequest(TargetRunConfigFields)` with `judge_model`,
     `specification`, `synthetic_user_guide`, `cases` (1 to `NUM_CASES_MAX`), extra forbidden.
     `POST /api/projects/{project_id}/tasks/{task_id}/eval_builder/ground_cases`, `no_write_lock`,
     `CancellableStreamingResponse`, approval policy. Before the stream: task, `guard_multiturn`,
     `resolve_target_run_config`, then the server (400 `no_openenv_server` from the domain error).

6. Judge.
   - `eval_builder_utils.build_judge_prompt_template(judge_prompt, multi_turn, grounded=False)`:
     when grounded, before the transcript, a `<judge_guidance>{{ reference_data.judge_guidance
     }}</judge_guidance>` block and a `{% if openenv_episode and openenv_episode.final_state %}`
     `<final_state>` block (`tojson`), and text telling the judge to grade the end result and
     what the agent told the user against the guidance, and to fail anything under "Must not
     happen".
   - `build_transient_judge_eval_config(task, judge, multi_turn, grounded=False)` sets
     `reference_keys=["judge_guidance"]` when grounded.
   - `run_judge_for_trace(..., judge_guidance=None, openenv_episode=None)`: grounded when
     `judge_guidance` is set; passes `reference_data={"judge_guidance": ...}` and the episode.
   - `JudgeStreamBase._judge_case` takes the case's guidance and episode and forwards them.
     `MultiTurnPipelineRun` reads them from the case and `CaseCompletedEvent.openenv_episode`.
     `JudgeTracesRequest.judge_guidance: list[str | None] | None` (same length as
     `leaf_run_ids`, validated); `JudgeTracesRun` passes each with the leaf's
     `openenv_episode`.
   - `BuildClaimsApiInput.judge_guidance: str | None`; `build_claims_for_trace(...,
     judge_guidance=None)` appends it to `eval_rubric` in a `<judge_guidance>` block, since that
     is part of what the judge ran with and kiln_server is unchanged.

7. Save.
   - `DrivenSyntheticCaseApi` gains `openenv_reset: OpenEnvReset | None` and
     `judge_guidance: str | None`. `MultiTurnSaveInfo` gains `openenv_server_id: str | None`.
   - `copilot_utils.validate_grounded_cases(save_info)`: with a server id, every case has both
     fields and its reset names that server; without one, no case has either. Mismatch is a 400.
     The route also 400s when the server id names no server in the project.
   - `build_multi_turn_eval_inputs` writes `openenv_reset` and
     `reference={"judge_guidance": ...}` when the case has them.
   - `copilot_utils.write_golden_references(leaves, references_by_leaf_id, written_out)` sets
     `reference` on each reviewed leaf, recording the previous value;
     `restore_golden_references(written)` rolls back. `persist_spec_save` takes
     `golden_references` and calls both.
   - `create_spec_with_copilot`: `eval.openenv_server_id` from the save info; the saved
     `LlmJudgeProperties` uses `build_judge_prompt_template(..., grounded=True)` and
     `reference_keys=["judge_guidance"]` on a grounded save.

8. Regenerate the OpenAPI client (`app/web_ui/src/lib/generate_schema.sh`) and the agent policy
   annotations for the two new routes.

## Tests

- `run_config_tools`: OpenEnv ids against the fake server, one list per server, no episode left
  open; a tool the server doesn't serve and a missing record raise `ValueError`; unreachable raises
  `OpenEnvError`; definitions keep order, skip skills, and resolve a non-OpenEnv tool.
- `_collect_task_capabilities` with an OpenEnv run config against the fake server; unreachable
  server gives the existing 500 with the URL.
- `reset_arguments_brief` route: brief text, null without a schema, 404, 502 unreachable.
- `ground_cases` route (stubbed `ground_cases`): frames in order for grounded and dropped cases,
  `judge_guidance` rendered, `grounding_failed` for an `OpenEnvError` cause and for a provider
  error, 400 for a run config with no OpenEnv server, 422 for an extra field.
- `grounding_events` with the real `ground_cases`, a scripted model and the fake server: a client
  abort (closing the stream mid-case) leaves no open session.
- Judge template with and without `grounded`; transient judge has `reference_keys` when grounded;
  `run_judge_for_trace` passes the guidance and the episode; pipeline and re-judge pass each
  case's guidance; re-judge rejects a guidance list of the wrong length; claims rubric includes
  the guidance.
- `CaseCompletedEvent` carries the ended episode for a grounded case; the SSE payload leaves it out.
- Save: grounded inputs carry `openenv_reset` and `reference`, golden leaves carry `reference`,
  `Eval.openenv_server_id` set, judge saved with `reference_keys`; mismatched server, a case
  missing its guidance, a grounded case without a server id, and an unknown server are 400s; a
  failed save restores the golden leaves' references.
