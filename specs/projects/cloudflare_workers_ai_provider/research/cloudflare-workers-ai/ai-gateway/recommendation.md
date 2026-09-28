# Recommendation: Should Kiln Support AI Gateway, and How?

This builds on [gateway-overview-and-endpoints.md](./gateway-overview-and-endpoints.md), [workers-ai-through-gateway.md](./workers-ai-through-gateway.md) and [comparable-tools.md](./comparable-tools.md). Where a point is my judgment rather than a sourced fact, it is labeled as such.

## Facts that drive the decision

1. **Routing Workers AI through a gateway is one optional HTTP header** on the same endpoint: `cf-aig-gateway-id: <id>` on `https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1/chat/completions` (or `/ai/run/{model}`). The token, account ID, model IDs and body don't change. Source: [AI Gateway Get started](https://developers.cloudflare.com/ai-gateway/get-started/), [REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/).
2. **The same credentials can also call third-party models** (`openai/…`, `anthropic/…`, `google/…`) on that endpoint through Unified Billing. This needs prepaid credits (5% fee), or BYOK keys stored on the gateway. Source: [REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/), [Unified Billing](https://developers.cloudflare.com/ai-gateway/features/unified-billing/).
3. **LiteLLM has no AI Gateway provider.** Its `cloudflare/` provider silently drops custom headers (tested on 1.87.1). The `openai/` provider pointed at `.../ai/v1` passes them through (also tested). Kiln already sends per-provider `default_headers`.
4. **Other tools are split.** Cloudflare's own SDKs (Vercel `workers-ai-provider`, `langchain-cloudflare`) use "Workers AI with an optional gateway". Coding agents built on models.dev (OpenCode, Kilo, Pi, VoltAgent) use "two providers", where the gateway provider is an OpenRouter-like multi-vendor router.
5. **Kiln already has OpenRouter** plus direct providers for OpenAI, Anthropic, Gemini and others. Third-party models through Cloudflare would duplicate what Kiln already offers, with a different bill.

## Options

### (a) Workers AI only

The connect screen asks for Account ID and API token. There is no gateway support.

- **Pros:** Smallest scope and a single connect flow. No extra failure modes: no gateway-not-found errors, no token-permission surprises, no caching or logging side effects. It is additive later. Adding an optional gateway field in a future release is not a breaking change.
- **Cons:** Users who run their Cloudflare AI traffic through a gateway can't see Kiln's calls in their gateway dashboards, spend limits or logs. Users can't pay for Workers AI with prepaid AI Gateway credits. Credits also unlock some frontier models (Kimi K2.6, Kimi K2.7 Code, GLM 5.2) without the Workers Paid plan, and raise their limit from 20 to 50 req/min ([Changelog 2026-08-07](https://developers.cloudflare.com/ai-gateway/changelog/)).

### (b) Workers AI with an optional AI Gateway ID ← recommended

The connect screen asks for Account ID, API token and an **optional** "AI Gateway ID". When the ID is set, Kiln adds `cf-aig-gateway-id: <id>` to every Workers AI request.

- **Pros:**
  - Low cost. It's one optional text field and one default header, which Kiln's `LiteLlmCoreConfig.default_headers` already supports.
  - No second model list and no second provider in the UI.
  - It matches how Cloudflare's own SDKs model it.
  - It unlocks the gateway features (logs, analytics, spend and rate limits, retries) and prepaid-credit billing for Workers AI. For credits, the user still has to set the gateway's "Workers AI Billing" to Unified billing in the dashboard.
- **Cons / risks:**
  - It only works if the Workers AI integration uses LiteLLM's **`openai/` provider against `.../ai/v1`**. With `cloudflare/`, the header is dropped. The fallback would be pointing `api_base` at the legacy `gateway.ai.cloudflare.com/.../workers-ai/` URL, which is untested and needs a second auth header on authenticated gateways. The API subtopic should confirm the route.
  - Validation needs thought. Any gateway ID other than `default` must already exist, and `default` is auto-created on first authenticated request. So a connect-time test call should include the header, and the error for a missing gateway should be turned into a clear message. I could not find the exact error body for "gateway not found". See the summary's open questions.
  - Token permissions are unclear. The REST API needs only "Workers AI Read". Cloudflare's Get Started guide also asks for "AI Gateway Read/Edit". A token without them may fail to auto-create `default`, or fail against an authenticated gateway. This is unverified. The help text should tell users which permissions to add.
  - The gateway can change behavior in ways the user may not expect. If the user turns on caching, identical requests from Kiln could return cached responses, which would hurt repeated sampling and evals. Caching is off by default. Logs store prompts and responses by default. Both are the user's own gateway settings, but Kiln's UI copy should mention them. (Judgment.)
  - Adding the field implies a promise that the gateway path keeps working. The REST API integration is new (2026-05-21 and 2026-08-07) and its docs are still changing.

### (c) Two separate providers: "Cloudflare Workers AI" and "Cloudflare AI Gateway"

The second provider exposes third-party models (`openai/gpt-…`, `anthropic/claude-…`, plus `@cf/…`) through Unified Billing or BYOK, like OpenCode and models.dev do.

- **Pros:** Gives users one Cloudflare bill for many vendors, plus gateway governance. Matches OpenCode/models.dev naming, so the `claude-maintain-models` skill could map to models.dev's `cloudflare-ai-gateway` entry.
- **Cons:**
  - It is a second OpenRouter. It needs its own curated model list with Kiln capability flags (structured output mode, tools, reasoning parsing) for each third-party model, and these may behave differently behind Cloudflare's translation layer.
  - It needs users to buy prepaid credits or set up BYOK before any third-party call works, which makes connect-time validation harder.
  - Two connect flows that share Account ID and token confuse users. Kilo Code shipped a bug where its dialog dropped these fields ([kilocode#9987](https://github.com/Kilo-Org/kilocode/issues/9987)).
  - The benefit over Kiln's existing OpenRouter and direct providers is modest: a single Cloudflare invoice at +5% on credits.

A variant, **(c′)**, would be one "Cloudflare" provider whose model list later adds third-party `author/model` entries next to `@cf/…` models. After the REST API merge they share the URL and credentials. This is what Cloudflare's `workers-ai-provider` is moving toward. It avoids a second connect flow but has the same model-list maintenance cost as (c). (Judgment.)

## Recommendation

**Go with (b): ship Workers AI as one provider with an optional AI Gateway ID field, if the API subtopic confirms Kiln will call Workers AI through LiteLLM's `openai/` provider at `https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1`.** If Kiln ends up on LiteLLM's `cloudflare/` provider instead, **ship (a)** and defer the gateway field. Adding it later does not break anything.

**Do not build (c) now.** Revisit only if users ask for "pay for OpenAI/Anthropic through my Cloudflare bill". If that happens, prefer (c′), which extends the same Cloudflare provider's model list, over a second provider with a duplicate connect flow.

Suggested details for (b) (judgment):
- Label the field "AI Gateway ID (optional)". The help text should say something like "Route requests through your Cloudflare AI Gateway for logs, caching and spend limits. Use `default` to auto-create one." Also say that the token needs AI Gateway permissions in addition to Workers AI Read (to be confirmed).
- Leave the field empty by default. An empty field means a direct Workers AI call, which is today's behavior.
- Include the header in the connect-time validation call, so a wrong gateway ID fails at connect time rather than on the first run.
- Consider sending `cf-aig-skip-cache: true` on sampling-type calls, or document that gateway caching can return identical outputs. Consider this only if caching turns out to affect Kiln flows in practice.
