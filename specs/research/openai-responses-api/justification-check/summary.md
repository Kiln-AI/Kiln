# Justification Check: "We can't set thinking level through Chat Completions"

## Bottom Line

**Partly true. As literally stated, it's false.** Chat Completions accepts `reasoning_effort` for every OpenAI reasoning model Kiln lists, on OpenAI, Azure and OpenRouter, and Kiln already sends it. Without tools it works.

Two things actually break on OpenAI direct and Azure:
1. **Reasoning plus function tools on GPT-5.4 and newer** (5.4, 5.5, the 5.6 family, GPT-6). Any effort other than `none` gets a 400. GPT-6 Astra and GPT-6.1 Sol can't use `none`, so tools are impossible on them.
2. **Seeing the reasoning.** Chat Completions returns no reasoning text or summary for OpenAI models. Summaries and encrypted reasoning items are Responses-only.

Smaller cases: `max` is Responses-only on Azure and was Responses-only on gpt-6.1-sol in Kiln's own test. Pro models are Responses-only, but LiteLLM already bridges them.

So the real reason to use Responses is "tools plus thinking on new OpenAI models, and visible thinking". Setting the level alone already works. The pinned LiteLLM 1.102.0 already auto-routes tools plus reasoning on GPT-5.4+ to Responses inside `completion()`. Evaluate that cheaper route before Kiln calls Responses itself.

## Key Findings

- **Chat Completions takes effort for all current models.** OpenAI's guides name `reasoning_effort` (Chat Completions) next to `reasoning.effort` (Responses). Third-party tests got 200 for `low` through `max` on GPT-6 Astra and GPT-5.6 Sol. Sources: [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model), [synthorai](https://synthorai.io/blog/gpt-6-astra-reasoning-effort).
- **Tools plus reasoning on GPT-5.4+ is a hard 400 on OpenAI direct and Azure.** OpenAI: "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`." It fires even when effort is unset, because the models reason by default. Sources: [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses), [community thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454), [Azure doc](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning), [LiteLLM #33221](https://github.com/BerriAI/litellm/issues/33221).
- **GPT-6 Astra and GPT-6.1 Sol can't call tools on Chat Completions at all.** They reject `none`. GPT-6 Sol and Luna can call tools only with `none`. Sources: [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [frigate #24555](https://github.com/blakeblackshear/frigate/discussions/24555).
- **Kiln already works around the tools case by turning tools off.** OpenAI-direct GPT-5.4+ entries have `supports_function_calling=False` ("until Kiln routes these models to /v1/responses"). Source: `ml_model_list.py`.
- **`max` is unreliable on Chat Completions.** Azure says Responses-only. Kiln measured a 400 on gpt-6.1-sol (2026-10-01). A third-party source saw GPT-5.6 Sol go from rejected to accepted, and Astra accept it. Kiln offers `max` on OpenAI-direct GPT-6 Astra, Sol and Luna without a recorded check.
- **Reasoning text is invisible on Chat Completions (OpenAI direct).** Reasoning tokens are billed, but "the message carries `role` and `content` only". By inference, Kiln shows no thinking for OpenAI-direct models, and `test_thinking_level_paid.py` should fail its "reasoning present" check for OpenAI.
- **Pro and codex models are Responses-only but already handled.** LiteLLM's map marks them `mode: responses`, and `completion()` bridges them. Source: [gpt-5.4-pro](https://developers.openai.com/api/docs/models/gpt-5.4-pro).
- **LiteLLM 1.102.0 already bridges tools plus reasoning on GPT-5.4+ and gpt-6\* (openai/azure).** Confirmed by offline probe. Kiln's workaround may be out of date. Source: [LiteLLM #23914](https://github.com/BerriAI/litellm/issues/23914).
- **`drop_params=True` causes silent drops.** `xhigh` is dropped when LiteLLM's map lacks the flag ([#40471](https://github.com/BerriAI/litellm/issues/40471)); the bundled map lacks gpt-6-sol, gpt-6-luna and gpt-6.1-sol. OpenRouter rewrites bare `max` to `xhigh`.
- **Not affected:** OpenRouter (effort plus tools work), Kiln's Azure entries (o-series and GPT-4.x), and `json_schema` structured output.

## Precise Verdict Matrix (OpenAI direct, Chat Completions)

| Case | Works on Chat Completions? |
|---|---|
| Effort, no tools, any listed GPT-5.x/6/o-series model | Yes |
| `none` / `minimal` | Depends on the model, and is the same on both APIs |
| `xhigh` | Yes, but LiteLLM may drop it silently if its map lacks the flag |
| `max` | Unreliable: Responses-only on Azure; 400 on gpt-6.1-sol (2026-10-01) |
| Effort + tools, GPT-5.2 and older, o-series | Yes |
| Effort + tools, GPT-5.4/5.5/5.6/GPT-6 Sol/Luna | No (only `none` works) |
| Any tools, GPT-6 Astra / 6.1 Sol | No |
| Pro / codex models | No, but LiteLLM bridges them automatically |
| Reasoning text returned | No (OpenAI direct) |
| Effort + `response_format` json_schema | Yes |

## Details
- [kiln-current-behaviour.md](./kiln-current-behaviour.md): Kiln's code path, the model catalogue and its workarounds, paid-test coverage, LiteLLM probes.
- [evidence.md](./evidence.md): verbatim quotes and error messages per case.

## Open Questions / Gaps
- No paid calls were made. `max` on gpt-6-astra/sol/luna and the OpenAI paid-test outcome are unverified.
- Reasoning visibility rests on a third-party measurement plus OpenAI's Responses-only summary examples. The table checkmarks were lost in extraction.
- Kiln's OpenRouter "bare reasoning_effort dropped on tool calls" claim has no public source and wasn't reproduced offline.
- Kiln uses `json_schema` for GPT-5.4 Pro, but OpenAI says "Structured outputs: Not supported". Flagged for the integration subtopic.

## Sources
- OpenAI docs (fetched 2026-10-05): the [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), the [GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model), the [migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses), and the model pages for [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [gpt-6-astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and [gpt-5.4-pro](https://developers.openai.com/api/docs/models/gpt-5.4-pro).
- [Azure OpenAI reasoning models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning).
- [OpenRouter reasoning tokens docs](https://openrouter.ai/docs/use-cases/reasoning-tokens) and [models API](https://openrouter.ai/api/v1/models).
- [OpenAI community thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454) (OpenAI support reply on 2026-09-07).
- [synthorai measurements](https://synthorai.io/blog/gpt-6-astra-reasoning-effort) (Sept 2026, secondary source).
- LiteLLM issues [#33221](https://github.com/BerriAI/litellm/issues/33221), [#23914](https://github.com/BerriAI/litellm/issues/23914), [#38084](https://github.com/BerriAI/litellm/issues/38084), [#40471](https://github.com/BerriAI/litellm/issues/40471) and [#40472](https://github.com/BerriAI/litellm/issues/40472).
- Downstream reports: [TradingAgents #403](https://github.com/TauricResearch/TradingAgents/issues/403), [pipecat #4043](https://github.com/pipecat-ai/pipecat/issues/4043), [frigate #24555](https://github.com/blakeblackshear/frigate/discussions/24555), [LibreChat #14355](https://github.com/danny-avila/LibreChat/issues/14355) and [oh-my-pi #11052](https://github.com/can1357/oh-my-pi/issues/11052).
- Local: Kiln's `litellm_adapter.py`, `ml_model_list.py`, `test_thinking_level_paid.py` and commit 1aed843a; the installed litellm 1.102.0 source and bundled model map; the remote model map on LiteLLM's GitHub `main`.
