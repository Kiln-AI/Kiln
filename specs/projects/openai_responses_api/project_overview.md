---
status: complete
---

# OpenAI Responses API for newer OpenAI models

OpenAI rejects function calling together with a reasoning effort on `/v1/chat/completions` for GPT-5.4 and newer. GPT-6 Astra, GPT-6.1 Sol and GPT-6.1 Terra reject tools on Chat Completions at any effort. OpenAI treats this as policy, not a bug. We worked around it in April 2026 by setting `supports_function_calling=False` on our OpenAI-direct providers for these models, so users can't attach tools to them. This applies to all newer OpenAI models, and every new one will have the same limit.

LiteLLM now routes these calls to `/v1/responses` itself, through its chat-to-responses conversion layer. That is the same design we use for our other 200+ models, so we keep it. No native Responses path and no Kiln provider routing flag: we let LiteLLM own the routing and upgrade it.

Research behind these decisions: [specs/research/openai-responses-api/summary.md](../../research/openai-responses-api/summary.md).

## Scope

1. **Upgrade LiteLLM** to the latest stable 1.106.x. Our pinned 1.102 drops a tool call when a reply also has text (fixed in 1.103.5), and invents reasoning ids that OpenAI rejects (fixed in 1.106.0). Keep the tight-range policy of pinning to one tested minor version. Run the full paid test suite across all models, not just OpenAI, because this is four minor versions of change.
2. **Send `store: false`** on OpenAI-direct calls. Responses stores requests for at least 30 days by default, while Chat Completions does not, so moving to Responses would quietly change retention.
3. **Turn tools back on** for the ten OpenAI-direct providers: GPT-5.4, GPT-5.5, GPT-5.6 Sol / Terra / Luna, GPT-6 Astra / Sol / Luna, and GPT-6.1 Sol / Terra. Push the remote model list update only after the app release with the LiteLLM upgrade is live. Older apps get an upgrade prompt. No existing run config can have tools on these models today, so nothing existing changes.
4. **Hide the `max` thinking level** on GPT-6 Astra, Sol and Luna for OpenAI direct. Chat Completions rejects `max`, and LiteLLM only switches to Responses when tools are attached, so a `max` run without tools fails. We already hide `max` on GPT-6.1 Sol and Terra for the same reason. Add a comment in `ml_model_list.py` explaining why.
5. **Reasoning summaries: off by default**, with a setting on the OpenAI setup screen to turn them on. OpenAI returns a 400 if the user's OpenAI organization isn't verified, so the setting must say it needs organization verification. When it's on, request reasoning summaries for the GPT-5.4+ and GPT-6 OpenAI-direct models; LiteLLM routes those calls to Responses by itself. Handle summaries that arrive in several parts when streaming.
6. **Check GPT-6.1 Terra with tools at `none`** with one paid call. LiteLLM keeps that call on Chat Completions, which OpenAI says this model doesn't allow. If it fails, remove `none` from GPT-6.1 Terra's OpenAI-direct thinking levels.

## Out of scope

- **Keeping reasoning across turns** (saved conversations, `return_on_tool_call` resume, the streaming tool loop). This is a separate project. Its handoff prompt is at [specs/research/openai-responses-api/handoff_reasoning_across_turns.md](../../research/openai-responses-api/handoff_reasoning_across_turns.md).
- **Routing tool-less `max` calls to Responses.** That waits until LiteLLM handles it.
- **A native `litellm.aresponses()` path or a Kiln provider routing flag.**
