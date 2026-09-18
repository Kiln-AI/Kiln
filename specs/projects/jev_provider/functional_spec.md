---
status: draft
---

# Functional Spec: Jev Provider (TypeSafe AI System One)

## Goals

1. A Kiln user can connect TypeSafe AI as a provider with an API key, pick a Jev model anywhere a model is picked, and run a compatible task against it.
2. Compatible means: single turn, no tools, a task output schema whose every property maps onto one of Jev's three question types (choice, score, noul). Everything else fails at runtime with a clear, specific error. The UI does not pre-validate compatibility.
3. Kiln's built-in eval judges (legacy G-Eval and LLM-as-Judge, and V2 LLM Judge) work with a Jev judge model. G-Eval uses Jev's native probabilities instead of the logprob approximation.
4. The mapping is lossless in both directions: JSON schema → Jev questions → Jev answers → a JSON object that validates against the task's output schema through Kiln's normal validation path.

## Non-goals (v1)

- Streaming, tools, MCP, multi-turn chat, or the agent/chat UI with a Jev model. These are runtime errors.
- Synthetic data generation and fine-tuning with Jev. Jev cannot generate text, so the model is flagged `supports_data_gen=False` and never offered as a fine-tune base.
- Nested objects, arrays, free-form strings, floats, `anyOf`/`oneOf`, or per-enum-value descriptions in the output schema. Runtime error listing every offending property.
- Cost estimation. Token counts are recorded; `cost` stays `None`.
- Any UI beyond the standard provider connect card and the model appearing in existing dropdowns.
- Exposing Jev's confidence/probabilities in the UI. They are persisted (see below) but no new UI reads them.

## Background: the Jev API

See `research/jev_api/summary.md` for the wire contract. Summary:

- `POST /v1/systemone` with `{state, model, questions}`; `state` is any JSON; `questions` is a dict of named questions.
- Question types: `noul` (yes/no, returns probability of yes), `choice` (labelled options, returns the argmax label plus a probability per label), `score` (ordered rubric, returns an expected value plus a probability per level, levels are 0-based indices).
- Every question has optional `instructions`. There is no system prompt.

## Provider

| Item | Value |
|---|---|
| Provider enum | `ModelProviderName.typesafe = "typesafe"` |
| Display name | TypeSafe AI |
| Auth | API key, stored in Kiln `Config` as `typesafe_api_key`; also honoured from env var `TYPESAFE_API_KEY` like other providers' keys |
| Base URL | `https://api.typesafe.ai` (constant, not user-configurable in v1) |
| Connect flow | Same as other key-based providers in Settings → AI Providers: enter key, Kiln validates it with `GET /v1/models`, saves on success, shows the API error on failure |
| Disconnect | Removes the key, same as other providers |
| Model | `ModelName.jev_1_13`, friendly name "Jev 1.13", `model_id="jev-1.13.0"` on the `typesafe` provider. Verify the exact model name against `GET /v1/models` during implementation and adjust. |

Model capability flags for the Jev entry:

| Flag | Value | Why |
|---|---|---|
| `supports_structured_output` | True | Only structured output is possible |
| `supports_data_gen` | False | Cannot generate text |
| `supports_logprobs` | True | Kiln uses this flag to mean "G-Eval can get a probability-weighted score". Jev returns probabilities natively, which is strictly better. |
| `suggested_for_evals` | False | Leave off until we have run our own comparisons. Users can still pick it. |
| `structured_output_mode` | `json_schema` | Nominal. The Jev adapter ignores the mode. Chosen so the prompt builder never appends JSON formatting instructions. |
| `reasoning_capable` | False | No reasoning, no intermediate outputs required |
| `multimodal_capable` / doc extraction | False | Text and JSON only |

The model appears in every existing model dropdown that the flags allow (run page, eval judge selection). Dropdowns that require data gen or text output already filter on the flags above.

## Task compatibility rules

Checked at run time inside the Jev adapter, before any network call, in this order. The first failing rule raises a `ValueError` whose message starts with `Jev (TypeSafe AI) can't run this task:` followed by the specific reason. All schema-mapping problems are collected and reported together in one message so the user fixes the schema in one pass.

1. **Prior trace present** (multi-turn continuation): `... Jev only supports single-turn runs.`
2. **Tools configured** on the run config: `... Jev does not support tools. Remove tools from the run config.`
3. **No output schema** on the task: `... Jev only supports tasks with a structured output schema. Add an output JSON schema whose properties are enums, booleans, or bounded integers.`
4. **Schema mapping failures**: `... the output schema has properties Jev can't answer:` followed by one line per property: `- <key>: <reason>`. Reasons are listed in the mapping table below.
5. **Zero mappable properties** (empty `properties`): `... the output schema has no properties.`

Streaming entry points are not overridden; the base class raises `NotImplementedError("Streaming is not supported for this adapter type")`, which is acceptable because no Kiln UI streams a plain task run.

