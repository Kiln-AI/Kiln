---
status: complete
---

# Functional Spec: Jev Provider (TypeSafe AI System One)

## Goals

1. A Kiln user can connect TypeSafe AI as a provider with an API key, pick the Jev model anywhere a model is picked, and run a compatible task against it.
2. Compatible means: single turn, no tools, a task output schema whose every property maps onto one of Jev's three question types (choice, score, noul). Everything else fails at runtime with a clear, specific error. The UI does not pre-validate compatibility.
3. Kiln's LLM-as-Judge evals (legacy and V2) work with a Jev judge. Probability-weighted scoring from Jev's native distributions is an optional, opt-in final phase.
4. The mapping is lossless in both directions: JSON schema → Jev questions → Jev answers → a JSON object that validates against the task's output schema through Kiln's normal validation path.
5. The mapping lives in a small standalone module (`JSONSchema2Jev`, `JevResult2JsonSchema`) that can be pulled out into an open-source project unchanged.

## Non-goals (v1)

- Streaming, tools, MCP, multi-turn chat, or the agent/chat UI with a Jev model. These are runtime errors.
- Synthetic data generation and fine-tuning with Jev. Jev cannot generate text, so the model is flagged `supports_data_gen=False` and never offered as a fine-tune base.
- Probability-weighted scoring in the core phases. Until the optional phase ships, the Jev model entry has `supports_logprobs=False`, so the existing UI greys the G-Eval option out with its existing message and the V2 judge's `g_eval` guard rejects it.
- Nested objects, arrays, free-form strings, unbounded numbers, `anyOf`/`oneOf`, or per-enum-value descriptions in the output schema. Runtime error listing every offending property.
- Cost estimation. The API returns token counts but no cost; `cost` stays `None`.
- Any UI beyond the standard provider connect card and the model appearing in existing dropdowns.
- Reading Jev's probabilities or confidence in the UI. They are persisted with the run (see below) but no new UI displays them.

## Background: the Jev API

See `research/jev_api/summary.md` for the wire contract. Summary:

- `POST /v1/systemone` with `{state, model, questions}`; `state` is any JSON; `questions` is a dict of named questions, all evaluated in parallel against the same state.
- Question types: `noul` (yes/no, returns the probability of yes), `choice` (labelled options, returns the argmax label plus a probability per label and a confidence), `score` (ordered rubric of 2 to 10 levels, returns an expected value plus a probability per level and a confidence; levels are 0-based indices).
- `instructions` is required for `noul`, optional for the others. There is no system prompt.

## Provider

| Item | Value |
|---|---|
| Provider enum | `ModelProviderName.typesafe = "typesafe"` |
| Display name | TypeSafe AI |
| Auth | API key, stored in Kiln `Config` as `typesafe_api_key`; also honoured from env var `TYPESAFE_API_KEY` like other providers' keys |
| Base URL | `https://api.typesafe.ai` (constant, not user-configurable in v1) |
| Connect flow | Same as other key-based providers in Settings → AI Providers: enter key, Kiln validates it with `GET /v1/models`, saves on success, shows the API error on failure |
| Disconnect | Removes the key, same as other providers |
| Model | `ModelName.jev_1_13`, friendly name "Jev 1.13", `model_id="jev-1.13.0"` on the `typesafe` provider. `GET /v1/models` cannot verify it: it lists aliases (`jev-latest`, `jev-preview`), not pinned versions. A `POST /v1/systemone` call is what confirms the pinned id. |

Model capability flags for the Jev entry:

| Flag | Value | Why |
|---|---|---|
| `supports_structured_output` | True | Only structured output is possible |
| `supports_data_gen` | False | Cannot generate text |
| `supports_logprobs` | False | Jev has no token logprobs. Greys out the G-Eval option in the UI and fails the V2 judge's `g_eval` guard until the optional phase adds `supports_probability_scores` |
| `supports_function_calling` | False | No tools |
| `suggested_for_evals` | False | Off until we have compared it against our usual judges. Users can still pick it. |
| `structured_output_mode` | `json_schema` | Nominal. The Jev adapter ignores the mode. Chosen so the prompt builder never appends JSON formatting instructions. |
| `reasoning_capable` | False | No reasoning, no intermediate outputs required |
| `multimodal_capable` / doc extraction | False | Text and JSON only |

