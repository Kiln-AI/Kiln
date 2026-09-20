---
status: complete
---

# Architecture: Jev Provider (TypeSafe AI System One)

Two-phase spec: this doc covers routing, the adapter, provider plumbing, evals, errors, and testing. Two components get their own docs because they carry most of the logic and tests:

- `components/jev_jsonschema.md`: the reusable module: JSON Schema → Jev questions (`JSONSchema2Jev`), Jev answers → JSON output plus probabilities and confidence (`JevResult2JsonSchema`), and the System One wire models.
- `components/jev_client.md`: the HTTP client and error mapping.

## Module layout

```
libs/core/kiln_ai/adapters/jev/
  __init__.py
  jev_client.py              # JevClient, JevApiError (HTTP only)
  test_jev_client.py
  jev_jsonschema/            # reusable module, no kiln_ai imports by convention, pydantic only
    __init__.py              # public API re-exports
    models.py                # System One wire models
    to_jev.py                # JSONSchema2Jev, QuestionSet, MappedQuestion, MappingOptions
    from_jev.py              # JevResult2JsonSchema, DecodedResult
    test_models.py  test_to_jev.py  test_from_jev.py
libs/core/kiln_ai/adapters/model_adapters/
  jev_adapter.py             # JevAdapter(BaseAdapter)
  test_jev_adapter.py
libs/core/kiln_ai/adapters/ml_model_list.py     # ModelAdapterId enum, KilnModelProvider.adapter field, Jev entry (TODO)
libs/core/kiln_ai/adapters/adapter_registry.py  # route on provider.adapter
libs/core/kiln_ai/adapters/provider_tools.py    # provider plumbing + default_adapter_for_provider
libs/core/kiln_ai/adapters/eval/eval_runner.py  # retryable JevApiError
```

No new runtime dependencies: `httpx` is already a `libs/core` dependency and `respx` is already a dev dependency for mocking it.

## Key decisions

1. **Reuse `KilnAgentRunConfigProperties`.** The Jev model is a normal `KilnModelProvider` entry under a new `ModelProviderName.typesafe`. Run configs, persistence, the UI, prompt builders, and `BaseAdapter.model_provider()` work unchanged. The adapter ignores `temperature`, `top_p`, `thinking_level`, and `structured_output_mode`.
2. **Route on a model-entry field, not on the provider name.** `KilnModelProvider` gains `adapter: ModelAdapterId = ModelAdapterId.litellm`, an enum with values `litellm` and `jev`. `adapter_for_task` resolves the entry with the existing `kiln_model_provider_from` and dispatches on it. Only the Jev entry sets `jev`.
3. **Keep the base adapter's invoke path.** `JevAdapter` implements only `adapter_name()` and `_run()`. Input validation, input transforms, output parse and schema validation, `generate_run`, saving, and `KilnRunError` wrapping are inherited.
4. **The mapping is a reusable module with a designed API**, not inlined into the adapter or client. No `kiln_ai` imports by convention; pydantic is its only dependency; errors are neutral. No packaging, README, or isolation tests in this repo; packaging happens when it moves to its own repo. The client and adapter import from it, never the reverse.
5. **Raise only `ValueError` / `RuntimeError` subclasses from the adapter**, because `format_error_message` passes those through verbatim and genericizes everything else.
6. **Probabilities and confidence persist as intermediate outputs only** in the core phases. The optional probability-weighted scoring phase adds an in-memory `RunOutput` field.

## Routing

### Enum and field (`ml_model_list.py`)

```python
class ModelAdapterId(str, Enum):
    litellm = "litellm"
    jev = "jev"

class KilnModelProvider(BaseModel):
    ...
    adapter: ModelAdapterId = ModelAdapterId.litellm
    """Which Kiln adapter runs this model. Defaults to LiteLLM; set to jev for TypeSafe's System One API."""
```

`KilnModelProvider` uses pydantic's default extra handling (ignore), so an older client reading the remote config ignores the field. Older clients never see the Jev entry anyway because they drop unknown provider names.

### `adapter_for_task` (`adapter_registry.py`)

