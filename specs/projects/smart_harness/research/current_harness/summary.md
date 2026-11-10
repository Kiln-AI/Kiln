# Research: How the Kiln Harness Works Today

A map of the code this project touches, made 2026-11-09/10 by reading the repo at `57c7c126`. Paths are relative to `libs/core/kiln_ai/` unless they start with another top-level folder. Line numbers will drift; re-check before relying on them.

## 1. One user message is one `invoke`

- `BaseAdapter.invoke` (`adapters/model_adapters/base_adapter.py:210`) → `invoke_returning_run_output` (:369) → `_run_returning_run_output` (:222) → the adapter's `_run`.
- Each call saves one new `TaskRun`. A follow-up message is a new `invoke` with `prior_trace` set to the parent run's trace; the new run links back with `parent_task_run_id` (`datamodel/task_run.py:126`). The server does this in `libs/server/kiln_server/run_api.py:788-815`.
- There is no session object and no turn counter. The only "first message" signal inside the adapter is `prior_trace is None`. Turn indexes are computed outside it (the server walks the parent chain; the eval runner counts user messages).
- `Task.turn_mode` is `single_turn` or `multiturn`. Multiturn tasks cannot have input or output schemas (`datamodel/task.py:184-203`).

## 2. The tool loop, and where it is duplicated

- `LiteLlmAdapter._run` (`adapters/model_adapters/litellm_adapter.py:415`) loops over "formatter turns" (two for chain-of-thought prompts). Each calls `_run_model_turn` (:282), which holds the tool loop: build kwargs → `litellm.acompletion` → append the assistant message → `process_tool_calls` (:1026) → repeat, up to 100 rounds.
- The streaming path repeats the same two loops in `adapters/model_adapters/adapter_stream.py` (`__aiter__` :138, `_stream_model_turn` :209). It reuses `process_tool_calls` but nothing else. Anything added to the loop must be added in both places, or the loops must be unified first.
- All tool calls go through `process_tool_calls` / `_run_tool_call` (:1026-1152). Results pass through unchanged. There is no generic size limit on tool results.
- `return_on_tool_call` ends the run early with the tool calls pending (:347-366). The caller runs the tools and resumes by sending tool results with `tool_call_id` plus the prior trace (`adapters/chat/chat_formatter.py:278-355`). This is an existing path where the model is called right after tool results that the harness did not run itself.

## 3. Run config and per-call settings

- `KilnAgentRunConfigProperties` (`datamodel/run_config.py:48-110`): `model_name`, `model_provider_name`, `prompt_id`, `top_p`, `temperature`, `structured_output_mode`, `thinking_level`, `tools_config`, `input_transform`. A second variant, `McpRunConfigProperties`, runs a whole task as one MCP tool call with no LLM.
- `input_transform` (a Jinja template applied to the input before the model sees it) is the only existing pre-model step configured on the run config.
- The run config is fixed in the adapter constructor. `invoke` takes no overrides. The provider, the LiteLLM model id and the tool list are cached on the adapter instance. Temperature, top_p and thinking level are re-read from `self.run_config` on each LLM call (`litellm_adapter.py:705, 869-878`).
- Thinking level is applied in `build_extra_body` (`litellm_adapter.py:705-810`) from the provider's `available_thinking_levels` and several provider flags.
- Each run stores a snapshot of its run config in `output.source.run_config`.

## 4. What a run records

- `TaskRun`: `input`, `output` (with a `DataSource`), `intermediate_outputs: Dict[str, str]`, `usage`, `cumulative_usage`, `trace`, `parent_task_run_id`.
- `trace` is a list of OpenAI-format messages plus Kiln-only fields (`latency_ms`, `usage`, `reasoning_content` on assistant messages; `is_error`, `error_message`, `kiln_task_tool_data` on tool messages; `utils/open_ai_types.py:47-131`). The Kiln-only fields are stripped before the provider call.
- Two things constrain an answer that did not come from the LLM:
  - A synthetic `DataSource` requires `model_name`, `model_provider` and `adapter_name` (`datamodel/task_output.py:246-275`).
  - For reasoning-capable providers, a run with no reasoning and no tool messages raises (`base_adapter.py:308-324`).
- Existing non-LLM precedents: `MCPAdapter` (source type `tool_call`, no usage) and `JevAdapter` (writes a system/user/assistant trace itself).

## 5. Hooks today

