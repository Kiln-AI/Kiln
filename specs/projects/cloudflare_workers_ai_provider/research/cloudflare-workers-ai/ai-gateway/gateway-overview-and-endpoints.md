# AI Gateway: What It Is, Endpoints, Auth, Billing

All Cloudflare docs below were read on 2026-09-28 via their Markdown versions (`.../index.md`). "Last updated" dates are the ones shown on each page.

## What it is

Cloudflare AI Gateway is a hosted proxy that sits between an app and one or more model providers. It adds logging, analytics, caching, rate limiting, retries/fallbacks, guardrails, DLP and spend limits. Workers AI is one of the providers it can sit in front of.

> "Cloudflare's AI Gateway allows you to gain visibility and control over your AI apps. By connecting your apps to AI Gateway, you can gather insights on how people are using your application with analytics and logging and then control how your application scales with features such as caching, rate limiting, as well as request retries, model fallback, and more."
> — [AI Gateway overview](https://developers.cloudflare.com/ai-gateway/)

Providers listed in the docs index include Workers AI, OpenAI, Anthropic, Google AI Studio, Vertex, Bedrock, Azure OpenAI, Groq, Mistral, Cohere, DeepSeek, xAI, Cerebras, OpenRouter, HuggingFace, Replicate, Perplexity and others ([llms.txt index](https://developers.cloudflare.com/ai-gateway/llms.txt)).

### Pricing

- Core features (analytics, caching, rate limiting) are free on all plans ([Pricing](https://developers.cloudflare.com/ai-gateway/reference/pricing/), updated 2026-09-24).
- Logs: customers who create their first gateway on or after 2026-09-24 pay [Workers Logs pricing](https://developers.cloudflare.com/workers/observability/logs/workers-logs/#pricing). Older customers keep "Legacy Logs" (100,000 logs total on Workers Free; 10,000,000 per gateway on Workers Paid).
- Unified Billing: "A 5% fee is applied to all credits purchased through Unified Billing ... Inference pricing from providers is passed through with no markup."

## The big 2026 change: AI Gateway merged into the Cloudflare REST API

This is the most important finding. Older blog posts and most third-party integrations describe only the `gateway.ai.cloudflare.com` URLs. They are now the legacy path.

- **2026-05-21**: "AI Gateway now uses the AI REST API on `api.cloudflare.com`. You can call any model — whether from OpenAI, Anthropic, Google, or hosted on Workers AI — through one unified API, using the same endpoints and authentication regardless of provider." ([Changelog](https://developers.cloudflare.com/ai-gateway/changelog/))
- **2026-08-07**: "Workers AI and AI Gateway unify model access and billing ... Use the same AI binding and REST API to call models hosted on Workers AI or by supported third-party providers." Prepaid AI Gateway credits can now pay for Workers AI. ([Changelog](https://developers.cloudflare.com/ai-gateway/changelog/))
- The [Authenticated Gateway](https://developers.cloudflare.com/ai-gateway/configuration/authentication/) page (updated 2026-06-17) says: "The `cf-aig-authorization` header is used with the `gateway.ai.cloudflare.com` endpoints, which continue to work. For new integrations, we recommend using the REST API at `api.cloudflare.com`, which uses the standard `Authorization` header."

## Endpoint families

There are now three ways to reach the gateway over HTTP. A fourth one is deprecated.

### 1. REST API on `api.cloudflare.com` (recommended by Cloudflare for new integrations)

Source: [REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/) (updated 2026-09-17).

| Endpoint | Format | Third-party models | Workers AI models (`@cf/`) |
| --- | --- | --- | --- |
| `POST /ai/run` | Envelope with `model`, `input` | Yes | Yes |
| `POST /ai/v1/chat/completions` | OpenAI chat completions | Yes | Yes |
| `POST /ai/v1/responses` | OpenAI Responses API | Yes | Model dependent |
| `POST /ai/v1/messages` | Anthropic Messages API | Yes | No |

All paths are under `https://api.cloudflare.com/client/v4/accounts/{account_id}`.

- **Auth**: "Authenticate with a Cloudflare API token that has the **Account** > **Workers AI** > **Read** permission. Pass it in the `Authorization` header. All `/accounts/{account_id}/ai/*` endpoints require the Workers AI permission. This applies to third-party models and to Workers AI (`@cf/`) models. A token that holds only an `AI Gateway` permission returns `401` with error code `10000`."
- **Model names**: third-party models use `author/model` (for example `openai/gpt-4.1`, `anthropic/claude-sonnet-4`). Workers AI models use `@cf/author/model`.
- **Selecting a gateway**: "By default, third-party model requests route through your account's default AI Gateway. To use a specific gateway, include the `cf-aig-gateway-id` header. Workers AI requests always require this header."
- **Per-request controls** are `cf-aig-*` headers: `cf-aig-skip-cache`, `cf-aig-cache-ttl`, `cf-aig-cache-key`, `cf-aig-collect-log`, `cf-aig-request-timeout`, `cf-aig-max-attempts`, `cf-aig-retry-delay`, `cf-aig-backoff`, `cf-aig-metadata`.
- **No provider key needed** for third-party models: "No provider SDKs or API keys are needed. Authentication and billing are handled through your Cloudflare account. Third-party models are billed via Unified Billing."

What "Workers AI requests always require this header" means is explained in [workers-ai-through-gateway.md](./workers-ai-through-gateway.md). In short, you need the header only if you want the request to go through a gateway. Without it, the call is a plain Workers AI call.

### 2. Provider-native endpoints on `gateway.ai.cloudflare.com` (legacy, still works)

```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/{provider}
```

These keep each provider's own request format ([Get started](https://developers.cloudflare.com/ai-gateway/get-started/), updated 2026-08-07). The Cloudflare token goes in `cf-aig-authorization`. `Authorization` is kept for the provider's own key:

> "Make sure your Cloudflare token is in `cf-aig-authorization`, not `Authorization`. The `Authorization` header is reserved for provider credentials." — [Troubleshooting](https://developers.cloudflare.com/ai-gateway/reference/troubleshooting/)

For Workers AI, the provider slug is `workers-ai`. The "provider key" is itself a Cloudflare API token. Examples:
- Native: `https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/workers-ai/@cf/meta/llama-3.1-8b-instruct` with `Authorization: Bearer {cf_api_token}` ([Changelog 2025-02-06](https://developers.cloudflare.com/ai-gateway/changelog/)).
- OpenAI-compatible: `https://gateway.ai.cloudflare.com/v1/${CF_ACCOUNT_ID}/${CF_GATEWAY_ID}/workers-ai/v1`, which LibreChat uses as an OpenAI `baseURL` ([LibreChat docs](https://www.librechat.ai/docs/configuration/librechat_yaml/ai_endpoints/cloudflare)).

The current [Workers AI provider page](https://developers.cloudflare.com/ai-gateway/usage/providers/workersai/) (updated 2026-09-17) no longer shows the `gateway.ai.cloudflare.com/.../workers-ai/...` URLs. It shows only the REST API with the `cf-aig-gateway-id` header and the Worker binding. The legacy URL still appears in the changelog and in third-party docs. **Inference:** Cloudflare is steering people off it, but has not announced that it is deprecated.

### 3. Unified OpenAI-compatible endpoint: `/compat/chat/completions`

```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat/chat/completions
```

Source: [Unified API (OpenAI compat)](https://developers.cloudflare.com/ai-gateway/usage/chat-completion/). Launched 2025-06-03 ([Changelog](https://developers.cloudflare.com/ai-gateway/changelog/)).

- "Specify the model using `{provider}/{model}` format": `openai/gpt-5-mini`, `google-ai-studio/gemini-2.5-flash`, `anthropic/claude-sonnet-4-5`, `workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast`, `grok/grok-4`, `dynamic/<route-name>`.
- Providers supported on this endpoint: Anthropic, OpenAI, Groq, Mistral, Cohere, Perplexity, Workers AI, Google AI Studio, Vertex, xAI, DeepSeek, Cerebras, Baseten, Parallel.
- Auth has two shapes:
  - **Stored key / Unified Billing**: the OpenAI SDK `apiKey` is the Cloudflare token (`apiKey: "{cf_api_token}"`), and there are no provider keys.
  - **Request-level provider key**: `apiKey` is the provider key, and the Cloudflare token goes in `cf-aig-authorization: Bearer {cf_api_token}` "if gateway is authenticated".
- The `default` gateway ID works with no setup: "The `default` gateway is created automatically on your first request — no setup needed."
- A `/compat/models` discovery endpoint exists. DevoxxGenie uses it to fill its model dropdown ([DevoxxGenie blog](https://genie.devoxx.com/blog/cloudflare-ai-gateway)). I did not find it in Cloudflare's own docs, so treat it as unverified from primary sources.

Note that the provider slugs differ between endpoints. `/compat` uses `google-ai-studio/...`, `grok/...` and `workers-ai/@cf/...`. The REST API uses `google/...`, `xai/...` and a bare `@cf/...`.

### 4. Universal Endpoint (deprecated)

The index lists "[Universal Endpoint (Deprecated)](https://developers.cloudflare.com/ai-gateway/usage/universal/)". This was a JSON array of provider requests with fallbacks. LiteLLM's request to support it ([BerriAI/litellm#1158](https://github.com/BerriAI/litellm/issues/1158), 2023-12-16) was closed as "not planned".

## Authentication summary

| Path | Cloudflare credential | Provider key needed? |
| --- | --- | --- |
| REST API `api.cloudflare.com/.../ai/*` | `Authorization: Bearer <CF token>` with **Workers AI Read** | No. Third-party models use Unified Billing, or a BYOK key stored on the gateway. |
| `gateway.ai.cloudflare.com/.../{provider}` | `cf-aig-authorization: Bearer <CF token>` (required when the gateway is authenticated) | Yes in `Authorization`, unless BYOK or Unified Billing applies. For Workers AI, the "provider key" is a CF token. |
| `gateway.ai.cloudflare.com/.../compat` | Either `Authorization: Bearer <CF token>` alone (stored key / Unified Billing), or `cf-aig-authorization` plus a provider key | Optional |

Other auth facts:
- The page now says: "AI Gateway requires a valid Cloudflare API token for each request." Its table still lists the case "Authentication Off, no header: request succeeds". So authentication is still a per-gateway setting. The **auto-created `default` gateway has Authentication On** ([Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/), updated 2026-09-15).
- Token scope: "The `AI Gateway Read`, `Run`, and `Edit` permissions cannot be restricted to a single gateway ... Any token with `AI Gateway Run` can send requests through every gateway in the account, including any configured with stored provider keys" ([Authenticated Gateway](https://developers.cloudflare.com/ai-gateway/configuration/authentication/)).
- The Get Started guide tells users to create a token with `AI Gateway - Read`, `AI Gateway - Edit` and `Workers AI - Read` ([Get started](https://developers.cloudflare.com/ai-gateway/get-started/)).

## Default gateway (auto-create)

From [Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/):

> "If you omit the gateway ID from your request entirely, AI Gateway defaults to using `default` as the gateway ID. When no gateway named `default` exists in your account, AI Gateway creates it on the first authenticated request."

| Setting | Default value |
| --- | --- |
| Authentication | On |
| Log collection | On |
| Caching | Off (TTL of 0) |
| Rate limiting | Off |
| Require provider credentials | Off |
| Workers AI billing | Standard billing |

"Auto-creation only applies to the gateway ID `default`. Using any other gateway ID requires creating the gateway first."

## BYOK (stored keys)

Source: [BYOK (Store Keys)](https://developers.cloudflare.com/ai-gateway/configuration/bring-your-own-keys/) (updated 2026-07-31).

- Provider keys are stored in Cloudflare Secrets Store and attached to a gateway. Requests then omit the provider `Authorization` header: "Note that you still need to pass `cf-aig-authorization`."
- A gateway can hold multiple keys per provider under aliases. `cf-aig-byok-alias` selects one, but only on provider-passthrough requests. On Unified Billing endpoints, "only the `default` alias is consulted".
- Prerequisite: the gateway must be authenticated.

## Unified Billing

Source: [Unified Billing](https://developers.cloudflare.com/ai-gateway/features/unified-billing/) (updated 2026-09-23).

- The user buys prepaid credits in the dashboard (5% fee). Third-party inference is then charged against those credits at pass-through prices.
- Credential precedence:
  1. A provider key on the request is forwarded unchanged.
  2. Otherwise, a BYOK `default`-alias key is used.
  3. Otherwise, the request goes to Unified Billing on Cloudflare-managed credentials.
- The "Require provider credentials" setting (`byok_only: true`, added 2026-09-14), or the per-request `cf-aig-no-wholesale: true` header, blocks the fallback to Unified Billing. "Workers AI requests do not use provider credentials. This setting does not block these requests."
- Workers AI can be billed to credits when the gateway's **Workers AI Billing** setting is "Unified billing". The default is "Standard billing", which is the normal Workers AI invoice. "Prepaid credits provide access to Workers AI models that otherwise require the Workers Paid plan and provide higher rate limits for frontier models." The changelog gives the numbers: 50 req/min per model with credits versus 20 req/min with standard billing, for `@cf/moonshotai/kimi-k2.6`, `@cf/moonshotai/kimi-k2.7-code` and `@cf/zai-org/glm-5.2`.
- Zero Data Retention applies only to Unified Billing requests that use Cloudflare-managed credentials.

## Other gateway features relevant to an app like Kiln

- **Caching** is off by default. It applies only to identical requests, and streaming responses are not cached by default ([Caching](https://developers.cloudflare.com/ai-gateway/features/caching/), [Troubleshooting](https://developers.cloudflare.com/ai-gateway/reference/troubleshooting/)). A per-request `cf-aig-skip-cache: true` bypasses it.
- **Logging** is on by default and stores prompts and responses. `cf-aig-collect-log-payload: false` (added 2026-03-17) keeps the metadata but drops the payloads ([Changelog](https://developers.cloudflare.com/ai-gateway/changelog/)).
- **Spend limits** (2026-06-05), **automatic retries** (2026-04-02), **User Insights** and **Cloudflare Access identity** (2026-08-05), **custom costs** (with cache-token rates, 2026-09-09) and **dynamic routes** (`model: "dynamic/<route>"`) are all gateway-side settings. None of them needs client changes beyond picking the gateway.
