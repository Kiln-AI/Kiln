---
name: kiln-add-model
description: Add new AI models to Kiln's ml_model_list.py and produce a Discord announcement. Use when the user wants to add, integrate, or register a new LLM model (e.g. Claude, GPT, DeepSeek, Gemini, Kimi, Qwen, Grok) into the Kiln model list, mentions adding a model to ml_model_list.py, or asks to discover/find new models that are available but not yet in Kiln.
---

# Add a New AI Model to Kiln

Integrating a new model into `libs/core/kiln_ai/adapters/ml_model_list.py` requires:

1. **`ModelName` enum** – add an enum member
2. **`built_in_models` list** – add a `KilnModel(...)` entry with providers
3. **`ModelFamily` enum** – only if the vendor is brand-new

After code changes, run paid integration tests, then draft a Discord post.

---

## Global Rules

These apply throughout the entire workflow.

- **Sandbox:** All `curl` and `uv run` commands MUST use `required_permissions: ["all"]`. The sandbox breaks `uv run` (Rust panics) and blocks network access for `curl`.
- **Slug verification:** NEVER guess or infer model slugs from naming patterns. Every `model_id` must come from an authoritative source (LiteLLM catalog, official docs, API reference, or changelog). If you can't verify a slug, tell the user and ask them to provide it.
- **Date awareness:** These models are often released very recently. Web search for current info before assuming you know the details.

---

## Phase 1 – Model Discovery (only when asked to find new/missing models)

If the user asks you to find new models, **do NOT just web search "new AI models this week"** — that only surfaces major releases. Instead, systematically check each family against **both** the LiteLLM catalog **and** models.dev, then union the results. Both are attempts to catalog available models and each has gaps the other fills.

1. **Read the `ModelFamily` and `ModelName` enums** to know what we already have.

2. **Query both catalogs for each family** (run in parallel where possible):

   **LiteLLM catalog** — filters out mirror providers to avoid duplicates:
   ```bash
   curl -s 'https://api.litellm.ai/model_catalog?model=SEARCH_TERM&mode=chat&page_size=500' -H 'accept: application/json' | jq '[.data[] | select(.provider != "openrouter" and .provider != "bedrock" and .provider != "bedrock_converse" and .provider != "vertex_ai-anthropic_models" and .provider != "azure") | .id] | unique | .[]'
   ```

   **models.dev** — search all model IDs across all providers:
   ```bash
   curl -s https://models.dev/api.json | jq '[to_entries[].value.models // {} | keys[]] | .[]' | grep -i "SEARCH_TERM"
   ```
   For details on a specific provider+model: `curl -s https://models.dev/api.json | jq '.["PROVIDER"].models["MODEL_ID"]'`

3. **Search terms** (one query per term):
   `claude`, `gpt`, `o1`, `o3`, `o4` (OpenAI reasoning), `gemini`, `llama`, `deepseek`, `qwen`, `qwq`, `mistral`, `grok`, `kimi`, `glm`, `minimax`, `hunyuan`, `ernie`, `phi`, `gemma`, `seed`, `step`, `pangu`

4. **Union and cross-reference** results from both catalogs against `ModelName`. A model found in either source counts as available. Focus on direct-provider entries (not OpenRouter/Bedrock/Azure mirrors). **Skip pure coding models** (e.g. `codestral`, `deepseek-coder`, `qwen-coder`).

5. **Run targeted web searches** per family to catch very fresh releases not yet in either catalog:
   - `"[family] new model [current year]"`
   - `"[family] release [current month] [current year]"`

6. **Present findings** as a summary. Let the user decide which to add.

---

## Phase 2 – Gather Context

1. **Read the predecessor model** in `ml_model_list.py` (e.g. for Opus 4.6 → read Opus 4.5). You inherit most parameters from it.