- None. There is no middleware, hook or callback around model calls or tool calls in the adapters.
- The injection points that exist: `AdapterConfig` (`base_adapter.py:78-135`: `allow_saving`, `return_on_tool_call`, `unmanaged_tools`, `automatic_prompt_caching`, …) and overridable methods (`build_completion_kwargs`, `build_extra_body`, `process_tool_calls`, `_run_tool_call`).
- Prompt caching (`automatic_prompt_caching`) is only turned on by the synthetic-user runner and eval drive, not by the server run endpoint.

## 6. Jev (decision model) integration

- `adapter_for_task` (`adapters/adapter_registry.py:225-264`) picks `JevAdapter` or `LiteLlmAdapter` from the model entry's `adapter` field. One model is listed: "Jev 1.13" on provider `typesafe`.
- `JevAdapter` overrides only `_run` (`adapters/model_adapters/jev_adapter.py:80-175`). It rejects any `prior_trace` ("Jev only supports single-turn runs"), tools, skills, and tasks with no output schema. Streaming is not implemented.
- The state sent to Jev is `{"task_instructions": <system prompt>, "input": <task input>}`.
- `adapters/jev/jev_jsonschema/` maps a flat object schema to one Jev question per property, all in one request:
  - string or integer enum → choice (up to 255 options)
  - boolean → noul
  - number 0–1 → noul
  - integer range of 2–10 values → score
  - Nested objects, arrays, free strings, `anyOf`/`oneOf`/`$ref` are rejected.
- Probabilities and confidence reach calling code only as two JSON-encoded strings in `intermediate_outputs`: `jev_probabilities` (`{property: {value: probability}}`) and `jev_confidence`. A typed `RunOutput.answer_probabilities` field was planned (Jev project Phase 9) and not built.
- No other decision-model API is supported (no generic `/v1/systemone` server, no OpenAI Decisions).

## 7. Code tools and the sandbox

- `CodeTool` (`datamodel/code_tool.py:39-80`): `tool_function_name`, `tool_description`, `parameters_schema`, `code` (stored as a sibling `tool.py`), `timeout_seconds`, `tool_allowlist`. Functional fields are immutable after create; a change is a new tool with a new ID.
- Code runs in a local `multiprocessing` spawn child (`tools/sandbox_bridge.py:477-555`, `sandbox/worker.py`). The entry point is a module-level `run(**kwargs)`. Return values: `str` as-is; dict/list/number/bool/None JSON-encoded.
- The child can call the tools on its allowlist through `kiln.tools.<name>(...)`. Those calls run in the parent process with the caller's `ToolCallContext`. Nesting is capped at depth 10; 16 top-level runs at once.
- Code tools are desktop only. `specs/projects/code_tools/project_overview.md:24,73` says "Desktop-only, forever… No server execution path" and "Server-side execution (never)". Saving or testing new code needs a project trust check.
- Code judges (`CodeEvalProperties`, `datamodel/eval.py:276-290`) share the same sandbox.
- A pytest shim (`tool_testing/`) lets authors unit-test code that calls other tools.
- **Measured start-up cost (this container, Linux, 4 cores, 2026-11-10):** one trivial code run through `run_bridged_child` took 212 ms the first time and a median of 76 ms after that (range 69–109 ms). Four in parallel finished in 79 ms total. macOS and Windows were not measured and are usually slower to spawn.

## 8. Tasks as tools (subagents)

- `KilnTaskTool` (`tools/kiln_task_tool.py:22-167`) wraps a task plus a saved run config. `run()` builds an adapter and calls `invoke`. The inner run is saved to the inner task's dataset when saving is allowed, tagged `tool_call`.
- The parent trace links to it with `kiln_task_tool_data = "project:::tool_id:::task_id:::run_id"` on the tool message.
- Tool ID kinds (`datamodel/tool_id.py:28-48`): built-ins, `mcp::remote::`, `mcp::local::`, `kiln_task::`, `kiln_tool::rag::`, `kiln_tool::code::`, `kiln_tool::memory::`, `kiln_tool::skill::`, `kiln_unmanaged::` (passed in by library users through `AdapterConfig.unmanaged_tools`), `kiln_tool::world::`.

## 9. Streaming events

- AI SDK stream events (`adapters/model_adapters/stream_events.py`): `start`, `start-step`, `text-*`, `reasoning-*`, `tool-input-*`, `tool-output-available`, `tool-output-error`, `finish-step`, `finish`. Every event carries a `kiln_metadata` dict.
- The streaming methods have no callers in this repo outside tests; the server run endpoint uses `invoke`.
