# API shape differences (beyond reasoning)

Primary sources, read 2026-10-05:
- [Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses) (the "migration guide")
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling.md), [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs.md), [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state.md)
- `openai-python` 3.24.0 generated types: [Responses create params](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_create_params.py), [Chat create params](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/completion_create_params.py), [stream events](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_stream_event.py)

## Input and output model

| Concern | Chat Completions | Responses |
|---|---|---|
| Input | `messages[]` | `input`: a string or a list of typed Items, plus an optional top-level `instructions` |
| Output | `choices[i].message` | `output[]`: typed Items (`reasoning`, `message`, `function_call`, built-in tool calls, ...). The SDK has an `output_text` helper |
| Multiple generations | `n` | **Not available**: "make separate requests if you need multiple candidate outputs" |
| System prompt | system/developer message | `instructions`, or a system/developer message Item. "`previous_response_id` does not carry over the previous response's top-level `instructions`" |
| Truncation | none (an oversized request errors) | `truncation: "auto" \| "disabled"` (default `disabled`, which returns a 400 on overflow) |
| Long jobs | none | `background: true` (recommended for pro models) |

Migration guide mapping table (verbatim rows):

| Chat Completions concept | Responses mapping |
| --- | --- |
| `messages[]` | `input`, as a string or an array of input Items |
| Assistant message | An output message Item in `response.output`; pass it back in `input` if you manually manage state |
| Tool or function call | A `function_call` output Item |
| Tool or function result | A `function_call_output` input Item linked to the call with `call_id` |
| Multiple generations with `n` | Not available in Responses; make separate requests if you need multiple candidate outputs |

Migration guide on why this matters for reasoning: "Treating every `output` entry as a message" and "Dropping reasoning, function call, or function call output Items when manually carrying context into the next response" are listed as common migration errors.

## Structured output

- Chat Completions: `response_format: {type: "json_schema", json_schema: {name, schema, strict}}` or `{type: "json_object"}`.
- Responses: `text: {format: {type: "json_schema", name, schema, strict, description}}`. The schema is *flattened*: `name`, `schema` and `strict` sit directly in `format`, with no nested `json_schema` key ([ResponseFormatTextJSONSchemaConfigParam](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_format_text_json_schema_config_param.py)). `text.verbosity` sits beside it.
- Migration guide: "Structured Outputs API shape is different. Instead of `response_format`, use `text.format` in Responses." A listed common error is "Using `response_format` in a Responses request instead of `text.format`."
- Capability parity: "Both Structured Outputs and JSON mode are supported in the Responses API, Chat Completions API, Assistants API, Fine-tuning API and Batch API." ([structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs.md))

## Tool calling

- Definition shape. Migration guide: "In Chat Completions, function definitions are externally tagged. In Responses, they are internally tagged." Chat Completions uses `{type:"function", function:{name, description, parameters, strict}}`. Responses uses `{type:"function", name, description, parameters, strict}` ([FunctionToolParam](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/function_tool_param.py)). The newer Responses-only fields are `async`, `allowed_callers`, `defer_loading` and `output_schema`.
- **Strict default differs.** Migration guide: "In Chat Completions, functions are non-strict by default. In Responses, omitting `strict` attempts strict mode; if the schema cannot be made compatible, Responses falls back to non-strict, best-effort function calling and returns the resolved tool with `strict: false`. To keep non-strict behavior in Responses explicitly, set `strict: false`." The function calling guide repeats this: "Chat Completions requests remain non-strict by default."
- Call and result shape. Responses emits a `function_call` item with `call_id`, `name` and `arguments` (a JSON string) ([ResponseFunctionToolCall](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_function_tool_call.py)). The result goes back as an input item `{type:"function_call_output", call_id, output}`. There is no `role: "tool"` message.
- Built-in tools (web search, file search, code interpreter, computer use, hosted shell, apply patch, image generation, remote MCP, tool search, skills, programmatic tool calling) are Responses-only. Migration guide: "With Chat Completions, you cannot use OpenAI-hosted tools natively and have to write your own tool integration." (Chat Completions does have its own `web_search_options` for the search-preview models, which is a separate thing.)
- **Reasoning with function tools.** Starting with GPT-5.4, this combination is blocked on Chat Completions. GPT-6 Astra and 6.1 Sol have no Chat Completions tool calling at all. See [reasoning-control.md §4](./reasoning-control.md).

## Logprobs