```python
case "kiln_agent":
    if not isinstance(run_config_properties, KilnAgentRunConfigProperties):
        raise ValueError("KilnAgentRunConfigProperties is required for kiln_agent adapters")
    model_provider = kiln_model_provider_from(
        run_config_properties.model_name, run_config_properties.model_provider_name
    )
    match model_provider.adapter:
        case ModelAdapterId.jev:
            return JevAdapter(kiln_task=kiln_task, run_config=run_config_properties, base_adapter_config=base_adapter_config)
        case ModelAdapterId.litellm:
            return LiteLlmAdapter(kiln_task=kiln_task, config=litellm_core_provider_config(run_config_properties), base_adapter_config=base_adapter_config)
        case _:
            raise_exhaustive_enum_error(model_provider.adapter)
```

`kiln_model_provider_from` is the same lookup `BaseAdapter.model_provider()` performs lazily. It calls `check_provider_warnings` on the built-in and custom-model paths, but a user-registry model returns from `find_user_model` before that check, so `JevAdapter` runs the check itself before building the client (see `_client_from_config`). The `mock_config` fixture in `test_adapter_registry.py` already supplies keys for every provider and gains `typesafe_api_key`.

### User-registered and custom models

`user_model_to_provider` and the custom-model fallback at the bottom of `kiln_model_provider_from` construct `KilnModelProvider` at runtime. Both set `adapter=default_adapter_for_provider(provider_name)`:

```python
def default_adapter_for_provider(provider_name: ModelProviderName) -> ModelAdapterId:
    return ModelAdapterId.jev if provider_name == ModelProviderName.typesafe else ModelAdapterId.litellm
```

So a user who registers `jev-preview` under TypeSafe via Settings → Add Models gets the Jev adapter. This helper is the one place provider-to-adapter knowledge lives outside the model list.

### LiteLLM sites that must not be reached

`lite_llm_core_config_for_provider` and `utils/litellm.py`'s `get_litellm_provider_info` both switch exhaustively over `ModelProviderName`. Their `typesafe` cases raise `ValueError("TypeSafe AI models do not run through LiteLLM")`.

## Data flow

```
run_api / eval runner
  └─ adapter_for_task(task, run_config)              # provider.adapter == jev → JevAdapter
       └─ BaseAdapter.invoke(input)
            ├─ validate input schema, apply input_transform            (existing)
            └─ JevAdapter._run(input, trace_ref)
                 ├─ reject prior_trace / tools / missing output schema
                 ├─ question_set = JSONSchema2Jev().convert(task.output_schema())   # IncompatibleSchemaError → Kiln ValueError
                 ├─ system_prompt = prompt_builder.build_prompt(include_json_instructions=False)
                 ├─ state = {"task_instructions": system_prompt, "input": input}
                 ├─ trace_ref[:] = [system, user]                                   # before the call, so a failure keeps a partial trace
                 ├─ response = await client.system_one(question_set.request(state, model_id))
                 ├─ decoded = JevResult2JsonSchema().convert(question_set, response.answers)
                 ├─ trace_ref.append(assistant(usage))
                 └─ return RunOutput(decoded.output, intermediate_outputs={jev_probabilities, jev_confidence}, trace=trace_ref), Usage(...)
            ├─ parse/validate output against task.output_json_schema   (existing)
            └─ generate_run + save                                       (existing)
```

## JevAdapter (`model_adapters/jev_adapter.py`)

```python
JEV_ADAPTER_NAME = "kiln_jev_adapter"
ERROR_PREFIX = "Jev (TypeSafe AI) can't run this task:"
SUPPORTED_SHAPES = "Supported property shapes: a string enum, an integer enum, a boolean, an integer with minimum and maximum spanning 2 to 10 values, or a number with minimum 0 and maximum 1."

class JevAdapter(BaseAdapter):
    def __init__(
        self,
        kiln_task: Task,
        run_config: KilnAgentRunConfigProperties,
        base_adapter_config: AdapterConfig | None = None,
        client: JevClient | None = None,
    ) -> None:
        super().__init__(task=kiln_task, run_config=run_config, config=base_adapter_config)
        self._client = client   # None → built lazily from Config.shared().typesafe_api_key

    def adapter_name(self) -> str:
        return JEV_ADAPTER_NAME

    async def _run(self, input: InputType, trace_ref: list[ChatCompletionMessageParam],
                   prior_trace: list[ChatCompletionMessageParam] | None = None) -> Tuple[RunOutput, Usage | None]: ...
```

