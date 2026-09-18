---
status: draft
---

# Architecture: Jev Provider (TypeSafe AI System One)

Two-phase spec: this doc covers the overall design, routing, adapter, eval integration, provider plumbing, errors and testing. Two components get their own docs because they carry most of the logic and most of the tests:

- `components/jev_jsonschema.md`: a standalone, extractable package: JSON schema → Jev questions (`JSONSchema2Jev`), Jev answers → JSON output plus probabilities (`JevResult2JsonSchema`), and the System One wire models.
- `components/jev_client.md`: the HTTP client and error mapping.

## Module layout

```
libs/core/kiln_ai/adapters/jev/
  __init__.py
  jev_client.py              # JevClient, JevApiError (HTTP only)
  test_jev_client.py
  jev_jsonschema/            # standalone package, no kiln_ai imports, pydantic only
    __init__.py  README.md  py.typed
    models.py  errors.py  options.py  to_jev.py  from_jev.py
    test_models.py  test_to_jev.py  test_from_jev.py  test_package_isolation.py
libs/core/kiln_ai/adapters/model_adapters/
  jev_adapter.py             # JevAdapter(BaseAdapter)
  test_jev_adapter.py
libs/core/kiln_ai/adapters/run_output.py        # + answer_probabilities field
libs/core/kiln_ai/adapters/adapter_registry.py  # route typesafe → JevAdapter
libs/core/kiln_ai/adapters/eval/eval_utils/scoring_utils.py  # G-Eval fast path
libs/core/kiln_ai/adapters/eval/eval_runner.py  # retryable JevApiError
```

Provider plumbing touches the usual files (listed in "Provider plumbing" below). No new runtime dependencies: `httpx` is already a `libs/core` dependency and `respx` is already a dev dependency for mocking it.

## Key decisions

1. **Reuse `KilnAgentRunConfigProperties`; do not add a run-config type.** The Jev model is a normal `KilnModelProvider` entry under a new `ModelProviderName.typesafe`. The run config carries `model_name`, `model_provider_name`, `prompt_id`, `structured_output_mode` exactly as for any LLM. This keeps the UI, run-config persistence, `_properties_for_task_output`, `model_provider()` lookup and the prompt builder working with zero changes. The adapter ignores `temperature`, `top_p`, `thinking_level` and `structured_output_mode`.
2. **Route by provider inside `adapter_for_task`.** The `"kiln_agent"` case checks `core_provider(model_name, model_provider_name) == ModelProviderName.typesafe` and returns `JevAdapter`; everything else still goes to `LiteLlmAdapter`. Using `core_provider` means a user-added model on the TypeSafe provider (via Settings → Add Models) routes correctly too.
3. **Keep the base adapter's invoke path.** `JevAdapter` implements only `adapter_name()` and `_run()`. Input validation, input transforms, output parse and schema validation, `generate_run`, saving, and `KilnRunError` wrapping are inherited. Unlike `MCPAdapter`, there is no reason to override `invoke`, because the Jev model has a real `KilnModelProvider` entry so `model_provider()` resolves.
4. **Probabilities travel on `RunOutput`, keyed by output value.** A new optional field `answer_probabilities: dict[str, dict[str, float]] | None` is populated only by `JevAdapter`. G-Eval consumes it through one fast path in `build_g_eval_score`, which both the legacy `GEval` and the V2 `LlmJudgeEval` already call.
5. **`supports_logprobs=True` on the Jev model entry.** Kiln uses that flag as "G-Eval is possible for this model". It gates the V2 judge's `g_eval` check and the UI's G-Eval toggle. Jev satisfies the intent (a probability distribution per rating) without logprobs. `AdapterConfig.top_logprobs` is ignored by `JevAdapter`.
6. **Raise only `ValueError` / `RuntimeError` subclasses from the adapter**, because `format_error_message` passes those through verbatim and genericizes everything else.
7. **The schema mapping is an extractable package.** `jev_jsonschema` has no Kiln imports, depends only on pydantic, uses relative imports, and raises neutral errors (`IncompatibleSchemaError` with structured `failures`, `UnexpectedAnswerError`). The adapter translates `IncompatibleSchemaError` into Kiln's user-facing wording. Kiln's HTTP client uses the package's wire models instead of defining its own. This keeps the OSS boundary clean from day one; extraction is a copy plus a `pyproject.toml`.

