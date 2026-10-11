# AI Gateway

## Bottom Line

Cloudflare AI Gateway is a hosted proxy for model traffic. It adds logs, analytics, caching, rate and spend limits, retries, guardrails, BYOK key storage and prepaid "Unified Billing". It sits in front of Workers AI and about 25 third-party providers.

In 2026 Cloudflare merged it into the normal REST API:
- Workers AI goes through a gateway when the request carries one optional header, `cf-aig-gateway-id: <id>`. Otherwise it is the same `api.cloudflare.com/.../ai/v1/chat/completions` call, with the same token and the same `@cf/...` model IDs.
- The same credentials can also call `openai/…`, `anthropic/…` and similar models, billed to prepaid Cloudflare credits.

LiteLLM has no AI Gateway provider. Its `cloudflare/` provider drops custom headers (tested). Its `openai/` provider pointed at `.../ai/v1` passes them through.

**Recommendation: option (b).** Ship one Workers AI provider with an optional "AI Gateway ID" field that adds the header. This depends on Kiln using LiteLLM's `openai/` route. If Kiln uses `cloudflare/`, ship (a) now and add the field later. Don't build a separate "AI Gateway" provider (c) now; it would duplicate OpenRouter and the direct providers Kiln already has.

## Key Findings

- **AI Gateway moved onto `api.cloudflare.com` in 2026.**
  - 2026-05-21: "AI Gateway now uses the AI REST API on `api.cloudflare.com`".
  - 2026-08-07: "Workers AI and AI Gateway unify model access and billing".
  - The old `gateway.ai.cloudflare.com` URLs "continue to work", but Cloudflare recommends the REST API for new integrations.
  - Sources: [Changelog](https://developers.cloudflare.com/ai-gateway/changelog/), [Authenticated Gateway](https://developers.cloudflare.com/ai-gateway/configuration/authentication/)
- **For Workers AI, going through a gateway takes one header.**
  - Add `cf-aig-gateway-id: default`, or a named gateway, to the normal Workers AI call.
  - The docs say "Workers AI requests always require the `cf-aig-gateway-id` header". Third-party models go through the `default` gateway without it.
  - Cloudflare's own Workers AI docs from the same month still show calls with no header. So the header reads as opt-in: add it to use a gateway, leave it off for a plain call. That reading is untested.
  - Sources: [Get started](https://developers.cloudflare.com/ai-gateway/get-started/), [Workers AI OpenAI compat](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- **There are four families of endpoints.**
  1. The REST API: `/ai/run`, `/ai/v1/chat/completions`, `/ai/v1/responses`, `/ai/v1/messages`. It uses the normal `Authorization` header with a token that has **Workers AI Read**. "A token that holds only an `AI Gateway` permission returns `401` with error code `10000`."
  2. The legacy per-provider URLs, `gateway.ai.cloudflare.com/v1/{acct}/{gw}/{provider}/…`. The Cloudflare token goes in `cf-aig-authorization`. `Authorization` carries the provider's own key.
  3. The OpenAI-compatible `…/{gw}/compat/chat/completions`, with `provider/model` IDs such as `workers-ai/@cf/…` and `openai/gpt-5-mini`.
  4. The Universal Endpoint, which is deprecated.
  - Sources: [REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/), [Unified API](https://developers.cloudflare.com/ai-gateway/usage/chat-completion/)
- **You don't have to send the upstream provider's key.**
  - The gateway picks credentials in this order: a provider key sent with the request, then a key stored on the gateway (BYOK, `default` alias), then Unified Billing on Cloudflare's own keys.
  - Unified Billing means prepaid credits with a 5% fee and pass-through token prices.
  - `byok_only` or `cf-aig-no-wholesale` stops the fall-through to Unified Billing.
  - Workers AI never needs a separate provider key.
  - Sources: [Unified Billing](https://developers.cloudflare.com/ai-gateway/features/unified-billing/), [BYOK](https://developers.cloudflare.com/ai-gateway/configuration/bring-your-own-keys/)
- **Prepaid credits change what Workers AI users can do.**
  - If a gateway's "Workers AI Billing" setting is "Unified billing", Workers AI calls through it are paid from credits.
  - Credits unlock `@cf/moonshotai/kimi-k2.6`, `kimi-k2.7-code` and `@cf/zai-org/glm-5.2` without the Workers Paid plan.
  - On credits those models allow 50 requests per minute instead of 20.
  - Sources: [Changelog 2026-08-07](https://developers.cloudflare.com/ai-gateway/changelog/), [Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/)
- **A gateway named `default` is created automatically on the first authenticated request.** Its settings are Authentication On, Logs On, Caching Off, Standard billing. Any other gateway ID must be created first. Source: [Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/)
- **The core features are free.** Logs for customers who started on or after 2026-09-24 follow Workers Logs pricing. Source: [Pricing](https://developers.cloudflare.com/ai-gateway/reference/pricing/)
- **LiteLLM 1.87.1 has no AI Gateway support.**
  - Its `cloudflare/` provider builds its headers from scratch. A `cf-aig-gateway-id` passed through `headers` or `extra_headers` is dropped. Confirmed against a local mock server.
  - `openai/` with `api_base=.../ai/v1` forwards the header.
  - LiteLLM closed the old request for gateway support ([#1158](https://github.com/BerriAI/litellm/issues/1158)) as "not planned".
  - Details: [workers-ai-through-gateway.md](./workers-ai-through-gateway.md).
- **Other tools don't agree on a shape.**
  - Cloudflare's own libraries use one Workers AI provider with an optional gateway: the Vercel AI SDK `workers-ai-provider` has a `gateway` option, and `langchain-cloudflare` has an `ai_gateway` parameter.
  - OpenCode, models.dev, Kilo, Pi and VoltAgent use two providers. Their "Cloudflare AI Gateway" provider is a router to many vendors, like OpenRouter, and asks for Account ID, Gateway ID and token.
  - LibreChat and DevoxxGenie always go through a gateway.
  - Open WebUI has no built-in support.
  - Details: [comparable-tools.md](./comparable-tools.md).

## Details

- [gateway-overview-and-endpoints.md](./gateway-overview-and-endpoints.md) — What the gateway is, every endpoint family with its auth rules quoted, the auto-created default gateway, BYOK, Unified Billing, pricing, and the 2025–2026 timeline.
- [workers-ai-through-gateway.md](./workers-ai-through-gateway.md) — A direct Workers AI call and a gateway call side by side, the older base-URL routing, what changes for the user, and the LiteLLM source reading plus the mock-server test of headers.
- [comparable-tools.md](./comparable-tools.md) — How 11 tools expose Workers AI and AI Gateway.
- [recommendation.md](./recommendation.md) — Options (a), (b), (c), and (c′) (one Cloudflare provider whose model list later adds third-party models), with trade-offs and suggested UI and validation details.

## Open Questions / Gaps

- **Token permissions.** Can a token with only "Workers AI Read" auto-create `default`, or use a gateway that requires authentication, through the header on `api.cloudflare.com`? The Get Started guide also asks for AI Gateway Read and Edit. This needs a live test.
- **Missing gateway error.** The status code and body for a gateway ID that doesn't exist are not documented. This needs a live test.
- **Credits on the OpenAI-compatible path.** The docs name only the native `/ai/run/{model}` endpoint for paying Workers AI with credits. It's unclear whether `/ai/v1/chat/completions` plus the header also bills to credits.
- **Is the header really opt-in?** Untested against a live account.
- **`/compat/models`.** This model-listing endpoint is sourced only from a third party (DevoxxGenie).
- **Legacy URL with LiteLLM's `cloudflare/` provider.** Analysed from source, not tested.
- **`langchain-cloudflare` retry settings.** The `aig_*` parameters come only from a search-engine summary.
- Direct fetches of developers.cloudflare.com and models.dev were blocked by the session proxy; those pages were read through Tavily extract.

## Sources

- [AI Gateway overview](https://developers.cloudflare.com/ai-gateway/)
- [llms.txt index](https://developers.cloudflare.com/ai-gateway/llms.txt)
- [REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/) (updated 2026-09-17)
- [Unified API](https://developers.cloudflare.com/ai-gateway/usage/chat-completion/)
- [Workers AI provider page](https://developers.cloudflare.com/ai-gateway/usage/providers/workersai/) (updated 2026-09-17)
- [Get started](https://developers.cloudflare.com/ai-gateway/get-started/) (updated 2026-08-07)
- [Authenticated Gateway](https://developers.cloudflare.com/ai-gateway/configuration/authentication/) (updated 2026-06-17)
- [BYOK](https://developers.cloudflare.com/ai-gateway/configuration/bring-your-own-keys/) (updated 2026-07-31)
- [Unified Billing](https://developers.cloudflare.com/ai-gateway/features/unified-billing/) (updated 2026-09-23)
- [Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/) (updated 2026-09-15)
- [Pricing](https://developers.cloudflare.com/ai-gateway/reference/pricing/) (updated 2026-09-24)
- [Caching](https://developers.cloudflare.com/ai-gateway/features/caching/)
- [Troubleshooting](https://developers.cloudflare.com/ai-gateway/reference/troubleshooting/)
- [Changelog](https://developers.cloudflare.com/ai-gateway/changelog/)
- [Workers AI OpenAI compat](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/) (updated 2026-09-18)
- LiteLLM 1.87.1 source, plus the mock-server test
- LiteLLM issues [#1158](https://github.com/BerriAI/litellm/issues/1158) and [#21115](https://github.com/BerriAI/litellm/issues/21115)
- [workers-ai-provider README](https://github.com/cloudflare/ai/blob/main/packages/workers-ai-provider/README.md)
- AI SDK pages: [AI Gateway](https://ai-sdk.dev/providers/community-providers/cloudflare-ai-gateway) and [Workers AI](https://ai-sdk.dev/providers/community-providers/cloudflare-workers-ai)
- [langchain-cloudflare README](https://github.com/cloudflare/langchain-cloudflare/blob/main/libs/langchain-cloudflare/README.md)
- [OpenCode providers](https://opencode.ai/docs/providers/)
- models.dev provider files: [cloudflare-ai-gateway](https://github.com/sst/models.dev/blob/dev/providers/cloudflare-ai-gateway/provider.toml) and [cloudflare-workers-ai](https://github.com/sst/models.dev/blob/dev/providers/cloudflare-workers-ai/provider.toml)
- [Kilo #9987](https://github.com/Kilo-Org/kilocode/issues/9987)
- Other tools: [Pi](https://developers.cloudflare.com/ai-gateway/integrations/coding-agents/pi/), [VoltAgent](https://voltagent.dev/models-docs/providers/cloudflare-ai-gateway), [DevoxxGenie](https://genie.devoxx.com/blog/cloudflare-ai-gateway), [LibreChat](https://www.librechat.ai/docs/configuration/librechat_yaml/ai_endpoints/cloudflare), [Open WebUI #3277](https://github.com/open-webui/open-webui/issues/3277)
