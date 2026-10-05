# Research: OpenAI Responses API support in Kiln (via LiteLLM)

## Bottom Line

**The justification is partly true.** "We can't set thinking level through Chat Completions" is false as stated. For every OpenAI reasoning model Kiln lists, Chat Completions accepts `reasoning_effort` when the request has no function tools. The claim is true for some specific cases. (1) Reasoning plus function tools on GPT-5.4 and newer, on OpenAI direct and Azure, gets an HTTP 400. GPT-6 Astra and GPT-6.1 Sol can't call tools on Chat Completions at all. (2) Some effort values only work on Responses. Kiln's own testing found `max` on GPT-6.1 Sol is one. (3) Pro models are Responses-only. (4) Chat Completions never returns reasoning text. Even with the effort set, OpenAI-direct runs show no thinking. OpenRouter is not affected.

**The adapter change can be small, and it fits your constraints.** LiteLLM 1.102 already sends some calls to `/v1/responses`. It does this for pro models, and for GPT-5.4+ calls with function tools and reasoning on. The reason Kiln turned function calling off on nine GPT-5.4+ OpenAI models was that LiteLLM didn't do this routing yet. That reason no longer holds at the pinned version. This is based on reading the source and running Kiln against a local fake server. No paid run has confirmed it.

**Recommended path ("Option A"):** add one opt-in field to `KilnModelProvider`, for example `openai_responses_api: bool`, limited to openai and azure_openai. When it's set, `LiteLlmAdapter` uses the model id `openai/responses/<model>`. That forces LiteLLM's built-in translation from Chat Completions to Responses, while Kiln keeps working with chat-shaped objects. Kiln also needs to ask for a reasoning summary and decide on `store`. And it must fix one existing bug: `acompletion_checking_response` reads only `choices[0]`. Estimated effort is 1–2 days plus a paid test pass. `BaseAdapter`, the trace format, streaming and the tool loops stay as they are.

## Key Findings

- **OpenAI restricts reasoning plus tools on Chat Completions from GPT-5.4 on.** The migration guide says: "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`". Users have reported the 400 for GPT-5.4, 5.5, 5.6, 6 Sol, 6 Astra and 6.1 Sol. From GPT-5.5 on, leaving the effort unset still fails, because those models reason by default. GPT-6.1 Sol has no workaround, since it also rejects `none`. ([Responses vs Chat Completions](./responses-vs-chat-completions/summary.md), [Justification check](./justification-check/summary.md))
- **Both APIs accept the same effort values; the reasoning features differ.** The SDK uses one enum (`none`…`max`) for both. Some features exist only in Responses: reasoning summaries, encrypted reasoning items for stateless multi-turn, `reasoning.mode: "pro"` (which replaces the separate pro model ids), `reasoning.context`, and changing the effort mid-conversation. ([Responses vs Chat Completions](./responses-vs-chat-completions/summary.md))
- **Chat Completions is not deprecated, but new reasoning features are going only to Responses.** It has no shutdown date. OpenAI recommends Responses for new projects. ([Responses vs Chat Completions](./responses-vs-chat-completions/summary.md))
- **Kiln already reaches Responses without meaning to.** LiteLLM switches a `completion()` call to `/v1/responses` in four cases: (a) the model map marks the model as Responses-only, which covers `gpt-5.4-pro` and `gpt-5.2-pro`; (b) the model id has a `responses/` prefix; (c) a process-wide flag is set; (d) the model is GPT-5.4+ or GPT-6 on openai or azure, and the call has a function tool with reasoning on. ([LiteLLM Responses support](./litellm-responses-support/summary.md))
- **Kiln's adapter works through that routing.** Kiln ran against a local fake server through LiteLLM's translation layer. Tool loops, structured output (both modes), usage, cost, reasoning capture and streaming all came through in chat shape. ([Kiln adapter integration](./kiln-adapter-integration/summary.md))
- **One real bug: tool calls dropped after preamble text, non-streaming only.** When a model writes text and calls a tool in the same reply, LiteLLM returns two choices. Kiln reads only `choices[0]`, so it returns the text as the final answer and never runs the tool. Streaming merges the two and works. Kiln's side of the fix is a few lines. This probably already affects the pro models today. Upstream issue #43316 is closed, but the code is unchanged through LiteLLM 1.105.0rc1. ([Kiln adapter integration](./kiln-adapter-integration/summary.md), [LiteLLM Responses support](./litellm-responses-support/summary.md))
- **Gaps in LiteLLM's translation at 1.102:**
  - No reasoning summary unless Kiln asks for one.
  - `store` is never set, so OpenAI's default of storing for 30 days applies.
  - `logprobs` is dropped. This doesn't matter in practice: no Kiln GPT-5.x/6 entry supports logprobs, and reasoning blocks logprobs in both APIs anyway.
  - `verbosity` is dropped. Fixed in 1.104.
  - The streaming path drops encrypted reasoning items between tool calls.
  - Tools are sent with `strict: null`.

  ([LiteLLM Responses support](./litellm-responses-support/summary.md))