Run config fields `temperature`, `top_p`, `thinking_level` are ignored silently. Chain-of-thought prompt generators are accepted; their thinking instructions are ignored (no `chain_of_thought` intermediate output is produced). Prompt content (simple, few-shot, multi-shot, saved prompts, fine-tune prompts, skills) is used in full.

## Output schema → Jev questions

The task output schema must be `type: object` with `properties` (Kiln already enforces this). Each property becomes one question named exactly after the property key. Question `instructions` is the property's `description`, else its `title`, else omitted.

| JSON schema property | Jev question | Answer → JSON value |
|---|---|---|
| `enum: [...]` where every value is a string, and `type` is absent or `"string"` | `choice` with `criteria = {value: null for value in enum}` (order preserved) | `answer.choice` verbatim |
| `enum: [...]` where every value is an integer, and `type` is absent or `"integer"` | `choice` with string labels `str(value)` | `int(answer.choice)` |
| `type: "boolean"` | `noul` with `instructions` as above | `answer.noul >= 0.5` |
| `type: "integer"` with both `minimum` and `maximum` set, `maximum - minimum + 1` between 2 and 10 inclusive | `score` with `criteria = [str(minimum), ..., str(maximum)]` (ascending, one level per integer) | `minimum + argmax(answer.probabilities)`; on a tie, the lowest level |
| Anything else | Unsupported; see reasons below | |