## Data flow

```
run_api / eval runner
  └─ adapter_for_task(task, run_config)            # provider == typesafe → JevAdapter
       └─ BaseAdapter.invoke(input)
            ├─ validate input schema, apply input_transform   (existing)
            └─ JevAdapter._run(input, trace_ref)
                 ├─ reject prior_trace / tools / missing output schema
                 ├─ question_set = JSONSchema2Jev().convert(task.output_schema())   # IncompatibleSchemaError → Kiln ValueError
                 ├─ system_prompt = prompt_builder.build_prompt(include_json_instructions=False, skills=...)
                 ├─ state = {"task_instructions": system_prompt, "input": input}
                 ├─ response = await JevClient(api_key).system_one(question_set.request(state, model_id))
                 ├─ decoded = JevResult2JsonSchema().convert(question_set, response.answers)
                 ├─ trace_ref[:] = [system, user, assistant(usage)]
                 └─ return RunOutput(decoded.output, intermediate_outputs={"jev_probabilities": json}, answer_probabilities=decoded.probabilities, trace=trace_ref), Usage(...)
            ├─ parse/validate output against task.output_json_schema   (existing)
            └─ generate_run + save                                       (existing)
```

## JevAdapter (`model_adapters/jev_adapter.py`)

```python
JEV_ADAPTER_NAME = "kiln_jev_adapter"

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

    async def _run(
        self,
        input: InputType,
        trace_ref: list[ChatCompletionMessageParam],
        prior_trace: list[ChatCompletionMessageParam] | None = None,
    ) -> Tuple[RunOutput, Usage | None]:
        ...
```

`_run` in order:

1. `if prior_trace: raise ValueError(f"{ERROR_PREFIX} Jev only supports single-turn runs.")` where `ERROR_PREFIX = "Jev (TypeSafe AI) can't run this task:"`.
2. `tools_config = as_kiln_agent_run_config(self.run_config).tools_config`; if it has any tools, raise the tools `ValueError`. (`BaseAdapter.available_tools()` would also surface unmanaged tools from `AdapterConfig`; check `self.base_adapter_config.unmanaged_tools` too.)
3. `schema = self.task.output_schema()`; `None` → the "no output schema" `ValueError`.
4. `question_set = JSONSchema2Jev().convert(schema)`. Catch `IncompatibleSchemaError` and re-raise as `ValueError(f"{ERROR_PREFIX} the output schema has properties Jev can't answer:\n" + "\n".join(f"- {f.key}: {f.reason}" for f in err.failures) + "\nSupported property shapes: a string enum, an integer enum, a boolean, or an integer with minimum and maximum spanning 2 to 10 values.")`. The package's default `MappingOptions` are used (argmax score decoding, 0.5 noul threshold, key fallback for instructions).
5. `system_prompt = self.prompt_builder.build_prompt(include_json_instructions=False, skills=self._resolve_skills())`. The prompt builder is always set because the run config is `kiln_agent`. Chain-of-thought instructions are never requested (`chain_of_thought_prompt()` is not called).
6. `state = build_jev_state(system_prompt, input)` → `{"task_instructions": system_prompt, "input": input}`. `input` is passed as-is (dict or str). Pure function, unit tested.
7. Resolve the client: `self._client or JevClient(api_key=Config.shared().typesafe_api_key)`; `JevClient.__init__` raises the missing-key `ValueError` when the key is falsy.
8. `model_id = self.model_provider().model_id`; raise `ValueError` if `None`.
9. `started = time.perf_counter()`; `response = await client.system_one(question_set.request(state=state, model=model_id))`; `latency_ms = int((time.perf_counter() - started) * 1000)`.
10. `decoded = JevResult2JsonSchema().convert(question_set, response.answers)`. `UnexpectedAnswerError` is a `RuntimeError`; let it propagate (message already starts with a neutral description; the adapter prefixes it with `TypeSafe AI returned an unexpected response: `).
11. Build the trace in place:
    ```python
    trace_ref[:] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format_user_message(input)},
        {"role": "assistant", "content": json.dumps(output, ensure_ascii=False), "usage": message_usage},
    ]
    ```
    Match how `LiteLlmAdapter.all_messages_to_trace` shapes the assistant message's `usage` (a `MessageUsage`), so `MessageUsage.from_trace` sums it.
