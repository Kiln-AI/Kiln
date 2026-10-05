# Reasoning control: Chat Completions vs Responses

All OpenAI docs below were read on 2026-10-05 through Tavily extract. `developers.openai.com` is blocked by this session's proxy, so direct fetches failed. The OpenAI docs pages carry no publish date; treat them as "live as of 2026-10-05". SDK quotes are from `openai/openai-python` `main` at version `3.24.0` ([_version.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/_version.py)). Its types are generated from OpenAI's OpenAPI spec.

## 1. Parameter shape

| | Chat Completions (`POST /v1/chat/completions`) | Responses (`POST /v1/responses`) |
|---|---|---|
| Effort | flat `reasoning_effort: "<value>"` | `reasoning: {effort: "<value>"}` |
| Summary of reasoning | **not available**: no request field, and no response field to carry it | `reasoning: {summary: "auto" \| "concise" \| "detailed"}` |
| Pro execution mode | **not available** | `reasoning: {mode: "standard" \| "pro"}` (GPT-5.6 / GPT-6 families) |
| Cross-turn reasoning rendering | **not available** | `reasoning: {context: "auto" \| "current_turn" \| "all_turns"}` |
| Encrypted reasoning for stateless replay | **not available** | `encrypted_content` on `reasoning` output items (default in stateless mode); legacy `include: ["reasoning.encrypted_content"]` |
| Mid-conversation effort change | **not available** | `configuration_update` input item (GPT-6 family) |

Evidence:

- Chat Completions request params in the SDK ([completion_create_params.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/completion_create_params.py)) have `reasoning_effort: Optional[ReasoningEffort]` and `verbosity`. They have no `reasoning` object, no summary, no mode and no context field.
- The Chat Completions assistant message type ([chat_completion_message.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/chat_completion_message.py)) has these fields: `content, refusal, role, annotations, audio, function_call, tool_calls`. **It has no reasoning or summary field**, so Chat Completions returns no reasoning text of any kind. Only the count shows up, as `usage.completion_tokens_details.reasoning_tokens`.
- The shared `Reasoning` type used by Responses ([reasoning.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/shared/reasoning.py)) has `context`, `effort`, `generate_summary` (deprecated), `mode` and `summary`.
- The migration guide says it directly: "Use `reasoning.effort` in Responses or `reasoning_effort` in Chat Completions." ([latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), GPT-6 migration section)

## 2. Effort values

The SDK enum, shared by both APIs ([reasoning_effort.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/shared/reasoning_effort.py)):

```python
ReasoningEffort: TypeAlias = Optional[Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]]
```

The docstring is the same on both `reasoning_effort` (Chat Completions) and `Reasoning.effort` (Responses): "Currently supported values are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`. ... Not all reasoning models support every value."

From the [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning):

> "Supported values are model-dependent and can include `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`."

> "Some models support only a subset of these values, so check the relevant model page before choosing a setting."

> "GPT-6 Astra does not support `none` reasoning effort. Setting `reasoning.effort` (Responses) or `reasoning_effort` (Chat Completions) to `none` returns HTTP 400. GPT-6.1 Sol does not support `none` or `minimal` and defaults to `medium`."

**The value set is the same in both APIs.** Neither API accepts an effort value that the other rejects. The differences are elsewhere: which models each endpoint serves, and which feature combinations each allows (see section 4).

Per-model accepted values and defaults are in [model-matrix.md](./model-matrix.md).

## 3. Reasoning features that exist only in Responses

### Reasoning summaries
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#reasoning-summaries):

> "While we don't expose the raw reasoning tokens emitted by the model, you can view a summary of the model's reasoning using the `summary` parameter."

> "Different models support different reasoning summary settings. For example, our computer use model supports the `concise` summarizer, while o4-mini supports `detailed`. To access the most detailed summarizer available for a model, set the value of this parameter to `auto`."

> "Reasoning summary output is part of the `summary` array in the `reasoning` output item. This output will not be included unless you explicitly opt in to including reasoning summaries."

> "Before using summarizers with our latest reasoning models, you may need to complete organization verification..."

From the SDK docstring: "`concise` is supported for `computer-use-preview` models and all reasoning models after `gpt-5`."

The [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses) capability table lists "Reasoning summaries" as a row. The extracted copy lost the check marks. Together with the missing message field above, this places summaries in Responses only.

The Responses reasoning item ([response_reasoning_item.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_reasoning_item.py)) has `summary: List[{type:"summary_text", text}]`, an optional `content: List[{type:"reasoning_text", text}]`, and an optional `encrypted_content`. Streaming adds `response.reasoning_summary_text.delta` and `response.reasoning_text.delta` events (see [api-differences.md](./api-differences.md)).