`_run` in order:

1. `if prior_trace: raise ValueError(f"{ERROR_PREFIX} Jev only supports single-turn runs.")`
2. Tools: `as_kiln_agent_run_config(self.run_config).tools_config` has a non-skill tool, or `self.base_adapter_config.unmanaged_tools` is non-empty → `ValueError(f"{ERROR_PREFIX} Jev does not support tools. Remove tools from the run config.")`. Skill tool ids (`SKILL_TOOL_ID_PREFIX`) are then rejected with their own message, since the UI offers skills as a separate control (see the functional spec's rule 3).
3. `schema = self.task.output_schema()`; `None` → `ValueError(f"{ERROR_PREFIX} Jev only supports tasks with a structured output schema. ...")`.
4. `question_set = JSONSchema2Jev().convert(schema)`. Catch `IncompatibleSchemaError` and re-raise as `ValueError(f"{ERROR_PREFIX} the output schema has properties Jev can't answer:\n" + "\n".join(f"- {f.key}: {f.reason}" for f in err.failures) + "\n" + SUPPORTED_SHAPES)`. Default `MappingOptions`.
5. `system_prompt = self.prompt_builder.build_prompt(include_json_instructions=False)` and nothing else. `chain_of_thought_prompt()` is never called: Jev has no thinking step, so it is sent no chain-of-thought thinking instructions. The consequence, accepted deliberately: a legacy LLM-as-Judge config's `eval_steps` reach the model only as thinking instructions and are its only required property, so a legacy Jev judge does not see its own steps and two legacy configs differing only in their steps send identical request bodies. No UI path creates a legacy judge config any more, and the V2 judge is unaffected because its `judge_instructions` render into the prompt template. No `skills` argument: a run config carrying a skill is rejected in step 2.
6. `state = build_jev_state(system_prompt, input)` → `{"task_instructions": system_prompt, "input": input}` with `input` passed as-is (dict or str). Module-level pure function.
7. `client = self._client or _client_from_config()`, which calls `check_provider_warnings(ModelProviderName.typesafe)` before constructing `JevClient(api_key=Config.shared().typesafe_api_key)`. The check is idempotent, so the built-in path repeating it is harmless, and it is the only place it runs for a user-registry model. An injected client skips it.
8. `model_id = self.model_provider().model_id`; `None` → `ValueError`.
9. Time the call with `time.perf_counter()`; `response = await client.system_one(question_set.request(state=state, model=model_id))`.
10. `decoded = JevResult2JsonSchema().convert(question_set, response.answers)`; `UnexpectedAnswerError` is re-raised as `RuntimeError(f"TypeSafe AI returned an unexpected response: {err}")`.
11. Trace, in place. The system and user messages are seeded before step 9, so a failed call still carries what was sent (the whole request is derived, so the user cannot reconstruct it from their own task); the assistant message is appended after step 10:
    ```python
    trace_ref[:] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format_user_message(input)},
    ]
    ...
    trace_ref.append(
        {"role": "assistant", "content": json.dumps(decoded.output, ensure_ascii=False), "usage": message_usage}
    )
    ```
    The final three-message shape is that of `LiteLlmAdapter.all_messages_to_trace`, so `MessageUsage.from_trace` sums it.
12. `usage = Usage(input_tokens, output_tokens, total_tokens=in+out, total_llm_latency_ms=latency_ms)`; `cost=None`.
13. Return `RunOutput(output=decoded.output, intermediate_outputs={"jev_probabilities": json.dumps(round4(decoded.probabilities), ensure_ascii=False), "jev_confidence": json.dumps(decoded.confidence, ensure_ascii=False)}, trace=trace_ref), usage`.

Steps 1 to 4 fail before any network call. Streaming is not overridden; `_create_run_stream` inherits `NotImplementedError`.

## Provider plumbing

Follow the checklist in `.claude/skills/claude-maintain-models/SKILL.md` ("Adding a Net-New Provider"). Values for this provider:

| Site | Change |
|---|---|
| `datamodel_enums.py` `ModelProviderName` | `typesafe = "typesafe"` |
| `utils/config.py` | `"typesafe_api_key": ConfigProperty(str, env_var="TYPESAFE_API_KEY", sensitive=True)` |
| `provider_tools.py` `provider_name_from_id` | `"TypeSafe AI"` |
| `provider_tools.py` `provider_warnings` | `required_config_keys=["typesafe_api_key"]`, message pointing at `https://console.typesafe.ai/keys` |
| `provider_tools.py` `lite_llm_core_config_for_provider` | `typesafe` case raises `ValueError` |
| `provider_tools.py` | `default_adapter_for_provider`; used by `user_model_to_provider` and the custom fallback |
| `utils/litellm.py` `get_litellm_provider_info` | `typesafe` case raises `ValueError` |
| `provider_api.py` | `connect_typesafe(key)`; dispatch in `connect_api_key`; clear key in `disconnect_api_key` |
| `web_ui/src/lib/stores.ts` `provider_name_map` | `typesafe: "TypeSafe AI"` |
| `web_ui/src/lib/ui/provider_image.ts` + `static/images/typesafe.svg` | Official mark supplied by the boss: copy `specs/projects/jev_provider/assets/typesafe_jev_logo.svg` to `app/web_ui/static/images/typesafe.svg`, keeping the path data and viewBox as delivered. Sibling icons (`cerebras.svg`, `featherless.svg`) keep their delivered fills too, so no recolouring; drop the `width`/`height` attributes only if the card renders it at the wrong size. Map `typesafe: "/images/typesafe.svg"` in `provider_image_map`. No `TODO`. |
| `connect_providers.svelte` | Provider card (`id: "typesafe"`, name "TypeSafe AI", one "API Key" field, short description), `status.typesafe` block, settings-key wiring |
| `web_ui/src/lib/api_schema.d.ts` | Regenerate |
| `.agents/scripts/provider_utils.py` | Add `typesafe` to `SKIP_PROVIDERS` |
| Skill docs (3 synced copies of `claude-maintain-models`, `kiln-check-deprecation`) | Provider row; note it is adapter-backed, not LiteLLM |

### Connect-flow validation (`connect_typesafe`)

Featherless's `/v1/models` was public, so it could not validate a key. TypeSafe's is not: `GET https://api.typesafe.ai/v1/models` is account-scoped and rejects a bad key, verified against the live endpoint. The GET check is therefore the confirmed choice, and the `POST /v1/systemone` fallback this section once held in reserve is not needed.

`requests.get("/v1/models", headers=Bearer)`. 200 → store key, return 200 "Connected to TypeSafe AI". 401/403 → 401 "Failed to connect to TypeSafe AI. Invalid API key." Other non-2xx → 400 with the status. Exception → 400 with the message.

The connect test suite mocks both success and 401.

### Model entry (`ml_model_list.py`)

```python
ModelFamily.jev = "jev"
ModelName.jev_1_13 = "jev_1_13"

# TODO: remove before merge; re-add after the client release that ships the TypeSafe provider (see spec release gating)
KilnModel(
    family=ModelFamily.jev,
    name=ModelName.jev_1_13,
    friendly_name="Jev 1.13",
    providers=[
        KilnModelProvider(
            name=ModelProviderName.typesafe,
            model_id="jev-1.13.0",
            adapter=ModelAdapterId.jev,
            supports_structured_output=True,
            supports_data_gen=False,
            supports_logprobs=False,
            supports_function_calling=False,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    ],
)
```

`model_id` cannot be confirmed against `GET /v1/models`: a live call lists aliases (`jev-latest`, `jev-preview`), not pinned versions, and Kiln pins. `jev-1.13.0` is confirmed by the model answering a `POST /v1/systemone` call. Unit tests do not depend on the entry: they construct the `KilnModelProvider` directly or patch `built_in_models`.

## Eval integration (core phases)

No eval code changes. Legacy LLM-as-Judge and V2 LLM Judge select the adapter through `adapter_for_task`, so a Jev judge works once routing exists. `eval_runner._is_retryable_error` gains `isinstance(err, JevApiError) and err.retryable`.

## Optional final phase: probability-weighted scoring

Opt-in; the implementation stops and asks before starting it.

- `KilnModelProvider.supports_probability_scores: bool = False`; `True` on the Jev entry. Exposed on `ModelDetails` in `provider_api.py` and the generated web types.
- Availability = `supports_logprobs or supports_probability_scores` at: `llm_judge_form.svelte` default-algorithm logic, `available_models_dropdown.svelte` `requires_logprobs` filter, and the V2 guard in `v2_eval_llm_judge.py`.
- UI label: for a model with `supports_probability_scores` the option reads "Probability-weighted"; logprob models keep "G-Eval". Disabled-state copy becomes "This scoring mode needs token probabilities, which this model or provider does not provide." Stored config type remains `g_eval`.
- `RunOutput.answer_probabilities: Dict[str, Dict[str, float]] | None = None`, set by `JevAdapter` from `decoded.probabilities`.
- `scoring_utils.build_g_eval_score`: if `run_output.answer_probabilities is not None`, return `scores_from_answer_probabilities(answer_probabilities, metrics)`: per metric, `Σ p(value) × score_from_token_string(value)` over values that map, normalized by their summed probability; raise the existing "No score found for metric" `ValueError` when none map. Logprob path untouched.

## Error handling

| Origin | Type | Handling |
|---|---|---|
| Compatibility / schema | `ValueError` (adapter translates `IncompatibleSchemaError`) | Verbatim to UI via `KilnRunError`. Not retried. |
| HTTP / transport | `JevApiError(RuntimeError)` with `.status_code`, `.retryable` | Verbatim. Retried by the eval runner when `retryable`. |
| Malformed response | `RuntimeError` (`UnexpectedAnswerError` from the module, or the client's own) | Verbatim. Not retried. |

`JevClient` never logs request bodies or the key. On failure it logs status code and `x-typesafe-request-id` at debug level.

## Testing strategy

All unit tests, no network. `respx` mocks `httpx` for the client; adapter tests inject a fake `JevClient`.

- `jev_jsonschema/test_*.py`: table-driven mapping and decoding, see the component doc. Most of the risk lives here.
- `test_jev_client.py`: request shape, every status branch in the error table, transport errors, malformed bodies.
- `test_jev_adapter.py`: pre-flight error ordering (prior trace, tools, skills, no schema, incompatible schema with prefix and every failing key); state for str and dict inputs; few-shot prompt content reaches `task_instructions`; JSON instructions excluded; trace shape; a partial system+user trace survives an API error and a decode error, and reaches `KilnRunError.partial_trace`; usage and latency; both intermediate outputs round-trip; `top_logprobs` ignored; end-to-end through `BaseAdapter.invoke` so schema validation runs; a simulated mapping bug is rejected by base validation.
- `test_adapter_registry.py`: a provider entry with `adapter=jev` routes to `JevAdapter`; default routes to `LiteLlmAdapter`; a user-registry model under TypeSafe routes to `JevAdapter`.
- `test_ml_model_list.py`: `adapter` defaults to `litellm` on every built-in entry except Jev.
- `test_provider_tools.py`, `test_provider_api.py`, `test_litellm_adapter.py`: standard provider-addition updates; connect success, invalid key, server error, exception, dispatch.
- Eval: one test each running `GEval.run_eval` (llm_as_judge) and `LlmJudgeEval.evaluate` (g_eval off) with a patched `adapter_for_task` returning a `JevAdapter` with a fake client.
- Paid smoke test (`--runpaid`, skipped without `TYPESAFE_API_KEY`): one structured task and one V2 judge, added to the prerelease whitelist with the model entry.
- Frontend: `npm run check` catches the `Record<ModelProviderName, …>` maps; one `connect_providers` test asserts the card renders and posts `provider: "typesafe"`.
