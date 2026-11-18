# Responses API streaming

Fetched 2026-10-30. The full streaming-events reference page is too large to fetch whole (the tool truncated it after the first event), so event fields below come from targeted extracts of [Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events), the guides, and the generated event union in the official Python SDK ([`response_stream_event.py`](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_stream_event.py), `main` branch, fetched 2026-10-30).

## Model: typed server-sent events, not chunks

> "Chat Completions streaming returns incremental chunks with a `delta` field. Responses streaming uses typed server-sent events. Update stream consumers to branch on each event's `type` and handle the events your UI or orchestration layer needs."
> — [migration guide, "Update streaming consumers"](https://developers.openai.com/api/docs/guides/migrate-to-responses)

> "The Responses API uses semantic events for streaming. Each event is typed with a predefined schema, so you can listen for events you care about."
> — [Streaming API responses guide](https://developers.openai.com/api/docs/guides/streaming-responses)

Every event carries `type` and `sequence_number`. Item-scoped events also carry `output_index` (position of the item in `response.output`) and `item_id`. Content-scoped events add `content_index`; reasoning-summary events add `summary_index`.

OpenAI lists "Adding new event types in streaming APIs" as a backwards-compatible change ([API Overview](https://developers.openai.com/api/reference/overview)). A consumer must ignore unknown event types rather than fail.

## Event types

The Python SDK's `ResponseStreamEvent` union (generated from the OpenAPI spec) has these members. Names map to wire `type` strings in the obvious way (`ResponseTextDeltaEvent` is `response.output_text.delta`).

Lifecycle: `response.created`, `response.queued`, `response.in_progress`, `response.completed`, `response.incomplete`, `response.failed`, `error`.

Item and content assembly: `response.output_item.added`, `response.output_item.done`, `response.content_part.added`, `response.content_part.done`, `response.output_text.delta`, `response.output_text.done`, `response.output_text.annotation.added`, `response.refusal.delta`, `response.refusal.done`.

Function tools: `response.function_call_arguments.delta`, `response.function_call_arguments.done`. Custom tools: `response.custom_tool_call_input.delta` / `.done`.

Reasoning: `response.reasoning_summary_part.added`, `response.reasoning_summary_part.done`, `response.reasoning_summary_text.delta`, `response.reasoning_summary_text.done`, `response.reasoning_text.delta`, `response.reasoning_text.done`.

Built-in tools and other: web search, file search, code interpreter, image generation, MCP, shell, audio, and `response.compaction.compacting` events.

Source: [openai-python `response_stream_event.py`](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_stream_event.py). OpenAI's guide lists a shorter subset and says "Common events to listen for when streaming text are: `response.created`, `response.output_text.delta`, `response.completed`, `error`." ([streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses))

## Payload shapes that matter for Kiln

### Text

```json
{ "type": "response.output_text.delta", "item_id": "msg_123", "output_index": 0, "content_index": 0, "delta": "In", "sequence_number": 1, "logprobs": [] }
{ "type": "response.output_text.done",  "item_id": "msg_123", "output_index": 0, "content_index": 0, "text": "In a shimmering forest ...", "sequence_number": 1, "logprobs": [] }
```

Source: [streaming events reference](https://developers.openai.com/api/reference/resources/responses/streaming-events).

### Function calls

From the function calling guide:

```json
{"type":"response.output_item.added","response_id":"resp_1234xyz","output_index":0,"item":{"type":"function_call","id":"fc_1234xyz","call_id":"call_1234xyz","name":"get_weather","arguments":""}}
{"type":"response.function_call_arguments.delta","response_id":"resp_1234xyz","item_id":"fc_1234xyz","output_index":0,"delta":"{\""}
...
{"type":"response.function_call_arguments.done","response_id":"resp_1234xyz","item_id":"fc_1234xyz","output_index":0,"arguments":"{\"location\":\"Paris, France\"}"}
{"type":"response.output_item.done","response_id":"resp_1234xyz","output_index":0,"item":{"type":"function_call","id":"fc_1234xyz","call_id":"call_1234xyz","name":"get_weather","arguments":"{\"location\":\"Paris, France\"}"}}
```

- The function name and `call_id` arrive once, on `response.output_item.added`. Argument deltas carry only `item_id` / `output_index`. ([Function calling guide, "Streaming"](https://developers.openai.com/api/docs/guides/function-calling))
- The guide's accumulator keys by `output_index`: `final_tool_calls[event.output_index] = event.item` on `output_item.added`, then `final_tool_calls[index].arguments += event.delta`.
- **Inference for Kiln:** `output_index` counts all output items (reasoning, message, function_call), so it is not the same as a Chat Completions `tool_calls[].index`. A translation to `ModelResponseStream` chunks has to keep its own counter of function-call items to produce a 0-based tool-call index, and must never use `output_index` (or `summary_index`) as a `choices` index.

### Reasoning summaries

```json
{ "type": "response.reasoning_summary_text.delta", "item_id": "rs_6806...", "output_index": 0, "summary_index": 0, "delta": "Responding to a greeting\n\n...", "sequence_number": 1 }
```

Field definitions, verbatim from the reference: `output_index`: "The index of the output item this summary text delta is associated with." `summary_index`: "The index of the summary part within the reasoning summary." ([streaming events reference](https://developers.openai.com/api/reference/resources/responses/streaming-events))

Sequence for a reasoning item with summaries (third-party summary consistent with the reference): `response.output_item.added` (item type `reasoning`), then per part `response.reasoning_summary_part.added`, `response.reasoning_summary_text.delta` (many), `response.reasoning_summary_text.done`, `response.reasoning_summary_part.done`, then `response.output_item.done`. ([OpenAI community "simple guide to events"](https://community.openai.com/t/responses-api-streaming-the-simple-guide-to-events/1363122/1), community post, not OpenAI docs)

A reasoning item can have several summary parts (`summary_index` 0, 1, 2...). Each part is a separate block of text; consumers that want one string have to join parts themselves (inference; the separator is up to the client).

### Encrypted reasoning while streaming

> "When streaming, use the completed reasoning item and its `encrypted_content` from the `response.output_item.done` event in subsequent requests. The `encrypted_content` in `response.output_item.added` may be incomplete."
> — [API reference, `Reasoning.encrypted_content`](https://developers.openai.com/api/reference/resources/responses/methods/create)

### Completion, usage, and errors

- `response.completed` carries the full `response` object (`id`, `output`, `usage`, ...). ([streaming events reference](https://developers.openai.com/api/reference/resources/responses/streaming-events)) The API reference's streaming example ends with a `response.completed` whose `response.usage` holds `input_tokens`, `input_tokens_details.cached_tokens`, `input_tokens_details.cache_write_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`, `total_tokens`. ([API reference example](https://developers.openai.com/api/reference/resources/responses/methods/create))
- Usage appears only at the end. A community guide puts it as: "True token usage is only present in response.completed" and "If you see response.incomplete or response.failed, stop assembling". (community post, [link](https://community.openai.com/t/responses-api-streaming-the-simple-guide-to-events/1363122/1)) Chat Completions instead needs `stream_options.include_usage` to get a final usage chunk ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)).
- A truncated stream ends with `response.incomplete` (not `response.completed`), with `incomplete_details.reason` on the response (inference from the response object schema and event list).
- Errors can arrive mid-stream as an `error` event. The misalignment-monitoring guide warns: "Streaming integrations must also handle errors while consuming the stream, even after receiving output." ([Misalignment monitoring](https://developers.openai.com/api/docs/guides/safety-checks/misalignment-monitoring))

### Stream obfuscation

`stream_options.include_obfuscation`: "Stream obfuscation adds random characters to an `obfuscation` field on streaming delta events to normalize payload sizes as a mitigation to certain side-channel attacks. These obfuscation fields are included by default... You can set `include_obfuscation` to false to optimize for bandwidth if you trust the network links." ([API reference, `stream_options`](https://developers.openai.com/api/reference/resources/responses/methods/create)) The same option exists on Chat Completions. Consumers must not treat `obfuscation` as content.

## Contrast with Chat Completions chunks (for the Kiln translation layer)

| Concern | Chat Completions chunk | Responses event |
| --- | --- | --- |
| Text | `choices[0].delta.content` | `response.output_text.delta.delta` (keyed by `item_id`, `content_index`) |
| Tool call start | `delta.tool_calls[i]` with `id`, `function.name` | `response.output_item.added` with `item.type == "function_call"`, `call_id`, `name` |
| Tool call args | `delta.tool_calls[i].function.arguments` | `response.function_call_arguments.delta` keyed by `item_id` / `output_index` |
| Reasoning text | none from OpenAI | `response.reasoning_summary_text.delta` (summaries), `response.reasoning_text.delta` |
| Finish | `finish_reason` on last choice | `response.completed` / `response.incomplete` / `response.failed` |
| Usage | final chunk only with `include_usage` | `response.completed.response.usage` |
| Multiple choices | `choices[n]` with `n > 1` | never; one generation per response |

Table compiled from the sources above; the right-hand column is documented, the mapping is my inference.
