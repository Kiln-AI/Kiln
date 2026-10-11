# Workers AI: Endpoints, Authentication and Credential Validation

Research date: 2026-09-28. Primary sources are the `cloudflare/cloudflare-docs` GitHub repo (commit `c153001`, 2026-09-28, the source of developers.cloudflare.com) and Cloudflare's published OpenAPI spec (`cloudflare/api-schemas`, `openapi.json`, fetched 2026-09-28). developers.cloudflare.com and api.cloudflare.com were blocked by this session's network proxy, so docs were read from the repo source and no live API call was made. Anything about live error bodies comes from third-party reports and is labeled.

## 1. The endpoints

All Workers AI REST endpoints live under `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/...`. The account ID is in the path of **every** call.

| Endpoint | Method | Shape | Notes |
|---|---|---|---|
| `/ai/run/{model_name}` | POST | Native. Body is the model's own input schema. Response wrapped in Cloudflare envelope `{result, success, errors, messages}` | The original API. [OpenAPI `workers-ai-post-run-model`] |
| `/ai/run` | POST | Native, model named in body | "generic interface ... where the model name is part of the request payload ... supports all AI Gateway features" [OpenAPI `workers-ai-post-run-generic`] |
| `/ai/v1/chat/completions` | POST | OpenAI Chat Completions | Recommended for OpenAI-style clients. Not in the OpenAPI spec; documented in the OpenAI-compat page. |
| `/ai/v1/embeddings` | POST | OpenAI Embeddings | |
| `/ai/v1/responses` | POST | OpenAI Responses | GPT-OSS models only, `stream: false` only |
| `/ai/models/search` | GET | Cloudflare envelope | Model catalog search; needs `Workers AI Read` or `Write` |

