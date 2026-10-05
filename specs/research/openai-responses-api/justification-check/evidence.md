# Evidence: Where Chat Completions Reasoning Control Breaks

These are web sources fetched on 2026-10-05. OpenAI docs and third-party blogs were read through Tavily extract, because the session proxy blocks `developers.openai.com`. Each claim is quoted. Where I infer something, I label it as an inference.

## 1. The baseline: Chat Completions does take `reasoning_effort`

- OpenAI reasoning guide ([developers.openai.com/api/docs/guides/reasoning](https://developers.openai.com/api/docs/guides/reasoning)): "Supported values are model-dependent and can include `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and `max`." It also says: "Setting `reasoning.effort` (Responses) or `reasoning_effort` (Chat Completions) to `none` returns HTTP 400." That sentence names both APIs as places where effort is set.
- The "Using GPT-6" guide ([developers.openai.com/api/docs/guides/latest-model](https://developers.openai.com/api/docs/guides/latest-model)) says: "Use `reasoning.effort` in Responses or `reasoning_effort` in Chat Completions." It also says: "GPT-6 Astra and GPT-6.1 Sol support Chat Completions, but tool calling requires Responses."
- Third-party measurement ([synthorai.io, "GPT-6 Astra Reasoning Effort"](https://synthorai.io/blog/gpt-6-astra-reasoning-effort), Sept 2026) on `/v1/chat/completions`: `low` through `max` return 200 on GPT-6 Astra and on GPT-5.6 Sol. `minimal` returns 400 on both. `none` returns 200 on both, even though the docs say Astra rejects it.
- OpenRouter ([reasoning-tokens docs](https://openrouter.ai/docs/use-cases/reasoning-tokens), fetched 2026-10-05) gives Chat Completions callers `reasoning: {"effort": ...}` with "`max`, `xhigh`, `high`, `medium`, `low`, `minimal` or `none` (OpenAI-style)". Its live `/api/v1/models` lists `reasoning`, `reasoning_effort` and `tools` as supported parameters for every GPT-5.x and GPT-6 model.

**So the literal claim is false.** For every current OpenAI reasoning model Kiln lists, Chat Completions accepts an effort level, as long as the request has no function tools.

## 2. Hard break: function tools + reasoning on GPT-5.4 and newer (OpenAI direct and Azure)

Official statements:

- Migration guide ([migrate-to-responses](https://developers.openai.com/api/docs/guides/migrate-to-responses)): "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`."
- Reasoning guide: "Use the Responses API for function calling. Chat Completions does not support function calling with GPT-6 Astra or GPT-6.1 Sol."
- GPT-6 Sol model page ([models/gpt-6-sol](https://developers.openai.com/api/docs/models/gpt-6-sol)): "Chat Completions supports function calling only with `reasoning_effort` set to `none`."
- GPT-6.1 Sol model page ([models/gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)): "Use the Responses API for tool calling. Chat Completions is supported without tool calling." The page also says: "The `none` and `minimal` reasoning efforts are not supported." So there is no workaround on Chat Completions for this model.
- Azure ([Azure OpenAI reasoning models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning)): "The `gpt-5.6` models support the Chat Completions API and tools, but can't combine reasoning with tools on Chat Completions." Also: "With GPT-5.6 models on the Chat Completions API, `none` is the only value you can combine with function tools."

Error messages as reported in the wild (verbatim):

- GPT-5.4, March 2026: `Function tools with reasoning_effort are not supported for gpt-5.4 in /v1/chat/completions. Please use /v1/responses instead.` Sources: [TradingAgents #403](https://github.com/TauricResearch/TradingAgents/issues/403), [pipecat #4043](https://github.com/pipecat-ai/pipecat/issues/4043).
- GPT-5.6 and GPT-6, July to Sept 2026: `Function tools with reasoning_effort are not supported for gpt-5.6-sol in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.` Sources: [OpenAI community thread](https://community.openai.com/t/gpt-5-6-chat-completion-reasoning-effort-bug-behavior-change/1386454), [LiteLLM #33221](https://github.com/BerriAI/litellm/issues/33221), [CrewAI forum](https://community.crewai.com/t/bug-report-openai-5-6-family-fails-all-tool-calling-via-native-openai-provider/7648), [LibreChat #14355](https://github.com/danny-avila/LibreChat/issues/14355).
- GPT-6 Astra: the same message with `gpt-6-astra` ([oh-my-pi #11052](https://github.com/can1357/oh-my-pi/issues/11052), Azure chat route).
- GPT-6.1 Sol has no escape hatch. One user tried both options ([frigate discussion #24555](https://github.com/blakeblackshear/frigate/discussions/24555)): `Unsupported value: 'reasoning_effort' does not support 'none' with this model. Supported values are: 'low', 'medium', 'high', and 'xhigh'.` and then `Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions.`

Important details:

- **Unset effort still fails.** GPT-5.6 and GPT-6 reason by default. A tools request that omits `reasoning_effort` still gets the 400 (LiteLLM #33221: "even without explicitly setting reasoning_effort"; LibreChat #14355). An OpenAI support reply on 2026-09-07 in the community thread: "Responses supports the tool workflow, but we haven't confirmed a fix for this exact Chat Completions combination." The thread was then closed.
- **Requests without tools are not affected.** Frigate: "Descriptions work fine since they don't use tools." The GPT-6 guide: "Chat Completions supports requests without tools."
- **Older models are fine.** OpenAI says the restriction starts at GPT-5.4. Kiln's own entries for GPT-5.2, 5.1, 5 and the o-series keep function calling on.
- **Silent drop variant.** LiteLLM [#23914](https://github.com/BerriAI/litellm/issues/23914) (Mar 2026): on Azure GPT-5.4, LiteLLM with `drop_params=True` "silently dropped" `reasoning_effort` when tools were present, giving `reasoning_tokens: 0`. Azure was then added to LiteLLM's auto-bridge. The installed 1.102.0 has a comment in `llms/azure/chat/gpt_5_transformation.py`: "Azure gpt-5.4+ with tools + reasoning_effort is now routed to the Responses API bridge".

## 3. `max` effort on Chat Completions: inconsistent across models and over time

- Azure doc: "`max` works only with GPT-6 or GPT-5.6 models and the Responses API."
- Kiln commit `1aed843a` (2026-10-01) says `gpt-6.1-sol` on OpenAI direct rejects `max` on `/v1/chat/completions` with a 400, while `/v1/responses` accepts it.
- synthorai (Sept 2026) on OpenAI direct: "In July, `reasoning_effort: "max"` returned 400 on GPT-5.6 Sol through Chat Completions. It is accepted now". Their table shows `max` → 200 on GPT-6 Astra via Chat Completions.
- LiteLLM [#38084](https://github.com/BerriAI/litellm/issues/38084) (Aug 2026), "case A": without conversion LiteLLM forwards `max` verbatim, "where OpenAI's chat-completions surface then rejects it with a 400 listing its accepted values". The model is not named in the extract I read.

Reading: whether `max` works on Chat Completions depends on the model and has changed over time. It is Responses-only on Azure, and was Responses-only on gpt-6.1-sol as of 2026-10-01 per Kiln's own test. Kiln exposes `max` on OpenAI-direct GPT-6 Astra, Sol and Luna. I found no Kiln record of a paid run that proves those values work.

## 4. Pro models are Responses-only

- GPT-5.4 Pro model page ([models/gpt-5.4-pro](https://developers.openai.com/api/docs/models/gpt-5.4-pro)): "GPT-5.4 Pro is available in the Responses API only to enable support for multi-turn model interactions before responding to API requests". It also says: "Reasoning.effort supports: medium (default), high and xhigh." Note that the same page lists "Structured outputs: Not supported", while Kiln sets `json_schema` for this model.
- LiteLLM's model map marks `gpt-5-pro`, `gpt-5.2-pro`, `gpt-5.4-pro`, `gpt-5.5-pro`, `o1-pro`, `o3-pro` and all `*-codex` models as `mode: "responses"`. `completion()` bridges them automatically (see [kiln-current-behaviour.md](./kiln-current-behaviour.md), section "LiteLLM already auto-routes the failing case to Responses"). So Kiln's GPT-5.4 Pro and GPT-5.2 Pro OpenAI entries already reach the Responses API today, thinking level included.
- OpenRouter has a `reasoning.mode: "pro"` switch: "only supported by OpenAI GPT-5.6 and newer, when served by OpenAI or Azure". OpenRouter also lists the `*-pro` slugs as normal Chat Completions models. On OpenRouter, pro models are reachable from Chat Completions.

## 5. Reasoning text is not returned by Chat Completions

- synthorai measured GPT-6 Astra at `medium` effort. Over `/v1/chat/completions`, reasoning tokens were billed (76, 75, 120) but no reasoning text came back: "none; the message carries `role` and `content` only". Over `/v1/responses` with `reasoning.summary: "auto"`, they got "a `reasoning` item with a 277 to 352 character summary".
- The OpenAI migration guide's capability table has a "Reasoning summaries" row. The checkmarks did not survive extraction, so I could not read which column has the tick. The reasoning guide's summary examples all use `client.responses.create(... reasoning.summary ...)`.
- The migration guide says encrypted reasoning items (needed to carry reasoning across stateless turns) are a Responses feature: "OpenAI offers encrypted reasoning items, allowing you to keep your workflow stateless while still benefiting from reasoning items."

Inference: for OpenAI direct, Chat Completions can **set** the effort but cannot **show** any reasoning. Kiln's UI and trace would show no thinking for OpenAI models. The paid thinking-level test would fail its "reasoning content present" check for OpenAI direct. OpenRouter is different: it returns `reasoning` / `reasoning_details` on Chat Completions for OpenAI models.

## 6. Structured output + reasoning on Chat Completions works

- synthorai: "`response_format` with a strict JSON schema returns schema-valid output on both" (GPT-6 Astra and GPT-5.6 Sol). The GPT-6 Sol and 6.1 Sol model pages list "Structured outputs: Supported".
- The only structured-output risk is Kiln's `function_calling` structured output mode. It sends a forced function tool, so on GPT-5.4+ OpenAI direct it falls under the tools restriction in section 2. Kiln sets `json_schema` for all of these entries, so this only bites if a user overrides the mode. (Inference from Kiln's `tool_call_params()`; not tested.)

## 7. Parameters that become incompatible once reasoning is on (Chat Completions and Responses)

GPT-6 guide: "When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`. For Chat Completions, also remove `logprobs`." This applies to both APIs, so it is not a reason to switch. It does mean Kiln's logprobs features can't be combined with reasoning on these models, whichever API is used.

## 8. OpenRouter: the restriction does not apply

- Kiln enables function calling on every OpenRouter GPT-5.x/6 entry and sends the `reasoning` object.
- The OpenRouter docs suggest OpenRouter talks to OpenAI through Responses upstream. They say "a Chat Completions or Messages API update sent to an OpenAI model becomes a Responses `configuration_update` item". The tool restriction is OpenAI's Chat Completions endpoint behaviour, so it does not reach OpenRouter callers. (Inference; I found no explicit OpenRouter statement on reasoning + tools for GPT-5.4+.)
- Kiln's comment that the bare `reasoning_effort` "is silently dropped on tool calls for these models" on OpenRouter has no public source I could find. Kiln presumably found it in testing. One possible contributor at the LiteLLM layer: `OpenrouterConfig` only advertises `reasoning_effort` when `litellm.supports_reasoning(model)` is true, and Kiln sets `drop_params=True`. In my probe with the current map, though, `reasoning_effort` survived for `openrouter/openai/gpt-6-sol`, so I could not reproduce a drop offline.

## 9. Azure and other OpenAI-model hosts in Kiln

- Azure OpenAI in Kiln has o1, o3, o3-mini and o4-mini (one fixed level each) plus GPT-4.x. o-series models accept `reasoning_effort` on Azure Chat Completions. The LiteLLM probe shows `azure o3 high → reasoning_effort: high`, and no source reports a tools restriction before GPT-5.4. None of the breakages above affect Kiln's current Azure entries. They would apply as soon as Kiln adds Azure GPT-5.4+ or GPT-6 deployments.
- The gpt-oss models (Groq, Cerebras, Fireworks, Ollama, OpenRouter, Featherless) have no thinking levels in Kiln and are served by OpenAI-compatible third-party Chat Completions APIs. They are out of scope for the Responses question.
