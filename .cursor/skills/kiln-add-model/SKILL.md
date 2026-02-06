---
name: kiln-add-model
description: Add new AI models to Kiln's ml_model_list.py and produce a Discord announcement. Use when the user wants to add, integrate, or register a new LLM model (e.g. Claude, GPT, DeepSeek, Gemini, Kimi, Qwen, Grok) into the Kiln model list, or mentions adding a model to ml_model_list.py.
---

# Add a New AI Model to Kiln

This skill walks you through the end-to-end process of integrating a new AI model into Kiln's `libs/core/kiln_ai/adapters/ml_model_list.py` and writing a Discord release note.

## Overview

Adding a model requires touching **three areas** of `ml_model_list.py` and then running tests:

1. **`ModelName` enum** – add an enum member
2. **`built_in_models` list** – add a `KilnModel(...)` entry with its providers
3. **`ModelFamily` enum** – only if the model belongs to a brand-new family

After code changes you run paid integration tests, then draft a Discord post.

---

## Step-by-step Workflow

### Phase 0 - Get the current date and time. Often these models come out extremely recently, so if the user is asking you to add a model, it probably came out in the last couple days and you will not know about it before hand.

### Phase 1 – Gather Context

1. **Read the predecessor model** in `ml_model_list.py` (e.g. for Claude Opus 4.6 → read Claude Opus 4.5). You will inherit most parameters from it.
2. **Get the OpenRouter slug.** Try these approaches in order:
   - **Best:** Use Shell with curl to query the API and grep for the model: `curl -s https://openrouter.ai/api/v1/models | python3 -m json.tool | grep -i "model-name"` (use `required_permissions: ["network"]`). This is more reliable than WebFetch for this large JSON response.
   - **Fallback:** WebSearch for `openrouter [model name] model id` or check the model's OpenRouter page directly (e.g. `https://openrouter.ai/anthropic/claude-opus-4.6`).
   - **Last resort:** WebFetch on `https://openrouter.ai/api/v1/models` — but this response is very large and may time out.

3. **Get the EXACT direct-provider slug** (Anthropic API, OpenAI API, Google Gemini API, etc.) and any known quirks.

   **CRITICAL: NEVER guess or infer slugs from naming patterns.** Every slug must come from an authoritative source — official docs, API reference, or changelog. The date-stamped portion of Anthropic IDs, the exact casing of OpenAI IDs, etc. are NOT predictable. You MUST verify each one.

   **Fetching strategies** (use whichever works — WebFetch and WebSearch can both time out):
   - **WebSearch** — good first attempt for most providers
   - **WebFetch** — good for specific doc pages or lightweight API endpoints (e.g. Anthropic models list)
   - **Shell with curl** — most reliable fallback, especially for API endpoints. Use `required_permissions: ["network"]`.

   Suggested search queries / URLs:
   - Anthropic: fetch `https://docs.anthropic.com/en/api/models/list` or search `anthropic [model name] API model identifier [current year]`
   - OpenAI: search `openai [model name] API model ID [current year]` or `"[model name]" site:platform.openai.com`
   - Google: search `gemini [model name] API model ID [current year]` or `"[model name]" site:ai.google.dev`
   - DeepSeek, Kimi, Qwen, etc.: search their official docs for the exact model identifier.

   If you cannot find the exact slug after trying multiple approaches, **tell the user you couldn't verify it** and ask them to provide it. Do NOT fall back to guessing based on naming conventions of older models.

4. **Identify quirks** from search results – things like:
   - Does the model support JSON schema structured output, or only function calling?
   - Does it have `temp_top_p_exclusive` (Anthropic Opus 4.1+ and Sonnet 4.5)?
   - Is it a reasoning model (needs `reasoning_capable`, parsers, special OpenRouter options)?
   - Does it support vision/multimodal? What MIME types?
   - Any rate limit concerns (`max_parallel_requests`)?

### Phase 2 – Code Changes

All changes go in `libs/core/kiln_ai/adapters/ml_model_list.py`.