- Chat Completions: `logprobs: true` plus `top_logprobs: N`. They are returned on `choices[i].logprobs`.
- Responses: `include: ["message.output_text.logprobs"]` plus `top_logprobs: N` (0 to 20). They are returned on `output_text` content parts (the migration guide's sample output shows `"logprobs": []` on each `output_text` part).
- In both APIs, logprobs are unsupported when reasoning effort is not `none`. Latest-model guide: "When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`. For Chat Completions, also remove `logprobs`. For Responses, remove `message.output_text.logprobs` from `include`."

## Streaming

- Chat Completions: SSE chunks of `chat.completion.chunk` with `choices[i].delta` (`content`, `tool_calls[i].function.arguments` fragments), ending with `data: [DONE]`. Usage arrives only when `stream_options.include_usage: true`, in "an additional chunk ... before the `data: [DONE]` message" whose `choices` is empty. The SDK docstring warns: "If the stream is interrupted, you may not receive the final usage chunk" ([stream options](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/chat_completion_stream_options_param.py)).
- Responses: typed semantic events. Migration guide: "Responses streaming uses typed server-sent events. Update stream consumers to branch on each event's `type`". The core events are `response.created`, `response.output_text.delta`, `response.completed` and `error`. Function-call streams add `response.function_call_arguments.delta` / `.done`.
- The full event union in the SDK (`ResponseStreamEvent`) also includes: `response.in_progress`, `response.queued`, `response.incomplete`, `response.failed`, `response.output_item.added` / `.done`, `response.content_part.added` / `.done`, `response.output_text.done`, `response.output_text.annotation.added`, `response.refusal.delta` / `.done`, **`response.reasoning_summary_part.added` / `.done`, `response.reasoning_summary_text.delta` / `.done`, `response.reasoning_text.delta` / `.done`**, custom-tool input deltas, and per-built-in-tool progress events (web search, file search, code interpreter, image gen, MCP, shell), plus `response.compaction.compacting`.
- Usage in streaming Responses comes on the final `response.completed` event's `response.usage` (inferred from the Response object shape; no extra opt-in parameter exists in the params type).
- Encrypted reasoning while streaming: take it from `response.output_item.done`, not `.added` (SDK docstring on `ResponseReasoningItem.encrypted_content`).

## Usage / token reporting

| | Chat Completions (`CompletionUsage`) | Responses (`ResponseUsage`) |
|---|---|---|
| Input | `prompt_tokens` | `input_tokens` |
| Output | `completion_tokens` | `output_tokens` |
| Total | `total_tokens` | `total_tokens` |
| Cached input | `prompt_tokens_details.cached_tokens` | `input_tokens_details.cached_tokens` |
| Cache writes | `prompt_tokens_details.cache_write_tokens` | `input_tokens_details.cache_write_tokens` |
| Reasoning | `completion_tokens_details.reasoning_tokens` | `output_tokens_details.reasoning_tokens` |
| Other | audio/image/text token splits, accepted/rejected prediction tokens | none |

Sources: [completion_usage.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/completion_usage.py), [response_usage.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_usage.py). The information is the same; only the field names differ. Cache-write tokens matter for GPT-5.6 and later, which bill cache writes at 1.25 times the input rate ([latest-model guide](https://developers.openai.com/api/docs/guides/latest-model)).

Truncation by token limit also reports differently. Chat Completions uses `finish_reason: "length"`. Responses uses `status: "incomplete"` with `incomplete_details.reason: "max_output_tokens"` ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). The token cap is `max_completion_tokens` in Chat Completions and `max_output_tokens` in Responses.

## Statefulness and `store`

- **Defaults.** Migration guide: "Responses are stored by default. Chat completions are stored by default for new accounts. To disable storage when using either API, set `store: false`." SDK docstring for Responses `store`: "Defaults to true when omitted. If set to true, response data will be stored for at least 30 days". Conversation-state guide: "Response objects are saved for 30 days by default."
- **Chaining.** `previous_response_id` reuses server-held context. Billing does not change: "Even when using `previous_response_id`, all previous input tokens for responses in the chain are billed as input tokens in the API." `previous_response_id` "Cannot be used in conjunction with `conversation`". There is also a Conversations API (`conversation` param) for persistent threads.
- **Stateless use is fully supported.** The migration guide lists three state options: `previous_response_id`, "Pass prior `output` Items back into the next request when you need to manage or trim context yourself", or Conversations. For stateless or ZDR use: "Set `store: false` ... Preserve and replay every returned reasoning item. Each item includes `encrypted_content` by default when you create a response." Also: "For ZDR organizations, OpenAI enforces `store: false` automatically." The rollout checklist adds: "If the flow is stateless or ZDR, add `store: false` and include encrypted reasoning items when reasoning context must continue across turns."
- **What stateless costs you.** You must replay *every* output item: reasoning items (with `encrypted_content`), function calls, and assistant messages with their `phase`. Persisted reasoning works only within one model family ("reasoning does not carry between the GPT-5.6 and GPT-5.5 families"). Stateless use loses nothing in capability, but the client has to keep more state. A stateless client that stores only visible text gets roughly Chat Completions-level reasoning continuity.

## OpenAI's own claims about performance (unverified marketing figures)

Migration guide, "Responses benefits":
- "Using reasoning models, like GPT-5, with Responses will result in better model intelligence when compared to Chat Completions. Our internal evals reveal a 3% improvement in SWE-bench with same prompt and setup."
- "Lower costs: Results in lower costs due to improved cache utilization (40% to 80% improvement when compared to Chat Completions in internal tests)."
- The reasoning guide adds: "Reasoning models work better with the Responses API. While the Chat Completions API is still supported, you'll get improved model intelligence and performance by using Responses."
