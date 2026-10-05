# Research Plan: Cloudflare Workers AI

## Goal

Inform the functional spec and architecture for the `cloudflare_workers_ai_provider` project: adding Cloudflare Workers AI as a standard Kiln provider (Kiln calls models through LiteLLM; each provider needs credentials, a cheap credential-validation call, and entries in `ml_model_list.py`). Answer three open questions from the project overview: should AI Gateway be included (one provider or two), is there a machine-readable model list for the `claude-maintain-models` skill, and is the model list static or per-account. Blocking: Step 2 (functional spec).

## Run

- Model: Opus (same model as the calling session)

## Subtopics

- [x] Workers AI API, auth and LiteLLM support — how Kiln would call it and validate credentials
- [x] Model catalog and discovery — static vs per-account list, machine-readable sources, model IDs, capabilities, lifecycle
- [x] AI Gateway — what it is, how it relates to Workers AI, and whether Kiln should support it (one provider or two)

## Focus Details

### Workers AI API, auth and LiteLLM support

How a client calls Workers AI text-generation models today. Cover: the endpoints (native `/accounts/{account_id}/ai/run/{model}` vs the OpenAI-compatible `/accounts/{account_id}/ai/v1/chat/completions`), and which is recommended; authentication (API token scopes, account ID — is the account ID required on every call, is there any single-credential option); LiteLLM's `cloudflare/` provider — which endpoint it uses, which env vars / params it expects (e.g. `CLOUDFLARE_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `api_base`), maturity and known bugs, and whether using LiteLLM's `openai/` provider against the OpenAI-compatible endpoint is a better route; feature support over that API: structured output (JSON schema / JSON mode), tool/function calling, vision/image input, reasoning/thinking output, streaming, logprobs, max context; a cheap authenticated call suitable for "connect" validation (e.g. token verify endpoint, models list) and what errors it returns for bad token vs bad account ID; pricing model (Neurons, free tier) and rate limits at a level that matters to users. Out of scope: which models exist and how to list them (Model catalog subtopic); AI Gateway (AI Gateway subtopic).

### Model catalog and discovery

What Cloudflare's "model list" concept is. Cover: is the catalog one global static list, or does it vary per account (e.g. account-specific fine-tunes/LoRAs, beta models, gated partner models)? Machine-readable sources: the models search API (`/accounts/{id}/ai/models/search` or similar) — does it need auth, what fields does it return (task type, context window, capabilities like function calling, deprecation info); any public unauthenticated JSON (docs site data, GitHub repo like `cloudflare/cloudflare-docs` model JSON files); coverage in models.dev and the LiteLLM model catalog (these are what Kiln's `claude-maintain-models` skill uses today — does either list Cloudflare Workers AI models, with what provider key and how current). Model ID format (`@cf/...`, `@hf/...`), which current text-generation models are notable (Llama, Qwen, Mistral, gpt-oss, Kimi, etc.) and which support function calling / JSON mode / vision. Deprecation and lifecycle: how models are retired and announced. End with a concrete recommended procedure for keeping Kiln's Cloudflare entries up to date. Out of scope: API call mechanics and auth (API subtopic); AI Gateway (AI Gateway subtopic).

### AI Gateway

What Cloudflare AI Gateway is and whether Kiln should support it. Cover: its purpose (proxy/observability/caching/rate-limiting in front of many providers, including Workers AI); its endpoints — provider-specific paths vs the OpenAI-compatible unified endpoint (`/compat/chat/completions` with `provider/model` IDs), and "unified billing" / BYOK / stored-keys features; auth (`cf-aig-authorization` header, gateway ID, account ID) and whether calls through it need the upstream provider's key; how routing Workers AI through a gateway differs from calling Workers AI directly (just a base URL change?); LiteLLM support for AI Gateway; how comparable tools (e.g. Vercel AI SDK, LangChain, LibreChat, Open WebUI, other LLM apps) expose Workers AI and AI Gateway — one provider, two providers, or gateway as an optional setting on another provider. Give a recommendation with trade-offs: (a) Workers AI only, (b) Workers AI with optional gateway ID, (c) two separate providers. Out of scope: Workers AI API details beyond how the gateway wraps them (API subtopic); the model catalog (Model catalog subtopic).