#### 2a. Add to `ModelName` enum

- Use snake_case: `claude_opus_4_6 = "claude_opus_4_6"`
- Place it **before** the predecessor (newer models first within their group)
- Follow the existing grouping convention (all claude together, all gpt together, etc.)

#### 2b. Add to `built_in_models` list

- Place the new `KilnModel(...)` **before** the predecessor entry (newer = higher in list)
- Copy the predecessor's structure and modify:
  - `name=ModelName.your_new_enum`
  - `friendly_name="Human Readable Name"`
  - `model_id` for each provider (the slug you found)
  - Adjust any flags based on quirks discovered

**Key rules for provider configuration (Note: these rules are not set in stone, things change):**

| Provider | `model_id` format | Notes |
|----------|-------------------|-------|
| `openrouter` | `vendor/model-name` | Verify via OpenRouter API or model page |
| `openai` | Bare model name | Verify via OpenAI docs/changelog |
| `anthropic` | Variable format | **Format changed over time:** Older models use date stamps (e.g. `claude-opus-4-5-20251101`), newer models may not (e.g. `claude-opus-4-6`). **Always verify via Anthropic docs** |
| `gemini_api` | Bare name | Verify via Google AI Studio docs |
| `fireworks_ai` | `accounts/fireworks/models/...` | Verify via Fireworks docs |
| `together_ai` | Vendor path format | Verify via Together docs |
| `vertex` | Usually same as gemini_api | Verify via Vertex docs |
| `siliconflow_cn` | Vendor/model format | Verify via SiliconFlow docs |

**Every single `model_id` must be verified from an authoritative source. No exceptions.**

**Inherit from predecessor** – if Claude Opus 4.5 uses `StructuredOutputMode.json_schema`, assume Opus 4.6 does too unless you found a quirk in your web search.

**Common flags to consider:**
- `structured_output_mode` – how the model handles JSON output
- `suggested_for_evals` / `suggested_for_data_gen` – see **zero-sum rule** below
- `multimodal_capable` / `supports_vision` / `supports_doc_extraction` – see **multimodal rules** below
- `reasoning_capable` – for thinking/reasoning models
- `temp_top_p_exclusive` – Anthropic models that can't have both temp and top_p
- `parser` / `formatter` – for models needing special parsing (e.g. R1-style thinking)

#### 2c. Multimodal capabilities

If the model supports any non-text inputs (images, documents, audio, video), configure multimodal flags. These follow a hierarchy:

- Set `multimodal_capable=True` and `supports_doc_extraction=True` if the model supports **one or more** MIME types
- Set `supports_vision=True` if the model supports **images**
- If `supports_vision=True`, you can also support PDFs by setting `multimodal_requires_pdf_as_image=True` (and adding `KilnMimeType.PDF` to the MIME type list). This renders PDFs as images before sending them to the model.
- `KilnMimeType.TXT` and `KilnMimeType.MD` are supported on **all** models that have `multimodal_capable=True` — always include them

**Strategy: start broad, narrow based on test failures.**
1. Enable a generous set of MIME types based on what the model claims to support
2. Run the tests
3. If a test fails because the provider/model **rejects a specific data type**, that's a valid failure — remove that MIME type and re-run
4. If a test fails for other reasons (timeout, auth, structured output), that's a different issue — don't remove MIME types for non-rejection failures

The full superset of MIME types available (Gemini uses all of these):
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

#### 2d. `suggested_for_evals` / `suggested_for_data_gen` rules

**Not every model gets these flags.** Only set them if:
- The **predecessor** in the same tier already has them (e.g. Opus 4.5 has `suggested_for_evals` → Opus 4.6 should too), OR
- Web search results indicate this model is a clear SOTA leap — in which case **ask the user to confirm** before setting the flag.

If the predecessor does NOT have the flag, do NOT add it to the new model by default.

