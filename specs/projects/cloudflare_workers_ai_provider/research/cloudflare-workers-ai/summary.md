# Research: Cloudflare Workers AI

## Bottom Line

Workers AI fits Kiln as a normal provider, with one wrinkle: it needs two credentials, an API token and a 32-hex account ID, and the account ID goes into every URL. Kiln should call the OpenAI-compatible endpoint `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions` through LiteLLM's `openai/` provider with a custom base URL, the same way Kiln wires SiliconFlow. Don't use LiteLLM's `cloudflare/` provider in Kiln's pinned version (1.87.x). It drops every parameter except `stream` and `max_tokens`, and it drops custom headers too. The best Connect check is `GET /accounts/{id}/ai/models/search?per_page=1`, which is free.

The three open questions from the project overview:

1. **AI Gateway: one provider, not two.** Ship one Workers AI provider with an optional "AI Gateway ID" field. When it's set, Kiln sends a `cf-aig-gateway-id` header on the same endpoint. This only works on the `openai/` route. Don't build a separate "Cloudflare AI Gateway" provider now; it would be a second OpenRouter.
2. **Machine-readable model list: yes.** The model search API is official and needs a token. There's also a public, undocumented JSON at `https://ai-cloudflare-com.pages.dev/api/models` that needs no login and feeds Cloudflare's own docs. Per-model JSON files are also in the `cloudflare/cloudflare-docs` GitHub repo. models.dev (`cloudflare-workers-ai`) is current and works as a cross-check. LiteLLM's Cloudflare catalog is stale.
3. **Static or per-account: static.** There's one global, Cloudflare-curated list of `@cf/...` IDs, like OpenRouter's. Accounts differ only in whether a call succeeds (paid-plan gating, one license-agree model), not in which IDs exist.

Nothing here was tested against a live Cloudflare account. Treat error codes and gateway behavior as documented or inferred, not observed.

## Key Findings

- **Use `/ai/v1`, not the native `/ai/run`.** `/ai/run` returns a different response shape for each model generation, while `/v1` returns one OpenAI shape. There's no `GET /ai/v1/models`; it returns 405. ([API](./workers-ai-api/summary.md))
- **LiteLLM's `cloudflare/` provider is being rewritten.** It moved to `/ai/v1` in LiteLLM 1.91.0 (July 2026), so it becomes a real option after an upgrade. Even then it takes the account ID only from an env var or `api_base`. ([API](./workers-ai-api/summary.md))
- **Connect validation.** Don't use `/user/tokens/verify`: it rejects valid account-owned tokens and doesn't check Workers AI permission. A bad account ID gives 404/7003. A bad token gives 401/403/10000. "Wrong token" and "wrong account" probably can't be fully told apart. ([API](./workers-ai-api/summary.md))
- **Features vary a lot by model generation.** Newer models behave like OpenAI (tools, JSON schema, logprobs, `reasoning_effort`). Older ones default to 256 output tokens, so always send `max_tokens`. Tool calling is labeled Beta. JSON mode isn't guaranteed and doesn't stream. Reasoning output arrives in three different field conventions, and LiteLLM's `openai/` provider already handles all three. ([API](./workers-ai-api/summary.md))
- **Catalog size and capability flags.** There are 31 text-generation models, all `@cf/...` since the last `@hf/` models were retired on 2026-05-30. 18 support function calling and 7 support vision. The public JSON carries `context_window`, `function_calling`, `vision`, `reasoning`, `reasoning_effort`, `price`, `require_workers_paid` and `planned_deprecation_date`. It has no JSON-mode flag and no max-output field, so those need Kiln's own per-model tests. ([Catalog](./model-catalog/summary.md))
- **Seven frontier models need a paid billing method.** They are Kimi K2.6 and K2.7 Code, GLM 5.2, 5.3 and 5.3 Flash, and DeepSeek V4 Pro and Flash. On Workers Free they return 403/5035. They're limited to 20 requests per minute per account per model, or 50 with prepaid AI Gateway credits. That's low for Kiln's parallel eval and synthetic-data runs. The free tier is 10,000 Neurons a day; Workers Paid is $5 a month. ([API](./workers-ai-api/summary.md), [Gateway](./ai-gateway/summary.md))
- **Retirements come in batches with 2–3 weeks' notice.** There were 19 models in October 2025 and 18 in May 2026. A model due for retirement gains `planned_deprecation_date` in the catalog data. A retired ID usually returns 5007, but once an ID was quietly pointed at a pricier model (Kimi K2.5 now runs K2.6). ([Catalog](./model-catalog/summary.md))
- **AI Gateway moved onto `api.cloudflare.com` in 2026.** For Workers AI, a gateway is now one header on the same call, with the same token and model IDs. The same credentials can also reach `openai/...` and `anthropic/...` models on prepaid Cloudflare credits. A `default` gateway is created automatically on the first authenticated request. ([Gateway](./ai-gateway/summary.md))
- **Comparable tools split on shape.** Cloudflare's own SDKs (Vercel `workers-ai-provider`, `langchain-cloudflare`) use Workers AI with an optional gateway. OpenCode, models.dev, Kilo and others use two providers, where the gateway provider acts as a multi-vendor router. ([Gateway](./ai-gateway/summary.md))

## Implications