### Pro mode (`reasoning.mode`)
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#reasoning-mode):

> "GPT-5.6 and GPT-6 models support `standard` and `pro` reasoning modes in the Responses API. `standard` is the default. Set `reasoning.mode` to `pro` for difficult tasks..."

> "Reasoning mode and reasoning effort are independent."

> "Existing Pro model IDs keep their current behavior and pricing."

[Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), GPT-5.6 section: "To use pro mode, keep your selected GPT-5.6 model and set `reasoning.mode` to `pro` in the Responses API; do not switch to a separate Pro model slug."

The [deprecations page](https://developers.openai.com/api/docs/deprecations.md) now names `gpt-5.6-sol` (`reasoning.mode: pro`) as the replacement for `o1-pro` (shutdown 2026-10-23), `o3-pro` and `gpt-5-pro` (shutdown 2026-12-11). Pro capability is moving from separate model IDs to a parameter that exists only in Responses.

### Persisted reasoning across turns (`reasoning.context`)
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#preserve-reasoning-across-calls):

> "For models released before GPT-5.6, the default behavior in a multi-step conversation is to carry over input and output tokens from each step without rendering reasoning from earlier turns into the next sample. GPT-5.6 models instead default to rendering available reasoning from earlier turns."

> `all_turns`: "Renders available, compatible reasoning items from earlier turns into the next sample. GPT-5.6 models and GPT-6.1 Sol support this value."

> "Persisted reasoning can be reused only within the same model family."

### Encrypted reasoning (stateless reasoning continuity)
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#preserve-reasoning-without-stored-responses):

> "When you create a response in stateless mode, reasoning items in the response's `output` array include an `encrypted_content` property by default. Stateless mode applies when `store` is `false` or when your organization uses Zero Data Retention (ZDR). The API still accepts the legacy `reasoning.encrypted_content` value in `include` for compatibility, but doesn't require it."

The SDK docstring is broader. It says `encrypted_content` "is populated by default for reasoning items returned by `POST /v1/responses` and WebSocket `response.create` requests. When streaming, use the completed reasoning item and its `encrypted_content` from the `response.output_item.done` event ... The `encrypted_content` in `response.output_item.added` may be incomplete."

The [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses) step 4 explains why this matters: "When a request includes `encrypted_content`, it is decrypted in memory, used for generating the next response, and then securely discarded."

### Keeping reasoning items with function calls
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#keeping-reasoning-items-in-context):

> "When doing function calling with a reasoning model in the Responses API, we highly recommend you pass back any reasoning items returned with the last function call (in addition to the output of your function). If the model calls multiple functions consecutively, you should pass back all reasoning items, function call items, and function call output items, since the last `user` message."

Chat Completions has no reasoning item to pass back. In a Chat Completions tool loop, the model's reasoning is always lost between calls.

### `phase` on assistant messages
[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) (`phase` parameter section): "For long-running or tool-heavy flows with GPT-5.5 and GPT-5.4 in the Responses API, use the assistant message `phase` field to avoid early stopping and other misbehavior. ... Missing or dropped `phase` can cause preambles to be treated as final answers in those workflows."

### `configuration_update` (change effort mid-conversation)
The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#change-reasoning-mid-conversation) says this is "supported by the GPT-6 model family in standard, single-agent mode." It is an input item, so it exists only in Responses.

## 4. Reasoning combined with function tools: the Chat Completions restriction

This is the most important finding for the "can't set thinking level" claim.

[Migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses), "Additional differences":

> "Reasoning models have a richer experience in the Responses API with improved tool usage. **Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`.**"

[Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), GPT-6 migration:

> "**Tool calling:** Use the Responses API. GPT-6 Astra and GPT-6.1 Sol support Chat Completions, but tool calling requires Responses. GPT-6 Sol and GPT-6 Luna support function calling in Chat Completions only with `reasoning_effort: "none"`. Use Responses for reasoning with tools."

[Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#reasoning-effort): "Use the Responses API for function calling. Chat Completions does not support function calling with GPT-6 Astra or GPT-6.1 Sol."

[Function calling guide](https://developers.openai.com/api/docs/guides/function-calling.md): "GPT-6 Astra requires the Responses API for tool calling. The Chat Completions examples use GPT-5.6 for compatibility."

The model pages for [gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol.md) and [gpt-6-luna](https://developers.openai.com/api/docs/models/gpt-6-luna.md) say: "Use the Responses API for built-in tools and function calling. Chat Completions supports function calling only with `reasoning_effort` set to `none`." The [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol.md) page says: "Use the Responses API for tool calling. Chat Completions is supported without tool calling."

**The pages disagree on GPT-5.4, 5.5 and 5.6.** The model pages for [gpt-5.4](https://developers.openai.com/api/docs/models/gpt-5.4.md), [gpt-5.5](https://developers.openai.com/api/docs/models/gpt-5.5.md), [gpt-5.6-sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol.md) and the other GPT-5.6 models do *not* state the restriction. They list Chat Completions and `function_calling` as "Supported". Only the migration guide's "Starting with GPT-5.4" sentence and the observed error messages establish it.

### The error, as reported in the field
Several independent bug reports quote OpenAI's 400 response verbatim.

- [pipecat-ai/pipecat#4043](https://github.com/pipecat-ai/pipecat/issues/4043), opened 2026-03-16 (11 days after GPT-5.4 shipped on 2026-03-05):
  `'Function tools with reasoning_effort are not supported for gpt-5.4 in /v1/chat/completions. Please use /v1/responses instead.'`, `type: invalid_request_error`, `param: reasoning_effort`
- [TauricResearch/TradingAgents#403](https://github.com/TauricResearch/TradingAgents/issues/403): same message for `gpt-5.4`.
- [microsoft/vscode#318969](https://github.com/microsoft/vscode/issues/318969) and [crmne/ruby_llm#785](https://github.com/crmne/ruby_llm/issues/785): same message for `gpt-5.5`.
- [OpenAI community thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454), 2026-07-11, and [LibreChat#14231](https://github.com/danny-avila/LibreChat/issues/14231): the newer wording, `Function tools with reasoning_effort are not supported for gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.` (also seen for `gpt-5.6-terra`). A forum regular wrote: "Blocking developer functions on reasoning models started with gpt-5.4." The thread was closed by OpenAI staff on Sep 7, and the extract shows no reversal.
- [frigate discussion #24555](https://github.com/blakeblackshear/frigate/discussions/24555): the same error for `gpt-6-sol`, `gpt-5.6-luna` and `gpt-6.1-sol`.

A third-party gateway doc, [APIYI "Migrating GPT-5.4+ to Responses"](https://docs.apiyi.com/en/api-capabilities/openai/responses-migration.md), reports test results. **This is a secondary source and is not verified against OpenAI docs.** It says:
- "All four of `low`, `medium`, `high` and `xhigh` trigger it in our tests. **Omitting `reasoning_effort` does not trigger it.**"
- Requests without `tools` are unaffected.
- `gpt-5.2` / `gpt-5.1` / `gpt-5` and earlier are "Not covered by the official announcement".
- Symptom 3: "no error, but the tool is never called" on some routes.

`ruby_llm#785` claims that gpt-5, gpt-5.1, gpt-5.2 and the o-series also reject the combination. That conflicts with OpenAI's "Starting with GPT-5.4" wording. I found no other evidence for it, so treat it as **unverified**.

### What the restriction does *not* cover (per docs)
- Requests with no `tools`. Effort works on Chat Completions for every model that Chat Completions serves.
- Structured output through `response_format: {type: "json_schema"}`. No doc restricts it with reasoning. The [structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs.md) says: "Both Structured Outputs and JSON mode are supported in the Responses API, Chat Completions API, ..."
- Note: **structured output implemented *as a forced function/tool call*** is a tool call, so it *is* covered.

## 5. Sampling parameters and reasoning (both APIs)

[Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), GPT-6 migration:

> "**Unsupported parameters:** When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`. For Chat Completions, also remove `logprobs`. For Responses, remove `message.output_text.logprobs` from `include`."

So logprobs and reasoning do not mix in either API. This is not a difference between the two.

## 6. Usage reporting of reasoning tokens

Both APIs report a reasoning-token count:
- Chat Completions: `usage.completion_tokens_details.reasoning_tokens` ([completion_usage.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/completion_usage.py))
- Responses: `usage.output_tokens_details.reasoning_tokens` ([response_usage.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_usage.py))

Reasoning guide: "While reasoning tokens are not visible via the API, they still occupy space in the model's context window and are billed as output tokens." Also: "If the generated tokens reach the context window limit or the `max_output_tokens` value you've set, you'll receive a response with a `status` of `incomplete` and `incomplete_details` with `reason` set to `max_output_tokens`. This might occur before any visible output tokens are produced". Pro mode "aggregates the model work performed to produce the final answer" into reported usage.