The model appears in every existing model dropdown that the flags allow (run page, eval judge selection). Dropdowns that require data gen, logprobs, or function calling already filter on the flags above.

### Model entry and release gating

Kiln's rule for new providers is that the model-list entry lands in a second PR after a client release, because the remote config is published from `main` and the web model library page reads it directly in the browser. An old client would otherwise show the Jev row labelled with the raw provider ID `typesafe` and offer a model it cannot connect. The Python side already drops unknown providers safely, so this is a model-library-only problem, but it is the reason the Featherless entries were rolled back.

What happened:

1. The entry was added on the feature branch so the feature could be tested end to end, with a `TODO` comment saying it must be removed before merge. CI enforces that no `TODO` comments reach `main`, so while that comment was there the PR could not merge with the entry in.
2. The entry was removed before merge as planned, then restored for manual testing, and the removal `TODO` was deleted on this branch by the user's decision — so the provider can be tested against the live API from this branch rather than after a release. The prerelease whitelist and the paid smoke test landed on the same branch — the work the original third step deferred until after the release.
3. So the gate is no longer mechanical. Nothing in CI now stops the entry reaching `main`; what stops it is the pull request staying a work in progress until the release that carries the provider has shipped. The reason is unchanged and still binding: the remote config is published from `main`, and an old client would show the Jev row labelled with the raw provider ID `typesafe` and offer a model it cannot connect. The pull request is not a GitHub draft; the marker is the `WIP:` prefix on its title, and whoever removes that prefix owns this check.

## Task compatibility rules

Checked at run time inside the Jev adapter, before any network call, in this order. The first failing rule raises a `ValueError` whose message starts with `Jev (TypeSafe AI) can't run this task:` followed by the specific reason. All schema-mapping problems are collected and reported together in one message so the user fixes the schema in one pass.

1. **Prior trace present** (multi-turn continuation): `... Jev only supports single-turn runs.`
2. **Tools configured** on the run config: `... Jev does not support tools. Remove tools from the run config.`
3. **Skills attached** to the run config: `... Jev does not support skills, which the model loads through a tool call. Remove the skills from the run config.` Skills are stored inside `tools_config.tools` as `kiln_tool::skill::<id>`, but the UI offers them as their own control, so they get their own message rather than being reported as tools. A config carrying both reports the tools first.
4. **No output schema** on the task: `... Jev only supports tasks with a structured output schema. Add an output JSON schema whose properties are enums, booleans, bounded integers, or numbers from 0 to 1.`
5. **Schema mapping failures**: `... the output schema has properties Jev can't answer:` followed by one line per property: `- <key>: <reason>`. Reasons are listed in the mapping table below.
6. **Zero mappable properties** (empty `properties`): `... the output schema has no properties.`

Streaming entry points are not overridden; the base class raises `NotImplementedError("Streaming is not supported for this adapter type")`, which is acceptable because no Kiln UI streams a plain task run.

Run config fields `temperature`, `top_p`, `thinking_level` are ignored silently. Chain-of-thought prompt generators are accepted but their thinking instructions are not sent: Jev has no thinking step, so it produces no `chain_of_thought` intermediate output and receives no chain-of-thought instructions. The system prompt is `build_prompt(include_json_instructions=False)` alone. The known consequence, accepted deliberately: `eval_steps` is the only required field of a legacy `llm_as_judge` eval config and travels only in the thinking instruction, so a legacy Jev judge does not see its own steps and two legacy configs differing only in their steps send identical requests. That is acceptable because no UI path creates a legacy judge config any more — `eval_config_builder.svelte` only ever creates V2 configs, leaving the Python library, the `create_eval_config` REST endpoint and the copilot flow — and the V2 judge is unaffected, because its `judge_instructions` render into the prompt template rather than the thinking instruction. Prompt content (simple, few-shot, multi-shot, saved prompts, fine-tune prompts) is used in full.

