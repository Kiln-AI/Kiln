# Responses API: request and response shape, compared with Chat Completions

All OpenAI pages below were fetched on 2026-10-30 through their markdown twins (append `.md` to the page URL). OpenAI's docs pages carry no publish date; treat them as "current as of 2026-10-30".

## Endpoint and top-level shape

- `POST /v1/responses` replaces `POST /v1/chat/completions`. The migration guide frames it as "three related changes: send requests to `/v1/responses`, read output from a typed `output` array, and choose how your application will carry state between turns." ([Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- Input is `input` (a string, or an array of items) instead of `messages`. System or developer guidance can go in top-level `instructions` or stay as `system`/`developer` message items "when you need to preserve an existing transcript". ([migration guide, "Map Messages to Items"](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- Text-only chat message arrays are accepted as-is: "If you are not using functions or multimodal inputs, text-only message inputs are compatible from one API to the other" (the guide's example passes the same `[{role, content}]` list to both). ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- `instructions` is not inherited through `previous_response_id`: "When using along with `previous_response_id`, the instructions from a previous response will not be carried over to the next response." ([API reference, Create a model response](https://developers.openai.com/api/reference/resources/responses/methods/create))

### Messages vs Items

> "The input to, and result of, a call to Chat Completions is an array of Messages, while the Responses API uses Items. An Item is a union of many types, representing the range of possibilities of model actions. A `message` is a type of Item, as is a `function_call` or `function_call_output`. Unlike a Chat Completions Message, where many concerns are glued together into one object, Items are distinct from one another and better represent the basic unit of model context."
> — [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)

Mapping table, verbatim from the migration guide:

| Chat Completions concept | Responses mapping |
| --- | --- |
| `messages[]` | `input`, as a string or an array of input Items |
| System or developer guidance | Top-level `instructions`, or compatible message Items when you need to preserve an existing transcript |
| User message | An input message Item with `role: "user"` |
| Assistant message | An output message Item in `response.output`; pass it back in `input` if you manually manage state |
| Tool or function call | A `function_call` output Item |
| Tool or function result | A `function_call_output` input Item linked to the call with `call_id` |
| Multiple generations with `n` | Not available in Responses; make separate requests if you need multiple candidate outputs |

**Implication for Kiln (inference):** one Chat Completions assistant message that carries both `content` and `tool_calls` corresponds to several Responses items: zero or more `reasoning` items, zero or more `message` items, and one `function_call` item per call. Going the other way, a single Responses `output` array has to be folded back into one assistant message (with `content` plus `tool_calls`) to keep Kiln's chat-format trace.

## Response object

Example output from the migration guide (gpt-5.5):

```json
{
  "id": "resp_68af...",
  "object": "response",
  "created_at": 1756315696,
  "model": "gpt-5.5",
  "output": [
    { "id": "rs_68af...", "type": "reasoning", "content": [], "summary": [] },
    {
      "id": "msg_68af...",
      "type": "message",
      "status": "completed",
      "content": [
        { "type": "output_text", "annotations": [], "logprobs": [], "text": "Under a quilt of moonlight, ..." }
      ],
      "role": "assistant"
    }
  ]
}
```

- No `choices`. "In Chat Completions, you receive an array of `choices`, each containing a `message`. In Responses, you receive an array of Items labeled `output`." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- `output_text` is an SDK convenience helper, not a wire field: "The Responses SDK has an `output_text` helper, which the Chat Completions SDK does not have." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- The guide lists common migration errors, including "Reading `choices[0].message.content` instead of `response.output_text` or `response.output`" and "Treating every `output` entry as a message. Reasoning, tool, and function calls are separate Item types." ([migration guide, "Check common migration errors"](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- `status` is `completed`, `incomplete`, etc. `incomplete_details.reason` is one of `max_output_tokens`, `max_messages`, `content_filter`, `steered`. ([API reference, Returns](https://developers.openai.com/api/reference/resources/responses/methods/create))
- Running out of tokens is a status, not a finish reason: "If the generated tokens reach the context window limit or the `max_output_tokens` value you've set, you'll receive a response with a `status` of `incomplete` and `incomplete_details` with `reason` set to `max_output_tokens`. This might occur before any visible output tokens are produced." ([Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning))
- Refusals are a content part of the message item: `{"type": "refusal", "refusal": "I'm sorry, I cannot assist with that request."}` inside `output[].content`. ([Structured model outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs))
- Assistant `message` items carry an optional `phase` (`commentary` or `final_answer`). The reference says: "For models like `gpt-5.3-codex` and beyond, when sending follow-up requests, preserve and resend phase on all assistant messages — dropping it can degrade performance." ([API reference, ResponseOutputMessage](https://developers.openai.com/api/reference/resources/responses/methods/create)) See [reasoning-and-state.md](./reasoning-and-state.md#phase).

### Usage object

```json
"usage": {
  "input_tokens": 81,
  "input_tokens_details": { "cached_tokens": 0, "cache_write_tokens": 0 },
  "output_tokens": 1035,
  "output_tokens_details": { "reasoning_tokens": 832 },
  "total_tokens": 1116
}
```

Source: example response in the [API reference](https://developers.openai.com/api/reference/resources/responses/methods/create). Field names differ from Chat Completions (`prompt_tokens` / `completion_tokens` / `prompt_tokens_details` / `completion_tokens_details` in the [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)). For models that support `prompt_cache_options`, `input_tokens_details.cache_write_tokens_details` splits writes into `ttl_30m_tokens` and `ttl_12h_tokens`, and "`cached_tokens` counts billed reads and excludes tokens charged as writes". ([Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching))

## Function tools

### Definition shape

The two APIs tag function definitions differently:

> "1. In Chat Completions, function definitions are externally tagged. In Responses, they are internally tagged.
> 2. In Chat Completions, functions are non-strict by default. In Responses, omitting `strict` attempts strict mode; if the schema cannot be made compatible, Responses falls back to non-strict, best-effort function calling and returns the resolved tool with `strict: false`. To keep non-strict behavior in Responses explicitly, set `strict: false`."
> — [migration guide, "Update function definitions and outputs"](https://developers.openai.com/api/docs/guides/migrate-to-responses)

Chat Completions:

```json
{ "type": "function", "function": { "name": "get_weather", "description": "...", "strict": true, "parameters": { ... } } }
```

Responses:

```json
{ "type": "function", "name": "get_weather", "description": "...", "parameters": { ... } }
```

The function calling guide repeats the strict rule in more detail:

> "If you send `strict: true` and your schema does not meet the requirements above, the request will be rejected with details about the missing constraints. If you omit `strict`, the default depends on the API: Responses requests will attempt to normalize your schema into strict mode when possible, and will fall back to non-strict, best-effort function calling if the schema cannot be made compatible with strict mode. When fallback happens, the response tool will show `strict: false`. Chat Completions requests remain non-strict by default. To opt out of strict mode in Responses and keep non-strict, best-effort function calling, explicitly set `strict: false`."
> — [Function calling guide, "Strict mode"](https://developers.openai.com/api/docs/guides/function-calling)

Strict mode requirements: "`additionalProperties` must be set to `false` for each object in the `parameters`" and "All fields in `properties` must be marked as `required`." ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling))

The Chat Completions reference confirms the opposite default there: `FunctionDefinition.strict: optional boolean or null (default: false)`. ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))

The Responses reference lists the `Function` tool as `{ name, parameters, strict, type, allowed_callers, async, defer_loading, description, output_schema }`, with `strict: boolean or null` and `parameters: map[unknown] or null` (no "optional" marker on either, but both nullable). ([API reference, tools](https://developers.openai.com/api/reference/resources/responses/methods/create))

**Implication for Kiln (inference):** if Kiln moves tool definitions over without setting `strict`, OpenAI will try to make every tool strict. A schema that is not strict-compatible silently falls back to non-strict. A schema that is compatible becomes strictly enforced, which changes behavior from today (non-strict on Chat Completions). Sending `strict: false` explicitly preserves today's behavior; sending `strict: true` with an incompatible schema is a hard 400.

### Tool calls in the output: `function_call`

> "The response `output` array contains an entry with the `type` having a value of `function_call`. Each entry with a `call_id` (used later to submit the function result), `name`, and JSON-encoded `arguments`."
> — [function calling guide, "Handling function calls"](https://developers.openai.com/api/docs/guides/function-calling)

```json
{ "id": "fc_12345xyz", "call_id": "call_12345xyz", "type": "function_call", "name": "get_weather", "arguments": "{\"location\":\"Paris, France\"}" }
```

Two ids: `id` (`fc_...`, the item id) and `call_id` (`call_...`, the correlation id). Reference: `FunctionCall { arguments, call_id, name, type, id?, async?, caller?, namespace?, status? }`; `call_id: string` "The unique ID of the function tool call generated by the model." ([API reference](https://developers.openai.com/api/reference/resources/responses/methods/create))

"Since model responses can include zero, one, or multiple calls, it is best practice to assume there are several." ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling)) `parallel_tool_calls` defaults to `true` on both endpoints.

### Tool results: `function_call_output`

```json
{ "type": "function_call_output", "call_id": "call_12345xyz", "output": "{\"temperature\": 25}" }
```

- `output`: "string or array of ResponseInputTextContent or ResponseInputImageContent or ResponseInputFileContent", string `maxLength: 10485760`. ([API reference, FunctionCallOutput](https://developers.openai.com/api/reference/resources/responses/methods/create))
- `call_id`: `minLength: 1`, `maxLength: 64`. (same source)
- The guide's loop appends **all** of `response.output` to the next input, then appends one `function_call_output` per call: `input_list += response.output` then `input_list.append({"type": "function_call_output", "call_id": item.call_id, "output": ...})`. ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling))
- "Note that for reasoning models like GPT-5 or o4-mini, any reasoning items returned in model responses with tool calls must also be passed back with tool call outputs." (same source)
- Listed migration errors: "Sending a function result without the matching `call_id`" and "Dropping reasoning, function call, or function call output Items when manually carrying context into the next response." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))

**Mapping to chat format (inference):** Chat `tool_calls[i].id` ↔ Responses `call_id`; Chat `{"role": "tool", "tool_call_id": X, "content": ...}` ↔ Responses `{"type": "function_call_output", "call_id": X, "output": ...}`. The Responses `fc_...` item id has no Chat Completions counterpart; it is only needed when replaying items by id (see the `store: false` notes in [reasoning-and-state.md](./reasoning-and-state.md)).

### `tool_choice`

Same values as Chat Completions (`auto`, `required`, `none`), but forcing one function is flat: `{"type": "function", "name": "get_weather"}` (Chat nests under `function`). Responses adds `allowed_tools`: `{"type": "allowed_tools", "mode": "auto", "tools": [{"type": "function", "name": "get_weather"}]}`. ([function calling guide, "Tool choice"](https://developers.openai.com/api/docs/guides/function-calling))

## Structured outputs: `text.format`

> "In the Responses API, Structured Outputs definitions have moved from `response_format` to `text.format`"
> — [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)

Chat Completions nests the schema under `json_schema`; Responses flattens it:

```python
# Chat Completions
response_format={"type": "json_schema", "json_schema": {"name": "person", "strict": True, "schema": {...}}}
# Responses
text={"format": {"type": "json_schema", "name": "person", "strict": True, "schema": {...}}}
```

Reference details for `text.format` (`ResponseFormatTextJSONSchemaConfig`):

- `name: string`, required. "Must be a-z, A-Z, 0-9, or contain underscores and dashes, with a maximum length of 64."
- `schema: map[unknown]`, required.
- `description: optional string`.
- **`strict: optional boolean or null (default: false)`** "Whether to enable strict schema adherence when generating the output. If set to true, the model will always follow the exact schema defined in the `schema` field."
- The default format is `{ "type": "text" }`. `{ "type": "json_object" }` is the older JSON mode, "Not recommended for gpt-4o and newer models".
- `text.verbosity`: `low` / `medium` / `high`, default `medium` (Chat Completions has a top-level `verbosity`).

Source: [API reference, `text`](https://developers.openai.com/api/reference/resources/responses/methods/create).

**Note the asymmetry:** function tools default to "attempt strict" on Responses, but `text.format` json_schema defaults to `strict: false`. Every example in the structured outputs guide sets `"strict": true` explicitly. ([Structured model outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)) If Kiln relies on strict JSON output, it has to send `strict: true` in `text.format`.

"Note: the first request you make with any schema will have additional latency as our API processes the schema, but subsequent requests with the same schema will not have additional latency." ([structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs))

Listed migration error: "Using `response_format` in a Responses request instead of `text.format`." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))

## Parameter differences (from the two API references)

I diffed the body parameter lists of the two reference pages ([Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create), [Chat Completions create](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)) fetched 2026-10-30:

| Only in Chat Completions | Responses equivalent (if any) |
| --- | --- |
| `messages` | `input` (+ optional `instructions`) |
| `reasoning_effort` | `reasoning.effort` |
| `response_format` | `text.format` |
| `verbosity` | `text.verbosity` |
| `max_completion_tokens`, `max_tokens` | `max_output_tokens` (`minimum: 16`) |
| `logprobs` (bool) | `include: ["message.output_text.logprobs"]` plus `top_logprobs` |
| `n` | none: "The Responses API omits this parameter and returns only one generation." |
| `stop`, `seed`, `frequency_penalty`, `presence_penalty`, `logit_bias`, `prediction` | none found in the Responses reference |
| `modalities`, `audio` | none ("Audio: Coming soon" in the migration guide's capability table) |
| `web_search_options` | `tools: [{"type": "web_search"}]` |
| `functions`, `function_call` (legacy) | `tools`, `tool_choice` |

| Only in Responses | Purpose |
| --- | --- |
| `input`, `instructions` | prompt |
| `reasoning` (`effort`, `summary`, `mode`, `context`, deprecated `generate_summary`) | reasoning controls |
| `text` (`format`, `verbosity`) | output format |
| `include` | extra output data, e.g. `reasoning.encrypted_content`, `message.output_text.logprobs` |
| `previous_response_id`, `conversation` | server-side state |
| `background`, `context_management`, `truncation` (default `disabled`), `max_tool_calls`, `prompt`, `access_programs` | other features |

Shared: `model`, `store`, `stream`, `stream_options`, `temperature`, `top_p`, `top_logprobs`, `tools`, `tool_choice`, `parallel_tool_calls`, `metadata`, `moderation`, `prompt_cache_key`, `prompt_cache_options`, `prompt_cache_retention` (deprecated), `safety_identifier`, `service_tier`, `user` (deprecated). Note `store` has different documented defaults on the two endpoints; see [data-retention-caching-pricing.md](./data-retention-caching-pricing.md).

### Parameters that reasoning models reject

- GPT-5.4: "The following parameters are only supported when using GPT-5.4 with reasoning effort set to `none`: `temperature`, `top_p`, `logprobs`. Requests that include these fields will raise an error for GPT-5.4 or GPT-5.2 with any other reasoning effort setting, or for older GPT-5 models such as `gpt-5`, `gpt-5-mini`, or `gpt-5-nano`." ([Using GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.4))
- GPT-6 family: "When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`. For Chat Completions, also remove `logprobs`. For Responses, remove `message.output_text.logprobs` from `include`." ([Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra))
- GPT-6 Astra: "does not support custom `temperature` or `top_p` values or log probabilities (`logprobs`)" ([API changelog, Sep 3 2026](https://developers.openai.com/api/docs/changelog)). Astra has no `none` effort, so these are never available on it.

These limits are the same on both endpoints; they are a model restriction, not an endpoint one.

## Things the docs say will break naive migrations

From the migration guide's "Check common migration errors" list, verbatim:

- Reading `choices[0].message.content` instead of `response.output_text` or `response.output`.
- Treating every `output` entry as a message. Reasoning, tool, and function calls are separate Item types.
- Dropping reasoning, function call, or function call output Items when manually carrying context into the next response.
- Sending a function result without the matching `call_id`.
- Using `response_format` in a Responses request instead of `text.format`.
- Reusing Chat Completions streaming chunk handlers without handling typed Responses events.
- Assuming `previous_response_id` removes billing for prior context. Previous input tokens in the response chain are still billed as input tokens.

Source: [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses).
