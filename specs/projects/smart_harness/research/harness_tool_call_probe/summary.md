# Research: Do Harness-Written Tool Calls Break Thinking Models?

Checked 2026-11-10. The question came from decision 4 in the [functional spec](../../functional_spec.md): when the harness, not the model, decides to call a tool, the conversation records the call the same way it would if the model had asked for it. An earlier research note claimed this breaks when thinking is on.

| File | What it is |
|---|---|
| [live_probe.md](live_probe.md) | 283 raw LiteLLM calls and 39 runs through Kiln's adapter, all through OpenRouter: 54 models Kiln lists, 20 model hosts. Includes the scripts. |
| [docs_probe.md](docs_probe.md) | What current provider, LiteLLM and OpenRouter documentation says, with quotes and links. |

## Findings

- **Through OpenRouter, the claim did not reproduce.** 129 calls had a harness-written tool call in their history. 124 succeeded. The 5 failures were routing refusals and a host outage, unrelated to the tool call. This includes Claude (Haiku 4.5, Haiku 5.5, Sonnet 4.6, 5, 5.5, Opus 5.5), Gemini 2.5 and 3.x, GPT-5.x and GPT-6, DeepSeek, Kimi, GLM, Grok and Qwen.
- **The model used the tool result** in 123 of the 124 successful calls.
- **Reasoning still came back** after the harness-written call for 47 of 52 models. For 4 of the other 5, the model's own tool call gave the same zero, so the harness-written call made no difference.
- **One model lost reasoning:** `thinkingmachines/inkling-small` returned no reasoning after a harness-written call in 8 of 8 calls, and 4 of those 8 answers were wrong. Attaching any reasoning text to the harness-written message restored it.
- **Kiln's own adapter handles the case today.** The existing path for resuming after a client-run tool call accepted a history ending in a harness-written call for all 7 models tried, streaming included.
- **Kiln already sends model-made tool calls back without their signatures** when it resumes from a stored trace. For Gemini that message has the same shape as a harness-written call.

## What the documentation adds

- Current Claude models with adaptive thinking do not require an assistant turn to start with a thinking block. Older Claude models with a manual thinking budget do.
- Google's own Gemini 3 API returns 400 for a function call with no thought signature. Google documents a placeholder value for calls the model did not generate, and LiteLLM adds it on its direct Gemini and Vertex routes.
- DeepSeek and Kimi thinking modes require reasoning text on assistant tool-call messages. LiteLLM adds a placeholder.
- On the newest Claude models, earlier messages must not be edited or removed on a later request. Appending is fine.

## Not established

- What each provider's own API does without OpenRouter in between. There were no direct Anthropic, Google or OpenAI keys. In Kiln this matters for the `anthropic`, `gemini_api`, `vertex`, `openai` and `amazon_bedrock` providers.
- Parallel harness-written calls, calls with arguments, structured output tasks, and prompt caching were not tested.