- **LiteLLM sometimes drops the effort without any error.** Kiln sends `drop_params=True`, and LiteLLM's model map decides which values each model accepts. If the remote map download fails, LiteLLM falls back to its bundled copy. That copy has no GPT-6 entries, so Kiln's "Extra High" quietly becomes the model's default (LiteLLM #40471). The map is downloaded each time the app starts, so which models get routed to Responses can change without a LiteLLM upgrade. ([LiteLLM Responses support](./litellm-responses-support/summary.md), [Justification check](./justification-check/summary.md))
- **Calling `litellm.aresponses()` directly ("Option B") costs about 10 times as much.** It would take an estimated 1.5–3 weeks. Kiln would have to rebuild the request translation, the output translation and the conversion of stream events into chat chunks. Kiln needs those chunks because `BaseAdapter.invoke_openai_stream` publicly yields `ModelResponseStream`. ([Kiln adapter integration](./kiln-adapter-integration/summary.md))

## Implications

- **Which models to opt in:** OpenAI-direct GPT-5.4+ and GPT-6, with function calling turned back on. Also add `max` back to GPT-6.1 Sol. Pro models that LiteLLM's map doesn't know (for example `gpt-6-sol-pro`) can then be added on OpenAI direct. Leave OpenRouter, the o-series and GPT-5.2 and older on Chat Completions.
- **A cheaper first step ("Option 0"):** remove `supports_function_calling=False` and rely on LiteLLM's automatic routing. It takes under half a day. It fixes reasoning plus tools, but nothing else. It also exposes more models to the preamble bug, so fix `choices[0]` first.
- **Decisions to design:**
  - `store` — set `store: false` plus `include: ["reasoning.encrypted_content"]` to stay stateless, or accept the 30-day storage default.
  - Summary level.
  - Whether to keep encrypted reasoning in streaming tool loops. That needs a small helper.
  - Whether `strict` should be explicit on tools.
- **Azure:** Kiln has no Azure GPT-5.4+ entries today, so nothing breaks there now. If they are added, a custom deployment name needs the `azure/responses/` prefix, because LiteLLM's automatic routing matches on the model name.
- **Tests:** existing unit tests that mock `acompletion` keep working, because LiteLLM's routing happens below that call. Two kinds of tests should be added:
  - A fake-server test that catches LiteLLM regressions on upgrade.
  - Paid tool-call and thinking-level tests for each opted-in model.
- **Paid thinking-level test:** it probably fails today for OpenAI direct, because Chat Completions returns no reasoning text. This is inferred, not run. Requesting a summary through the Responses route should fix it.

## Conflicts and Uncertainty

