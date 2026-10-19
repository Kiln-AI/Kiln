---
status: complete
---

# Functional Spec: Cloudflare Provider (Workers AI + optional AI Gateway)

Research behind the decisions here: [research summary](./research/cloudflare-workers-ai/summary.md).

## Overview

Add Cloudflare as a standard Kiln model provider. Users connect with a Cloudflare API token and account ID, and can optionally give an AI Gateway ID so their calls go through that gateway. Kiln then offers a curated set of Cloudflare Workers AI models in the model picker, the same way it does for other providers.

There's no new UX beyond the existing connect-provider screen and model picker.

## Scope

### In scope

- One new provider, shown to users as **Cloudflare**.
- A connect flow with three fields: API token (required), account ID (required) and AI Gateway ID (optional). Every field is validated on connect.
- Running Workers AI text-generation models through Cloudflare's OpenAI-compatible endpoint, directly or through the user's AI Gateway.
- A curated model list in `ml_model_list.py`, limited to Cloudflare's newer, OpenAI-style models (see [Model Selection](#model-selection)).
- A process safeguard against Cloudflare silently running a different model than the one requested (see [No Model Substitution](#no-model-substitution)).
- Updates to the model-maintenance and deprecation-check skills so the Cloudflare list stays current.

### Out of scope

- A separate "Cloudflare AI Gateway" provider, and third-party models reached through the gateway (`openai/...`, `anthropic/...`). The provider is named "Cloudflare" so this can be added later without renaming.
- Cloudflare's older models, whose API format differs from OpenAI's (see [Model Selection](#model-selection)).
- Embeddings, image generation, speech and other non-chat Workers AI tasks.
- LoRA fine-tunes on Workers AI, and fine-tuning in general.
- Kiln-side awareness of the user's Cloudflare plan (Free vs Workers Paid), and AI Gateway billing settings. The user manages these in the Cloudflare dashboard.
- Upgrading LiteLLM.

## Provider Identity

- Internal provider ID: `cloudflare`.
- Display name: "Cloudflare".
- Model IDs are Cloudflare's own `@cf/<author>/<model>` IDs, for example `@cf/zai-org/glm-5.3`.

## Credentials and Configuration

| Field | Required | Stored as | Env var | Notes |
|---|---|---|---|---|
| API token | Yes | Kiln config, secret | `CLOUDFLARE_API_KEY` | Needs the Workers AI permission. Live, a Workers-AI-only token worked with the `default` gateway, so the UI asks for no AI Gateway permission. Other gateways and gateway features weren't tested. |
| Account ID | Yes | Kiln config | `CLOUDFLARE_ACCOUNT_ID` | A 32-character hex string from the Cloudflare dashboard. |
| AI Gateway ID | No | Kiln config | `CLOUDFLARE_AI_GATEWAY_ID` | When set, every call goes through this gateway. When empty, calls go directly to Workers AI, unless the `CLOUDFLARE_AI_GATEWAY_ID` env var is set (the standard config fallback). |

The env var names match the ones LiteLLM and models.dev use for the first two fields.

The connect screen's help text tells users where to find each value, and which token permissions to grant. The approved strings are in [ui_design.md](./ui_design.md).

## Connect Flow

1. The user opens Cloudflare on the connect-provider screen and enters an API token, an account ID and, optionally, an AI Gateway ID.
2. Kiln validates every field that was entered before saving anything.
   - An invalid token, account ID or gateway ID must fail the connect. Kiln must never save a configuration that it knows fails.
   - Name the failing field in the error when Kiln can tell which one it is. Cloudflare may not distinguish "wrong token" from "wrong account ID". In that case, one combined message is acceptable ("Check your API token and account ID").
   - The architecture step decides how to validate. The research suggests the free models-search call for the token and account ID. The gateway ID may need its own check, which could cost a very small amount. That's acceptable if no free check exists.
3. On success, Kiln saves the fields and shows Cloudflare as connected, like other providers.
4. Disconnect clears all three fields.

## Calling Models

- Kiln calls Cloudflare's OpenAI-compatible endpoint, `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions`, through LiteLLM's generic OpenAI route. This is the same pattern Kiln uses for SiliconFlow.
- Kiln does not use LiteLLM's built-in `cloudflare/` provider. In Kiln's pinned LiteLLM version, it drops most request parameters and the gateway header.
- If a gateway ID is set, every request goes through that gateway by adding the `cf-aig-gateway-id` header. The same token, URL and model IDs are used either way.
- Streaming, structured output, tool calling, vision and reasoning follow Kiln's normal per-model settings in `ml_model_list.py`. Cloudflare's own capability flags are guidance only; Kiln's per-model tests decide the final settings.
- Cloudflare's JSON mode doesn't support streaming. That's acceptable.
- Output length must not be silently cut short. Cloudflare's older models default to 256 output tokens. Excluding them is the main mitigation. The architecture step must confirm with a live test that the included models don't truncate when Kiln sends no max-token value. If they do, Kiln sends an explicit max-token value for this provider.

## Model Selection

### Rule

Include only Cloudflare's newer text-generation models, which use the OpenAI Chat Completions format natively. Exclude Cloudflare's older models, which use a different format behind a translation layer. Those default to 256 output tokens and have unreliable tool calling and JSON mode.

Also skip pure coding models, classifiers and LoRA base models, as the model-maintenance skill does for other providers.

### Initial list (PR 2)

All of these already exist in Kiln's model list. Each gets a Cloudflare provider entry.

| Kiln model | Cloudflare ID | Needs Workers Paid |
|---|---|---|
| DeepSeek V4 Pro | `@cf/deepseek-ai/deepseek-v4-pro-0813` | Yes |
| DeepSeek V4 Flash | `@cf/deepseek-ai/deepseek-v4-flash-0731` | Yes |
| GLM 5.3 | `@cf/zai-org/glm-5.3` | Yes |
| GLM 5.3 Flash | `@cf/zai-org/glm-5.3-flash` | Yes |
| GLM 5.2 | `@cf/zai-org/glm-5.2` | Yes |
| GLM 4.7 Flash | `@cf/zai-org/glm-4.7-flash` | No |
| Kimi K2.6 | `@cf/moonshotai/kimi-k2.6` | Yes |
| Qwen 3.8 27B | `@cf/qwen/qwen3.8-27b` | No |
| Gemma 4 26B A4B | `@cf/google/gemma-4-26b-a4b-it` | No |
| Nemotron 3 Super | `@cf/nvidia/nemotron-3-120b-a12b` | No |

Models that need the Workers Paid plan are included. On a free account, the call fails with Cloudflare's error.

Qwen 3.8 27B works on the OpenAI-compatible endpoint (confirmed live) and stays in. It's slow (about 23 tokens per second), so very long non-streaming generations can hit Cloudflare's server-side timeout (code 3046). That's accepted.

### Excluded older models

| Cloudflare model | Kiln model it would map to | Notes |
|---|---|---|
| `@cf/openai/gpt-oss-120b` | GPT-OSS 120B | The notable loss: popular, free-plan, tools and reasoning. Excluded by decision; available from other Kiln providers. |
| `@cf/openai/gpt-oss-20b` | GPT-OSS 20B | Same as above. |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | Llama 4 Scout | Vision and tools. |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Llama 3.3 70B | Only 24K context, and reportedly doesn't emit tool calls on the OpenAI-compatible endpoint. |
| `@cf/qwen/qwen3-30b-a3b-fp8` | Qwen3 30B A3B | 32K context. |
| `@cf/mistralai/mistral-small-3.1-24b-instruct` | Mistral Small 3.x (version match unverified) | No `response_format` support. |
| `@cf/qwen/qwq-32b`, `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | QwQ 32B, R1 Distill Qwen 32B | Old reasoning models. |
| `@cf/meta/llama-3.2-1b/3b-instruct`, `llama-3.2-11b-vision-instruct`, `llama-3.1-8b-instruct-fp8` | Llama 3.2 1B/3B/11B, Llama 3.1 8B | Small, older models. |

Skipped for other reasons: `kimi-k2.7-code` and `qwen2.5-coder-32b` (coding models), `llama-guard-3-8b` (classifier), the four `-lora` base models, and `gemma-sea-lion-v4-27b-it` and `granite-4.0-h-micro` (Kiln has no entries for these models).

Users can still add any `@cf/...` ID, including excluded ones, through Kiln's existing custom-model feature, at their own risk.

## No Model Substitution

We don't want Kiln to run a different model than the one the user chose. An error is better than substitution. But this is Cloudflare's behavior, not Kiln's, so the safeguards are limited to what's low-risk.

Why: when Cloudflare retired Kimi K2.5 in May 2026, it pointed the old ID at the more expensive Kimi K2.6 instead of returning an error. Cloudflare has no documented setting that turns this off.

Requirements:

1. **Process (required).** The maintenance and deprecation skills remove or mark deprecated any Cloudflare model that gains a `planned_deprecation_date`, before that date. This way Kiln stops offering a model before it can be aliased.
2. **Runtime check (optional).** If Cloudflare's response reports which model actually ran, Kiln could compare it with the requested ID and fail on a mismatch. Only build this if a live test shows it can be done cleanly and locally, for example as a small check in the Cloudflare response path. If it needs a risky change to the shared adapter code, or the response doesn't carry the information, skip it and record that in the architecture doc.

## Errors

- Cloudflare's error message is shown to the user as-is, the same way Kiln handles other providers' errors. There are no custom friendly messages in this project.
- If the optional runtime no-substitution check is built, its mismatch error is the one Kiln-generated runtime error.

## Rate Limits and Concurrency

- No Cloudflare-specific concurrency settings. All entries use Kiln's default parallelism.
- For reference, Cloudflare's documented limits (verified in the `cloudflare-docs` source, `workers-ai/platform/limits.mdx`, 2026-09-28) are 300 requests per minute for text generation. The exception is models that need Workers Paid: they're limited to 20 requests per minute per account per model, or 50 with prepaid AI Gateway credits. Users running large evals or synthetic data jobs on those models will hit 429s. That's Cloudflare's limit, not Kiln's.

### Rate-limit errors must be recognized as rate limits

Rate limits are expected with Cloudflare, so Kiln's existing rate-limit handling must work for it. Several callers treat a rate limit differently from other errors. They recognize it by the exception type `litellm.RateLimitError`:

- `is_retryable_error` in `adapters/retry_classification.py` marks it retryable. The eval runner, the synthetic-user runner and the eval builder then retry it with backoff.
- `is_batch_fatal_error` must *not* match it. That function aborts a whole batch on errors like bad credentials (`AuthenticationError`, `PermissionDeniedError`, `NotFoundError`). If a Cloudflare rate limit arrived as one of those, one throttled call would abort an entire eval run.
- `format_error_message` in `adapters/errors.py` shows the standard "Rate limit exceeded" message.

Requirements:

1. A Cloudflare rate limit must reach Kiln's callers as `litellm.RateLimitError` (unwrapped from `KilnRunError` as usual), both with and without a gateway ID.
2. A rate limit must never surface as an authentication, permission or not-found error.
3. The architecture confirms this with a live test that triggers a real 429 (for example, a burst of tiny requests to a model limited to 20 requests per minute), and records the status code, Cloudflare error code and LiteLLM exception type for each path. If LiteLLM doesn't produce `RateLimitError`, the Cloudflare provider path maps the error itself.
4. Unit tests cover the mapping, using the recorded error bodies.

Cloudflare uses 429 for more than one condition: per-model rate limits, out of capacity (code 3040), and the free plan's daily quota being used up (code 3036). All three are treated as rate limits. The daily-quota case won't clear on retry, but Kiln's retry counts are small, so the cost is a few wasted attempts before the error shows. That's accepted, and it matches how Kiln handles other providers' quota errors.

## Model List Maintenance

Update `.agents/skills/claude-maintain-models/SKILL.md`, and the deprecation-check skill, with a Cloudflare section:

- **Source of truth:** Cloudflare's public model JSON at `https://ai-cloudflare-com.pages.dev/api/models` (no login), or the models-search API when a token is available. The per-model JSON in the `cloudflare/cloudflare-docs` GitHub repo is a fallback.
- **Cross-check:** models.dev, under provider key `cloudflare-workers-ai`. Don't rely on it for retirements, because it no longer deletes retired models.
- **Never:** LiteLLM's catalog for Cloudflare. It's months stale.
- **Inclusion rule:** only newer OpenAI-format text-generation models, per [Model Selection](#model-selection). The skill text must say how to tell the two formats apart.
- **Deprecations:** flag any Kiln Cloudflare entry whose model has a `planned_deprecation_date`, and remove it before that date (see [No Model Substitution](#no-model-substitution)).
- **Lagging provider:** add Cloudflare to the skill's lagging-providers check, so new Cloudflare-hosted versions of existing Kiln models get picked up.

Use the draft skill text in [recommended-maintenance-procedure.md](./research/cloudflare-workers-ai/model-catalog/recommended-maintenance-procedure.md) as the starting point.

## Release Sequencing

Follow the model-maintenance skill's rule for new providers:

- **PR 1, provider support:** the provider ID, config fields, LiteLLM wiring, connect and disconnect, the optional runtime no-substitution check if built, and the web UI connect entry. It can merge whenever it's ready.
- **PR 2, models and skill docs:** the `ml_model_list.py` entries and the skill updates. It merges only after a client release that includes PR 1.

## Testing

- Unit tests for the config fields, the connect validation for each field (including every failure case), the LiteLLM wiring with and without a gateway ID, and the runtime no-substitution check if built.
- Per-model tests run automatically for each `ml_model_list.py` entry, as for other providers. These set the final structured-output mode, tool calling, vision and reasoning flags.
- Live tests need a Cloudflare account on Workers Paid, with a token, an account ID and a gateway ID provided through this environment's secrets.

### Dev network allowlist

Hosts needed for development and live testing:

| Host | Why |
|---|---|
| `api.cloudflare.com` | Inference, the models-search API, and connect validation. |
| `ai-cloudflare-com.pages.dev` | The public model JSON used by the maintenance skill. |
| `developers.cloudflare.com` | Cloudflare docs. |
| `gateway.ai.cloudflare.com` | Older AI Gateway URLs. Only needed to debug gateway behavior. |
| `models.dev` | Cross-check source for the maintenance skill. |
| `api.litellm.ai`, `docs.litellm.ai` | LiteLLM catalog (used by the skill for other providers) and docs. |

## Open Questions for Architecture

These need a live account to answer. The architecture step must answer or design around each one. Development continues in a new container with the dev network allowlist above in place, so these can be tested directly.

- Does Cloudflare's response report which model actually ran? This decides whether the optional runtime no-substitution check is possible.
- What's the cheapest reliable way to validate a gateway ID? What error comes back for a gateway ID that doesn't exist?
- Which token permissions does a gateway need?
- Is the gateway header truly optional for Workers AI calls? The docs contradict each other.
- Do the included models truncate output when Kiln sends no max-token value?
- Does Qwen 3.8 27B work on the OpenAI-compatible endpoint?
- What does a real Cloudflare rate limit look like (status, error code, LiteLLM exception type), directly and through a gateway? See [Rate-limit errors](#rate-limit-errors-must-be-recognized-as-rate-limits).