12. `usage = Usage(input_tokens=..., output_tokens=..., total_tokens=in+out, total_llm_latency_ms=latency_ms)`; `cost=None`.
13. Return `RunOutput(output=decoded.output, intermediate_outputs={"jev_probabilities": json.dumps(rounded(decoded.probabilities))}, answer_probabilities=decoded.probabilities, trace=trace_ref), usage`. `decoded.confidence` is dropped in v1.

Streaming is not overridden. `_create_run_stream` inherits `NotImplementedError`.

### Why the ordering matters

Steps 1 to 4 fail before any network call and before the API key is needed, so a user with no key still gets the schema error that is actually blocking them. Step 7 fails on the key. The eval runner's retries never re-run compatibility failures because those are `ValueError`s not classified retryable.

## RunOutput change (`adapters/run_output.py`)

```python
@dataclass
class RunOutput:
    output: Dict | str
    intermediate_outputs: Dict[str, str] | None
    output_logprobs: ChoiceLogprobs | None = None
    trace: list[ChatCompletionMessageParam] | None = None
    answer_probabilities: Dict[str, Dict[str, float]] | None = None
```

Outer key: output property name. Inner key: the JSON output value rendered as a string (`"pass"`, `"3"`, `"true"`). Values sum to about 1 per property. Only `JevAdapter` sets it; every existing constructor call is unaffected because it defaults to `None`.

## Adapter routing (`adapter_registry.py`)

```python
case "kiln_agent":
    if not isinstance(run_config_properties, KilnAgentRunConfigProperties):
        raise ValueError(...)
    if core_provider(run_config_properties.model_name, run_config_properties.model_provider_name) == ModelProviderName.typesafe:
        return JevAdapter(kiln_task=kiln_task, run_config=run_config_properties, base_adapter_config=base_adapter_config)
    return LiteLlmAdapter(...)
```

`litellm_core_provider_config` is not called for TypeSafe, so its `lite_llm_core_config_for_provider` case can raise a clear `ValueError("TypeSafe AI models do not run through LiteLLM")`. Same for `utils/litellm.py`'s `get_litellm_provider_info` match: raise `ValueError` in the `typesafe` case (the exhaustive-match guard requires a case).

## G-Eval fast path (`eval_utils/scoring_utils.py`)

Add at the top of `build_g_eval_score`, before `raw_output_from_logprobs_fn` is called:

```python
if run_output.answer_probabilities is not None:
    return scores_from_answer_probabilities(run_output.answer_probabilities, list(outputs.keys()))
```

```python
def scores_from_answer_probabilities(
    answer_probabilities: Dict[str, Dict[str, float]],
    metrics: List[str],
) -> EvalScores:
    """Expected score per metric from a full distribution over rating values.

    Same estimator as rating_token_to_score: sum(p * score) over values that map to a
    score via score_from_token_string, normalized by the summed probability of those
    values. Raises ValueError (same message as the logprob path) when a metric is
    missing or no value maps to a score.
    """
```