Unsupported reasons (one per property, exact wording is the coding agent's call but each must name the property and say what would be accepted):

- `enum` with mixed or non-scalar values, or with zero values.
- `enum` values that are strings but `type` says something other than `string` (and likewise for integers).
- Duplicate `enum` values after string conversion.
- `type: integer` without both `minimum` and `maximum`, or with a range of 1 or more than 10 levels. Note `exclusiveMinimum`/`exclusiveMaximum` are not honoured; they count as missing bounds.
- `type: number`, `string` without `enum`, `array`, `object`, `null`, a list of types, or no `type` and no `enum`.
- `anyOf`, `oneOf`, `allOf`, `$ref`, `const`.

Properties are answered whether or not they are listed in `required`. `additionalProperties` is ignored. Property order in the request follows the schema's property order.

The 10-level cap on `score` comes from third-party reports and is enforced locally so the error is specific. If the API rejects a request for any other limit (question count, option count, state size), the API's own error message is surfaced verbatim.

### Descriptions

Kiln's eval schemas put the scoring instruction and the scale explanation in the property `description`, so the eval rubric reaches Jev as the question `instructions` without special handling. For the five_star case the criteria labels are `"1"` … `"5"` and the description already says "an integer from 1 to 5, where 1 is the worst and 5 is the best".

## Kiln inputs → Jev state

The adapter builds the `state` as a JSON object:

```json
{
  "task_instructions": "<system prompt from the run config's prompt builder, JSON formatting instructions excluded>",
  "input": <the task input: the parsed dict when the task has an input schema, else the plain string>
}
```

Rationale: TypeSafe's docs recommend an object for anything non-trivial so relationships stay explicit, and it avoids JSON-encoding structured inputs inside a string. The system prompt lives in `state` rather than in every question's `instructions`, because state is shared across questions and the API's size limit counts state plus the longest single question.

Input transforms (Jinja `input_transform` on the run config) are applied by the base class before the adapter sees the input, as today. Input schema validation also happens in the base class, as today.

## Jev answers → Kiln output

The adapter assembles `{property_key: mapped_value}` for every property and returns it as a dict. The base adapter validates the dict against the task's output schema exactly as it does for any other model, so a mapping bug surfaces as the standard "This task requires a specific output schema" error rather than silently saving bad data.

### Probabilities

Two places, both keyed by property and by the *output-schema value* (not Jev's internal label), so consumers never need to know the question type:

1. `RunOutput.answer_probabilities: dict[str, dict[str, float]] | None` (new, in-memory only). For a `noul` this is `{"true": p, "false": 1 - p}`. For a `score` the keys are the integer values as strings (`"1"`…`"5"`), not the 0-based levels. For a `choice` the keys are the enum values as strings.
2. `TaskRun.intermediate_outputs["jev_probabilities"]`: the same structure JSON-encoded as a string, so it is persisted with the run and visible wherever intermediate outputs are shown. Rounded to 4 decimal places.

`confidence` values are not persisted in v1.

## Trace and usage

The adapter synthesizes a two-turn OpenAI-style trace so run details, full-trace evals and the "error with trace" UI behave like any other run:

- `system`: the `task_instructions` string
- `user`: the input (dict inputs JSON-encoded, as `format_user_message` does today)
- `assistant`: the output dict JSON-encoded, carrying per-message `usage`

`Usage` is populated from the response: `input_tokens`, `output_tokens`, `total_tokens` (sum), `total_llm_latency_ms` (wall clock of the HTTP call), `cost=None`, `cached_tokens=None`.

The saved `TaskOutput.source.properties` carry the usual `adapter_name`, `model_name`, `model_provider`, `prompt_id`, `structured_output_mode`, `temperature`, `top_p` via the existing base-class code path. `adapter_name` is `"kiln_jev_adapter"`.

## Evals with a Jev judge

- **Legacy G-Eval and LLM-as-Judge** (`g_eval.py`): the judge task's output schema is built by `build_score_schema(allow_float_scores=False)`, which produces only shapes in the mapping table. The adapter is selected by provider, so no change to how the eval builds the run config. The `SIMPLE_CHAIN_OF_THOUGHT` prompt id is accepted and its thinking step ignored.
  - LLM-as-Judge: unchanged; consumes the discrete dict output.
  - G-Eval: `build_g_eval_score` gains a fast path. When `run_output.answer_probabilities` is present, each metric's score is `Σ p(value) × score_from_token_string(value)` over that metric's distribution, normalized by the summed probability of recognized values. This reproduces exactly what the logprob path computes, but from a full distribution. The logprob path is untouched for other models.
- **V2 LLM Judge** (`v2_eval_llm_judge.py`): same fast path. Its existing `supports_logprobs` guard passes because the Jev entry sets that flag.
- **Full-trace evals**: the trace text lands in the judge prompt as today. Very long traces can exceed Jev's state limit; the API error is surfaced and the eval runner records it as a failed job like any other judge error.
- **Eval runner retries**: transient Jev errors (429, 5xx, timeouts, connection failures) are classified retryable alongside the LiteLLM transient errors so the runner's existing two retries apply.

## Error handling

All errors raised inside the adapter propagate through the existing `KilnRunError` wrapping, so the run page shows the message with any partial trace. Because `format_error_message` passes `ValueError` and `RuntimeError` text through verbatim and genericizes everything else, the adapter raises only those two families:

| Situation | Exception | Message |
|---|---|---|
| Compatibility or schema-mapping failure | `ValueError` | As specified above |
| Missing API key | `ValueError` | `TypeSafe AI API key not set. Connect TypeSafe AI in Settings → AI Providers.` |
| HTTP 401/403 | `JevApiError(RuntimeError)` | `Authentication with TypeSafe AI failed. Check your API key.` |
| HTTP 429 | `JevApiError` (retryable) | `TypeSafe AI rate limit exceeded. Wait a moment and try again.` |
| HTTP 422 | `JevApiError` | `TypeSafe AI rejected the request: ` + each `detail[].msg` joined with `; ` |
| Other 4xx | `JevApiError` | `TypeSafe AI rejected the request (HTTP <code>): <body, truncated to 500 chars>` |
| 5xx | `JevApiError` (retryable) | `TypeSafe AI is currently unavailable. Try again in a moment.` |
| Timeout / connection error | `JevApiError` (retryable) | `Could not connect to TypeSafe AI. Check your network connection.` |
| Response missing an answer for a question, wrong answer type, or unparseable body | `RuntimeError` | `TypeSafe AI returned an unexpected response: <detail>` |

Request timeout: 60 seconds total (Jev responds in well under a second; the generous value covers large states). No client-side retries in the adapter itself; retries are the caller's job (eval runner) so interactive runs fail fast.

The API key is never included in error messages or logs.

## Configuration and defaults

- `Config.typesafe_api_key`: the only new setting.
- No per-run options. Jev has no temperature or sampling controls.

## Compatibility and constraints

- Python 3.10+ for `libs/core`. HTTP via the already-present `httpx` dependency, async client. No new runtime dependencies.
- Adding a value to `ModelProviderName` changes the OpenAPI schema; regenerate `app/web_ui/src/lib/api_schema.d.ts`.
- Remote model-list config can only reference providers the running app already knows, so the provider enum ships in the app and the model entry can later be tuned remotely like any other.
- No changes to persisted file formats other than the new optional `intermediate_outputs` key, which existing readers ignore.

## Acceptance checks

1. Connect TypeSafe AI with a valid key; the provider shows connected and "Jev 1.13" appears in the run page model dropdown.
2. A task with output schema `{"rating": integer 1..5, "verdict": enum [pass, fail], "is_spam": boolean}` runs and saves a run whose output validates, with `jev_probabilities` in intermediate outputs.
3. The same task with an added `summary: string` property fails before any network call with a message naming `summary` and the accepted shapes.
4. A run config with a tool attached fails with the tools message.
5. A legacy G-Eval and a V2 LLM Judge (with and without `g_eval`) configured with the Jev judge produce scores on a small eval set, and the G-Eval scores are non-integer where the judge is uncertain.
6. With an invalid key, connecting fails with the API's message and running fails with the authentication message.
7. `uv run ./checks.sh --agent-mode` passes, including the OpenAPI schema check.