**Zero-sum rule:** When adding a new model with `suggested_for_evals=True` or `suggested_for_data_gen=True`, **remove those flags from the oldest model in the same family** to keep the total count roughly constant. The UI surfaces these as recommended picks, and too many suggestions dilutes the signal.

Before making any changes, **ask the user to confirm** the swap. For example:

> "Opus 4.8 looks like it should be suggested for evals (inheriting from 4.7). Currently Opus 4.5, 4.6, and 4.7 are all suggested. I'd like to add 4.8 and delist 4.5. Sound good?"

Steps:
1. Search `built_in_models` for all entries in the same `ModelFamily` that have the flag set
2. Identify the oldest one(s)
3. Propose the swap to the user and wait for confirmation
4. Remove the flag (or set it to `False`) on the oldest
5. Set the flag on the new model

#### 2e. Add to `ModelFamily` enum (only if needed)

Only add a new family if the model vendor is completely new (not already in the enum).

### Phase 3 – Run Tests

Tests are paid (they call real LLMs). The user's Cursor is configured to prompt for approval on `uv run` commands, so **just execute the commands directly** (with `required_permissions: ["all"]` since they need network access). You can briefly mention what the test does, but don't wait for a separate text confirmation — the Cursor approval dialog handles gating.

#### 3a. Smoke test – verify the slug works

Before running the full suite, run a **single specific test** to confirm the provider slug is valid and the model responds. Pick one test+provider combo. Just execute it:

```bash
uv run pytest --runpaid --ollama -k "test_data_gen_sample_all_models_providers[model_enum_name-provider_name]"
```

Example: `uv run pytest --runpaid --ollama -k "test_data_gen_sample_all_models_providers[kimi_k2_5-openrouter]"`

The pytest parameter IDs use `ModelName` enum value + `ModelProviderName` enum value (from `get_all_models_and_providers()` in `test_prompt_adaptors.py` which iterates `built_in_models`). You can find the exact IDs by running `--collect-only` first if unsure.

This catches bad slugs, auth issues, or provider misconfigurations early before burning through a full paid test run. If the smoke test fails, fix the slug/config before proceeding.

#### 3b. Full test suite

Once the smoke test passes, execute the full suite:

```bash
uv run pytest --runpaid --ollama -k "model_enum_name"
```

Example: `uv run pytest --runpaid --ollama -k "kimi_k2_5"`

The test key (`-k`) uses the `ModelName` enum value (snake_case).

**If tests fail:**
- Re-run only the failing test(s) **with `-v`** to get verbose output for debugging
- Check the error output for structured output issues, API errors, or parameter mismatches
- Common fixes: change `structured_output_mode`, adjust provider-specific flags, comment out a problematic provider

#### 3c. Multimodal / extraction tests

If the model has `supports_doc_extraction=True`, run the extraction tests separately. These are in `libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py`.

The key test is `test_extract_document_success` — it's parametrized by model+provider AND by MIME type, so it tests each supported type individually. Tests automatically skip MIME types not in the model's `multimodal_mime_types` list.

**Step 1:** Collect the test IDs for the new model to see what will run:

```bash
uv run pytest --collect-only libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -q | grep model_enum_name
```

This will show test IDs like:
```
...::test_extract_document_success[application/pdf-text_probe0-claude_opus_4_6-openrouter]
...::test_extract_document_success[image/png-text_probe5-claude_opus_4_6-anthropic]
```

**Step 2:** Run the extraction tests for the new model. Use `-k` with the model name to filter:

```bash
uv run pytest --runpaid --ollama libs/core/kiln_ai/adapters/extractors/test_litellm_extractor.py::test_extract_document_success -k "model_enum_name"
```

**Handling MIME type failures:**
- If a test fails because the provider **rejects the data type** (e.g. 400 error, unsupported format), that's a valid failure — remove that `KilnMimeType` from the model's `multimodal_mime_types` list and re-run
- If a test fails for other reasons (timeout, content mismatch, auth), investigate the root cause — don't just remove the MIME type

### Phase 4 – Discord Announcement

After tests pass, draft a Discord post. Format:

