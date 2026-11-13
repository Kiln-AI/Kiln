# Reasoning, reasoning items, and conversation state

All OpenAI pages fetched 2026-10-30. Third-party sources (GitHub issues, community threads) are labeled as such.

## Reasoning effort

Request field: `reasoning.effort` (Responses) or `reasoning_effort` (Chat Completions).

> "Supported values are model-dependent and can include `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`."
> — [Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning)

Both references list the same enum, including `max`, with a generic `default: "medium"`: Responses `reasoning.effort: optional ReasoningEffort or null (default: "medium")`; Chat Completions `reasoning_effort: optional ReasoningEffort or null (default: "medium")`. ([Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create), [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))

**`max` is not documented as Responses-only.** The Chat Completions reference lists `max` among accepted `reasoning_effort` values. I found no OpenAI statement that `max` requires Responses. (Kiln hides `max` on GPT-6.1 Sol; the reason must come from somewhere other than an OpenAI endpoint restriction, or from undocumented behavior. Not verified without an API key.)

Per-model effort values and defaults are in [models-and-endpoint-support.md](./models-and-endpoint-support.md).

Notable model rules from the reasoning guide:

> "GPT-6 Astra does not support `none` reasoning effort. Setting `reasoning.effort` (Responses) or `reasoning_effort` (Chat Completions) to `none` returns HTTP 400. GPT-6.1 Sol does not support `none` or `minimal` and defaults to `medium`."
>
> "Use the Responses API for function calling. Chat Completions does not support function calling with GPT-6 Astra or GPT-6.1 Sol."
>
> "Defaults are also model-dependent rather than universal. `gpt-5.5` defaults to `medium` reasoning effort."

GPT-5.4 and GPT-5.2 default to `none`: "GPT-5.2 and GPT-5.4 support `none` as their lowest reasoning effort for lower-latency interactions. It is the default setting for both models." ([Using GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.4))

### Reasoning mode (`pro`): Responses only