- **Do OpenAI's own pages agree on GPT-5.4–5.6?** The model pages for those models list Chat Completions function calling as "Supported" with no caveat. Only the migration guide's "Starting with GPT-5.4" sentence and many field reports of the 400 establish the restriction. The evidence leans clearly toward the restriction being real.
- **Are GPT-5.2 and older affected?** OpenAI says the restriction starts at GPT-5.4. One issue (ruby_llm#785) claims gpt-5, 5.1, 5.2 and the o-series also fail. Nothing else backs it up. Kiln keeps function calling on for these models. The evidence leans toward them not being affected.
- **Default effort on GPT-5.4.** OpenAI's model page and LiteLLM's map both say `none`. LiteLLM's routing check assumes unset means `medium` on every GPT-5.4+ model. A third-party test also says that leaving effort unset doesn't trigger the 400 on 5.4. So 5.4 probably defaults to `none` and 5.5+ to `medium`. The only effect is that LiteLLM sends some 5.4 tool calls to Responses when it doesn't need to.
- **GPT-5.5 + `minimal`.** LiteLLM's docs table lists `minimal` for GPT-5.5. The OpenAI model page doesn't, and LiteLLM's map marks it unsupported. LiteLLM drops it without an error. The OpenAI page sides with the map, so LiteLLM's docs table is wrong.
- **`max` on Chat Completions changes by model and over time.** A third-party test (Sept 2026) says GPT-6 Astra and GPT-5.6 Sol accept it now. Kiln's commit of 2026-10-01 says GPT-6.1 Sol rejects it. Azure says `max` works only on Responses. Kiln offers `max` on OpenAI-direct GPT-6 Astra, Sol and Luna, and no paid run proves those work.
- **Does Chat Completions store responses?** The adapter research assumed it doesn't. OpenAI's migration guide says Chat Completions are "stored by default for new accounts" too. So switching may not change retention for every account.
- **OpenRouter.** Kiln's comment says OpenRouter drops a bare `reasoning_effort` when tools are present. No public source confirms this, and the offline probe could not reproduce it.

## Gaps

- **No paid calls were made.** Every LiteLLM and Kiln behaviour was checked against a local fake server. A paid run on OpenAI direct is needed to confirm these things:
  - LiteLLM's routing fixes reasoning plus tools for real.
  - Real models write a preamble and a tool call in one non-streaming reply.
  - How OpenAI treats `strict: null` on tools.
  - Whether OpenAI accepts `summary` with effort `none`.
  - Which `max` values Chat Completions accepts.
- **OpenAI docs were read only through Tavily extract.** The proxy blocks developers.openai.com. The check marks in the migration guide's capability table were lost, so "reasoning summaries are Responses-only" comes from the SDK types, not from that table. The o3 and o4-mini effort lists were not read.
- **Azure routing was not tested end to end.** The fake-server probe only showed which URL was hit; the fake reply failed to parse.
- **Kiln's current paid thinking-level results for OpenAI are unknown.** Nobody could tell whether those tests fail today or simply haven't been run.
- **Upstream close reason for LiteLLM #43316** was not visible. Kiln should plan to fix the preamble bug itself.
- **Refusal handling was not checked.** Nobody verified whether Responses refusal content maps to `message.refusal`.

## Subtopics

- **[Responses vs Chat Completions](./responses-vs-chat-completions/summary.md)** — OpenAI API semantics. Both APIs accept the same effort values. Reasoning plus tools on GPT-5.4+, pro models, summaries and encrypted reasoning work only on Responses. Chat Completions is supported but no longer gets the new reasoning features.
- **[LiteLLM Responses support](./litellm-responses-support/summary.md)** — LiteLLM 1.102 sends pro models and GPT-5.4+ tools-with-reasoning calls to Responses on its own. The `openai/responses/` prefix forces this for any model. It returns chat-shaped objects, with known gaps: two choices after a preamble, no summary by default, no `store`, no logprobs. Moving within the current pin (1.102.0 → 1.102.2) changes nothing.
- **[Kiln adapter integration](./kiln-adapter-integration/summary.md)** — Kiln ran unchanged through LiteLLM's translation against a fake server. Recommends a per-model flag that forces the `responses/` prefix (1–2 days) over calling `aresponses()` directly (1.5–3 weeks).
- **[Justification check](./justification-check/summary.md)** — partly true. Effort works on Chat Completions without tools, but fails with tools on GPT-5.4+, for some `max` values and for pro models. Chat Completions never returns reasoning text. Kiln's model list already documents two of these failures in comments.