Skills are rejected, not ignored: Kiln gives the model a callable `SkillTool` and the prompt section tells it to "load it with `skill(name)`". Jev answers questions and cannot call anything, so a skill's content would never be loaded and the run would silently lose it. Rejecting is the honest outcome, and it is rule 3 above.

## Output schema → Jev questions

The task output schema must be `type: object` with `properties` (Kiln already enforces this). Each property becomes one question named exactly after the property key. Question `instructions` is the property's `description`, else its `title`, else the property key itself. A bare key such as `is_spam` is still a usable question, and `noul` requires instructions.

The conversion in both directions is a standalone package, `jev_jsonschema`, written so it can be lifted into its own open-source project: no Kiln imports, pydantic as its only dependency, neutral error messages, and the decoding knobs below exposed as options. Kiln's adapter wraps the package's errors with the Kiln-facing prefix above and uses the default options.

| JSON schema property | Jev question | Answer → JSON value |
|---|---|---|
| `enum: [...]` where every value is a string, and `type` is absent or `"string"` | `choice` with `criteria = {value: null for value in enum}` (order preserved, bare labels) | `answer.choice` verbatim |
| `enum: [...]` where every value is an integer, and `type` is absent or `"integer"` | `choice` with string labels `str(value)` | `int(answer.choice)` |
| `type: "boolean"` | `noul` | `answer.noul >= threshold`; threshold is a module option, default 0.5 |
| `type: "number"` with `minimum: 0` and `maximum: 1` exactly (inclusive bounds) | `noul` with `instructions = X` and `criteria = {"true": X, "false": "inverse of X"}`, where X is the description, else title, else key. So a property `correctness` yields true: "correctness", false: "inverse of correctness", which tells Jev the probability is a degree of X rather than the answer to a question. | `answer.noul` as a float |
| `type: "integer"` with both `minimum` and `maximum` set, `maximum - minimum + 1` between 2 and 10 inclusive | `score` with `criteria = [str(minimum), ..., str(maximum)]` (ascending, one level per integer) | `minimum + level` where `level` has the highest probability; on a tie, the lowest level |
| Anything else | Unsupported; see reasons below | |

