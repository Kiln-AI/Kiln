# `store`, data retention, ZDR, prompt caching, and pricing

Fetched 2026-10-30.

## `store` defaults differ between the two endpoints

**Responses: stored unless you say otherwise.**

- Reference: "`store: optional boolean or null (default: true)` Whether to store the generated model response for later retrieval via API. Defaults to true when omitted. If set to true, response data will be stored for at least 30 days, subject to the data retention exceptions." ([Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create))
- "Response objects are saved for 30 days by default. They can be viewed in the dashboard logs page or retrieved via the API. You can disable this behavior by setting `store` to `false` when creating a Response." ([Conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state))
- Data controls: "the Responses API has a 30 day Application State retention period by default, or when the `store` parameter is set to `true`. In those cases, response data will be stored for at least 30 days." ([Data controls](https://developers.openai.com/api/docs/guides/your-data))

**Chat Completions: documentation conflicts.**

- Reference: "`store: optional boolean or null (default: false)` Whether or not to store the output of this chat completion request for use in our model distillation or evals products." ([Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))
- Migration guide: "Responses are stored by default. Chat completions are stored by default for new accounts. To disable storage when using either API, set `store: false`." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- I could not resolve which is true for a given account without an API key. The data-controls table lists `/v1/chat/completions` application state retention as "None, see below for exceptions".

**Implication for Kiln (inference):** if Kiln switches to `/v1/responses` and does not send `store`, every Kiln call starts being stored on OpenAI's side for at least 30 days and shows up in the user's dashboard logs. That is a data-handling change for users who are not ZDR. Sending `store: false` keeps today's behavior on the Chat Completions reference's terms. With `store: false`, reasoning continuity across calls needs encrypted reasoning items (see [reasoning-and-state.md](./reasoning-and-state.md)).

## ZDR and other retention controls

- Abuse monitoring logs are separate from `store`: "By default, abuse monitoring logs are generated for all API feature usage and retained for up to 30 days." Both `/v1/chat/completions` and `/v1/responses` show "Abuse monitoring retention: 30 days". ([Data controls](https://developers.openai.com/api/docs/guides/your-data))
- Under Zero Data Retention: "the `store` parameter for `/v1/responses` and `v1/chat/completions` will always be treated as `false`, even if the request attempts to set the value to `true`." (same source)
- Both endpoints are "Zero Data Retention eligible: Yes, see below for limitations". `/v1/conversations` and `/v1/conversations/items` are "Until deleted" and not ZDR-eligible. (same source)
- Encrypted reasoning under ZDR: "When a request includes `encrypted_content`, it is decrypted in memory, used for generating the next response, and then securely discarded. Any new reasoning tokens are immediately encrypted and returned to you, ensuring no intermediate state is persisted." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses))
- Background mode: "stores response data to disk for roughly 10 minutes to enable polling." ([Data controls](https://developers.openai.com/api/docs/guides/your-data))
- "For server-side compaction, no data is retained when `store="false"`." (same source)
- Responses-specific exceptions listed: audio outputs stored 1 hour, hosted containers, MCP servers being third parties, image/file CSAM scanning. (same source)
- Strict-mode tool schemas on **fine-tuned** models "are cached for performance, and are not eligible for zero data retention." ([Function calling guide](https://developers.openai.com/api/docs/guides/function-calling))

## Prompt caching

Caching is automatic on both endpoints, but several controls differ by model generation and endpoint.

- Migration guide claim: "Lower costs: Results in lower costs due to improved cache utilization (40% to 80% improvement when compared to Chat Completions in internal tests)." ([migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)) OpenAI gives no method. The GPT-5.4 guide ties this to reasoning: passing CoT between turns gave "improved intelligence, fewer generated reasoning tokens, higher cache hit rates, and lower latency". ([Using GPT-5.4](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.4))
- What changes the cached prefix: `model`, `tools`, `parallel_tool_calls`, `text.format`, `reasoning.effort`, `text.verbosity`, `context_management`. ([Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching))
- **GPT-5.6 and later charge for cache writes:** "cache writes cost 1.25× the standard, uncached input-token rate for the default 30-minute lifetime. In the Responses API, you can choose a 12-hour minimum lifetime at a write rate of 2.5× ordinary input. Subsequent reads cost 0.1× the ordinary input rate on most of these models and 0.05× on GPT-6.1 Sol and GPT-6.1 Terra." GPT-5.5 and earlier have "No additional cache-write charge". (same source)
- The `"12h"` lifetime is described as Responses-only in the guide's table ("`"30m"` (default), or `"12h"` in the Responses API"). **Discrepancy:** both API references describe `prompt_cache_options.ttl` as `"30m"`, "currently the only supported value", while `prompt_cache_breakpoint.ttl` accepts `"30m"` or `"12h"` in both references. ([Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create), [Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))
- `prompt_cache_options` and `prompt_cache_breakpoint` exist on both endpoints for GPT-5.6+ (per both references). Prewarming (`prompt_cache_options.prewarm`) is documented for the Responses API. ([Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching))
- Since 2026-05-29: "For organizations without ZDR enabled, `prompt_cache_retention` now defaults to `24h` instead of `in_memory`, enabling extended prompt caching by default." Applies to `v1/responses`, `v1/chat/completions`, `v1/batch`. ([API changelog](https://developers.openai.com/api/docs/changelog))
- "All prompt caching features are compatible with Zero Data Retention (ZDR). The prompt cache stores key-value (KV) tensors rather than the original prompt text... with a maximum retention period of 24 hours." ([Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching))
- Cached tokens on GPT-5.6+ are reported in `usage.input_tokens_details.cached_tokens` and `cache_write_tokens` (Responses). Chat Completions has `prompt_tokens_details.cached_tokens` and `prompt_tokens_details.cache_write_tokens`. ([both references](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create))

**Implication for Kiln's cost tracking (inference):** on GPT-5.6+ models, a correct cost needs three input rates (uncached, cache read, cache write), regardless of endpoint. Responses moves the field names (`input_tokens*`), so any cost code reading `prompt_tokens_details` must change.

## Token pricing

- Model pages list one token price table per model, not per endpoint (e.g. GPT-6.1 Sol: $2 input, $0.10 cached input, $2.50 cache writes, $10 output per 1M; [model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol)). I found no statement that the same tokens cost differently on `/v1/responses` vs `/v1/chat/completions`. (Absence of evidence, not a statement.)
- Built-in tools are billed per call and only exist on Responses (e.g. "File search tool call pricing applies to the Responses API only"). ([Pricing](https://developers.openai.com/api/docs/pricing))
- `previous_response_id` does not save input tokens: "all previous input tokens for responses in the chain are billed as input tokens in the API." ([Conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state))
- Reasoning tokens: "While reasoning tokens are not visible via the API, they still occupy space in the model's context window and are billed as output tokens." ([Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning)) Replayed encrypted reasoning items become input tokens on the next call (inference from "billed as input tokens" for context and from items occupying context; not stated explicitly).
- Pro mode "bills those tokens at the selected model's standard token rates" but does more work. ([Reasoning models guide](https://developers.openai.com/api/docs/guides/reasoning))
- Long context: e.g. "Prompts with more than 272K input tokens are priced at 2x input and cache rates and 1.5x output for the full request" (GPT-6 Astra page). Same on either endpoint as far as the pages say.
