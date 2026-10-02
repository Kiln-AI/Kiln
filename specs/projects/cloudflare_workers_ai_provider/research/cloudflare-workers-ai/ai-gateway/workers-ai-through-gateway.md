# Routing Workers AI Through AI Gateway, and What LiteLLM Does With It

## Direct call vs gateway call: the actual difference

On the current (Sept 2026) REST API, routing a Workers AI call through a gateway takes **one extra HTTP header**. The URL, token, model ID and request body stay the same.

Direct Workers AI, from the [Workers AI OpenAI-compat page](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/) (updated 2026-09-18), with no gateway header:

```bash
curl https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions \
  --header "Authorization: Bearer {api_token}" \
  --data '{"model": "@cf/meta/llama-3.1-8b-instruct", "messages": [...]}'
```

Through AI Gateway, from [AI Gateway Get started](https://developers.cloudflare.com/ai-gateway/get-started/) (updated 2026-08-07):

```bash
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/ai/v1/chat/completions" \
  --header "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  --header "cf-aig-gateway-id: default" \
  --data '{"model": "@cf/moonshotai/kimi-k2.6", "messages": [...]}'
```

> "The `cf-aig-gateway-id: default` header routes this Workers AI request through your account's default gateway. If the gateway does not exist, AI Gateway creates it on the first authenticated request."
> "For third-party models, you do not need to specify a gateway ... Workers AI requests always require the `cf-aig-gateway-id` header."

**How I read "always require".** Cloudflare's own Workers AI docs from the same month still show the endpoint without the header. So the sentence means: a Workers AI request goes through a gateway only when this header is present, and there is no implicit default gateway for `@cf/` models. It does not mean direct Workers AI calls now fail without the header. This is inference from comparing the two pages, and I have not checked it against a live account.

The native endpoint works the same way: `POST /ai/run/@cf/moonshotai/kimi-k2.6` plus `cf-aig-gateway-id` ([REST API](https://developers.cloudflare.com/ai-gateway/usage/rest-api/)). "To use prepaid AI Gateway credits for Workers AI, use the model-in-path endpoint shown above." That note is attached to the native `/ai/run/{model}` form. The docs do not say plainly whether credits billing also works on `/ai/v1/chat/completions`. See Open Questions in the summary.

### The legacy way: a different base URL

Before the REST API merge, routing Workers AI through a gateway meant swapping the base URL:

| | Base URL |
| --- | --- |
| Direct, OpenAI-compat | `https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1` |
| Via gateway, OpenAI-compat (legacy) | `https://gateway.ai.cloudflare.com/v1/{acct}/{gateway}/workers-ai/v1` ([LibreChat](https://www.librechat.ai/docs/configuration/librechat_yaml/ai_endpoints/cloudflare)) |
| Via gateway, native (legacy) | `https://gateway.ai.cloudflare.com/v1/{acct}/{gateway}/workers-ai/@cf/...` ([Changelog 2025-02-06](https://developers.cloudflare.com/ai-gateway/changelog/)) |
| Via gateway, unified `/compat` | `https://gateway.ai.cloudflare.com/v1/{acct}/{gateway}/compat` with model `workers-ai/@cf/...` ([Unified API](https://developers.cloudflare.com/ai-gateway/usage/chat-completion/)) |

On the legacy paths, the Workers AI token goes in `Authorization`. If the gateway is authenticated, which the auto-created `default` gateway is, a Cloudflare token with gateway `Run` permission must also go in `cf-aig-authorization` ([Authenticated Gateway](https://developers.cloudflare.com/ai-gateway/configuration/authentication/)). That can be the same token if it has both scopes. That makes the legacy route more awkward than the header route.

### What stays the same

The credentials don't change. It's the same account ID and the same API token with **Workers AI Read**. The REST API page says all `/ai/*` endpoints need exactly that permission. **Unverified:** whether a Workers-AI-only token can *auto-create* the `default` gateway, and whether routing through an authenticated gateway on `api.cloudflare.com` also needs an `AI Gateway` permission on the token. The Get Started guide asks for `AI Gateway - Read` + `AI Gateway - Edit` + `Workers AI - Read`, which suggests the gateway permissions may matter for auto-creation.

**Model IDs don't change.** Model IDs stay `@cf/...` on the REST API path. They change only on the legacy `/compat` path, where they become `workers-ai/@cf/...`.

**Features:** **inferred** from the gateway being a pass-through proxy on the same endpoint, not stated feature by feature in the docs. Request and response bodies are Workers AI's own, so structured output, tools and streaming should behave the same.

### What changes for the user

| Aspect | Direct | Through gateway |
| --- | --- | --- |
| Observability | Workers AI dashboard usage only | Per-request logs (prompts and responses stored by default), analytics, cost, User Insights |
| Caching | None | Optional. Off by default. Applies only to identical requests |
| Rate limiting / spend limits | Workers AI platform limits only | Configurable per gateway |
| Billing | Workers AI standard billing | Standard by default, or prepaid credits ("Unified billing") when set on the gateway. Credits unlock some frontier models without Workers Paid, with higher per-model rate limits (50 vs 20 req/min) |
| Retries/fallback | Client-side | Gateway-side retries, dynamic routes |
| Data handling | Workers AI only | Plus gateway log storage, unless logging is off or `cf-aig-collect-log-payload: false` is sent |

Sources: [Manage gateways](https://developers.cloudflare.com/ai-gateway/configuration/manage-gateway/), [Unified Billing](https://developers.cloudflare.com/ai-gateway/features/unified-billing/), [Changelog 2026-08-07](https://developers.cloudflare.com/ai-gateway/changelog/), [Caching](https://developers.cloudflare.com/ai-gateway/features/caching/).

**Risk for Kiln (inference).** Suppose a user turns on caching for their gateway. Kiln sometimes sends identical requests on purpose, for example several samples of the same prompt in synthetic data generation, or repeated eval runs. Those could come back as cached copies. Streaming responses are "not cached by default", and caching is off by default, so the risk is limited to users who opt in. Kiln could send `cf-aig-skip-cache: true` if this matters.

## LiteLLM support

Installed version checked: **LiteLLM 1.87.1** (`/home/user/Kiln/.venv/lib/python3.13/site-packages/litellm`).

### No first-class AI Gateway provider

- `grep` over the LiteLLM source finds no `gateway.ai.cloudflare.com`, no `cf-aig-*` handling, and no `cloudflare_ai_gateway` provider. The only "AI gateway" provider is `vercel_ai_gateway`.
- Older feature requests for AI Gateway support were closed or never done. [#1158](https://github.com/BerriAI/litellm/issues/1158) (2023-12-16, universal endpoint) was "Closed as not planned". Per-provider requests exist for Vertex ([#3732](https://github.com/BerriAI/litellm/issues/3732)), Bedrock ([#1040](https://github.com/BerriAI/litellm/issues/1040)) and Google AI Studio ([#5428](https://github.com/BerriAI/litellm/issues/5428), [#9975](https://github.com/BerriAI/litellm/issues/9975)).
- [#21115](https://github.com/BerriAI/litellm/issues/21115) (2026-02-13, open, no maintainer response seen) says LiteLLM's Cloudflare provider "hasn't been updated in approximately 10 months".

### The native `cloudflare/` provider drops custom headers

In LiteLLM 1.87.1:

- In `litellm/main.py` (around line 4155), `api_base` defaults to `https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/`. It can be overridden with `api_base` or `CLOUDFLARE_API_BASE`.
- In `litellm/llms/cloudflare/chat/transformation.py`, `validate_environment()` **builds a fresh header dict and ignores the `headers` it receives**:

```python
headers = {
    "accept": "application/json",
    "content-type": "apbplication/json",
    "Authorization": "Bearer " + api_key,
}
return headers
```

I tested this against a local mock HTTP server with the script at `scratchpad/hdr_test.py` (not in the repo). I passed `headers={"cf-aig-gateway-id": "my-gw"}` (the kwarg Kiln's `LiteLlmAdapter` uses) and then `extra_headers=...`:

```
cloudflare/  -> POST /client/v4/accounts/ACCT/ai/run/%40cf/meta/llama-3.1-8b-instruct | auth: Bearer CFTOKEN | cf-aig-gateway-id: None
openai/      -> POST /client/v4/accounts/ACCT/ai/v1/chat/completions             | auth: Bearer CFTOKEN | cf-aig-gateway-id: my-gw
```

So:
- With `cloudflare/`, the gateway header approach **does not work**, because the header is silently dropped. The only way to reach a gateway would be to point `api_base` at the legacy `https://gateway.ai.cloudflare.com/v1/{acct}/{gw}/workers-ai/`. Also note that `@` is URL-encoded to `%40` in the path, and the content-type typo `apbplication/json` is present. (**Unverified** against the live gateway. The `cf-aig-authorization` header, which an authenticated gateway needs, also could not be added.)
- With `openai/` pointed at `https://api.cloudflare.com/client/v4/accounts/{acct}/ai/v1`, custom headers go through, so adding `cf-aig-gateway-id` works. Kiln already has a `default_headers` slot in `LiteLlmCoreConfig` (`libs/core/kiln_ai/adapters/provider_tools.py`), which OpenRouter uses. A gateway ID would therefore just be one more default header.

Whether Kiln should use `openai/` or `cloudflare/` for Workers AI in general belongs to the API subtopic. From the gateway side, **only the `openai/` route makes an optional gateway cheap to support.**

### Third-party models via Cloudflare in LiteLLM

The REST API `/ai/v1/chat/completions` is OpenAI-compatible and takes `author/model` IDs. So `openai/<author>/<model>` via LiteLLM's OpenAI provider, with `api_base` set to `.../ai/v1`, should reach third-party models with only the Cloudflare token. This is **inferred** from the docs and not tested live. It is the same shape as how Kiln uses OpenRouter today.