For five_star the distribution keys are `"1"`…`"5"`; for pass/fail they are `"pass"`/`"fail"`; for pass/fail/critical add `"critical"`. All are already in `TOKEN_TO_SCORE_MAP`. Boolean outputs (`"true"`/`"false"`) are not eval rating types, so they map to nothing and raise, which is correct: eval schemas never produce booleans.

`build_llm_as_judge_score` is unchanged: the discrete dict output is already the argmax value.

The legacy `GEval` still requests `top_logprobs=10` in `AdapterConfig`; `JevAdapter` ignores it. The V2 judge's `supports_logprobs` guard passes via the model flag.

## Eval runner retries (`eval_runner.py`)

`_is_retryable_error` gains: `isinstance(err, JevApiError) and err.retryable`. The runner already unwraps `KilnRunError` to the original exception before this check.

## Provider plumbing

Follow the repo's checklist in `.claude/skills/claude-maintain-models/SKILL.md` ("Adding a Net-New Provider"), which lists every touchpoint from the Featherless integration. Specific values for this provider:

| Site | Change |
|---|---|
| `datamodel_enums.py` `ModelProviderName` | `typesafe = "typesafe"` |
| `utils/config.py` | `"typesafe_api_key": ConfigProperty(str, env_var="TYPESAFE_API_KEY", sensitive=True)` |
| `provider_tools.py` `provider_name_from_id` | `"TypeSafe AI"` |
| `provider_tools.py` `provider_warnings` | `required_config_keys=["typesafe_api_key"]`, message pointing at `https://typesafe.ai` for a key |
| `provider_tools.py` `lite_llm_core_config_for_provider` | `typesafe` case raises `ValueError` (never reached in practice) |
| `utils/litellm.py` `get_litellm_provider_info` | `typesafe` case raises `ValueError` |
| `provider_api.py` `connect_api_key` / `disconnect_api_key` | dispatch to `connect_typesafe(key)`; disconnect clears `typesafe_api_key` |
| `provider_api.py` `connect_typesafe(key)` | `requests.get("https://api.typesafe.ai/v1/models", headers=Bearer)`. 200 → store key, return 200 "Connected to TypeSafe AI". 401/403 → 401 "Failed to connect to TypeSafe AI. Invalid API key." Other non-2xx → 400 with the status code. Exception → 400 with the message. Same shape as `connect_featherless`. |
| `web_ui/src/lib/stores.ts` `provider_name_map` | `typesafe: "TypeSafe AI"` |
| `web_ui/src/lib/ui/provider_image.ts` + `static/images/typesafe.svg` | Monochrome glyph. The coding agent cannot fetch brand assets; ship a simple placeholder glyph and leave a `TODO` for a human to swap in the official mark before merge. |
| `connect_providers.svelte` | Provider card `{ name: "TypeSafe AI", id: "typesafe", description: "Jev: a decision model that returns typed answers with probabilities. Structured-output tasks and eval judges only.", featured: false, api_key_steps: [...], api_key_fields: ["API Key"] }`, a `status.typesafe` block, and the settings-key wiring that flips `connected` when `typesafe_api_key` is set. |
| `web_ui/src/lib/api_schema.d.ts` | Regenerate (`generate_schema.sh`) |
| `.agents/scripts/provider_utils.py` | Add `typesafe` to `SKIP_PROVIDERS` (no enumerable catalog worth crawling) |
| Skill docs (3 synced copies of `claude-maintain-models/SKILL.md`, `kiln-check-deprecation/SKILL.md`) | Add the provider row and note it is adapter-backed, not LiteLLM |

### Model list entry (`ml_model_list.py`, shipped separately, see the implementation plan)

```python
ModelFamily.jev = "jev"
ModelName.jev_1_13 = "jev_1_13"

KilnModel(
    family=ModelFamily.jev,
    name=ModelName.jev_1_13,
    friendly_name="Jev 1.13",
    providers=[
        KilnModelProvider(
            name=ModelProviderName.typesafe,
            model_id="jev-1.13.0",
            supports_structured_output=True,
            supports_data_gen=False,
            supports_logprobs=True,
            supports_function_calling=False,
            structured_output_mode=StructuredOutputMode.json_schema,
        ),
    ],
)
```

