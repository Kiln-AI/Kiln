---
status: complete
---

# Phase 3: Routing and the Jev adapter

## Overview

Make a Kiln task runnable against Jev. Today every `kiln_agent` run config routes to
`LiteLlmAdapter`; this phase adds a routing decision carried on the model entry itself
(`KilnModelProvider.adapter`), dispatches on it in `adapter_for_task`, and adds
`JevAdapter`, the first non-LiteLLM `kiln_agent` adapter. `JevAdapter` is the first
consumer of Phase 2's `jev_jsonschema` module and `JevClient`.

The adapter implements only `adapter_name()` and `_run()`. Input validation, input
transforms, output parsing and schema validation, run generation, saving and
`KilnRunError` wrapping are all inherited from `BaseAdapter`, so a mapping bug surfaces
as the standard output-schema validation error rather than saving bad data.

The Jev model entry lands with a removal `TODO` — Phase 6 removes it before the PR opens
and Phase 7 re-adds it after a client release. Tests must therefore never depend on the
entry existing.

## Steps

1. `libs/core/kiln_ai/adapters/ml_model_list.py`:

   - New enum beside `ModelParserID` / `ModelFormatterID`:

     ```python
     class ModelAdapterId(str, Enum):
         litellm = "litellm"
         jev = "jev"
     ```

   - `KilnModelProvider` gains `adapter: ModelAdapterId = ModelAdapterId.litellm` with a
     docstring line in the class attribute list.
   - `ModelFamily.jev = "jev"` and `ModelName.jev_1_13 = "jev_1_13"`.
   - Append the Jev `KilnModel` entry at the end of `built_in_models`, preceded by the
     removal `TODO` comment the plan requires (`supports_structured_output=True`,
     `supports_data_gen=False`, `supports_logprobs=False`,
     `supports_function_calling=False`, `structured_output_mode=json_schema`,
     `adapter=ModelAdapterId.jev`, `model_id="jev-1.13.0"`).

2. `libs/core/kiln_ai/adapters/provider_tools.py`:

   ```python
   def default_adapter_for_provider(provider_name: ModelProviderName) -> ModelAdapterId:
       return (
           ModelAdapterId.jev
           if provider_name == ModelProviderName.typesafe
           else ModelAdapterId.litellm
       )
   ```

   Used by `user_model_to_provider` (in `base_kwargs`) and by the custom-model fallback at
   the bottom of `kiln_model_provider_from`. `adapter` joins `name`/`model_id` in the set of
   fields a `UserModelEntry` override cannot set: routing follows the provider.

3. `libs/core/kiln_ai/adapters/adapter_registry.py` — in the `kiln_agent` case, resolve the
   provider with `kiln_model_provider_from(model_name, model_provider_name)` and match on
   `model_provider.adapter`: `jev` → `JevAdapter`, `litellm` → the existing
   `LiteLlmAdapter` construction, `_` → `raise_exhaustive_enum_error`.