Unsupported reasons (one per property, exact wording is the coding agent's call but each must name the property and say what would be accepted):

- `enum` with mixed or non-scalar values, or with zero values.
- `enum` values that are strings but `type` says something other than `string` (and likewise for integers).
- Duplicate `enum` values after string conversion.
- `enum` with more than 255 values (Jev's choice limit).
- `type: integer` without both `minimum` and `maximum`, or with a range of 1 or more than 10 levels.
- `type: number` with bounds other than exactly 0 and 1, or missing bounds.
- `string` without `enum`, `array`, `object`, `null`, a list of types, or no `type` and no `enum`.
- `anyOf`, `oneOf`, `allOf`, `$ref`, `const`, `not`.
- `multipleOf`, `exclusiveMinimum`, `exclusiveMaximum` on any property. A question offers a fixed set of answers, so a constraint that narrows them further cannot be honoured; rejecting up front beats a paid call whose answer then fails the task's own output validation.

Properties are answered whether or not they are listed in `required`, since Jev cannot abstain. `additionalProperties` is ignored. Property order in the request follows the schema's property order.

The 10-level cap on `score` and the 255-option cap on `choice` are documented API limits and are enforced locally so the error names the property. If the API rejects a request for any other limit (question count, state size), the API's own error message is surfaced verbatim.

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

### Probabilities and confidence

Persisted in `TaskRun.intermediate_outputs` as two JSON-encoded strings, so they travel with the run and appear wherever intermediate outputs are shown:

- `jev_probabilities`: `{property: {output value as string: probability}}`. Keys are output-schema values, not Jev's internal labels: `"pass"`/`"fail"` for a choice, `"1"`…`"5"` for a score (after adding `minimum`), `"true"`/`"false"` for a boolean or 0..1 number noul. Rounded to 4 decimal places.
- `jev_confidence`: `{property: confidence}`. Jev's confidence for choice and score answers; `null` for noul answers, which carry none.

## Trace and usage

The adapter synthesizes a two-turn OpenAI-style trace so run details, full-trace evals and the "error with trace" UI behave like any other run:

- `system`: the `task_instructions` string
- `user`: the input (dict inputs JSON-encoded, as `format_user_message` does today)
- `assistant`: the output dict JSON-encoded, carrying per-message `usage`

The `system` and `user` messages are written before the HTTP call and the `assistant` message is added after the answers decode, so a failed run keeps a partial trace of what was sent. That matters more here than for other providers: the whole request is derived (system prompt, input and output schema become `state` and questions), so a user cannot reconstruct it by reading their own task.

`Usage` is populated from the response: `input_tokens`, `output_tokens`, `total_tokens` (sum), `total_llm_latency_ms` (wall clock of the HTTP call), `cost=None`, `cached_tokens=None`.

The saved `TaskOutput.source.properties` carry the usual `adapter_name`, `model_name`, `model_provider`, `prompt_id`, `structured_output_mode`, `temperature`, `top_p` via the existing base-class code path. `adapter_name` is `"kiln_jev_adapter"`.

## Evals with a Jev judge

- **Legacy LLM-as-Judge** (`g_eval.py` with `config_type == llm_as_judge`): the judge task's output schema is built by `build_score_schema(allow_float_scores=False)`, which produces only shapes in the mapping table. The adapter is selected by provider, so the eval code does not change. The `SIMPLE_CHAIN_OF_THOUGHT` prompt id it uses is accepted, but Jev is sent no thinking instructions, so the `eval_steps` that prompt id carries do not reach it — even though `eval_steps` is the config's only required property. A legacy Jev judge therefore does not see its own steps, and two legacy configs differing only in their steps send identical requests. Accepted because the legacy judge is unreachable from the UI (only the library, the `create_eval_config` endpoint and the copilot flow create one) and the V2 judge is unaffected. Scores come from the discrete dict output as today.
- **V2 LLM Judge** (`v2_eval_llm_judge.py`) with `g_eval=False`: same. With `g_eval=True` the existing `supports_logprobs` guard raises before running, and the UI never offers it, until the optional phase below.
- **Full-trace evals**: the trace text lands in the judge prompt as today. Very long traces can exceed Jev's state limit; the API error is surfaced and the eval runner records it as a failed job like any other judge error.
- **Eval runner retries**: transient Jev errors (429, 5xx, timeouts, connection failures) are classified retryable alongside the LiteLLM transient errors so the runner's existing two retries apply. No retries happen inside the adapter itself, so interactive runs fail fast.

### Optional final phase: probability-weighted scoring from native distributions

Opt-in: the implementation stops before this phase and asks whether to proceed. This is not G-Eval. G-Eval is chain-of-thought plus token logprobs; Jev has neither. It is a probability-weighted expected score computed from the distribution Jev returns for each rating, which happens to be what Kiln's existing logprob scoring path approximates. When it ships:

- A new model-entry flag `supports_probability_scores: bool = False` on `KilnModelProvider`, set `True` for Jev, exposed on the API's `ModelDetails`. `supports_logprobs` keeps its literal meaning (token logprobs) and stays `False` for Jev.
- The eval UI offers the probability-weighted option for a model with `supports_probability_scores`. Labelling and copy (the existing option is called "G-Eval", which is wrong for Jev) are decided in the UI design step.
- Availability becomes `supports_logprobs or supports_probability_scores` in the three places that check it: the judge form's default-algorithm logic, the model dropdown's `requires_logprobs` filter, and the V2 judge's `g_eval` guard.
- `RunOutput` gains an optional `answer_probabilities: dict[str, dict[str, float]]` field, keyed by property then output value (the same structure as `jev_probabilities`), populated only by the Jev adapter.
- Kiln's existing `build_g_eval_score` takes a fast path when `answer_probabilities` is present: each metric's score is `Σ p(value) × score(value)` over values that map through the existing `TOKEN_TO_SCORE_MAP` (`"1"`…`"5"`, `"pass"`, `"fail"`, `"critical"`), normalized by the summed probability of those values. This is the same estimator the logprob path computes. The logprob path is untouched for other models. Both the legacy and V2 judges call this function, so both get it. The stored config type stays `g_eval` for compatibility; only the presentation changes.
- The legacy path still passes `top_logprobs=10` in `AdapterConfig`; the Jev adapter ignores it.

## Error handling

All errors raised inside the adapter propagate through the existing `KilnRunError` wrapping, so the run page shows the message with any partial trace. Because `format_error_message` passes `ValueError` and `RuntimeError` text through verbatim and genericizes everything else, the adapter raises only those two families:

| Situation | Exception | Message |
|---|---|---|
| Compatibility or schema-mapping failure | `ValueError` | As specified above |
| Missing API key | `ValueError` (existing) | Kiln's existing provider check raises the standard `provider_warnings` message: `Attempted to use TypeSafe AI without an API key set. ...` The adapter runs this check itself before building the client, because a user-registry model resolves before the resolver's own check. |
| HTTP 401/403 | `JevApiError(RuntimeError)` | `Authentication with TypeSafe AI failed. Check your API key.` |
| HTTP 429 | `JevApiError` (retryable) | `TypeSafe AI rate limit exceeded. Wait a moment and try again.` |
| HTTP 422 | `JevApiError` | `TypeSafe AI rejected the request: ` + each `detail[].msg` joined with `; `, truncated to 500 chars (the raw body, also truncated, when it is not a FastAPI-style detail) |
| Other 4xx | `JevApiError` | `TypeSafe AI rejected the request (HTTP <code>): <body, truncated to 500 chars>` |
| 5xx | `JevApiError` (retryable) | `TypeSafe AI is currently unavailable. Try again in a moment.` |
| Timeout, or any other `httpx.RequestError` (connection failure, a proxy's mislabeled response encoding) | `JevApiError` (retryable) | `Could not connect to TypeSafe AI. Check your network connection.` A timeout adds ` (timed out)`. |
| Response missing an answer for a question, wrong answer type, a non-finite number, or an unparseable body | `RuntimeError` | `TypeSafe AI returned an unexpected response: <detail>`, with any value quoted from the response bounded |

Request timeout: 60 seconds total (Jev responds in well under a second; the generous value covers large states).

The API key is never included in error messages or logs.

## Configuration and defaults

- `Config.typesafe_api_key`: the only new Kiln setting.
- No per-run options. Jev has no temperature or sampling controls.
- The standalone module exposes decoding options (noul threshold, default 0.5; maximum score levels, default 10; score decoding strategy, default highest probability). Kiln uses the defaults and does not surface them.

## Compatibility and constraints

- Python 3.10+ for `libs/core`. HTTP via the already-present `httpx` dependency, async client. No new runtime dependencies.
- Adding a value to `ModelProviderName` changes the OpenAPI schema; regenerate `app/web_ui/src/lib/api_schema.d.ts`.
- No changes to persisted file formats other than the two new optional `intermediate_outputs` keys, which existing readers ignore.

## Acceptance checks

1. Connect TypeSafe AI with a valid key; the provider shows connected and "Jev 1.13" appears in the run page model dropdown.
2. A task with output schema `{"rating": integer 1..5, "verdict": enum [pass, fail], "is_spam": boolean, "correctness": number 0..1}` runs and saves a run whose output validates, with `jev_probabilities` and `jev_confidence` in intermediate outputs, and the request for `correctness` carried criteria true "correctness" / false "inverse of correctness".
3. The same task with an added `summary: string` property fails before any network call with a message naming `summary` and the accepted shapes.
4. A run config with a tool attached fails with the tools message.
5. A legacy LLM-as-Judge eval and a V2 LLM Judge (g_eval off) configured with the Jev judge produce scores on a small eval set. The eval UI shows G-Eval disabled for Jev.
8. (Optional phase) With `supports_probability_scores` set, the eval UI offers probability-weighted scoring for Jev, and both the legacy and V2 judges in that mode produce non-integer scores where Jev's distribution is spread across ratings.
6. With an invalid key, connecting fails with the API's message and running fails with the authentication message.
7. `uv run ./checks.sh --agent-mode` passes, including the OpenAPI schema check. (The `TODO` on the model entry no longer gates the merge: it was deleted in Phase 8 — see "Model entry and release gating" above.)
