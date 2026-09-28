# Live Test Findings (2026-09-28)

Tested against a real Cloudflare account from the dev container, with a user-owned API token. **The account is on Workers Free.** Every paid-only model returns 403 / code 5035, so tests that need those models are still open (see [Still Open](#still-open)).

Inputs for the architecture. Not a spec artifact.

## Connect Validation

`GET /accounts/{acct}/ai/models/search?per_page=1`:

| Case | HTTP | Cloudflare code | Body message |
|---|---|---|---|
| Valid token and account | 200 | — | — |
| Valid token, well-formed account ID it can't access | 403 | 10000 | `Authentication error` |
| Malformed account ID (`notanaccount`) | 404 | 7003 | `Could not route to ..., perhaps your object identifier is invalid?` |
| Invalid token (40 chars) | 401 | 10000 | `Authentication error` |
| Junk token (`x`) | 400 | 9106 | `Authentication failed (status: 400)` |

- `per_page` is ignored. The call returns 65 models (about 100 KB) whatever `per_page` says. It's still free and fast enough for a connect check.
- `/user/tokens/verify` returned `active` for this user-owned token. Still don't use it, per the research: it rejects account-owned tokens.
- **The search endpoint ignores `cf-aig-gateway-id`.** A made-up gateway ID still returns 200, so this call can't validate a gateway.

## Gateway

- **The header is optional.** Direct calls without it work.
- `cf-aig-gateway-id: default` works with this token. The token can't list gateways (`GET /ai-gateway/gateways` returns 403 / 10000), so it probably has no AI Gateway permission. Not confirmed: whether the `default` gateway already existed or was auto-created by this call, and whether the call was really logged in the gateway. The response has no `cf-aig-*` headers either way.
- A gateway ID that doesn't exist returns **400 / code 2001, `Please configure AI Gateway in the Cloudflare dashboard`**.
- A gateway ID with invalid characters (`bad id!`) returns 400 / code 2001, `Invalid request path. Expected path prefix /v1/:accountTag/:gatewayId`.
- **Free gateway check:** a chat completion for a made-up model ID (`@cf/kiln/connection-check`, `max_tokens: 1`) with the gateway header returns:
  - 400 / 2001 if the gateway doesn't exist;
  - 400 / 5007 `No such model` if the gateway is fine (the same as with no gateway);
  - 401 / 10000 if the token is bad.
  
  No model runs, so it costs nothing.

## Model Reporting and Substitution

- A successful `/v1/chat/completions` response has `model` set to the requested ID (checked for GLM 4.7 Flash, Gemma 4, Nemotron 3, Qwen 3.8, Llama 3.3 70B).
- **Aliasing confirmed:** a request for `@cf/moonshotai/kimi-k2.5` returns `Model @cf/moonshotai/kimi-k2.6 is not available on the Workers Free plan`. So Cloudflare silently resolves K2.5 to K2.6. Whether a *successful* aliased response reports `k2.5` or `k2.6` in `model` needs a paid account.

## Output Length (No `max_tokens` Sent)

Prompt: "Write every integer from 1 to 700...". About 2,000+ output tokens, well past the 256 default of older models.

| Model | Result |
|---|---|
| GLM 4.7 Flash | Complete (700/700), `finish_reason: stop`, 2,406 completion tokens |
| Gemma 4 26B A4B | Complete, 3,185 tokens |
| Nemotron 3 Super | Complete, 5,131 tokens |
| Qwen 3.8 27B | Streaming: complete, 5,810 tokens, **4 min 12 s** (~23 tokens/s). Non-streaming: failed with `AiError: Request timeout`, code 3046 |

No truncation on the free models tested. Paid-only models are untested.

## Qwen 3.8 27B on `/v1`

Works on `/v1/chat/completions` (short prompt: 200, 1.3 s). It returns reasoning in `message.reasoning`. It's slow: long non-streaming generations hit Cloudflare's server-side timeout (3046). The HTTP status for 3046 wasn't captured.

## Rate Limits

Burst of `max_tokens: 1` calls to `@cf/meta/llama-3.2-1b-instruct` through LiteLLM `openai/` (as Kiln will call it), with `num_retries=0`:

- 400 requests in 4.7 s: all succeeded. The documented 300/min isn't enforced strictly at small bursts.
- 1,212 requests in 7.4 s: 51 failed with **HTTP 429, code 3021, `AiError: AiError: rate limiting: inference request per min rate reached`**.
- Through `cf-aig-gateway-id: default`: same 429 / 3021.
- On both paths, LiteLLM raises **`litellm.RateLimitError`**. Kiln's classifiers on the real exception: `is_retryable_error=True`, `is_batch_fatal_error=False`, and `format_error_message` returns "Rate limit exceeded. Wait a moment and try again."

**Conclusion:** the rate-limit requirement works without changes. The architecture only needs unit tests pinning the mapping, using the recorded bodies.

## Other Errors Through LiteLLM `openai/`

| Case | HTTP / code | LiteLLM exception | Retryable | Batch-fatal |
|---|---|---|---|---|
| Deprecated model (`llama-3.1-8b-instruct`) | 410 / 5028 | `APIError` | No | No |
| Unknown model | 400 / 5007 | `BadRequestError` | No | No |
| Paid-only model on Free plan | 403 / 5035 | `APIError` (not `PermissionDeniedError`) | No | No |
| Missing gateway | 400 / 2001 | `BadRequestError` | No | No |
| Bad token | 401 / 10000 | `AuthenticationError` | No | Yes |
| Well-formed wrong account ID (on chat) | 401 / 10000 | `AuthenticationError` | No | Yes |

The wrong account ID returns 401 on chat but 403 on models-search.

## Still Open

Needs a Workers Paid account:

- Whether an aliased ID's successful response reports the requested or the actual model. This decides the optional runtime no-substitution check.
- Output length and `/v1` behavior for the seven paid-only models.
- The 20 requests/min limit on paid-only models. Expected to be the same 429 / 3021, but unconfirmed.

Needs the dashboard, or a token with AI Gateway permission:

- Whether requests with `cf-aig-gateway-id: default` actually appear in the gateway's logs.
- Whether the `default` gateway was auto-created by a token without AI Gateway permission.

Not captured:

- The HTTP status for timeout code 3046 (it decides whether LiteLLM treats it as retryable).
