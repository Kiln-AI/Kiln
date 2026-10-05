# Research Plan: OpenAI Responses API support in Kiln (via LiteLLM)

## Goal

Decide what it would take for Kiln to call OpenAI's Responses API for select providers/models, still through LiteLLM and ideally contained inside `LiteLlmAdapter` (no change to the `BaseAdapter` API). Also fact-check the stated motivation: "we use the Chat Completions API today and can't set thinking level through it." Note: Kiln's adapter already sends `reasoning_effort` / `reasoning: {effort}` on chat completions (`libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py` ~L569-600), so the real question is which models/providers/feature combinations that fails for.

## Run

- Model: Opus (same model as the session; not a frontier-tier step-down case)
- Kiln pins `litellm>=1.102.0,<1.103` (`libs/core/pyproject.toml`)

## Subtopics

- [x] Responses API vs Chat Completions — what Responses offers that Chat Completions doesn't, with emphasis on reasoning/thinking control
- [ ] LiteLLM Responses support — `litellm.responses()`, provider coverage, bridges, and gaps at the pinned version
- [ ] Kiln adapter integration — where a Responses path fits in `LiteLlmAdapter`, what must be mapped, and the effort
- [ ] Justification check — does "can't set thinking level via Completions" hold, for which models/providers

## Focus Details

### Responses API vs Chat Completions

Read OpenAI's primary docs (https://developers.openai.com/api/reference/responses/overview, migration guide, reasoning guide, model pages). Answer: how reasoning is controlled in each API (`reasoning_effort` vs `reasoning: {effort, summary}`), which effort values exist and which models accept them; which models or features are Responses-only (e.g. pro models, reasoning summaries, encrypted reasoning items carried across turns, reasoning + function tools on newer GPT-5.x models, built-in tools); structured output, tool calling, logprobs, streaming event shape, usage/token reporting differences; statefulness (`previous_response_id`, `store`) and whether stateless use is fully supported. Is OpenAI deprecating or freezing Chat Completions? Out of scope: LiteLLM behaviour (subtopic 2), Kiln code (subtopic 3).

### LiteLLM Responses support

Read https://docs.litellm.ai/docs/response_api, LiteLLM source and release notes/GitHub issues. Answer: the `litellm.responses()` / `aresponses()` signature and return types; which providers it natively supports (OpenAI, Azure, OpenRouter, others) vs which go through LiteLLM's chat-completions bridge; the reverse bridge — does `litellm.completion()` already auto-route some OpenAI models (e.g. `-pro`, codex) to `/v1/responses`, and is there a flag/prefix (e.g. `openai/responses/...`) to force a model through Responses while keeping the chat-completions interface? How does `reasoning_effort` on `completion()` get translated for OpenAI models, and does LiteLLM drop or reject it in any case (e.g. with tools)? Streaming, tool calls, structured output (`text.format` / `response_format`), cost tracking, usage. What exists in litellm 1.102.x vs later versions; known bugs. Out of scope: OpenAI API semantics themselves (subtopic 1), Kiln code (subtopic 3).

### Kiln adapter integration

Mainly codebase investigation of this repo, with web checks of LiteLLM types as needed. Read `libs/core/kiln_ai/adapters/model_adapters/litellm_adapter.py`, `base_adapter.py`, `adapter_stream.py`, `litellm_config.py`, `ml_model_list.py` (provider/model config, thinking-level fields), and related tests. Answer: every place the adapter depends on the chat-completions shape (message building, tool-call loop, structured output modes, logprobs, streaming, usage/cost, reasoning-content capture, prompt caching, multi-turn / trace saving); what a Responses code path inside `LiteLlmAdapter` would need to translate in and out; how per-model opt-in could be expressed (e.g. a flag on `KilnModelProvider`) without touching `BaseAdapter`; whether "use LiteLLM's own completion→responses bridge" is a smaller change than calling `litellm.responses()` directly; test impact and rough effort. Produce a concrete option comparison. Out of scope: external API semantics beyond what's needed (subtopics 1-2).

### Justification check

Verify the claim "we can't set thinking level through Chat Completions". Check, per relevant provider in Kiln (OpenAI, Azure OpenAI, OpenRouter, and any other OpenAI-model hosts Kiln lists), whether chat completions accepts reasoning effort for current OpenAI reasoning models (GPT-5.x family, o-series, pro/codex variants), including edge cases: effort values like `none`/`minimal`/`xhigh`, reasoning combined with function tools or structured output, and Responses-only models. Look at Kiln's existing paid test `libs/core/kiln_ai/adapters/model_adapters/test_thinking_level_paid.py` and model list to see what Kiln already does, then find primary-source evidence (OpenAI docs, error messages reported in GitHub issues/forums) of where it breaks. Verdict: true / partly true / false, with the precise cases. Out of scope: designing the integration (subtopic 3).
