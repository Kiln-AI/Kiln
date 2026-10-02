# Workers AI Text-Generation Models: IDs, Capabilities, Kiln Mapping

Snapshot date: 2026-09-28. Primary source: the 31 `Text Generation` model JSON files in [`cloudflare/cloudflare-docs` `src/content/workers-ai-models/`](https://github.com/cloudflare/cloudflare-docs/tree/production/src/content/workers-ai-models) at commit `c1530017` (2026-09-28), cross-checked against the public JSON at `https://ai-cloudflare-com.pages.dev/api/models` fetched the same day (same 65 model names).

## Model ID format

- **`@cf/<author>/<model>`** — Cloudflare-hosted. Every current model uses this prefix (all 65 on 2026-09-28). Examples: `@cf/openai/gpt-oss-120b`, `@cf/zai-org/glm-5.3`, `@cf/deepseek-ai/deepseek-v4-pro-0813`.
- **`@hf/<author>/<model>`** — historically models served via Hugging Face's TGI stack. In the data these had `"source": 2` (vs `1` for `@cf`). The docs still say the Hugging Face Chat UI template "works with any text generation models that begin with the `@hf` parameter" ([hugging-face-chat-ui.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/configuration/hugging-face-chat-ui.mdx)). **The last four `@hf/` models (`@hf/google/gemma-7b-it`, `@hf/nousresearch/hermes-2-pro-mistral-7b`, `@hf/meta-llama/meta-llama-3-8b-instruct`, `@hf/mistral/mistral-7b-instruct-v0.2`) were retired on 2026-05-30** ([changelog](https://developers.cloudflare.com/changelog/post/2026-05-08-planned-model-deprecations/)). `@hf/` is effectively dead; Kiln should expect only `@cf/`.
- The `<author>` segment is Cloudflare's own org slug and does not always match Hugging Face: `mistral` vs `mistralai`, `meta` vs `meta-llama`, `zai-org`, `moonshotai`, `deepseek-ai`, `qwen`.
- Suffixes carry meaning and are part of the ID: `-fp8`, `-fp8-fast`, `-awq`, `-int8` (quantization/serving variant), `-lora` (LoRA-capable base), and **dated snapshots** like `deepseek-v4-flash-0731` / `deepseek-v4-pro-0813`. Slugs cannot be guessed from the HF repo name.
- With LiteLLM the ID is prefixed with the provider: `cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast` (LiteLLM catalog `provider: "cloudflare"`). models.dev uses the bare `@cf/...` ID under provider key `cloudflare-workers-ai`.

## Current text-generation catalog (31 models)

Flags are Cloudflare's own `properties` (`"true"` = set; `–` = absent). Price is USD per 1M input / output / cached-input tokens. "Paid" = `require_workers_paid`.

| Model ID | Added | Context | Tools (`function_calling`) | Reasoning (efforts) | Vision | Paid | Price in/out/cache |
|---|---|---|---|---|---|---|---|
| `@cf/zai-org/glm-5.3` | 2026-08-14 | 1,310,720 | ✓ | ✓ (max/high/low, mandatory) | – | ✓ | 1.40 / 4.40 / 0.26 |
| `@cf/zai-org/glm-5.3-flash` | 2026-08-26 | 1,310,720 | ✓ | ✓ (max/high/low, mandatory) | ✓ | ✓ | 0.15 / 0.50 / 0.03 |
| `@cf/qwen/qwen3.8-27b` | 2026-08-17 | 262,144 | ✓ | ✓ (low/medium/xhigh) | ✓ | – | 0.45 / 3.20 / 0.05 |
| `@cf/deepseek-ai/deepseek-v4-pro-0813` | 2026-08-13 | 1,048,576 | ✓ | ✓ (max/high/low/none) | – | ✓ | 1.32 / 3.96 / 0.044 |
| `@cf/deepseek-ai/deepseek-v4-flash-0731` | 2026-07-31 | 1,048,576 | ✓ | ✓ (max/high/low/none) | – | ✓ | 0.44 / 1.32 / 0.014 |
| `@cf/zai-org/glm-5.2` | 2026-06-15 | 262,144 | ✓ | ✓ (max/high/none) | – | ✓ | 1.40 / 4.40 / 0.26 |
| `@cf/moonshotai/kimi-k2.7-code` | 2026-06-12 | 262,144 | ✓ | ✓ (mandatory, no levels) | ✓ | ✓ | 0.95 / 4.00 / 0.19 |
| `@cf/moonshotai/kimi-k2.6` | 2026-04-20 | 262,144 | ✓ | ✓ (high/none) | ✓ | ✓ | 0.95 / 4.00 / 0.16 |
| `@cf/google/gemma-4-26b-a4b-it` | 2026-04-02 | 256,000 | ✓ | ✓ (toggle only) | ✓ | – | 0.10 / 0.30 |
| `@cf/nvidia/nemotron-3-120b-a12b` | 2026-02-24 | 256,000 | ✓ | ✓ | – | – | 0.50 / 1.50 |
| `@cf/zai-org/glm-4.7-flash` | 2026-01-28 | 131,072 | ✓ | ✓ (toggle only) | – | – | 0.0605 / 0.40 |
| `@cf/ibm-granite/granite-4.0-h-micro` | 2025-10-07 | 131,000 | ✓ | – | – | – | 0.017 / 0.112 |
| `@cf/aisingapore/gemma-sea-lion-v4-27b-it` | 2025-09-23 | 128,000 | – | – | – | – | 0.351 / 0.555 |
| `@cf/openai/gpt-oss-120b` | 2025-08-05 | 128,000 | ✓ | ✓ (low/medium/high, mandatory) | – | – | 0.35 / 0.75 |
| `@cf/openai/gpt-oss-20b` | 2025-08-05 | 128,000 | ✓ | ✓ (low/medium/high, mandatory) | – | – | 0.20 / 0.30 |
| `@cf/qwen/qwen3-30b-a3b-fp8` | 2025-04-30 | 32,768 | ✓ | ✓ | – | – | 0.0509 / 0.335 |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | 2025-04-05 | 131,000 | ✓ | – | ✓ | – | 0.27 / 0.85 |
| `@cf/mistralai/mistral-small-3.1-24b-instruct` | 2025-03-18 | 128,000 | ✓ | – | – (see note) | – | 0.351 / 0.555 |
| `@cf/qwen/qwq-32b` | 2025-03-05 | 24,000 | – | ✓ | – | – | 0.66 / 1.00 |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | 2025-02-27 | 32,768 | – | – | – | – | 0.66 / 1.00 |
| `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | 2025-01-22 | 80,000 | – | ✓ | – | – | 0.497 / 4.881 |
| `@cf/meta/llama-guard-3-8b` | 2025-01-22 | 131,072 | – | – | – | – | 0.484 / 0.03 |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 2024-12-06 | 24,000 | ✓ | – | – | – | 0.293 / 2.253 |
| `@cf/meta/llama-3.2-11b-vision-instruct` | 2024-09-25 | 128,000 | – | – | ✓ | – | 0.0485 / 0.676 |
| `@cf/meta/llama-3.2-3b-instruct` | 2024-09-25 | 80,000 | – | – | – | – | 0.0509 / 0.335 |
| `@cf/meta/llama-3.2-1b-instruct` | 2024-09-25 | 60,000 | – | – | – | – | 0.027 / 0.201 |
| `@cf/meta/llama-3.1-8b-instruct-fp8` | 2024-07-25 | 32,000 | – | – | – | – | 0.152 / 0.287 |
| `@cf/meta-llama/llama-2-7b-chat-hf-lora` | 2024-04-02 | 8,192 | – | – | – | – | – (LoRA base, beta) |
| `@cf/google/gemma-2b-it-lora` | 2024-04-02 | 8,192 | – | – | – | – | – (LoRA base, beta) |
| `@cf/google/gemma-7b-it-lora` | 2024-04-02 | 3,500 | – | – | – | – | – (LoRA base, beta) |
| `@cf/mistral/mistral-7b-instruct-v0.2-lora` | 2024-04-01 | 15,000 | – | – | – | – | – (LoRA base) |

Also relevant: two `Image-to-Text` models, `@cf/moondream/moondream3.1-9B-A2B` (vision) and `@cf/llava-hf/llava-1.5-7b-hf` (beta). These are not chat models.

Notes and inconsistencies found:

- **Mistral Small 3.1 vision:** the 2025-04-11 changelog says it has "support for vision and tool calling", and its input schema accepts `image_url`, but its JSON has no `vision` property. models.dev lists it as text-only input. Treat vision as unverified.
- **DeepSeek V4 Flash context:** Cloudflare docs JSON says 1,048,576 (after the fix in docs PR #33055, 2026-09-17). models.dev says context 1,310,720 / output 1,048,576. They disagree.
- **GLM-5.3 / 5.3 Flash context 1,310,720** exceeds what models.dev calls the "gateway max 1048576" ([models.dev commit 489a3f4e](https://github.com/sst/models.dev/commit/489a3f4e), "glm-5.3-flash limit 1310720 exceeds gateway max 1048576"). models.dev caps output at 1,048,576.
- **Qwen 3.8 27B endpoint:** its launch changelog lists only the binding and "the REST API at `/ai/run`" plus AI Gateway, while DeepSeek V4 / GLM-5.3 posts also list "the OpenAI-compatible endpoint". Whether every model works on `/v1/chat/completions` is for the API subtopic to confirm ([qwen changelog](https://developers.cloudflare.com/changelog/post/2026-08-17-qwen-3.8-27b-workers-ai/)).
- The May 2026 deprecation post says `@cf/meta/llama-3.1-8b-instruct-fast` "will remain active", but it is not in the public list or the docs data. It may be a hidden alias. Unverified.

## Structured output / JSON mode

- Workers AI supports OpenAI-style `response_format` with `{"type": "json_object"}` or `{"type": "json_schema", "json_schema": {...}}` ([json-mode.mdx](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers-ai/features/json-mode.mdx)). The docs caveat, verbatim: "Workers AI can't guarantee that the model responds according to the requested JSON Schema… an error `JSON Mode couldn't be met` is returned and must be handled." and "JSON Mode currently doesn't support streaming."
- **There is no per-model JSON-mode flag in the catalog.** The docs' "Supported Models" list is badly stale: 3 of its 6 models were retired on 2026-05-30 (`llama-3-8b-instruct`, `llama-3.1-8b-instruct`, `hermes-2-pro-mistral-7b`) and one on 2025-10-01 (`deepseek-coder-6.7b-instruct-awq`).
- Proxy signal: the per-model input JSON Schema. 28 of 31 text-gen input schemas accept `response_format`, and 27 of those mention `json_schema`. No `response_format` at all: `llama-3.2-11b-vision-instruct`, `mistral-small-3.1-24b-instruct`, `qwq-32b`. `response_format` without `json_schema`: `llama-guard-3-8b`. Schema presence is a weak signal; Kiln must confirm with paid tests per model.
- models.dev has a `structured_output` field per model (e.g. `false` for Llama 3.x, `true` for Nemotron and GLM-4.7-Flash). It is partly hand-set and partly inherited from `base_model`.

## Function calling, vision, reasoning

- **Function calling:** use the `function_calling` property (18 hosted models, all text generation). The docs' own example model for it (`@hf/nousresearch/hermes-2-pro-mistral-7b`) is retired, so the docs prose is stale; the property is current.
- **Vision:** use the `vision` property (7 text-gen models on 2026-09-28: glm-5.3-flash, qwen3.8-27b, kimi-k2.7-code, kimi-k2.6, gemma-4-26b-a4b-it, llama-4-scout, llama-3.2-11b-vision). Do not infer vision from `image_url` in the input schema: `qwq-32b` has `image_url` in its schema and no vision.
- **Reasoning:** `reasoning: "true"` plus an optional `reasoning_effort` object `{supported_efforts, default_effort, mandatory, default_enabled, normalizes_to}`. Example from the live JSON for Kimi K2.6: `"supported_efforts":["high","none"],"default_effort":"high","normalizes_to":{"low":"high","medium":"high","max":"high","null":"high"}`. This maps well onto Kiln's `available_thinking_levels`. Cloudflare changes these often (docs PR #33541 on 2026-09-24, "Update model reasoning efforts"), so re-read them when adding a model.

## Mapping to existing Kiln `ModelName`s (for the spec, to verify when adding)

Kiln already has enum members for most of the notable Cloudflare models (checked in `libs/core/kiln_ai/adapters/ml_model_list.py` on 2026-09-28): `gpt_oss_120b`, `gpt_oss_20b`, `kimi_k2_6`, `glm_5_3`, `glm_5_3_flash`, `glm_5_2`, `glm_4_7_flash`, `deepseek_4_pro`, `deepseek_4_flash`, `qwen_3p8_27b`, `qwen_3_30b_a3b`, `gemma_4_27b` (Kiln's entry already uses `google/gemma-4-26b-a4b-it` on OpenRouter), `nemotron_3_super` (OpenRouter `nvidia/nemotron-3-super-120b-a12b`; Cloudflare's `nemotron-3-120b-a12b` maps to it per models.dev `base_model = "nvidia/nemotron-3-super-120b-a12b"`), `llama_4_scout`, `llama_3_3_70b`, `llama_3_2_1b/3b/11b`, `llama_3_1_8b`, `mistral_small_3` (version match unverified — Kiln's may not be 3.1), `qwq_32b`, `deepseek_r1_distill_qwen_32b`.

Probably skip: `kimi-k2.7-code` and `qwen2.5-coder-32b` (the skill says to skip pure coding models), the four `-lora` bases (need a `lora` parameter, beta, tiny context), `llama-guard-3-8b` (a classifier), `gemma-sea-lion-v4-27b-it` and `granite-4.0-h-micro` (no existing Kiln family entries — a product decision).

Two quantization caveats worth recording on Kiln entries: Llama 3.3 70B is the `fp8-fast` variant with only a 24,000-token context; Qwen3 30B is `fp8` with a 32,768 context.
