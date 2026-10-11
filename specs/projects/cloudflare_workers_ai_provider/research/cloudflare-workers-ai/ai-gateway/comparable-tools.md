# How Other Tools Expose Workers AI and AI Gateway

The question is whether other tools treat these as one provider, as two providers, or as a gateway setting on a Workers AI provider. Sources were read on 2026-09-28.

## Summary table

| Tool | Shape | Credentials asked for | Source |
| --- | --- | --- | --- |
| **Cloudflare `workers-ai-provider`** (Vercel AI SDK, Cloudflare-maintained) | **Workers AI provider with an optional `gateway` option.** It now also routes third-party `provider/model` slugs through the gateway (experimental) | `accountId` + `apiKey` (or Worker `binding`); optional `gateway: {id}` | [README](https://github.com/cloudflare/ai/blob/main/packages/workers-ai-provider/README.md) |
| **Cloudflare `ai-gateway-provider`** (Vercel AI SDK) | A separate gateway wrapper that wraps other AI SDK providers, with fallback across models | `accountId`, `gateway`, `apiKey` ("Only required if your gateway has authentication enabled") | [AI SDK docs](https://ai-sdk.dev/providers/community-providers/cloudflare-ai-gateway) |
| **LangChain** (`langchain-cloudflare`, Cloudflare-maintained) | **Workers AI chat class with an optional `ai_gateway` parameter** | Account ID + API token; optional gateway | [README](https://github.com/cloudflare/langchain-cloudflare/blob/main/libs/langchain-cloudflare/README.md) |
| **OpenCode** | **Two separate providers**: "Cloudflare Workers AI" and "Cloudflare AI Gateway" | Workers AI: Account ID + API key. AI Gateway: Account ID + Gateway ID + API token | [OpenCode providers docs](https://opencode.ai/docs/providers/) |
| **models.dev** (catalog behind OpenCode and others) | **Two provider entries**: `cloudflare-workers-ai` and `cloudflare-ai-gateway` | `cloudflare-workers-ai`: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_KEY`. `cloudflare-ai-gateway`: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID` | [workers-ai provider.toml](https://github.com/sst/models.dev/blob/dev/providers/cloudflare-workers-ai/provider.toml), [ai-gateway provider.toml](https://github.com/sst/models.dev/blob/dev/providers/cloudflare-ai-gateway/provider.toml) |
| **Kilo Code** (OpenCode fork) | Two providers, inherited from OpenCode | Same as OpenCode. Their VS Code connect dialog had a bug that dropped Account ID and Gateway ID | [Kilo-Org/kilocode#9987](https://github.com/Kilo-Org/kilocode/issues/9987) |
| **VoltAgent** | `cloudflare-ai-gateway/<model>` provider, from models.dev | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID` | [VoltAgent docs](https://voltagent.dev/models-docs/providers/cloudflare-ai-gateway) |
| **Pi** (coding agent) | Built-in `cloudflare-ai-gateway` provider | `CLOUDFLARE_API_KEY` (gateway token), `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_GATEWAY_ID` (can be `default`) | [Cloudflare docs: Pi](https://developers.cloudflare.com/ai-gateway/integrations/coding-agents/pi/) |
| **DevoxxGenie** (IntelliJ plugin, v1.10.0) | One "Cloudflare AI Gateway" provider. It builds the `/compat` URL from three fields and discovers models from `/compat/models` | Cloudflare token, account ID, gateway name (default `default`) | [DevoxxGenie blog](https://genie.devoxx.com/blog/cloudflare-ai-gateway) |
| **LibreChat** | No built-in provider. A documented "Cloudflare Workers AI" custom endpoint that goes **through a gateway** (legacy `.../workers-ai/v1` URL) | `CF_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`; hand-maintained model list (`fetch: false`) | [LibreChat docs](https://www.librechat.ai/docs/configuration/librechat_yaml/ai_endpoints/cloudflare) |
| **Open WebUI** | No native provider found. The 2024 feature request for Workers AI is closed. Community "functions" or generic OpenAI connections are used instead | n/a | [open-webui#3277](https://github.com/open-webui/open-webui/issues/3277), [community function](https://openwebui.com/f/christiant/cloudfare_workerai) |
| **LiteLLM** | `cloudflare/` provider (Workers AI only). No AI Gateway provider | `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, optional `CLOUDFLARE_API_BASE` | [LiteLLM docs](https://docs.litellm.ai/docs/providers/cloudflare_workers); source of 1.87.1 |

## Notes per tool

### Cloudflare's own libraries: Workers AI with an optional gateway

Cloudflare maintains both the Vercel AI SDK `workers-ai-provider` and `langchain-cloudflare`. Both use the **"Workers AI provider plus optional gateway"** shape.

`workers-ai-provider` options, verbatim from the README:

| Option | Description |
| --- | --- |
| `binding` | "Workers AI binding (`env.AI`). Use this OR credentials." |
| `accountId` | "Cloudflare account ID. Required with `apiKey`." |
| `apiKey` | "Cloudflare API token. Required with `accountId`." |
| `gateway` | "Optional AI Gateway config." |
| `providers` | "Experimental. Wire-format plugins that enable routing `\"/\"` slugs via gateway." |

It now also accepts third-party slugs such as `workersai("openai/gpt-5", …)` and `workersai("deepseek/deepseek-chat", {byok: true, …})`: "Without `byok`, provider auth headers are stripped so unified billing / the gateway's stored key applies." So Cloudflare's own SDK is folding "third-party models via the gateway" **into the Workers AI provider**. It does not add a second provider for them.

`langchain-cloudflare`: "When `ai_gateway` is configured, OpenAI-compatible mode routes through the Workers AI chat completions path on AI Gateway." The class also exposes `aig_request_timeout`, `aig_max_attempts`, `aig_retry_delay` and `aig_backoff`, according to a search-engine summary of the README. I did not see those four parameters in the README extract I read, so treat them as lightly sourced.

### Multi-provider coding agents: two providers

OpenCode, models.dev, Kilo Code, VoltAgent and Pi treat **AI Gateway as its own provider**. It gets its own model namespace (`openai/gpt-4o`, `anthropic/claude-sonnet-4`, ...), its own connect flow (Account ID → Gateway ID → token), and third-party models billed through Unified Billing or BYOK. OpenCode's text: "Cloudflare AI Gateway lets you access models from OpenAI, Anthropic, Workers AI, and more through a unified endpoint. With Unified Billing you don't need separate API keys for each provider."

In this pattern the gateway provider is mainly **a multi-vendor router, like OpenRouter**, not a way to observe Workers AI traffic. The Kilo Code bug shows the cost of two similar connect flows. Both need an Account ID, and one field was easy to drop.

The models.dev `cloudflare-ai-gateway` entry notes that it routes "other third-party providers ... over the catalog-aware REST API: POST `/ai/v1/chat/completions`, `/ai/v1/responses`, and `/ai/v1/messages`". So even the "two providers" camp now uses the same `api.cloudflare.com` endpoint that Workers AI uses.

### Single-app integrations: gateway-first

DevoxxGenie and LibreChat's recipe both require a gateway ID. They treat the gateway as the way in. DevoxxGenie markets it as "One Key, Every Provider".

## Takeaways for Kiln

1. **No consensus.** Cloudflare's own SDKs use "Workers AI plus optional gateway". Multi-provider coding agents use "two providers". Nobody I found uses "gateway only, no direct Workers AI".
2. Tools that ship **two providers** do so to get **third-party models under one Cloudflare bill**, which is an OpenRouter-like feature. Tools that ship **one provider with a gateway option** do so for **observability and caching of Workers AI traffic**.
3. After the 2026 REST API merge, both uses hit the same URL with the same token. The gateway ID is only a header. **Inference:** the two-provider split now mostly reflects model-catalog and UX choices, not a technical need.