Sources:
- OpenAI-compatible page, verbatim: "Workers AI provides OpenAI-compatible endpoints for text generation through Chat Completions (`/v1/chat/completions`) and for text embedding models (`/v1/embeddings`). The Responses API (`/v1/responses`) is available only for GPT-OSS models. Easily call Workers AI by swapping the `baseURL` in the standard OpenAI SDK." and "Most Workers AI text generation models support the OpenAI Chat Completions API." ([docs page](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/), [source](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/configuration/open-ai-compatibility.mdx), [partial](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/partials/workers-ai/openai-compatibility.mdx))
- The documented base URL for the OpenAI SDK is `https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/ai/v1`, with the API token as `apiKey` (same page).
- Paths for `/ai/run`, `/ai/run/{model_name}`, `/ai/models/search`, `/ai/models/schema`, `/ai/tasks/search`, `/ai/authors/search`, `/ai/finetunes` are in the [Cloudflare OpenAPI spec](https://raw.githubusercontent.com/cloudflare/api-schemas/main/openapi.json) (v4.0.0). `/ai/v1/*` paths are not in that spec.
- `GET /ai/v1/models` does **not** exist. A third-party report (2026-09-28) shows Cloudflare returning `405 {"result":null,"success":false,"errors":[{"code":7001,"message":"GET not supported for requested URI."}],"messages":[]}` for it ([ks1686/peaproxy#45](https://github.com/ks1686/peaproxy/issues/45)). So the OpenAI SDK's `models.list()` cannot be used for validation or discovery.

### Native vs OpenAI-compatible: which is recommended

Cloudflare does not say "use X" in one sentence, but everything points to `/ai/v1/chat/completions` for chat clients:

- Every 2026 model launch post lists the OpenAI-compatible endpoint as a first-class way in (e.g. Kimi K2.6: "Use Kimi K2.6 through the Workers AI binding (`env.AI.run()`), the REST API at `/ai/run`, or the OpenAI-compatible endpoint at `/v1/chat/completions`" — [changelog 2026-04-20](https://developers.cloudflare.com/changelog/post/2026-04-20-kimi-k2-6-workers-ai/)).
- The native `/ai/run` response shape is **not uniform across models**. Older models return `{"result": {"response": "...", "tool_calls": [...], "usage": {...}}}` (e.g. `llama-3.3-70b-instruct-fp8-fast` output schema). Newer models (Kimi K2.6, GLM, Gemma 4, DeepSeek V4, Qwen 3.8, Nemotron) return a full OpenAI chat-completion object (`id`, `choices[].message`, `usage.completion_tokens_details.reasoning_tokens`) inside `result` (from the model JSON files in [`src/content/workers-ai-models/`](https://github.com/cloudflare/cloudflare-docs/tree/production/src/content/workers-ai-models)). GPT-OSS on `/ai/run` "dynamically detects your input format and accepts Chat Completions (`messages`), legacy Completions (`prompt`), or Responses API (`input`)" ([release notes 2026-02-17](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/release-notes/workers-ai.yaml)). A client of `/ai/run` has to handle several response shapes; a client of `/ai/v1/chat/completions` gets one.
- Cloudflare has actively fixed OpenAI-compat bugs on `/v1/chat/completions` (tool-call IDs, `finish_reason: "tool_calls"`, `content: null` assistant messages; 2026-02-17 release notes, same source).
- LiteLLM itself moved its `cloudflare/` provider off `/ai/run` to `/ai/v1` in June 2026, logging: "Cloudflare api_base ending in '/ai/run' is the legacy Workers AI path and no longer serves OpenAI-compatible requests" (see [litellm-support.md](./litellm-support.md)).

**Inference:** for Kiln, `/ai/v1/chat/completions` is the right endpoint. `/ai/run` remains needed only for features not on `/v1` (e.g. reranking, image/audio models — out of scope).

Other request options worth knowing:
- `options.rejectIfBusy: true` at the top level of a `/v1/chat/completions` body makes a request fail fast with HTTP 429 / code 3040 instead of queueing for capacity ([reject-if-busy](https://developers.cloudflare.com/workers-ai/features/reject-if-busy/), added 2026-09-17). "OpenAI clients that preserve custom fields can send this option."
- `x-session-affinity: <id>` header routes requests to the same instance to raise prefix-cache hits; cached input tokens are billed at a discount ([prompt caching](https://developers.cloudflare.com/workers-ai/features/prompt-caching/)).

## 2. Authentication

### Header
`Authorization: Bearer <API_TOKEN>` on every call. The OpenAPI spec also accepts the legacy `X-Auth-Email` + `X-Auth-Key` (Global API Key) scheme for `/ai/run` and `/ai/models/search`; Cloudflare calls tokens "the preferred authorization scheme" ([Model Search API reference](https://developers.cloudflare.com/api/resources/ai/subresources/models/methods/list/)).

### Token permissions
- The dashboard path is Workers AI > **Use REST API** > **Create a Workers AI API Token** (a prefilled template). Verbatim: "If you choose to create an API token instead of using the template, that token will need permissions for both `Workers AI - Read` and `Workers AI - Edit`." ([REST API get-started](https://developers.cloudflare.com/workers-ai/get-started/rest-api/))
- The OpenAPI spec lists `x-api-token-group: ['Workers AI Write', 'Workers AI Read']` for `/ai/run/{model}` and `/ai/models/search`, and the API reference renders this as "Accepted Permissions (at least one required)". **Discrepancy:** the spec implies Read alone can run inference; the get-started doc says to grant both. Third-party integrations ask users for `Workers AI:Read` only ([OmniRoute#5423](https://github.com/diegosouzapw/OmniRoute/issues/5423)). Kiln's help text should tell users to use the template (Read + Edit), which works either way.
- Permission names: "Workers AI Read — Grants read access to Workers AI", "Workers AI Edit — Grants write access to Workers AI" ([permissions reference](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)).

### User tokens vs account tokens
Cloudflare has two token kinds, and this matters for validation:
- **User API tokens** (created under My Profile > API Tokens). New ones are prefixed `cfut_`.
- **Account API tokens** (Manage Account > API Tokens; need Super Administrator to create). New ones are prefixed `cfat_`. Workers AI is listed ✅ in the account-token compatibility matrix ([account-owned tokens](https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/)).
- Token formats table (verbatim): Global API Key `cfk_[40 characters][checksum]`, User API Token `cfut_...`, Account API Token `cfat_...`. "Existing tokens continue to work." Pre-2026 tokens are unprefixed 40-character strings ([token formats](https://developers.cloudflare.com/fundamentals/api/get-started/token-formats/)).

### Is the account ID required on every call? Is there a single-credential option?
- **Yes, required.** Every Workers AI path is `/accounts/{account_id}/ai/...`, including the OpenAI-compatible base URL. The account ID is a 32-hex-character string (OpenAPI example `023e105f4ecef8ad9ca31a8372d0c353`), found on the dashboard Workers AI page under "Get Account ID" or the account overview sidebar.
- **No documented single-credential option for Workers AI direct.** I found no endpoint that takes only a token.
- Could Kiln derive the account ID from the token? `GET /accounts` lists "all accounts you have ownership or verified access to", but the OpenAPI spec lists only the `api_email`+`api_key` security scheme for it, and wrangler users with scoped tokens report needing extra permissions (`User > Memberships > Read`, `Account Settings > Read`) to list accounts ([workers-sdk#9129](https://github.com/cloudflare/workers-sdk/issues/9129)); account tokens have no Memberships permission at all. **Inference (not tested):** a token created from the Workers AI template probably cannot list its accounts, so auto-discovery is unreliable. Ask the user for both values. Kiln already has a two-field precedent (Fireworks: API Key + Account ID in `app/desktop/studio_server/provider_api.py`).
- A malformed or unsubstituted account ID produces a routing error, not an auth error: `404 {"result":null,"success":false,"errors":[{"code":7003,"message":"Could not route to /client/v4/accounts/$%7BCLOUDFLARE_ACCOUNT_ID%7D/ai/v1/chat/completions, perhaps your object identifier is invalid?"}],"messages":[]}` ([anomalyco/opencode#18552](https://github.com/anomalyco/opencode/issues/18552), 2026-03-21).

## 3. A cheap authenticated call for "Connect"

### Candidates

| Call | Checks token | Checks account ID | Checks Workers AI permission | Cost |
|---|---|---|---|---|
| `GET /user/tokens/verify` | yes (user tokens only) | no | no | free |
| `GET /accounts/{id}/tokens/verify` | yes (account tokens) | yes | no | free |
| `GET /accounts/{id}/ai/models/search?per_page=1` (live test: `per_page` is ignored) | yes (both kinds) | yes | **yes** | free (no inference) |
| `POST /accounts/{id}/ai/v1/chat/completions` tiny prompt | yes | yes | yes | burns Neurons; can hit 403/5035 on paid-only models |
| `GET /accounts/{id}/ai/v1/models` | — | — | — | does not exist (405) |

- `/user/tokens/verify` returns `{"result":{"id":"...","status":"active"},"success":true,...,"messages":[{"code":10000,"message":"This API Token is valid and active"}]}` ([create token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)). But it **rejects valid account-owned tokens** with `success:false [{"code":1000,"message":"Invalid API Token"}]`; those must use `GET /accounts/{account_id}/tokens/verify` ([noorinalabs-deploy#511](https://github.com/noorinalabs/noorinalabs-deploy/issues/511), 2026-06-30; same bug hit [favonia/cloudflare-ddns#1197](https://github.com/favonia/cloudflare-ddns/issues/1197)). Also neither verify endpoint checks that the token has Workers AI permission.
- `GET /accounts/{account_id}/ai/models/search`: "Searches Workers AI models by name or description." Accepted permissions: `Workers AI Write` or `Workers AI Read`. Query params: `per_page`, `page`, `task`, `author`, `source`, `hide_experimental`, `search`, `include_deprecated`, `format` (`openrouter`). Returns the standard envelope `{errors, messages, result[], success}`; declared error response is 404 ([OpenAPI](https://raw.githubusercontent.com/cloudflare/api-schemas/main/openapi.json), [API reference](https://developers.cloudflare.com/api/resources/ai/subresources/models/methods/list/)).

**Recommendation:** validate with `GET https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search?per_page=1` (optionally `&task=Text Generation`). It is free, works for user and account tokens, and exercises the same token + account + Workers AI permission that inference needs. The live test found `per_page` is ignored; Kiln's check uses `search=kiln-connection-check` instead, which returns an empty result ([live test findings](../../../live_test_findings.md)).

### Expected error responses (partly inferred — not tested live)

| Situation | Expected response | Confidence |
|---|---|---|
| Malformed account ID (wrong length, placeholder) | HTTP 404, code `7003` "Could not route to ..., perhaps your object identifier is invalid?" | Observed on `/ai/v1/chat/completions` ([opencode#18552](https://github.com/anomalyco/opencode/issues/18552)); assumed same for `/ai/models/search` |
| Bad / revoked token | HTTP 401 (sometimes 403), code `10000` "Authentication error" | Cloudflare's AI Search error table lists `10000 Authentication error — 401` ([AI Search error codes](https://developers.cloudflare.com/ai-search/troubleshooting/api-error-codes)); many community reports of `{"success":false,"errors":[{"code":10000,"message":"Authentication error"}]}` for Workers AI. LiteLLM's exception mapper matches the literal string "Authentication error" for Cloudflare. |
| Valid token, well-formed account ID it cannot access, or token lacking Workers AI permission | Most likely HTTP 403 / code `10000` "Authentication error" | Inferred from general Cloudflare API behavior; no Workers-AI-specific source found |
| Workers Free account calling a paid-only model | HTTP 403, code `5035` "This model requires a Workers Paid plan" | Documented ([errors](https://developers.cloudflare.com/workers-ai/platform/errors/), [changelog 2026-07-28](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/)) |

**Implication:** Kiln cannot reliably tell "wrong token" from "token can't access this account" by status code alone. A practical UI split is: 404/7003 → "Account ID looks invalid"; 401/403 with 10000 → "Token invalid or lacks Workers AI permission for this account"; anything else → show the raw error.

## 4. Workers AI error codes (inference-time)

Verbatim from [Workers AI errors](https://developers.cloudflare.com/workers-ai/platform/errors/) (current source):

| Name | Internal code | HTTP | Description |
|---|---|---|---|
| No such model | 5007 | 400 | No such model `${model}` or task |
| Invalid data | 5004 | 400 | Invalid data type for base64 input |
| Incomplete request | 3003 | 400 | Request is missing headers or body |
| Account not allowed for private model | 5018 / 3041 | 403 | The account is not allowed to access this model |
| Model agreement | 5016 | 403 | User has not agreed to Llama3.2 model terms |
| Account blocked | 3023 | 403 | Service unavailable for account |
| Model requires Workers Paid plan | 5035 | 403 | This model requires a Workers Paid plan |
| Invalid model ID | 3042 | 404 | The model name is invalid |
| Request too large | 3006 | 413 | |
| Timeout / Aborted | 3007 / 3008 | 408 | |
| Account limited | 3036 | 429 | "You have used up your daily free allocation of 10,000 neurons. Please upgrade to Cloudflare's Workers Paid plan..." |
| Out of capacity | 3040 | 429 | "Capacity temporarily exceeded, please try again." Also returned by `rejectIfBusy` |

Also seen in the wild: input-schema validation failures come back as HTTP 400 with code 5006 and messages like `AiError: Bad input: Error: oneOf at '/' not met, ...` ([OmniRoute#2539](https://github.com/diegosouzapw/OmniRoute/issues/2539), on `/ai/run`).

Note for Kiln's error handling: HTTP 429 means three different things. 3021 is the per-minute rate limit (observed in the live test: "rate limiting: inference request per min rate reached"; see [live test findings](../../../live_test_findings.md#rate-limits)), 3036 is the daily free quota and 3040 is transient capacity. 3021 and 3040 are worth retrying; 3036 isn't.