Confirm `model_id` against `GET /v1/models` when implementing; `jev-latest` is the alias the SDK defaults to, but Kiln pins versions.

Until that entry lands, tests construct the `KilnModelProvider` via a fixture that patches `built_in_models` (the same approach `test_adapter_registry.py` uses for config), and local manual testing adds the entry on the branch.

## Release gating

Per the repo rule that bit the Featherless integration: remote config publishes `built_in_models` from `main` to every deployed client immediately. Clients without the `typesafe` enum drop the provider with a warning; clients with the enum but without the adapter or UI would show a broken model. So the model-list entry is a separate final phase, merged only after a client release containing everything else is live. Everything else (enum, adapter, routing, UI, evals) can ship in one PR because no model references the provider until the entry lands.

## Error handling

| Origin | Type | Handling |
|---|---|---|
| Compatibility / schema | `ValueError` (adapter translates the package's `IncompatibleSchemaError`) | Verbatim to UI via `KilnRunError`. Not retried. |
| Missing key | `ValueError` | Verbatim. |
| HTTP / transport | `JevApiError(RuntimeError)` with `.status_code: int | None`, `.retryable: bool` | Verbatim message. Retried by the eval runner when `retryable`. |
| Malformed response | `RuntimeError` (`UnexpectedAnswerError` from the package, or the client's own) | Verbatim. Not retried. |

`JevClient` never logs request bodies (they contain user data) or the key. It logs status code and request id (`x-typesafe-request-id`) at debug level on failure.

## Testing strategy

All unit tests, no network. `respx` mocks `httpx` at the transport layer for the client; the adapter tests inject a fake `JevClient`.

- `jev_jsonschema/test_*.py`: table-driven, see the component doc. This is where most of the risk lives. Includes the isolation test that fails if any `kiln_ai` import creeps into the package.
- `test_jev_client.py`: request body shape, header, model, every status-code branch in the error table, timeout and connection errors, malformed bodies.
- `test_jev_adapter.py`: ordering of pre-flight errors (prior trace, tools, no schema, incompatible schema with the Kiln prefix and every failing key, then missing key), state construction with string and dict inputs, few-shot prompt content reaching `task_instructions`, JSON instructions excluded, trace shape, usage and latency, `intermediate_outputs["jev_probabilities"]` round-trips, `answer_probabilities` populated, `top_logprobs` ignored, end-to-end through `BaseAdapter.invoke` so output schema validation runs, and a mapping-bug simulation proving invalid output is rejected by the base validation.
- `test_adapter_registry.py`: `typesafe` routes to `JevAdapter`; a user-registry model on TypeSafe routes to `JevAdapter`; other providers still route to `LiteLlmAdapter`.
- `test_eval_utils.py` / `test_g_eval.py`: `scores_from_answer_probabilities` for five_star, pass_fail, pass_fail_critical, unknown value raises, and that `build_g_eval_score` takes the fast path when `answer_probabilities` is set and the logprob path otherwise. One test runs `GEval.run_eval` and one runs `LlmJudgeEval.evaluate` (g_eval on and off) with a patched `adapter_for_task` returning a `JevAdapter` with a fake client.
- `test_provider_tools.py`, `test_provider_api.py`, `test_litellm_adapter.py`: the standard provider-addition updates (friendly name, warnings, connect/disconnect success, invalid key, server error, exception, dispatch).
- Paid smoke test (`--runpaid`, skipped without `TYPESAFE_API_KEY`): one structured task and one V2 judge against the live API, added to `pytest_prerelease_whitelist.py` once the model entry exists.
- Frontend: `npm run check` catches the `Record<ModelProviderName, …>` maps. Add one `connect_providers` test asserting the TypeSafe card renders and posts to `connect_api_key` with `provider: "typesafe"`.
