---
status: complete
---

# Phase 3: The real agent

## Overview

The grounding agent on a Kiln model: `ground_case` runs one case through Kiln's adapter with the
grounding session's tools, and `ground_cases` runs many through `AsyncJobRunner` and streams
progress. The prototype command's `--engine kiln` calls `ground_cases`, so the checkpoint after
this phase can measure the agent on the models a user would pick. The final answer comes back in
one of two styles, chosen per run: structured output (a JSON response format) or a
`submit_result` tool. The prompt gains the two rules from the phase 2 checkpoint. No test makes a
paid call: the model is stubbed at `acompletion_checking_response`, against the fake OpenEnv
server.

Constraints found while reading the adapter, which shape the steps below:

- With tools present, a tool-call structured output mode is refused ("Function calling/tools
  can't be used as the JSON response format if you're also using tools"), and `default` resolves
  to tool calls for most providers. Structured output uses the model's listed mode with
  `function_calling` and `function_calling_weak` disallowed and `json_schema` as the fallback, as
  the v2 LLM judge does.
- Strict `json_schema` closes every object (`additionalProperties: false`), which would force
  `Evidence.args` to `{}`. The schema the model sees carries `args` as a JSON string; Kiln parses
  it back to an object.
- The adapter turns any non-`ToolCallError` exception from a tool into an error message for the
  model, unless it is run-ending. `GroundingLimitReached` is not, so the run would go on. The
  session records the first such stop and `ground_case` cancels the run when it happens.
- `asyncio.timeout` is 3.11+; `libs/core` supports 3.10, so the time limit uses
  `asyncio.wait_for` and catches `asyncio.TimeoutError`.

## Steps

1. `libs/core/kiln_ai/eval_grounding/session.py`
   - `SUBMIT_RESULT_TOOL = "submit_result"`, reserved with the session tool names, so a server
     tool by that name is exposed as `env_submit_result`.
   - Stop tracking: every tool's run is wrapped so an exception other than `ToolCallError`
     (`GroundingLimitReached`, or an `OpenEnvError` not shown to the model) is recorded once.
     `stop_error -> BaseException | None` and `async def wait_until_stopped() -> None`.
   - `async def close_tools() -> None`: releases the current episode and refuses every later call
     with `TOOLS_CLOSED_MESSAGE` ("Your environment work is over. Don't call any more tools:
     return your result now."). Refusals count toward `calls_after_limit` like limit refusals, so
     a model that keeps calling still hits the hard stop. `last_reset` is unchanged.

2. `libs/core/kiln_ai/eval_grounding/models.py`
   - `result_json_schema(*, args_as_json_string: bool) -> dict[str, Any]`: the schema of
     `GroundingResult` the model sees, written out (no `$ref`), every property listed in
     `required`, nullables as `["<type>", "null"]` or `anyOf` with null. With
     `args_as_json_string`, `evidence.args` is a string.
   - `GroundingResult.from_model_output(data: dict[str, Any], *, args_as_json_string: bool)`:
     decodes each `evidence.args` string to an object (a string that is not a JSON object raises
     `ValueError`), then validates.

3. `libs/core/kiln_ai/eval_grounding/prompt.py`
   - `AnswerStyle = Literal["reply_json", "structured_output", "submit_result"]` and
     `KilnAnswerStyle = Literal["structured_output", "submit_result"]`.
   - `system_prompt(limits, time_limit_s, answer_style="reply_json")`: the template's last
     section becomes `{final_answer}`, one per style. All three show the same JSON skeleton
     (`args` as a string for `structured_output`). `reply_json` keeps today's wording, so the
     `claude` engine's prompt is unchanged apart from the two rules below. `submit_result` says
     to call the tool once, fix and call again if it reports a problem, then reply "done".
   - Rule: a case that expects the agent under test to refuse, where the server itself doesn't
     refuse or enforce it, is dropped as `unrepresentable`, with a `drop_detail` saying the server
     doesn't enforce it.
   - Rule: `must_not_happen` must not forbid the way the server records the expected change (for
     example, a server that records a delete as an update); check what the rehearsal changed.

4. `libs/core/kiln_ai/eval_grounding/agent.py` (new)

   ```python
   async def ground_case(
       case: GroundingCase,
       *,
       eval_context: EvalContext,
       openenv_server: OpenEnvServer,
       session_manager: OpenEnvSessionManager,
       server_tools: Sequence[OpenEnvTool],
       model_name: str,
       model_provider: ModelProviderName,
       target_tools: list[ToolCallDefinition],
       reset_schema: dict[str, JsonValue] | None,
       metadata: OpenEnvMetadata,
       answer_style: KilnAnswerStyle = "structured_output",
       system_prompt_text: str | None = None,
       limits: GroundingLimits = DEFAULT_LIMITS,
       time_limit_s: float = DEFAULT_TIME_LIMIT_S,
   ) -> GroundingOutcome
   ```

   `server_tools` is new against `architecture.md`: the session needs the server's tools, and
   `target_tools` is the run config's list, which in the product is not the same thing.

   - In-memory `Task` (no parent): `instruction` = the system prompt for the style;
     `output_json_schema` = `result_json_schema(args_as_json_string=True)` for
     `structured_output`, none for `submit_result`.
   - Run config: `KilnAgentRunConfigProperties(model_name, model_provider_name,
     prompt_id=SIMPLE, structured_output_mode=<as above>, tools_config=ToolsRunConfig(tools=[]))`.
   - `AdapterConfig(allow_saving=False, unmanaged_tools=session.tools() + [submit tool when that
     style], open_openenv_session=False)`.
   - `_SubmitResultTool(UnmanagedKilnTool)`: parameters = `result_json_schema(args_as_json_string=
     False)`. A valid call records the result, closes the session's tools and returns "Recorded.
     Reply with only the word done." An invalid call returns the validation error as a
     `ToolCallError`; the second invalid call records the failure. Calls after either are refused.
   - Each adapter call races `session.wait_until_stopped()`; a stop cancels the run.
   - Result handling:
     - `structured_output`: a normal run's output dict goes through `from_model_output`. A
       `KilnRunError` whose cause is the task's output not parsing or not matching its schema, or
       a `from_model_output` failure, gets one follow-up in the same trace (`prior_trace` = the
       run's trace or the error's partial trace, input = the "reply with only the result"
       message), after `session.close_tools()`. A second failure drops as `invalid_output`.
     - `submit_result`: an accepted submission is the result. Two invalid submissions drop as
       `invalid_output`. A run that ends without calling the tool gets one follow-up asking for
       it, after `close_tools()`.
     - A `GroundingLimitReached` stop is a `limit` drop with its message, unless a submission was
       already accepted. An `OpenEnvError` stop, or a `KilnRunError` whose cause is an
       `OpenEnvError`, raises that error. Other adapter errors are raised as they are.
     - `asyncio.wait_for(..., time_limit_s)`; `asyncio.TimeoutError` is a `limit` drop.
     - The outcome comes from `GroundingOutcome.from_result(result, openenv_reset=
       session.last_reset, call_log=session.call_log, usage=<summed over the calls>)`.
   - `finally: await session.close()`.

5. `libs/core/kiln_ai/eval_grounding/batch.py` (new)

   ```python
   @dataclass(frozen=True)
   class CaseGrounded:
       case_index: int
       outcome: GroundingOutcome

   @dataclass(frozen=True)
   class GroundingFinished:
       grounded: int
       dropped: int
       usage: Usage

   GroundingProgress = CaseGrounded | GroundingFinished

   async def ground_cases(
       cases: Sequence[GroundingCase],
       *,
       eval_context, openenv_server, session_manager, model_name, model_provider,
       target_tools, answer_style="structured_output", system_prompt_text=None,
       limits=DEFAULT_LIMITS, time_limit_s=DEFAULT_TIME_LIMIT_S,
       concurrency: int = CONCURRENCY,
   ) -> AsyncIterator[GroundingProgress]
   ```

   The arguments are spelled out rather than `**ground_case_kwargs`, so callers are type checked.
   Reads `reset_schema`, `metadata` and `list_tools` once, then runs `ground_case` per case
   through `AsyncJobRunner` with `concurrency`. Yields `CaseGrounded` per finished case, then
   `GroundingFinished`. A case that raises: the generator cancels the runner (whose workers'
   `ground_case` release their episodes), then re-raises the error. Closing the generator early
   cancels the rest the same way.

6. `app/desktop/studio_server/dev/ground_cases.py`
   - `--engine kiln` requires `--model` and `--provider`; `--answer-style
     structured_output|submit_result` (kiln only, default `structured_output`).
   - Engine kiln: reads the prepared inputs, lists the server's tools for `target_tools`, runs
     `ground_cases` and prints a progress line per case. Writes `system_prompt.txt`,
     `outcomes.json` and `summary.json` as the `claude` engine does, with `engine: "kiln"`, the
     model, provider and answer style. An error from `ground_cases` is printed and written as
     `summary["error"]`, naming the case that raised it and the underlying error's type;
     the outcomes so far are kept; exit 1.
   - The not-implemented constant and exit 2 go away. Module docstring updated.

## Tests

- `eval_grounding/test_session.py`
  - `close_tools`: releases the episode; later calls refused with the closed message; past
    `calls_after_limit` it raises `GroundingLimitReached`; `last_reset` kept.
  - Stop tracking: the hard stop sets `stop_error` and `wait_until_stopped` returns; a transient
    environment error sets it; a `ToolCallError` refusal does not.
  - A server tool named `submit_result` is exposed as `env_submit_result`.
- `eval_grounding/test_models.py`
  - `result_json_schema`: a full grounded result and a drop validate against it; property names
    match `GroundingResult`'s fields; with `args_as_json_string`, `args` is a string.
  - `from_model_output`: decodes args strings; rejects args that are not a JSON object; passes
    object args through when not encoded.
- `eval_grounding/test_prompt.py`
  - Each answer style's final section; the skeleton names every field in all three; the refusal
    and `must_not_happen` rules are present.
- `eval_grounding/test_agent.py` (fake server, stubbed model)
  - Structured output: grounded result takes `openenv_reset` from the last `start_episode`, not
    from the model; `evidence.args` decoded; usage summed.
  - The schema the model sees (from the adapter's `json_schema_response_format()`) keeps `args` as
    a string under strict closing.
  - Structured output mode: the provider's listed tool-call mode is swapped for `json_schema`.
  - Unparseable output retried once in the same trace (the follow-up's prior trace is the first
    run's), then grounded; twice unparseable drops `invalid_output`; the adapter's own schema
    error is retried too.
  - Tools are closed during the follow-up: a `start_episode` there is refused and the saved reset
    is the one from before.
  - Grounded with no `start_episode` becomes `invalid_output`.
  - Model drop keeps its reason and detail.
  - Limit: a model that keeps calling after the limit is stopped and drops as `limit`, and the
    model is not called again after the hard stop.
  - Timeout: drops as `limit`.
  - An environment error during a tool call is raised as the `OpenEnvError`.
  - Submit style: accepted submission grounds; the tool's parameters keep `args` as an object;
    an invalid submission gets the error back and a fixed one grounds; two invalid drop
    `invalid_output`; no submission gets one follow-up, then `invalid_output`.
  - Every exit releases the episode (the one-session server accepts a new episode).
- `eval_grounding/test_batch.py`
  - Progress per case and a final count with summed usage; reset schema, metadata and tools read
    once; concurrency bound respected; a raised error cancels the remaining cases, re-raises, and
    leaves no episode open; closing the generator early cancels the rest.
- `dev/test_ground_cases.py`
  - `--engine kiln` with `ground_cases` stubbed: writes outcomes and summary with engine, model,
    provider and answer style; passes the prepared inputs through.
  - `--engine kiln` needs `--model` and `--provider`; `--answer-style` refused for `claude`.
  - An error from `ground_cases` keeps earlier outcomes, records it as `summary["error"]`,
    exits 1.
