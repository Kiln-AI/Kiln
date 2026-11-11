# LiteLLM Support for Workers AI

Research date: 2026-09-28. Sources: LiteLLM source installed in Kiln's venv (**1.87.1**, pinned by `libs/core/pyproject.toml` as `litellm>=1.87.0,<1.88`), wheels of later releases downloaded from PyPI and inspected, LiteLLM `main` on GitHub, and LiteLLM GitHub issues/PRs. docs.litellm.ai was blocked by this session's proxy, so the LiteLLM docs page was not read directly.

## Bottom line

- LiteLLM's `cloudflare/` provider had **two very different implementations**. Until June 2026 it called the native `/ai/run/{model}` endpoint and supported only `stream` and `max_tokens`. Since PR #31053 (merged 2026-06-23, first stable release containing it: **1.91.0**, 2026-07-04) it is a thin subclass of LiteLLM's OpenAI chat config that calls `/ai/v1/chat/completions`.
- **Kiln's pinned version (1.87.x) has the old, broken implementation.** It cannot do tools, structured output, temperature, reasoning, or even plain text on newer models. Do not use `cloudflare/` with the current pin.
- **Recommended route:** use LiteLLM's `openai/` provider against `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`, the same "custom OpenAI-compatible provider with a base URL" pattern Kiln already uses for SiliconFlow. It works on 1.87.1 and is functionally what the new `cloudflare/` provider does anyway.

## 1. The old `cloudflare/` provider (LiteLLM ≤ 1.90.x, including Kiln's 1.87.1)

File: `litellm/llms/cloudflare/chat/transformation.py` (installed copy in `.venv/lib/python3.13/site-packages/litellm/`).