> "GPT-5.6 and GPT-6 models support `standard` and `pro` reasoning modes in the Responses API. `standard` is the default. Set `reasoning.mode` to `pro` for difficult tasks..."
>
> "Pro mode aggregates the model work performed to produce the final answer and bills those tokens at the selected model's standard token rates... Existing Pro model IDs keep their current behavior and pricing."
> — [Reasoning models guide, "Reasoning mode"](https://developers.openai.com/api/docs/guides/reasoning)

"To use pro mode, keep your selected GPT-5.6 model and set `reasoning.mode` to `pro` in the Responses API; do not switch to a separate Pro model slug." ([Using GPT-5.6](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.6)) The Chat Completions reference has no `mode` field.

### Changing effort mid-conversation (`configuration_update`): Responses only, GPT-6

An input item `{"type": "configuration_update", "reasoning": {"effort": "high"}}` placed before the next user message changes effort from that point on while keeping the request-level `reasoning.effort` (and the prompt-cache prefix) unchanged. "Configuration updates are supported by the GPT-6 model family in standard, single-agent mode." Adjacent updates are rejected; they cannot be combined with automatic compaction or truncation. ([Reasoning models guide, "Change reasoning mid-conversation"](https://developers.openai.com/api/docs/guides/reasoning))

## Reasoning summaries: Responses only

> "While we don't expose the raw reasoning tokens emitted by the model, you can view a summary of the model's reasoning using the `summary` parameter... To access the most detailed summarizer available for a model, set the value of this parameter to `auto`. `auto` will be equivalent to `detailed` for most reasoning models today..."
>
> "Reasoning summary output is part of the `summary` array in the `reasoning` output item. This output will not be included unless you explicitly opt in to including reasoning summaries."
>
> "Before using summarizers with our latest reasoning models, you may need to complete organization verification to ensure safe deployment."
> — [Reasoning models guide, "Reasoning summaries"](https://developers.openai.com/api/docs/guides/reasoning)

Request: `reasoning: {"effort": "low", "summary": "auto"}`. Reference: `summary: optional "auto" or "concise" or "detailed" or null`; "`concise` is supported for `computer-use-preview` models and all reasoning models after `gpt-5`." `generate_summary` is deprecated in favor of `summary`. ([API reference](https://developers.openai.com/api/reference/resources/responses/methods/create))

Output:

```json
{ "id": "rs_6876...", "type": "reasoning",
  "summary": [ { "type": "summary_text", "text": "**Answering a simple question**\n\nI'm looking at..." } ] }
```

**Chat Completions has no summary channel.** The Chat Completions create reference (request and response object) contains no `summary`, `reasoning_content`, or `encrypted` field; the only reasoning data it returns is the count `completion_tokens_details.reasoning_tokens`. ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), checked by text search of the full page.) The migration guide's capability table also has a "Reasoning summaries" row (its check marks did not survive the markdown export, so I rely on the reference instead).

A reasoning item can hold several summary parts (`summary[]`), each streamed with its own `summary_index`. See [streaming.md](./streaming.md).

## Reasoning items

Reference (`Reasoning` item, usable as input and output):

> "A description of the chain of thought used by a reasoning model while generating a response. Be sure to include these items in your `input` to the Responses API for subsequent turns of a conversation if you are manually managing context."
>
> Fields: `id: string`; `summary: array of SummaryTextContent`; `type: "reasoning"`; `content: optional array of {text, type: "reasoning_text"}`; `encrypted_content: optional string or null`; `status: optional`.
>
> `encrypted_content`: "The encrypted content of the reasoning item. This is populated by default for reasoning items returned by `POST /v1/responses` and WebSocket `response.create` requests. When streaming, use the completed reasoning item and its `encrypted_content` from the `response.output_item.done` event in subsequent requests. The `encrypted_content` in `response.output_item.added` may be incomplete. This is especially important when `store` is `false` or when using Zero Data Retention."
> — [API reference, input item `Reasoning`](https://developers.openai.com/api/reference/resources/responses/methods/create)

Reasoning items are opaque: "Persisted reasoning provides continuity; it does not expose the model's raw reasoning. The reasoning items remain opaque, and the API does not return their reasoning text." ([Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning))

### Passing reasoning items back during tool calls

> "When doing function calling with a reasoning model in the Responses API, we highly recommend you pass back any reasoning items returned with the last function call (in addition to the output of your function). If the model calls multiple functions consecutively, you should pass back all reasoning items, function call items, and function call output items, since the last `user` message."
>
> "The simplest way to do this is to pass in all reasoning items from a previous response into the next one. Our systems will smartly ignore any reasoning items that aren't relevant to your functions, and only retain those in context that are relevant."
>
> "For advanced use cases where you might be truncating and optimizing parts of the context window before passing them on to the next response, just ensure all items between the last user message and your function call output are passed into the next response untouched."
> — [Reasoning models guide, "Keeping reasoning items in context"](https://developers.openai.com/api/docs/guides/reasoning)

This is the core reason OpenAI blocks tools-with-reasoning on Chat Completions (OpenAI does not state the reason; a community member's reading in [this thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454) is "The goal is likely to encourage you to maintain multi-turn reasoning during tool calls"). The GPT-5.4 guide does say: "The biggest difference, and main reason to migrate from Chat Completions to the Responses API for GPT-5.4, is support for passing chain of thought (CoT) between turns... Passing CoT exists only in the Responses API." ([Using GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.4))

### Persisted reasoning across turns: `reasoning.context`

> "For models released before GPT-5.6, the default behavior in a multi-step conversation is to carry over input and output tokens from each step without rendering reasoning from earlier turns into the next sample. GPT-5.6 models instead default to rendering available reasoning from earlier turns. Use `reasoning.context` to select either behavior on supported models."
> — [Reasoning models guide, "How reasoning works"](https://developers.openai.com/api/docs/guides/reasoning)

| Value | Behavior |
| --- | --- |
| `auto` | Uses the selected model's default. Omitting `reasoning.context` has the same effect as `auto`. |
| `current_turn` | Makes reasoning from the active turn available, but does not render reasoning from earlier turns into the next sample. |
| `all_turns` | Renders available, compatible reasoning items from earlier turns into the next sample. GPT-5.6 models and GPT-6.1 Sol support this value. |

- "The GPT-5.6 model family supports `all_turns` and uses it by default. Earlier models default to `current_turn`. GPT-6.1 Sol also supports `all_turns`."
- "`all_turns` has an effect only when the request has access to earlier response items. Use `previous_response_id`, attach the response to a conversation, or manually replay the complete response history."
- "Persisted reasoning can be reused only within the same model family... When you switch model families, the API omits incompatible reasoning from the model's context, even when `reasoning.context` is `all_turns`."

Source: [Reasoning models guide, "Preserve reasoning across calls"](https://developers.openai.com/api/docs/guides/reasoning).

**Discrepancy:** Microsoft's Azure page says "GPT-5.4, GPT-5.5, GPT-5.6, and GPT-6 models support `all_turns` for the `reasoning.context` parameter. GPT-5.6 and GPT-6 models use it by default." ([Azure reasoning models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)) OpenAI's own page names only GPT-5.6 and GPT-6.1 Sol. Treat OpenAI's page as authoritative for OpenAI-direct.

**Implication for Kiln (inference):** with GPT-5.6+ defaulting to `all_turns`, a multi-turn Kiln conversation (prior trace replayed as input) gets better results only if earlier reasoning items are replayed too. Kiln's chat-format trace does not carry reasoning items today, so it would get `current_turn`-like behavior for earlier turns regardless of the setting. Within one tool loop (the current turn), reasoning items must be replayed between tool calls or the model loses its reasoning between calls.

## `store`, stateless mode, and encrypted reasoning

### What the docs say now

> "When you create a response in stateless mode, reasoning items in the response's `output` array include an `encrypted_content` property by default. Stateless mode applies when `store` is `false` or when your organization uses Zero Data Retention (ZDR). The API still accepts the legacy `reasoning.encrypted_content` value in `include` for compatibility, but doesn't require it."
> — [Reasoning models guide, "Preserve reasoning without stored responses"](https://developers.openai.com/api/docs/guides/reasoning)

The migration guide's steps:

> "To stop storing state while still using reasoning:
> - Set `store: false` in the store field.
> - Preserve and replay every returned reasoning item. Each item includes `encrypted_content` by default when you create a response.
>
> ...For ZDR organizations, OpenAI enforces `store: false` automatically. When a request includes `encrypted_content`, it is decrypted in memory, used for generating the next response, and then securely discarded. Any new reasoning tokens are immediately encrypted and returned to you, ensuring no intermediate state is persisted."
> — [migration guide, "Decide when to store state"](https://developers.openai.com/api/docs/guides/migrate-to-responses)

The official stateless examples replay full output items, ids included: `history.extend(item.model_dump() for item in first.output)` followed by a second call with `store=False`. ([Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning), [Conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state))

The `include` reference text still describes `reasoning.encrypted_content` as the way to get encrypted reasoning ("Includes an encrypted version of reasoning tokens in reasoning item outputs. This enables reasoning items to be used in multi-turn conversations when using the Responses API statelessly"). It is not marked deprecated in the reference, only called "legacy" in the guide. ([API reference, `include`](https://developers.openai.com/api/reference/resources/responses/methods/create))

### When this changed (dated, partly inferred)

- On 2026-07-11 a community regular wrote: "The default of the API with `store:false` is actually not to supply the reasoning" (you had to ask with `include`). ([OpenAI community thread, 2026-07-11](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454))
- On 2026-07-13 another user reported "API responses started sending encrypted_content today without 'include' parameter". A reply on 2026-07-17 says this is intentional for stateless and ZDR requests, and the replier also saw it with `store: true`, which the docs do not clearly cover: "They also do not document any way to suppress it." ([OpenAI community thread, 2026-07-13](https://community.openai.com/t/responses-attach-encrypted-content-without-explicitly-specifying-to-do-so/1386738))
- Earlier SDK/maintainer guidance (Jan 2026) still required `include`: "When you turn store option off, your model settings need to have `response_include=["reasoning.encrypted_content"]`. This SDK does not automatically set it under the hood because non-reasoning models such as gpt-4.1 do not work with the option." ([openai-agents-python #2265, 2026-01-07](https://github.com/openai/openai-agents-python/issues/2265))

**Practical reading (inference):** for OpenAI-direct today, `encrypted_content` comes back without `include`, but sending `include: ["reasoning.encrypted_content"]` is still accepted and is the safe choice for proxies, Azure, and older behavior. The agents-SDK maintainer's warning that non-reasoning models (gpt-4.1) "do not work with the option" was not re-verified; Kiln should only add `include` for reasoning models.

### What happens when a reasoning item is replayed by id with `store: false`

The documented error (exact text, reported in several third-party trackers):

```text
Item with id 'rs_...' not found. Items are not persisted when `store` is set to false. Try again with `store` set to true, or remove this item from your input.
```

Reported as HTTP 404 with `'type': 'invalid_request_error', 'param': 'input'` against OpenAI ([openai-agents-python #919](https://github.com/openai/openai-agents-python/issues/919); [#2265, 2026-01-07](https://github.com/openai/openai-agents-python/issues/2265); [vercel/ai #7543, 2025-07-25](https://github.com/vercel/ai/issues/7543); [zed #59207, 2026-06](https://github.com/zed-industries/zed/issues/59207)), and as HTTP 400 in other reports (Azure; Bifrost proxy).

When it happens, from those reports:

1. **Reasoning item sent with an `id` and no `encrypted_content` (or `encrypted_content: null`) while `store: false`.** The server tries to look the item up by id, finds nothing, and fails. Vercel's report shows the offending input: `{"type": "reasoning", "id": "rs_...", "encrypted_content": null, "summary": []}`. Fix in every case: get `encrypted_content` (via `include` before mid-July 2026, by default since) and replay it with the item. ([vercel/ai #7543](https://github.com/vercel/ai/issues/7543))
2. **OpenAI-direct accepts `id` + `encrypted_content` together with `store: false`.** This matches OpenAI's own example (replaying `item.model_dump()`, ids included, with `store=False`) and a Bifrost report that "Calling the same payload directly against `api.openai.com/v1/responses` (bypassing Bifrost) works correctly." ([maximhq/bifrost #5410](https://github.com/maximhq/bifrost/issues/5410))
3. **Azure appears to reject `id` + `encrypted_content` with `store: false`.** A Codex issue (2026-07-28) shows an Azure OpenAI backend returning the same "not found" error for an input reasoning item that had both `id` and non-empty `encrypted_content`, with `store: false`. It succeeds when ids are stripped from input items, or with `store: true`. Codex works around it by sending `store: true` to Azure (`store: provider.is_azure_responses_endpoint()`). ([openai/codex #35739](https://github.com/openai/codex/issues/35739); older Azure report [openai/codex #3292](https://github.com/openai/codex/issues/3292)) This is third-party evidence, not an Azure statement.
4. Some clients "fix" it by dropping reasoning items from replay (e.g. [badlogic/pi-mono #3369](https://github.com/badlogic/pi-mono/issues/3369)). That avoids the error but loses reasoning continuity, against OpenAI's guidance above.

**Safe shape for Kiln's tool loop (inference from the above):** `store: false`; replay each reasoning item with its `encrypted_content`; if Azure must be supported with `store: false`, omit the `id` field on replayed input items (or at least on reasoning items). Prior-art details are another subtopic's lane.

## `phase`

> "For long-running or tool-heavy flows with GPT-5.5 and GPT-5.4 in the Responses API, use the assistant message `phase` field to avoid early stopping and other misbehavior. `phase` is optional at the API level, but OpenAI recommends using it. Use `phase: "commentary"` for intermediate assistant updates, such as preambles before tool calls, and `phase: "final_answer"` for the completed answer. Don't add `phase` to user messages."
>
> "Missing or dropped `phase` can cause preambles to be treated as final answers in those workflows."
> — [Reasoning models guide, "`phase` parameter"](https://developers.openai.com/api/docs/guides/reasoning)

`phase` was released 2026-02-24 ([API changelog](https://developers.openai.com/api/docs/changelog)). Replaying assistant text as a plain `{"role": "assistant", "content": "..."}` loses `phase`. Chat Completions has no `phase` field, so Kiln's chat-format trace cannot carry it without an extension (inference).

## Server-side state: `previous_response_id` and the Conversations API

Three options for multi-turn state, per the migration guide:

> "- Use `previous_response_id` when you want OpenAI to manage prior response context. Resend stable `instructions` on each request, because `previous_response_id` does not carry over the previous response's top-level `instructions`.
> - Pass prior `output` Items back into the next request when you need to manage or trim context yourself.
> - Use the Conversations API when you need a persistent conversation object."
> — [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)

- `previous_response_id` "Cannot be used in conjunction with `conversation`." ([API reference](https://developers.openai.com/api/reference/resources/responses/methods/create))
- It needs the earlier response to be stored (the guide's example sets `store=True` on both calls). Inference: it cannot work with `store: false` or under ZDR, since nothing is stored.
- Billing: "Even when using `previous_response_id`, all previous input tokens for responses in the chain are billed as input tokens in the API." ([Conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state))
- Conversations API (released 2025-08-20 per the [changelog](https://developers.openai.com/api/docs/changelog)): "persist conversation state as a long-running object with its own durable identifier... Conversations store items, which can be messages, tool calls, tool outputs, and other data." Pass `conversation=conversation.id` to `responses.create`. ([Conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state))
- Retention: "Response objects are saved for 30 days by default... Conversation objects and items in them are not subject to the 30 day TTL. Any response attached to a conversation will have its items persisted with no 30 day TTL." (same source). `/v1/conversations` is not ZDR-eligible ([Data controls](https://developers.openai.com/api/docs/guides/your-data)).
- OpenRouter's Responses API rejects both: "Requests that set `store: true` or a non-null `previous_response_id` are rejected with a `400` error." ([OpenRouter Responses API](https://openrouter.ai/docs/api_reference/responses/overview))

**Implication for Kiln (inference):** Kiln already owns the whole transcript (`TaskRun.trace`), so manual item replay with `store: false` matches its model. `previous_response_id` and Conversations would add OpenAI-side state, retention, and ZDR conflicts, and would not work through OpenRouter.

## Misalignment monitoring (GPT-6 Astra): a Responses-only failure mode

- "Misalignment monitoring asynchronously checks for potential issues during agent work in supported Responses API requests. Checks can trigger safety alerts or stop a conversation for review." ([API changelog, 2026-09-03](https://developers.openai.com/api/docs/changelog))
- Coverage: Responses requests "using persisted reasoning, WebSockets, or OpenAI compaction" are monitored and can be blocked; other Responses requests are monitored with alerts only; "Chat Completions API requests: Not covered by this monitoring system."
- "When misalignment monitoring blocks a request before streaming begins, the API returns HTTP `403`, with error type `invalid_request_error` and code `misalignment_policy_violation`. Match the error code rather than the message text. Streaming integrations must also handle errors while consuming the stream, even after receiving output."

Source: [Misalignment monitoring guide](https://developers.openai.com/api/docs/guides/safety-checks/misalignment-monitoring). Inference: replaying encrypted reasoning items (persisted reasoning) on covered models opts the request into the blocking path, so Kiln's error handling should recognize this code.