- **One decision gates two others.** Choosing LiteLLM's `openai/` route over `cloudflare/` is what makes the gateway field possible, because `cloudflare/` drops the header. It also avoids the old provider's dropped parameters. If Kiln upgrades LiteLLM past 1.91 later, it can revisit `cloudflare/`. But `cloudflare/` would still need a fix before the gateway header works.
- **Connect UI.** Two required fields (Account ID, API token), plus an optional AI Gateway ID if option (b) is taken. The help text should name the token permissions: Workers AI Read (the dashboard template also grants Edit), and possibly AI Gateway Read/Edit when a gateway is used, which is unconfirmed.
- **Error mapping matters.** Kiln should show 5035 as "this model needs Workers Paid", not as a bad key. It should treat 429 code 3036 (daily free quota used up) as don't-retry, and 429 code 3040 (out of capacity) as retry.
- **Model list maintenance.** Maintain the entries statically in `ml_model_list.py`. Update the `claude-maintain-models` skill to read Cloudflare's public JSON, or the search API when a token is available, as the source of truth. Use models.dev as a cross-check and don't rely on LiteLLM for Cloudflare. Add Cloudflare to the skill's "Lagging Providers" section and to `provider_utils.py` for deprecation checks, and flag models that gain `planned_deprecation_date`. Draft skill text is in the catalog subtopic.
- **Per-model flags must be tested, not copied.** JSON mode support, whether `/v1` translates `response_format`, `tools` and `image_url` for older models, and tool-call reliability (Llama 3.3 70B reportedly doesn't emit tool calls on `/v1`) all need Kiln's paid per-model tests.
- **Concurrency.** The low limits on paid-only models suggest a conservative default concurrency for this provider.

## Conflicts and Uncertainty

- **Is the gateway header optional?** The AI Gateway docs say "Workers AI requests always require the `cf-aig-gateway-id` header". Cloudflare's Workers AI docs from the same month show calls without it. The gateway subtopic reads the header as opt-in, but that's untested. It matters: if the header were required, a direct call would fail.
- **Validation call vs gateway ID.** The API subtopic recommends `/ai/models/search` for Connect. The gateway subtopic recommends that the Connect call include the gateway header, so a wrong gateway ID fails early. Nobody established whether the search endpoint honours or checks that header. If it doesn't, validating a gateway ID may need a real, billed chat call.
- **Credits on the `/v1` path.** The docs name only `/ai/run/{model}` for paying Workers AI with gateway credits. It's unclear whether `/v1/chat/completions` plus the header bills to credits. That's the path Kiln would use.
- **Which paid-only models credits unlock.** The gateway changelog names three (Kimi K2.6, K2.7 Code, GLM 5.2). The launch posts for DeepSeek V4 and GLM 5.3 say "Workers Paid plan or prepaid AI Gateway credits". This is probably all seven, but no single source says so.
- **Source disagreements on model data.** Kimi K2.6 thinking control is `thinking` in the changelog and `enable_thinking` in the model schema. Mistral Small 3.1 has vision per the changelog but no vision flag in the data. DeepSeek V4 Flash context is 1,048,576 per Cloudflare and 1,310,720 per models.dev. Prefer Cloudflare's own model data, and confirm by testing.
- **Moving target.** The REST API merge for AI Gateway (May and August 2026) and the LiteLLM `cloudflare/` rewrite (July 2026) are both recent, and their docs are still changing.

## Gaps

- **No live testing, across all three subtopics.** The session proxy blocked `api.cloudflare.com`, `developers.cloudflare.com`, `models.dev` and `docs.litellm.ai`, and there were no Cloudflare credentials. Findings come from the `cloudflare/cloudflare-docs` GitHub source, Cloudflare's OpenAPI spec, LiteLLM source (plus one local mock-server test of headers), Tavily extracts and third-party bug reports. A short session with a real Free and a real Paid account would close most gaps below.
- **Connect error bodies** for "valid token, wrong but well-formed account ID" and "token without Workers AI permission" are inferred, not observed.
- **Gateway behavior:** the error for a gateway ID that doesn't exist, whether a Workers-AI-only token can auto-create `default` or use an authenticated gateway, and whether the header is truly opt-in.
- **`/v1` compatibility for every model.** Not checked. Qwen 3.8's launch post mentions only `/ai/run`. Also unknown: whether `/v1` rejects or ignores OpenAI parameters an older model doesn't declare.
- **Exact response shape of `/ai/models/search`**, including its `format=openrouter` fields, and whether an account ever sees private models in it. The OpenAPI spec leaves the item schema untyped.
- **Smaller items:** whether GPT-OSS returns reasoning on `/v1/chat/completions`; whether the Cloudflare-wide 1,200 requests per 5 minutes limit applies to inference; whether LiteLLM 1.90.x patch releases already include the `cloudflare/` rewrite; what a retired ID actually returns.

## Subtopics

- [Workers AI API, auth and LiteLLM support](./workers-ai-api/summary.md) — endpoints, credentials, Connect validation, error codes, feature support, pricing and limits. Headline: use `/ai/v1` via LiteLLM `openai/`, and validate with `/ai/models/search`.
- [Model catalog and discovery](./model-catalog/summary.md) — static vs per-account list, machine-readable sources, current text models, lifecycle and a maintenance procedure for the skill. Headline: one global static list, with a public JSON and models.dev as good sources.
- [AI Gateway](./ai-gateway/summary.md) — what the gateway is, its endpoint families, billing, LiteLLM support and how other tools expose it. Headline: one provider with an optional gateway ID header, option (b).