- **Endpoint:** `api_base` default is `f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"` + URL-encoded model. `main.py` resolves: `api_key = api_key or litellm.cloudflare_api_key or litellm.api_key or get_secret("CLOUDFLARE_API_KEY")`; `account_id = get_secret("CLOUDFLARE_ACCOUNT_ID")`; `api_base = api_base or litellm.api_base or get_secret("CLOUDFLARE_API_BASE") or <default>`.
- **Account ID only from env.** There is no `account_id` kwarg. Without the env var the URL becomes `/accounts/None/ai/run/...`. The only per-call override is passing a full `api_base`.
- **Supported params:** `get_supported_openai_params` returns exactly `["stream", "max_tokens"]` (`max_completion_tokens` is mapped to `max_tokens`). Everything else — `temperature`, `top_p`, `tools`, `tool_choice`, `response_format`, `logprobs` — is unsupported. With `drop_params=True` (Kiln sets this in `litellm_adapter.py`) these are **silently dropped**, so a structured-output request would silently run unstructured. PR #31053 confirms: "Requests carrying `tools` or `tool_choice` parameters raised `UnsupportedParamsError`" ([PR #31053](https://github.com/BerriAI/litellm/pull/31053)).
- **Response parsing:** reads `result["response"]`, falling back to `result["response_text"]` (added April 2026). Newer models return an OpenAI object with `choices` inside `result`, so content comes back **empty** on 1.87.1 (earlier versions raised `KeyError: 'response'` — [litellm#24065](https://github.com/BerriAI/litellm/issues/24065), Nemotron 3 on v1.82.3, closed "not planned"). Tool calls and reasoning are never parsed.
- **Usage:** token counts are **estimated locally** with a tokenizer (`litellm.utils.get_token_count`), not read from Cloudflare's `usage`.
- **Cosmetic bug:** request header is `"content-type": "apbplication/json"` (typo in source).
- **Exception mapping** (`litellm_core_utils/exception_mapping_utils.py`): if the error string contains `"Authentication error"` → `AuthenticationError`; `"must have required property"` → `BadRequestError`.
- An open issue asks for the provider to be updated to "reflect cloudflare's expanded ai api" ([litellm#21115](https://github.com/BerriAI/litellm/issues/21115), opened 2026-02-13, open, no maintainer reply).

## 2. The new `cloudflare/` provider (LiteLLM ≥ 1.91.0)

[PR #31053 "fix(cloudflare): route native Workers AI provider through OpenAI-compatible endpoint"](https://github.com/BerriAI/litellm/pull/31053), merged 2026-06-23. Commit history: [transformation.py on main](https://github.com/BerriAI/litellm/commits/main/litellm/llms/cloudflare/chat/transformation.py).

Verified by inspecting PyPI wheels: 1.87.5, 1.89.4 and 1.90.0 still have the old code; 1.91.0, 1.92.0, 1.93.0, 1.96.0, 1.99.0 and 1.103.0 (latest, 2026-09-27) have the new code. (1.90.x patch releases after 1.90.0 were not checked.)

What the new code does (from `main` and the 1.103.0 wheel):
- `class CloudflareChatConfig(OpenAIGPTConfig)` — inherits full OpenAI param support and response parsing.
- `_resolve_api_base`: if no `api_base`, reads `CLOUDFLARE_ACCOUNT_ID` and returns `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`; raises `"Missing CLOUDFLARE_ACCOUNT_ID - set CLOUDFLARE_ACCOUNT_ID in the environment or pass api_base explicitly"` if unset. An `api_base` ending in `/ai/run` is rewritten to `/ai/v1` with the warning: "Cloudflare api_base ending in '/ai/run' is the legacy Workers AI path and no longer serves OpenAI-compatible requests; rewriting to the '/ai/v1' endpoint".
- `main.py` `_complete_cloudflare`: `api_key = api_key or litellm.cloudflare_api_key or litellm.api_key or get_secret("CLOUDFLARE_API_KEY")`; `api_base = api_base or litellm.api_base or get_secret("CLOUDFLARE_API_BASE")`.
- Env vars (PR description): `CLOUDFLARE_API_KEY` required; `CLOUDFLARE_ACCOUNT_ID` required when `api_base` is not set; `CLOUDFLARE_API_BASE` optional.
- Still no per-call `account_id` parameter. Kiln would pass `api_base` with the account ID baked in, which also avoids env vars.
- The model cost map in 1.103.0 has ~32 `cloudflare/...` entries with pricing, context, `supports_function_calling`, `supports_reasoning` and an `rpm` field (e.g. `cloudflare/@cf/moonshotai/kimi-k2.6`: `rpm: 20`). 1.87.1 has only 4 stale entries (llama-2, mistral-7b v0.1, codellama). Catalog accuracy is for the Model Catalog subtopic.

Maturity note: the new provider is ~3 months old and has had one substantive commit since (lint/format only). A reranking PR ([#40053](https://github.com/BerriAI/litellm/pull/40053), 2026-09-06) says reranking only exists on `/ai/run` and that one Cloudflare base URL should back chat, embeddings and rerank; its files are **not** in the 1.103.0 wheel, so its status is unclear. Out of scope for chat anyway.

## 3. `openai/` + custom base URL (recommended for Kiln)

- Kiln pattern: in `libs/core/kiln_ai/utils/litellm.py`, providers like `siliconflow_cn`, `openai_compatible` set `is_custom = True`, which uses `openai/<model_id>` as the LiteLLM model and requires an explicit `api_base`. In `libs/core/kiln_ai/adapters/provider_tools.py`, SiliconFlow's `LiteLlmCoreConfig` sets `base_url` and passes `api_key` via `additional_body_options`. Workers AI would be the same with `base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"`. Model IDs like `@cf/zai-org/glm-4.7-flash` pass through as `openai/@cf/zai-org/glm-4.7-flash`; the OpenAI client sends the part after `openai/` as the `model` body field (standard LiteLLM behavior, not tested against Cloudflare here).
- Behavior on LiteLLM 1.87.1 that matters:
  - Non-streaming reasoning: `_extract_reasoning_content` reads `message["reasoning_content"]`, else `message["reasoning"]`, else parses `<think>...</think>` out of content (`litellm_core_utils/prompt_templates/common_utils.py`). This covers all three shapes Workers AI models use (see [feature-support.md](./feature-support.md)).
  - Streaming reasoning: `OpenAIChatCompletionStreamingHandler._map_reasoning_to_reasoning_content` renames `delta.reasoning` → `delta.reasoning_content` ("Some OpenAI-compatible providers (e.g., GLM-5, hosted_vllm) return delta.reasoning").
  - Usage comes from Cloudflare's `usage` block (including `prompt_tokens_details.cached_tokens` on newer models) instead of local estimates.
- Trade-offs vs `cloudflare/` on a newer LiteLLM:
  - `openai/` gets no LiteLLM cost tracking from the `cloudflare/` model-cost map, and exceptions are labeled as OpenAI. Kiln does its own model metadata in `ml_model_list.py`, so this is minor.
  - `openai/` may send OpenAI-only params (e.g. `stream_options`, `parallel_tool_calls`) that legacy Workers AI models' schemas don't list. Whether `/v1/chat/completions` ignores or rejects unknown fields per model is **untested**.
  - Switching to `cloudflare/` later is cheap: once Kiln's pin is ≥ 1.91, change the provider name to `cloudflare` and keep passing `api_base`.

## 4. Other clients (context)

- Cloudflare's own Vercel AI SDK provider (`workers-ai-provider`) and `@cloudflare/tanstack-ai` target Workers AI directly ([changelog 2026-02-13](https://developers.cloudflare.com/changelog/post/2026-02-13-glm-4.7-flash-workers-ai/)). Known bug there: it sent `response_format.json_schema` as a bare schema, which "Native Workers AI models (`@cf/...`) are tolerant of" but OpenAI partner models reject ([cloudflare/ai#559](https://github.com/cloudflare/ai/issues/559), 2026-06-08, closed).
- LibreChat documents Workers AI as a generic OpenAI-compatible custom endpoint with a static model list and `fetch: false` ([LibreChat docs](https://www.librechat.ai/docs/configuration/librechat_yaml/ai_endpoints/cloudflare)) — consistent with there being no `/v1/models`.
- OmniRoute changed its form to require both API Token and Account ID and builds `.../accounts/{ACCOUNT_ID}/ai/v1` ([OmniRoute#5423](https://github.com/diegosouzapw/OmniRoute/issues/5423), 2026-06-29).
