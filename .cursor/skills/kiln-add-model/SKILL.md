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
   - Provider-specific flags (`temp_top_p_exclusive`, etc.)?
   - Rate limit concerns (`max_parallel_requests`)?

6. **Determine thinking levels** — does the model support configurable reasoning effort? See [Thinking Levels Reference](#thinking-levels-reference) for the full lookup chain. Key quick checks:
   - Check the **vendor model page** (e.g. OpenAI model pages say "Reasoning.effort supports: X, Y, Z")
   - Check **OpenRouter** `supported_parameters` — if `reasoning` is absent, skip thinking levels
   - R1-style thinking models (DeepSeek, Qwen thinking variants) do NOT get thinking level dicts

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
- **`friendly_name` must follow the existing naming pattern** of sibling models in the same family. Check the predecessor. For example, Claude Sonnets use `"Claude {version} Sonnet"` (e.g. "Claude 4.5 Sonnet"), not `"Claude Sonnet {version}"`. Do NOT use the vendor's marketing name if it differs from Kiln's established convention.

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

**Every single `model_id` must be verified from an authoritative source. No exceptions.**

**Setting flags — use catalog data + predecessor as dual signals:**

The LiteLLM catalog and models.dev responses include capability flags (`supports_vision`, `supports_function_calling`, `supports_reasoning`, etc.). Use these as the **primary signal** for what to enable on the new model:

- If the catalog says `supports_vision: true` → enable `supports_vision`, `multimodal_capable`, and vision MIME types (see 2c)
- If the catalog says `supports_function_calling: true` → use `StructuredOutputMode.json_schema` (or `function_calling` depending on provider norms — check predecessor)
- If the catalog says `supports_reasoning: true` → enable `reasoning_capable` and check if parser/formatter/thinking flags are needed

Then **cross-check against the predecessor**. The predecessor tells you *how* Kiln configures a similar model (which `structured_output_mode`, which provider-specific flags, etc.). The catalog tells you *what* the model can do. Use both:
- Catalog says the model supports vision but predecessor doesn't have it? Enable it — this is a new capability.
- Predecessor has `temp_top_p_exclusive` but nothing in the catalog mentions it? Keep it — it's a provider quirk the catalog doesn't track.
- Catalog and predecessor disagree on something? Trust the catalog for capabilities, trust the predecessor for Kiln-specific configuration patterns.

**Common flags:**
- `structured_output_mode` – how the model handles JSON output
- `suggested_for_evals` / `suggested_for_data_gen` – see **zero-sum rule** below
- `multimodal_capable` / `supports_vision` / `supports_doc_extraction` – see **multimodal rules** below
- `reasoning_capable` – for thinking/reasoning models
- `temp_top_p_exclusive` – Anthropic models that can't have both temp and top_p
- `parser` / `formatter` – for models needing special parsing (e.g. R1-style thinking)

#### 2c. Multimodal capabilities

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

### 3f. Thinking Levels (`available_thinking_levels` / `default_thinking_level`)

If the model supports configurable reasoning effort (not just on/off), add `available_thinking_levels` and `default_thinking_level` to each provider entry. See [Thinking Levels Reference](#thinking-levels-reference) for the full lookup chain and existing constants.

**Quick rules:**
- Reuse an existing `_THINKING_LEVELS` constant if the levels match exactly
- Create a new constant only if levels differ; name it `{MODEL}_{PROVIDER_CONTEXT}_THINKING_LEVELS`
- `default_thinking_level` must be one of the values in `available_thinking_levels`

---

## Phase 4 – Run Tests

Tests call real LLMs and cost money. Ideally the user only needs to consent to two script executions: the smoke test, then the full parallel suite.

**Vertex AI authentication:** Vertex tests require active gcloud credentials. If you are changing a model that uses Vertex, you must not run the test until asking the user to run `gcloud auth application-default login` before trying. These failures are auth issues, not model config problems.

**`-k` filter syntax:** Always use bracket notation for model+provider filtering, never `and`:
- Good: `-k "test_name[glm_5-fireworks_ai]"` or `-k "glm_5"`
- Bad: `-k "glm_5 and fireworks"` — `and` is a pytest keyword expression that can match wrong tests

### 4a. Enable parallel testing

Before running paid tests, enable parallel testing in `pytest.ini`:

```ini
# Change this line:
# addopts = -n auto
# To:
addopts = -n 8
```

**Important:** Revert this change after all tests complete (re-comment the line).

### 4b. Smoke test — verify slug works

Run a single test+provider combo first:

```bash
uv run pytest --runpaid --ollama -k "test_tools_all_built_in_models[MODEL_ENUM-PROVIDER]"
```

If it fails, fix the slug/config before proceeding. Use `--collect-only` to find exact parameter IDs if unsure.

### 4c. Full test suite

```bash
uv run pytest --runpaid --ollama -k "MODEL_ENUM" -v
```

**If tests fail — debug one at a time:**
1. Pick ONE failing test, run it with `-v` for full output
2. Fix the config
3. Re-run that single test to verify
4. Only re-run the full suite once the single test passes

### 4d. Extraction tests (if `supports_doc_extraction=True`)

Tests are in `libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py`.

```bash
# See what will run:
uv run pytest --collect-only libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -q | grep MODEL_ENUM

# Run them:
uv run pytest --runpaid --ollama libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -k "MODEL_ENUM"
```

If a provider rejects a data type (400 error), remove that `KilnMimeType` and re-run.

### 4e. Revert parallel testing

After all tests complete, **revert `pytest.ini`** back to the commented-out state:

```ini
# addopts = -n auto
```

### 4f. Test output format

After all tests finish, present results to the user as:

1. **Two paragraphs of nuance** – describe any unusual findings, things you tried and reverted, known pre-existing failures vs new failures, API quirks discovered, and any config adjustments made during testing.

2. **Per-model per-test dump** – organized by model name and provider, using this format:

```
Model Name (provider):
✅ test_name[model_enum-provider]
❌ test_name[model_enum-provider] -- brief failure reason
⏭️ test_name[model_enum-provider]
```

Use ✅ for PASSED, ❌ for FAILED (with brief reason), ⏭️ for SKIPPED.

---

## Phase 5 – Discord Announcement

**Do NOT draft the Discord announcement automatically.** After presenting test results, ask the user if they want a Discord announcement drafted. Only proceed if they confirm.

When requested, use this format:

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
- [ ] `friendly_name` matches the naming pattern of sibling models in the same family
- [ ] `ModelFamily` enum updated (only if new family)
- [ ] All provider slugs verified from authoritative sources
- [ ] Flags inherited from predecessor and adjusted for quirks
- [ ] Thinking levels configured if model supports reasoning effort (see [Thinking Levels Reference](#thinking-levels-reference))
- [ ] Preserve existing comments from predecessor (e.g. reasoning notes, MIME type groupings)
- [ ] Zero-sum applied if model is suggested for evals/data gen
- [ ] RAG config templates updated if the new model replaces one used in `app/web_ui/src/routes/(app)/docs/rag_configs/[project_id]/add_search_tool/rag_config_templates.ts`
- [ ] Parallel testing enabled in `pytest.ini` (`addopts = -n 8`)
- [ ] Smoke test passed
- [ ] Full test suite passed
- [ ] Per-model per-test result dump presented with nuance paragraphs
- [ ] Parallel testing reverted in `pytest.ini` (re-commented)
- [ ] Discord announcement drafted (only if user requests it)

---

## Provider Quirks Reference

### Anthropic
- Newer models (Opus 4.1+, Sonnet 4.5+) need `temp_top_p_exclusive=True`
- Opus 4.5+ uses `json_schema`; older Opus uses `function_calling`
- Extended thinking models: `anthropic_extended_thinking=True` + `reasoning_capable=True`

### OpenAI
- Most GPT models use `json_schema` for structured output
- GPT-5.x models support `available_thinking_levels` — see [Thinking Levels Reference](#thinking-levels-reference)
- Chat/instant variants (e.g. GPT-5.3 Instant) may not support reasoning effort
- o-series models have fixed thinking tiers (separate model entries per tier, not configurable levels)

### Google/Gemini
- `gemini_reasoning_enabled=True` for reasoning-capable models
- Gemini 3.x models support `available_thinking_levels` — see [Thinking Levels Reference](#thinking-levels-reference)
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

## Thinking Levels Reference

No API provides the available thinking levels programmatically — they must be manually sourced. Use this lookup chain in priority order:

### Lookup Chain

1. **Vendor model page** (most authoritative)
   - **OpenAI:** Each model page includes "Reasoning.effort supports: X, Y, Z" in the description text. URL: `https://developers.openai.com/api/docs/models/{model-id}`
   - **Anthropic:** The [effort docs](https://platform.claude.com/docs/en/build-with-claude/effort) list levels per model. Opus 4.6 supports `low, medium, high, max`; Sonnet 4.6 supports `low, medium, high`.
   - **Google Gemini:** The models API returns `thinking: true/false` (boolean only). Levels come from docs.

2. **Vercel AI Gateway docs** — clean structured tables per provider:
   - `https://vercel.com/docs/ai-gateway/capabilities/reasoning/openai`
   - `https://vercel.com/docs/ai-gateway/capabilities/reasoning/anthropic`
   - `https://vercel.com/docs/ai-gateway/capabilities/reasoning/google`

3. **Inherit from predecessor** — if the same family/tier model has a `_THINKING_LEVELS` dict, the new model very likely uses the same or a superset.

4. **OpenRouter `supported_parameters`** — check if `reasoning` is present:
   ```bash
   curl -s https://openrouter.ai/api/v1/models | jq '.data[] | select(.id == "SLUG") | .supported_parameters'
   ```
   If `reasoning` is absent, the model does not support effort levels — skip thinking levels entirely.

5. **Smoke test** — as a last resort, send a request with an invalid effort level and check the error message, which often enumerates the valid values.

### Important Distinctions

- **Effort-level models** (GPT-5.x, Claude 4.x, Gemini 3.x) → add `available_thinking_levels` dicts
- **R1-style thinking models** (DeepSeek R1, Qwen thinking variants) → on/off thinking, NOT effort levels. Use `reasoning_capable=True` + `parser=ModelParserID.r1_thinking`. Do NOT add thinking level dicts.
- **Chat/instant models** (e.g. GPT-5.3 Instant) → may not support reasoning effort at all. Verify on the vendor model page.

### Existing Constants

Reuse when levels match exactly. Create a new constant only if levels differ. This is not an exhaustive list.

| Constant | Levels | Default | Used by |
|----------|--------|---------|---------|
| `GPT_5_4_OPENAI_THINKING_LEVELS` | none, low, medium, high, xhigh | none | GPT-5.4 |
| `GPT_5_4_PRO_OPENAI_THINKING_LEVELS` | medium, high, xhigh | medium | GPT-5.4 Pro |
| `GPT_5_2_OPENAI_THINKING_LEVELS` | none, low, medium, high, xhigh | none | GPT-5.2, GPT-5.2 Chat |
| `GPT_5_2_PRO_OPENAI_THINKING_LEVELS` | medium, high, xhigh | medium | GPT-5.2 Pro |
| `GPT_5_1_OPENAI_THINKING_LEVELS` | none, low, medium, high | none | GPT-5.1 |
| `GPT_5_OPENAI_THINKING_LEVELS` | minimal, low, medium, high | medium | GPT-5, GPT-5 Mini, GPT-5 Nano, GPT-5 Chat |
| `GEMINI_3_PRO_THINKING_LEVELS` | low, medium, high | high | Gemini 3 Pro, Gemini 3.1 Pro |
| `GEMINI_3_FLASH_THINKING_LEVELS` | minimal, low, medium, high | high | Gemini 3 Flash, Gemini 3.1 Flash Lite |
| `CLAUDE_ANTHROPIC_EFFORT_THINKING_LEVELS` | low, medium, high | high | Claude (Anthropic direct) |
| `CLAUDE_OPENROUTER_THINKING_LEVELS` | none, minimal, low, medium, high, xhigh | none | Claude (OpenRouter) |

### Sources That Do NOT Work

These were investigated and confirmed to lack thinking level data:
- **OpenRouter API** — only boolean `reasoning` in `supported_parameters`
- **LiteLLM catalog** — only `supports_reasoning: true/false`
- **Google Gemini models API** — only `thinking: true/false`
- **OpenAI `/v1/models` endpoint** — minimal object with no capability fields

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
