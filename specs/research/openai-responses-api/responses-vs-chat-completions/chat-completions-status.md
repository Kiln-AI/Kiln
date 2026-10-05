# Is OpenAI deprecating or freezing Chat Completions?

**Short answer:** It is not deprecated. It has no shutdown date and is not tagged "legacy". OpenAI still ships new frontier models to it. In practice, though, it has fallen behind for reasoning models. Since GPT-5.4 (March 2026), the newest capabilities either skip Chat Completions or are blocked on it.

## Evidence that it is still supported

- [Deprecations page](https://developers.openai.com/api/docs/deprecations.md) (read 2026-10-05) lists no deprecation of `/v1/chat/completions`. The only endpoint-level API sunsets on it are the Assistants API (shut down 2026-08-26, replaced by "Responses API and Conversations API"), reusable prompts (`v1/prompts`, 2026-11-30), the Evals platform, Agent Builder and the Videos API. The page defines "legacy" as "models and endpoints that no longer receive updates". Chat Completions is not tagged that way. The docs sidebar puts Agent Builder, Evals, Fine-tuning and Assistants under "Legacy APIs", and Chat Completions is not there.
- [Migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses): "**While Chat Completions remains supported, Responses is recommended for all new projects.**" and "Chat Completions remains supported, so you can migrate one user flow at a time."
- [Reasoning guide](https://developers.openai.com/api/docs/guides/reasoning): "While the Chat Completions API is still supported, you'll get improved model intelligence and performance by using Responses."
- [Changelog](https://developers.openai.com/api/docs/changelog.md): GPT-5.4 (Mar 5, 2026), GPT-5.4 mini/nano (Mar 17) and GPT-5.5 (Apr 24) were all released "to the Chat Completions and Responses API". Every GPT-5.6 and GPT-6 model page lists Chat Completions as "Supported".
- The Chat Completions params type in `openai-python` 3.24.0 still gains new fields: `max` effort, `prompt_cache_options` and `service_tier: "fast"` ([completion_create_params.py](https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/completion_create_params.py)).
- OpenAI's stated policy at the Responses launch ([New tools for building agents](https://openai.com/index/new-tools-for-building-agents/), March 2025): "Chat Completions remains our most widely adopted API, and we're fully committed to supporting it with new models and capabilities. Developers who don't require built-in tools can confidently continue using Chat Completions. We'll keep releasing new models to Chat Completions whenever their capabilities don't depend on built-in tools or multiple model calls."

## Evidence of functional erosion (the "frozen in practice" side)

1. **Pro models and pro mode are Responses-only.** These are gpt-5-pro, gpt-5.2-pro, gpt-5.4-pro, gpt-5.5-pro and o3-pro, plus `reasoning.mode: "pro"` on GPT-5.6 and GPT-6.
2. **Reasoning with function tools is blocked on Chat Completions from GPT-5.4 on.** GPT-6 Astra and GPT-6.1 Sol do not support tool calling on Chat Completions at all. This restriction goes beyond the March 2025 policy, which only promised to withhold models that need built-in tools or multiple model calls. Plain function tools are neither of those. Developers have complained in the [OpenAI forum](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454) ("Don't nanny developers"), and the thread was closed without a reversal.
3. **Reasoning features introduced since 2025 exist only in Responses.** These include reasoning summaries, encrypted reasoning items, `reasoning.context` (persisted reasoning), `configuration_update`, assistant `phase`, compaction, async tool calling, programmatic tool calling, multi-agent, mid-turn steering and WebSocket mode ([latest-model guide](https://developers.openai.com/api/docs/guides/latest-model)).
4. **OpenAI's own docs now lead with Responses.** Examples are written for Responses first. The function calling guide notes: "The Chat Completions examples use GPT-5.6 for compatibility."

## Interpretation (mine, not OpenAI's)

Nothing indicates a planned shutdown. A client that sends simple prompt-in, text-or-JSON-out requests with a reasoning effort can keep using Chat Completions for current OpenAI models. A client that needs any of the following must use Responses for OpenAI models from GPT-5.4 onward: (a) reasoning together with function or tool calls, (b) pro models or pro mode, (c) reasoning summaries, or (d) reasoning carried across turns or tool calls.
