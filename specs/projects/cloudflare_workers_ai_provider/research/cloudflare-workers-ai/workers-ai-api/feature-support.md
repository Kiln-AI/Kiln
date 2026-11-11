# Workers AI: Feature Support over the API

Research date: 2026-09-28. Main sources: the Workers AI feature docs and the per-model JSON files that generate the model pages, both in [`cloudflare/cloudflare-docs`](https://github.com/cloudflare/cloudflare-docs) (commit `c153001`, 2026-09-28): `src/content/docs/workers-ai/features/*`, `src/content/workers-ai-models/*.json`, `src/content/release-notes/workers-ai.yaml`, `src/content/changelog/workers-ai/*`. Nothing here was tested live (api.cloudflare.com was blocked from this session).

Which models exist and how to keep the list current belongs to the Model Catalog subtopic. This doc uses the model files only to show what the **API** supports per model.

## Headline: two generations of model schema

The model JSON files show two distinct input schemas (my classification, from the `schema.input` of each file):

- **"OpenAI-shape" models** (2026 launches: Kimi K2.6/K2.7 Code, GLM 4.7 Flash/5.2/5.3/5.3 Flash, Gemma 4 26B, DeepSeek V4 Flash/Pro, Qwen 3.8 27B, Nemotron 3). Input schema is essentially OpenAI Chat Completions: `messages`, `max_completion_tokens`, `tools`, `tool_choice`, `parallel_tool_calls`, `response_format` (OpenAI shape `{type:"json_schema", json_schema:{name, description, schema, strict}}`), `logprobs`, `top_logprobs` (0–20), `stream_options`, `reasoning_effort`, `chat_template_kwargs`. Output on `/ai/run` is a full OpenAI chat-completion object (`choices[].message.tool_calls`, `usage.prompt_tokens_details.cached_tokens`, `usage.completion_tokens_details.reasoning_tokens`).
- **"Legacy" models** (Llama 3.x/4, Mistral, older Qwen, GPT-OSS, Granite, LoRA models). Input schema: `prompt` or `messages`, `raw`, `lora`, `max_tokens` (default **256**), `temperature`, `top_p`, `top_k`, `seed`, `repetition_penalty`, `frequency_penalty`, `presence_penalty`, `tools` (Cloudflare's `{name, description, parameters}` shape or OpenAI function shape), `response_format` `{type: "json_object"|"json_schema", json_schema: {}}`. No `logprobs`, no `tool_choice`. Native output: `{response, tool_calls[{name, arguments}], usage}`.

`/ai/v1/chat/completions` sits in front of both. Cloudflare says "Most Workers AI text generation models support the OpenAI Chat Completions API" ([OpenAI compat](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)) but does not document how it translates OpenAI requests for legacy models. That translation is where the rough edges are (see below).

## Per-feature summary

### Structured output (JSON schema / JSON mode)
- Docs: "JSON Mode is compatible with OpenAI's implementation; to enable add the `response_format` property" with `type` in `["json_object", "json_schema"]` and "`json_schema` must be a valid JSON Schema declaration." The doc example puts the **bare schema** directly under `json_schema` (no `name`/`schema` wrapper) ([JSON mode](https://developers.cloudflare.com/workers-ai/features/json-mode/)).
- Caveats, verbatim: "Workers AI can't guarantee that the model responds according to the requested JSON Schema... If that's the case, then an error `JSON Mode couldn't be met` is returned and must be handled." and "**JSON Mode currently doesn't support streaming.**"
- The JSON mode page's "Supported Models" list is stale: it still names `@cf/meta/llama-3-8b-instruct`, `@cf/meta/llama-3.1-8b-instruct` and `@hf/nousresearch/hermes-2-pro-mistral-7b`, which were deprecated on 2026-05-30 ([deprecations](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/)). The per-model schemas are a better guide: most models list `response_format`; `mistral-small-3.1-24b-instruct` and `qwq-32b` list only `guided_json`; `llama-3.2-11b-vision-instruct` lists neither.
- OpenAI-shape models take the standard `{name, schema, strict}` envelope. Legacy models "are tolerant of the bare schema shape" per a third-party report ([cloudflare/ai#559](https://github.com/cloudflare/ai/issues/559)). **Unknown (must test):** whether a legacy model behind `/v1/chat/completions` correctly unwraps the OpenAI envelope that LiteLLM/Kiln sends, or treats `{name, schema}` as the schema itself. Launch posts for Kimi K2.5 and K2.7 Code advertise "Structured outputs with JSON mode and JSON Schema support".
- Kiln implication: prefer `json_schema` mode for OpenAI-shape models; for legacy models, plan to test `json_schema` vs `json_object` vs function-calling per model; streaming + structured output should not be combined.

### Tool / function calling
- Docs label function calling **Beta**. Two styles: "embedded" (a JS helper package, not relevant to Kiln) and "traditional" ([function calling](https://developers.cloudflare.com/workers-ai/features/function-calling/), [traditional](https://developers.cloudflare.com/workers-ai/features/function-calling/traditional/)). Model pages carry a `function_calling` property.
- 2026-02-17 release notes list fixes on `/v1/chat/completions`: preserved tool-call IDs ("Previously, the endpoint was generating new IDs which broke multi-turn tool calling"), `finish_reason: "tool_calls"` reported correctly (it was hardcoded to `"stop"`), `content: null` assistant messages with `tool_calls` accepted, and the binding no longer rejecting its own `tool_call_id` values ([release notes](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/release-notes/workers-ai.yaml)). Multi-turn tool calling on `/v1` was broken until Feb 2026.
- Third-party finding (not verified): "The default text model (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`) does not emit tool calls on `/v1`. Models like `@cf/openai/gpt-oss-120b` do." ([meirdick/laravel-cf-workersai](https://github.com/meirdick/laravel-cf-workersai)). Treat the `function_calling` flag as necessary, not sufficient; Kiln's per-model test suite should confirm.
- `tool_choice` / `parallel_tool_calls` appear only in OpenAI-shape model schemas.

### Vision / image input
- Model property `vision: true` on: Kimi K2.6, K2.7 Code, Gemma 4 26B, GLM 5.3 Flash, Qwen 3.8 27B, Llama 4 Scout, Llama 3.2 11B Vision.
- OpenAI-shape models accept `content` parts of type `text`, `image_url` (`{url, detail}`), `video_url`, `input_audio`, `file`.
- Legacy Llama 4 Scout: `image_url.url` must be a data URI — schema text: "image uri with data (e.g. data:image/jpeg;base64,/9j/...). **HTTP URL will not be accepted**". Kiln should always send base64 data URIs.
- Llama 3.2 11B Vision's schema has a separate top-level `image` field and no `image_url` part; whether `/v1` maps OpenAI image parts to it is undocumented.
- Since 2026-02-17 message `content` accepts arrays (multi-part) for "all affected chat models including GPT-OSS models, Llama 3.x, Mistral, Qwen, and others" (release notes). Before that, array content was rejected (e.g. `Type mismatch of '/messages/0/content', 'array' not in 'string'` — [OmniRoute#2539](https://github.com/diegosouzapw/OmniRoute/issues/2539)).

### Reasoning / thinking
Reasoning is **inconsistent across models**, both in how you control it and where the output appears.

Control:
- `reasoning_effort` (OpenAI-shape models). Each model's JSON declares `supported_efforts`, a default, whether it can be disabled (`mandatory`), and how unsupported values are normalized. Examples: DeepSeek V4 `max, high, low, none` (default `high`); GLM 5.2 `max, high, none` (default `max`); GLM 5.3 / 5.3 Flash `max, high, low`, mandatory (cannot disable); Kimi K2.6 `high, none` ("Compatibility aliases: low maps to high; medium maps to high; max maps to high"); Qwen 3.8 `low, medium, xhigh` (default `xhigh`, and `supports_max_tokens: false`).
- `chat_template_kwargs.enable_thinking` / `clear_thinking` (in the Kimi, GLM, Gemma 4 schemas). **Conflict:** the Kimi K2.6 changelog says "K2.6 uses `chat_template_kwargs.thinking` to control reasoning, replacing `chat_template_kwargs.enable_thinking`" ([changelog 2026-04-20](https://developers.cloudflare.com/changelog/post/2026-04-20-kimi-k2-6-workers-ai/)), while the K2.6 model JSON still documents `enable_thinking`. Needs a live test.
- GPT-OSS: Responses-style `reasoning: {effort: low|medium|high, summary}`; "Reasoning cannot be disabled." (model JSON).

Output field:
- `reasoning` — Kimi K2.6 ("returns reasoning content in the `reasoning` field, replacing `reasoning_content`", same changelog).
- `reasoning_content` — Qwen3 30B A3B and Gemma SEA-LION output schemas; Kimi K2.5 (now aliased to K2.6).
- Inline `<think>` tags in content — likely for older reasoning models like `deepseek-r1-distill-qwen-32b` and `qwq-32b` (inferred; their schemas only show `response`).
- A third-party client confirms: "Reasoning text appears under different keys across models (`reasoning_content`, `reasoning`, or embedded in `content`)" ([meirdick/laravel-cf-workersai](https://github.com/meirdick/laravel-cf-workersai)).
- LiteLLM 1.87.1's OpenAI path handles all three (see [litellm-support.md](./litellm-support.md)). Kiln's per-model config will need to say which reasoning style each model uses, the same way other providers do.

### Streaming
- `stream: true` supported on all text-generation models (SSE, `text/event-stream`). `stream_options.include_usage` on OpenAI-shape models.
- Not with JSON mode (docs, above). GPT-OSS Responses API is non-streaming only.
- Known open bug (2026-09-02): on `/v1/chat/completions` with `llama-3.3-70b-instruct-fp8-fast`, numeric-looking tokens arrive as JSON numbers — `{"choices":[{"index":0,"delta":{"content":6}}]}` — causing "silent character loss" in clients ([cloudflare/ai#651](https://github.com/cloudflare/ai/issues/651), open; related #277).
- Streaming quirk in native API: final usage chunk carries `"response": null` ([typesense#2858](https://github.com/typesense/typesense/issues/2858), via search snippet).

### Logprobs
- Only OpenAI-shape models list `logprobs` (bool) and `top_logprobs` (0–20) in their schema, and their output schema includes `choices[].logprobs.content[].top_logprobs`. Legacy models (Llama, GPT-OSS, Mistral, older Qwen) have no logprobs parameter. Whether the OpenAI-shape models actually return populated logprobs was not verified.

### Max context and max output
- Context window is a per-model property (`context_window`), enforced in tokens since Feb 2025 ("changed our APIs to estimate and validate the number of tokens in the input prompt, not the number of characters" — [changelog 2025-02-24](https://developers.cloudflare.com/changelog/post/2025-02-24-context-windows/)). Current range: 3,500 (gemma-7b-it-lora) to 1,310,720 (GLM 5.3); DeepSeek V4 is 1,048,576; Kimi K2.6 262,144; GPT-OSS 128,000; Llama 3.3 70B fp8-fast only 24,000.
- **Default output length is small on legacy models.** Legacy schemas set `max_tokens` default **256** (Llama 3.x/4, GPT-OSS, Mistral, Qwen 2.5 Coder, QwQ, etc.). A third party reports "Cloudflare caps a completion at 256 tokens when the request omits `max_completion_tokens`" on `/v1/chat/completions` ([meirdick/laravel-cf-workersai](https://github.com/meirdick/laravel-cf-workersai)). **Kiln should always send an explicit max tokens for Workers AI**, or structured outputs will be truncated.

## Per-model API feature table

Derived from `src/content/workers-ai-models/*.json` (2026-09-28). "Schema" is my classification above. "Effort" lists supported `reasoning_effort` values. Blank = not declared.

| Model | Schema | Context | Tools | Reasoning | Effort | Vision | Logprobs | response_format | Paid only | Beta |
|---|---|---|---|---|---|---|---|---|---|---|
| @cf/deepseek-ai/deepseek-r1-distill-qwen-32b | legacy | 80000 | | yes | | | | bare json_schema | | |
| @cf/deepseek-ai/deepseek-v4-flash-0731 | OpenAI | 1048576 | yes | yes | max,high,low,none | | yes | OpenAI envelope | yes | |
| @cf/deepseek-ai/deepseek-v4-pro-0813 | OpenAI | 1048576 | yes | yes | max,high,low,none | | yes | OpenAI envelope | yes | |
| @cf/google/gemma-2b-it-lora | legacy | 8192 | | | | | | bare json_schema | | yes |
| @cf/google/gemma-4-26b-a4b-it | OpenAI | 256000 | yes | yes | yes | yes | yes | OpenAI envelope | | |
| @cf/google/gemma-7b-it-lora | legacy | 3500 | | | | | | bare json_schema | | yes |
| @cf/aisingapore/gemma-sea-lion-v4-27b-it | legacy | 128000 | | | | | | bare json_schema | | |
| @cf/zai-org/glm-4.7-flash | OpenAI | 131072 | yes | yes | yes | | yes | OpenAI envelope | | |
| @cf/zai-org/glm-5.2 | OpenAI | 262144 | yes | yes | max,high,none | | yes | OpenAI envelope | yes | |
| @cf/zai-org/glm-5.3-flash | OpenAI | 1310720 | yes | yes | max,high,low (cannot disable) | yes | yes | OpenAI envelope | yes | |
| @cf/zai-org/glm-5.3 | OpenAI | 1310720 | yes | yes | max,high,low (cannot disable) | | yes | OpenAI envelope | yes | |
| @cf/openai/gpt-oss-120b | legacy | 128000 | yes | yes | low,medium,high (cannot disable) | | | bare json_schema | | |
| @cf/openai/gpt-oss-20b | legacy | 128000 | yes | yes | low,medium,high (cannot disable) | | | bare json_schema | | |
| @cf/ibm-granite/granite-4.0-h-micro | legacy | 131000 | yes | | | | | bare json_schema | | |
| @cf/moonshotai/kimi-k2.6 | OpenAI | 262144 | yes | yes | high,none | yes | yes | OpenAI envelope | yes | |
| @cf/moonshotai/kimi-k2.7-code | OpenAI | 262144 | yes | yes | yes (cannot disable) | yes | yes | OpenAI envelope | yes | |
| @cf/meta-llama/llama-2-7b-chat-hf-lora | legacy | 8192 | | | | | | bare json_schema | | yes |
| @cf/meta/llama-3.1-8b-instruct-fp8 | legacy | 32000 | | | | | | bare json_schema | | |
| @cf/meta/llama-3.2-11b-vision-instruct | legacy | 128000 | | | | yes | | none | | |
| @cf/meta/llama-3.2-1b-instruct | legacy | 60000 | | | | | | bare json_schema | | |
| @cf/meta/llama-3.2-3b-instruct | legacy | 80000 | | | | | | bare json_schema | | |
| @cf/meta/llama-3.3-70b-instruct-fp8-fast | legacy | 24000 | yes | | | | | bare json_schema | | |
| @cf/meta/llama-4-scout-17b-16e-instruct | legacy | 131000 | yes | | | yes | | bare json_schema + guided_json | | |
| @cf/meta/llama-guard-3-8b | legacy | 131072 | | | | | | bare json_schema | | |
| @cf/mistral/mistral-7b-instruct-v0.2-lora | legacy | 15000 | | | | | | bare json_schema | | |
| @cf/mistralai/mistral-small-3.1-24b-instruct | legacy | 128000 | yes | | | | | guided_json only | | |
| @cf/nvidia/nemotron-3-120b-a12b | OpenAI | 256000 | yes | yes | | | yes | OpenAI envelope | | |
| @cf/qwen/qwen2.5-coder-32b-instruct | legacy | 32768 | | | | | | bare json_schema | | |
| @cf/qwen/qwen3-30b-a3b-fp8 | legacy | 32768 | yes | yes | | | | bare json_schema | | |
| @cf/qwen/qwen3.8-27b | OpenAI | 262144 | yes | yes | low,medium,xhigh | yes | yes | OpenAI envelope | | |
| @cf/qwen/qwq-32b | legacy | 24000 | | yes | | | | guided_json only | | |

Notes on the table:
- The model files in the docs repo may lag or lead the live catalog (e.g. the pricing page still lists models deprecated on 2026-05-30). The Model Catalog subtopic covers authoritative discovery.
- "Paid only" means the model returns `403 / 5035` on the Workers Free plan ([changelog 2026-07-28](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/); pricing page lists the same set plus DeepSeek V4 and GLM 5.3/5.3 Flash).