4. New `libs/core/kiln_ai/adapters/model_adapters/jev_adapter.py`:

   ```python
   JEV_ADAPTER_NAME = "kiln_jev_adapter"
   ERROR_PREFIX = "Jev (TypeSafe AI) can't run this task:"
   SUPPORTED_SHAPES = (
       "Supported property shapes: a string enum, an integer enum, a boolean, an integer "
       "with minimum and maximum spanning 2 to 10 values, or a number with minimum 0 and "
       "maximum 1."
   )

   def build_jev_state(system_prompt: str, input: InputType) -> dict[str, Any]:
       return {"task_instructions": system_prompt, "input": input}

   class JevAdapter(BaseAdapter):
       def __init__(self, kiln_task, run_config, base_adapter_config=None, client=None): ...
       def adapter_name(self) -> str: ...
       async def _run(self, input, trace_ref, prior_trace=None) -> Tuple[RunOutput, Usage | None]: ...
   ```

   `_run`, in order:

   1. `prior_trace` → `ValueError(f"{ERROR_PREFIX} Jev only supports single-turn runs.")`
   2. Tools on the run config or `base_adapter_config.unmanaged_tools` →
      `ValueError(f"{ERROR_PREFIX} Jev does not support tools. Remove tools from the run config.")`
   3. No output schema → `ValueError(f"{ERROR_PREFIX} Jev only supports tasks with a structured output schema. Add an output JSON schema whose properties are enums, booleans, bounded integers, or numbers from 0 to 1.")`
   4. `JSONSchema2Jev().convert(schema)`; `IncompatibleSchemaError` → `ValueError`. A
      schema-level failure (the module's `ROOT_KEY`) reads
      `f"{ERROR_PREFIX} the output {reason}."`; property failures read
      `f"{ERROR_PREFIX} the output schema has properties Jev can't answer:"` + one
      `- key: reason` line each + `SUPPORTED_SHAPES`.
   5. `system_prompt = self.prompt_builder.build_prompt(include_json_instructions=False, skills=self._resolve_skills())`. Never calls `chain_of_thought_prompt()`.
   6. `state = build_jev_state(system_prompt, input)`.
   7. `client = self._client or JevClient(api_key=Config.shared().typesafe_api_key)`.
   8. `model_id = self.model_provider().model_id`; `None` → `ValueError`.
   9. `time.perf_counter()` around `await client.system_one(question_set.request(state=state, model=model_id))`.
   10. `decoded = JevResult2JsonSchema().convert(question_set, response.answers)`.
   11. `trace_ref[:] = [system, user, assistant]`, the assistant message carrying
       `MessageUsage` so `MessageUsage.from_trace` sums it; the user message built with
       `format_user_message(input)`.
   12. `Usage(input_tokens, output_tokens, total_tokens, total_llm_latency_ms)`, `cost=None`.
   13. `RunOutput(output=decoded.output, intermediate_outputs={"jev_probabilities": ..., "jev_confidence": ...}, trace=trace_ref)`. Probabilities rounded to 4 decimal
       places; both values JSON-encoded strings.

   Steps 1 to 4 fail before any network call. Streaming is not overridden.

5. `libs/core/kiln_ai/adapters/jev/jev_jsonschema/__init__.py` re-exports `ROOT_KEY` so the
   adapter can tell a schema-level failure from a property failure through the module's
   public API.

## Tests

`model_adapters/test_jev_adapter.py` (new):

- `test_rejects_prior_trace`, `test_rejects_tools` (run-config tools and unmanaged tools),
  `test_rejects_task_without_output_schema` — each asserts the prefix and message.
- `test_preflight_error_order`: a run config that trips several rules reports the first.
- `test_incompatible_schema_lists_every_failing_property`: message names every bad key and
  ends with the supported-shapes sentence; no network call made.
- `test_schema_level_failure_message`: empty `properties` reads "the output schema has no
  properties."
- `test_state_for_string_input` / `test_state_for_dict_input`: `task_instructions` plus the
  input passed through unchanged.
- `test_prompt_content_reaches_state`: a few-shot prompt builder's examples land in
  `task_instructions`, and JSON formatting instructions do not.
- `test_request_shape`: model id, one question per property, schema property order.
- `test_trace_shape`: three messages, roles, the assistant message's JSON content and usage.
- `test_usage_and_latency`: token counts summed, `total_llm_latency_ms` populated,
  `cost is None`.
- `test_intermediate_outputs_round_trip`: both keys parse back to the expected dicts,
  probabilities rounded to 4 places, `jev_confidence` null for noul kinds.
- `test_top_logprobs_ignored`: `AdapterConfig(top_logprobs=10)` changes nothing.
- `test_end_to_end_through_invoke`: a task with all five mapped kinds runs through
  `BaseAdapter.invoke`, output validates, run is not saved, `adapter_name` is recorded.
- `test_mapping_bug_rejected_by_base_validation`: a decoder that returns an out-of-schema
  value raises the base class's output-schema error.
- `test_api_error_propagates`: `JevApiError` from the client reaches the caller wrapped in
  `KilnRunError` with its message intact.

`test_adapter_registry.py`:

- `mock_config` gains `typesafe_api_key`.
- a provider entry with `adapter=jev` routes to `JevAdapter`; the default routes to
  `LiteLlmAdapter`; a user-registry model under TypeSafe routes to `JevAdapter`.

`test_ml_model_list.py`:

- every built-in provider entry has `adapter == litellm` except TypeSafe entries, which are
  `jev`. Written so it still passes once Phase 6 removes the entry.

`test_provider_tools.py`:

- `default_adapter_for_provider` returns `jev` only for TypeSafe.
- a custom (untested) model under TypeSafe gets `adapter=jev`; under another provider,
  `litellm`.
- a user model entry cannot override `adapter`.