```
New Model: [Model Name] 🚀
[One-liner about what the model is and that it's now in Kiln]

Kiln Test Pass Results
[Model Name]:
✅ Tool Calling
✅ Structured Data ([mode used])
✅ Synthetic Data Generation
✅ Evals (only include if suggested_for_evals=True)
✅ Document extraction: [list formats] (only include if supports_doc_extraction=True)
✅ Vision: [list formats] (only include if supports_vision=True)

Model Variants, Hosts and Quirks
[Model Name]:
Available on: [list providers]
[Any quirks or notes]

How to Use These Models in Kiln
Simply restart Kiln, and all these models will appear in your model dropdown if you have the appropriate API configured.
```

Use ⚠️ for features that are flaky or have caveats. Use ❌ for unsupported features.

---

## Provider-Specific Quirk Reference

### Anthropic
- Newer models (Opus 4.1+, Sonnet 4.5+) need `temp_top_p_exclusive=True` on the Anthropic provider
- Opus 4.5 uses `json_schema`, older Opus uses `function_calling`
- Extended thinking models need `anthropic_extended_thinking=True` and `reasoning_capable=True`
- **Model ID format has changed over time.** Older models used date-stamped IDs (e.g. `claude-opus-4-5-20251101`), but newer models may drop the date stamp (e.g. `claude-opus-4-6`). **Do NOT assume the format — always verify via the Anthropic models list API:** `https://docs.anthropic.com/en/api/models/list`. The `id` field in the response is the exact model ID to use.

### OpenAI
- Most GPT models use `json_schema` for structured output
- Reasoning models (o-series) need `thinking_level` parameter
- Chat variants sometimes lack JSON schema support (use `json_instruction_and_object`)
- OpenRouter slugs: `openai/model-name`

### Google/Gemini
- Need `gemini_reasoning_enabled=True` for reasoning-capable models
- Gemini API provider often needs `thinking_level="medium"` and `max_parallel_requests=2`
- Support rich multimodal (audio, video, images, documents)

### DeepSeek
- R1 models need `parser=ModelParserID.r1_thinking` and `reasoning_capable=True`
- V3 models often available on OpenRouter, Fireworks, SiliconFlow CN
- Some need `r1_openrouter_options=True` and `require_openrouter_reasoning=True`

### OpenRouter (general)
- Slugs: `vendor/model-name`
- For reasoning models: may need `require_openrouter_reasoning=True`
- Some models need `openrouter_skip_required_parameters=True`
- Logprobs: `logprobs_openrouter_options=True` if supported

### Qwen3 / Thinking Models
- Thinking variants need `reasoning_capable=True`, `parser=ModelParserID.r1_thinking`
- No-thinking variants need `formatter=ModelFormatterID.qwen3_style_no_think`
- SiliconFlow may need `siliconflow_enable_thinking=True/False`

---

## Checklist Before Finishing

- [ ] `ModelName` enum entry added (before predecessor)
- [ ] `KilnModel` entry added to `built_in_models` (before predecessor)
- [ ] `ModelFamily` enum updated (only if new family)
- [ ] Provider slugs verified (OpenRouter, direct API)
- [ ] Flags inherited from predecessor and adjusted for quirks
- [ ] Zero-sum: if new model is suggested for evals/data gen, oldest same-family suggestion removed
- [ ] Smoke test passed (single test to verify slug)
- [ ] Full test suite passed (with user permission)
- [ ] Discord announcement drafted
- [ ] If you found a useful URL for verifying slugs, append it to the Verified Slug Sources section below

---

## Verified Slug Sources

When you find a reliable URL for looking up model slugs, **append it here** so future runs of this skill benefit. Format: `- [Provider]: [URL] — [brief note]`

- OpenRouter: https://openrouter.ai/api/v1/models — JSON list of all models, search for the `id` field
- Anthropic: https://docs.anthropic.com/en/api/models/list — API endpoint docs with example response showing exact model IDs (note: format changed over time, newer models may not have date stamps)