2. **Query the LiteLLM catalog** for the new model. This is the primary slug source since Kiln uses LiteLLM. See the [Slug Lookup Reference](#slug-lookup-reference) for query syntax and all verified sources.

3. **Get the OpenRouter slug** via:
   - `curl -s https://openrouter.ai/api/v1/models | jq '.data[].id' | grep -i "SEARCH_TERM"`
   - Fallback: WebSearch for `openrouter [model name] model id`

4. **Get the direct-provider slug** (Anthropic, OpenAI, Google, etc.). Use the LiteLLM catalog first, then official docs. See the [Slug Lookup Reference](#slug-lookup-reference) for provider-specific URLs.

5. **Identify quirks** — check the [Provider Quirks Reference](#provider-quirks-reference) for the relevant provider, and web search for any new quirks:
   - Structured output mode (JSON schema vs function calling)?
   - Reasoning model (needs `reasoning_capable`, parsers, OpenRouter options)?
   - Vision/multimodal support? Which MIME types?
   - Provider-specific flags (`temp_top_p_exclusive`, `thinking_level`, etc.)?
   - Rate limit concerns (`max_parallel_requests`)?

---

## Phase 3 – Code Changes

All changes go in `libs/core/kiln_ai/adapters/ml_model_list.py`.

### 3a. `ModelName` enum

- snake_case: `claude_opus_4_6 = "claude_opus_4_6"`
- Place **before** predecessor (newer first within group)
- Follow existing grouping (all claude together, all gpt together, etc.)

### 3b. `KilnModel` entry in `built_in_models`

- Place **before** predecessor entry (newer = higher in list)
- Copy predecessor's structure and modify: `name`, `friendly_name`, `model_id` per provider, flags

**Provider `model_id` formats:**

| Provider | Format | Notes |
|----------|--------|-------|
| `openrouter` | `vendor/model-name` | Always verify via API |
| `openai` | Bare model name | Verify via OpenAI docs |
| `anthropic` | Variable — older models have date stamps, newer may not | Always verify via Anthropic docs |
| `gemini_api` | Bare name | Verify via Google AI Studio docs |
| `fireworks_ai` | `accounts/fireworks/models/...` | Verify via Fireworks docs |
| `together_ai` | Vendor path format | Verify via Together docs |
| `vertex` | Usually same as gemini_api | Verify via Vertex docs |
| `siliconflow_cn` | Vendor/model format | Verify via SiliconFlow docs |

**Inherit from predecessor** — if the predecessor uses `StructuredOutputMode.json_schema`, assume the new model does too unless you found a quirk.

**Common flags:** `structured_output_mode`, `reasoning_capable`, `temp_top_p_exclusive`, `parser`/`formatter`, multimodal flags, `suggested_for_evals`/`suggested_for_data_gen`.

### 3c. Multimodal capabilities

If the model supports non-text inputs, configure:

- `multimodal_capable=True` and `supports_doc_extraction=True` if it supports any MIME types
- `supports_vision=True` if it supports images
- `multimodal_requires_pdf_as_image=True` if vision-capable but no native PDF support (also add `KilnMimeType.PDF` to MIME list). **Always set this on OpenRouter providers** — OpenRouter routes PDFs through Mistral OCR which breaks LiteLLM parsing.
- Always include `KilnMimeType.TXT` and `KilnMimeType.MD` on any `multimodal_capable` model

**Strategy: start broad, narrow based on test failures.** Enable a generous set of MIME types, run tests, and remove only types the provider explicitly rejects (400 errors). Don't remove types for timeout/auth/content-mismatch failures.

Full MIME superset (Gemini uses all):
```python
# documents
KilnMimeType.PDF, KilnMimeType.CSV, KilnMimeType.TXT, KilnMimeType.HTML, KilnMimeType.MD
# images
KilnMimeType.JPG, KilnMimeType.PNG
# audio
KilnMimeType.MP3, KilnMimeType.WAV, KilnMimeType.OGG
# video
KilnMimeType.MP4, KilnMimeType.MOV
```

### 3d. `suggested_for_evals` / `suggested_for_data_gen`

**Only set these if** the predecessor already has them, OR web search shows the model is a clear SOTA leap (ask user to confirm first).

**Zero-sum rule:** When adding a new model with these flags, remove them from the oldest same-family model to keep the suggested count stable. **Ask the user to confirm** the swap before making changes.

### 3e. `ModelFamily` enum (only if needed)

Only add a new family if the vendor is completely new.

---

## Phase 4 – Run Tests

Tests call real LLMs and cost money. Just execute commands directly — Cursor prompts for approval.

**`-k` filter syntax:** Always use bracket notation for model+provider filtering, never `and`:
- Good: `-k "test_name[glm_5-fireworks_ai]"` or `-k "glm_5"`
- Bad: `-k "glm_5 and fireworks"` — `and` is a pytest keyword expression that can match wrong tests

### 4a. Smoke test — verify slug works

Run a single test+provider combo first:

```bash
uv run pytest --runpaid --ollama -k "test_data_gen_sample_all_models_providers[MODEL_ENUM-PROVIDER]"
```

If it fails, fix the slug/config before proceeding. Use `--collect-only` to find exact parameter IDs if unsure.

### 4b. Full test suite

```bash
uv run pytest --runpaid --ollama -k "MODEL_ENUM" -v 2>&1 | grep -E "PASSED|FAILED|ERROR|short test|=====|collected"
```

**If tests fail — debug one at a time:**
1. Pick ONE failing test, run it with `-v` for full output
2. Fix the config
3. Re-run that single test to verify
4. Only re-run the full suite once the single test passes

### 4c. Extraction tests (if `supports_doc_extraction=True`)

Tests are in `libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py`.

```bash
# See what will run:
uv run pytest --collect-only libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -q | grep MODEL_ENUM

# Run them:
uv run pytest --runpaid --ollama libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -k "MODEL_ENUM"
```

If a provider rejects a data type (400 error), remove that `KilnMimeType` and re-run.

---

## Phase 5 – Discord Announcement

```
New Model: [Model Name] 🚀
[One-liner about the model and that it's now in Kiln]

Kiln Test Pass Results
[Model Name]:
✅ Tool Calling
✅ Structured Data ([mode used])
✅ Synthetic Data Generation
✅ Evals (only if suggested_for_evals=True)
✅ Document extraction: [formats] (only if supports_doc_extraction=True)
✅ Vision: [formats] (only if supports_vision=True)

Model Variants, Hosts and Quirks
[Model Name]:
Available on: [list providers]
[Any quirks or notes]

How to Use These Models in Kiln
Simply restart Kiln, and all these models will appear in your model dropdown if you have the appropriate API configured.
```

Use ⚠️ for flaky features, ❌ for unsupported.

### Test Summary

After the Discord announcement, print a per-test summary listing every test that ran for the model. Use the full pytest parametrize ID so the user can see exactly which test+provider combos passed, failed, or were flaky.

Format:
```
Test Summary: [Model Name]
✅ test_data_gen_all_models_providers[model_enum-provider]
✅ test_data_gen_sample_all_models_providers[model_enum-provider]
✅ test_tools_all_built_in_models[model_enum-provider]
⚠️ test_structured_input_cot_prompt_builder[model_enum-provider] — assert 3 == 5 (content quality flake)
❌ test_all_built_in_models_structured_output[model_enum-provider] — 400 Bad Request (unsupported feature)
```

Rules:
- ✅ for passed tests
- ⚠️ for tests that failed due to content quality flakes (e.g. model returned fewer items than expected, weak assertion mismatches) — include a brief reason
- ❌ for tests that failed due to real errors (bad slug, unsupported feature, 400/500 errors) — include a brief reason
- List every test, grouped by provider if the model has multiple providers
- Include extraction tests (Phase 4c) if they were run

---

## Checklist

- [ ] `ModelName` enum entry added (before predecessor)
- [ ] `KilnModel` entry added to `built_in_models` (before predecessor)
- [ ] `ModelFamily` enum updated (only if new family)
- [ ] All provider slugs verified from authoritative sources
- [ ] Flags inherited from predecessor and adjusted for quirks
- [ ] Zero-sum applied if model is suggested for evals/data gen
- [ ] Smoke test passed
- [ ] Full test suite passed
- [ ] Discord announcement drafted

---

## Provider Quirks Reference

### Anthropic
- Newer models (Opus 4.1+, Sonnet 4.5+) need `temp_top_p_exclusive=True`
- Opus 4.5+ uses `json_schema`; older Opus uses `function_calling`
- Extended thinking models: `anthropic_extended_thinking=True` + `reasoning_capable=True`

### OpenAI
- Most GPT models use `json_schema` for structured output
- Reasoning models (o-series) need `thinking_level` parameter
- Chat variants sometimes lack JSON schema (use `json_instruction_and_object`)

### Google/Gemini
- `gemini_reasoning_enabled=True` for reasoning-capable models
- Gemini API often needs `thinking_level="medium"` + `max_parallel_requests=2`
- Rich multimodal support (audio, video, images, documents)

### DeepSeek
- R1 models: `parser=ModelParserID.r1_thinking` + `reasoning_capable=True`
- V3 models: often available on OpenRouter, Fireworks, SiliconFlow CN
- Some need `r1_openrouter_options=True` + `require_openrouter_reasoning=True`

### OpenRouter (general)
- Slugs: `vendor/model-name`
- Reasoning models: may need `require_openrouter_reasoning=True`
- Some models: `openrouter_skip_required_parameters=True`
- Logprobs: `logprobs_openrouter_options=True` if supported
- Always `multimodal_requires_pdf_as_image=True` (OpenRouter's PDF routing breaks LiteLLM)

### Qwen3 / Thinking Models
- Thinking variants: `reasoning_capable=True`, `parser=ModelParserID.r1_thinking`
- No-thinking variants: `formatter=ModelFormatterID.qwen3_style_no_think`
- SiliconFlow may need `siliconflow_enable_thinking=True/False`

---

## Slug Lookup Reference

Use **both** LiteLLM and models.dev when looking up slugs — they complement each other. LiteLLM gives you the exact slugs Kiln will use (since Kiln runs on LiteLLM), while models.dev often has broader coverage of newer or niche models with pricing, context limits, and capability details.

### LiteLLM Model Catalog (https://api.litellm.ai/model_catalog)

100 free requests/day, no key needed. Supports server-side filtering: `model=` (substring match), `provider=`, `mode=`, `supports_vision=true`, `supports_reasoning=true`, `page_size=500`.

```bash
# Find all variants of a model across providers:
curl -s 'https://api.litellm.ai/model_catalog?model=MODEL_NAME&mode=chat&page_size=500' \
  -H 'accept: application/json' | jq '.data[] | {id, provider, mode, max_input_tokens, supports_vision, supports_reasoning, supports_function_calling}'

# List all models for a provider:
curl -s 'https://api.litellm.ai/model_catalog?provider=PROVIDER&mode=chat&page_size=500' \
  -H 'accept: application/json' | jq '.data[].id'
```

### models.dev (https://models.dev/api.json)

Mega JSON covering 50+ providers with model IDs, pricing, context limits, capabilities, and release dates. **Large file — always use curl+jq, never WebFetch.**

```bash
# Search all model IDs across all providers:
curl -s https://models.dev/api.json | jq '[to_entries[].value.models // {} | keys[]] | .[]' | grep -i "SEARCH_TERM"

# List all model IDs for a specific provider:
curl -s https://models.dev/api.json | jq '.["PROVIDER"].models | keys[]'

# Get full details for a specific provider+model:
curl -s https://models.dev/api.json | jq '.["PROVIDER"].models["MODEL_ID"]'
```

### Other verified sources
- OpenRouter: `curl -s https://openrouter.ai/api/v1/models | jq '.data[].id' | grep -i "SEARCH_TERM"`
- Anthropic: https://docs.anthropic.com/en/api/models/list
- Cerebras: https://inference-docs.cerebras.ai/models/overview

When you find a new reliable slug source, append it here.
