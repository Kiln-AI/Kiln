# Research: Moving Kiln's OpenAI calls to the Responses API

## Bottom Line

The root constraint is OpenAI's, and OpenAI treats it as policy, not a bug. Starting with GPT-5.4, Chat Completions refuses function tools when `reasoning_effort` is anything but `none`. GPT-6 Astra, GPT-6.1 Sol and GPT-6.1 Terra refuse tools on Chat Completions at any effort. Kiln worked around this in April 2026 by setting `supports_function_calling=False` on ten OpenAI-direct providers. The flag only hides tools in the UI, and it was the right call at the time. Since then, two LiteLLM upgrades made for other reasons taught LiteLLM to send these tool calls to `/v1/responses` by itself through its chat-to-responses conversion layer, so on today's `main` the flag no longer guards against the 400. It still can't just be removed, for two reasons. First, at Kiln's pinned LiteLLM 1.102.x that conversion layer silently drops a tool call when the reply also contains text, and it never sets `store`, `include` or a reasoning summary. Second, released desktop builds on LiteLLM 1.87.1 read the same remote model list and would get the 400 for every `gpt-6*` model. For the spec's main choice: LiteLLM's native `aresponses()` avoids most of the conversion layer's defects, but Kiln then has to write both directions of the conversion, including the chat-chunk stream its public streaming method returns. Keeping the conversion layer keeps the chat shapes, but it needs a LiteLLM bump to at least 1.103.5 plus Kiln-side workarounds for defects that are still open upstream. Whichever path Kiln picks, other frameworks show it will have to own three decisions: which item ids to send, where reasoning lives between turns, and an explicit `store` setting.

## Key Findings

- **The rule and its scope.** OpenAI's docs say: "Starting with GPT-5.4, Chat Completions does not support tool calling with `reasoning_effort` values other than `none`." GPT-6 Astra, 6.1 Sol and 6.1 Terra need Responses for tools at any effort. OpenAI support wrote that it hasn't "confirmed a fix" for the Chat Completions case. Chat Completions isn't deprecated, but each model generation since GPT-5.4 has added features that only work on Responses: reasoning summaries, Pro models and pro mode, and passing reasoning between turns. ([OpenAI Responses API](./openai-responses-api/summary.md))
- **How the workaround went stale.** The flag was added in #1351 (2026-04-30), when Kiln's LiteLLM 1.81.16 sent all tool calls to Chat Completions. LiteLLM 1.87.1 (Kiln bump 2026-06-18) started sending gpt-5.4+ tool calls to Responses on its own. LiteLLM 1.102.0 (Kiln bump 2026-09-30) added `gpt-6*`. Neither bump PR mentions OpenAI. Today all ten providers go to `/v1/responses` with tools at any level except `none`. ([History](./history-of-the-workaround/summary.md))
- **Kiln already runs the conversion layer in production.** LiteLLM's model map marks `gpt-5.4-pro` and `gpt-5.2-pro` as Responses-only, so every Kiln call to them already goes through the conversion, with tools enabled and `store` unset. ([Adapter](./kiln-adapter-and-public-surface/summary.md), [History](./history-of-the-workaround/summary.md))
- **The worst defect is silent.** In 1.102.x, a non-streamed reply holding text plus a function call comes back as two choices. Kiln reads `choices[0]`, so the tool never runs and the narration is saved as the answer, with no error. Two subtopics reproduced this against Kiln's real adapter and a local fake server, and a LiteLLM issue reports it from production. It is fixed from LiteLLM 1.103.5 (2026-10-17), which Kiln's `<1.103` pin excludes. ([LiteLLM](./litellm-responses-support/summary.md), [Adapter](./kiln-adapter-and-public-surface/summary.md))
- **Other conversion-layer defects are still open in every version checked, up to 1.108.0rc1.**
  - Streamed reasoning summary deltas use `summary_index` as the choice index.
  - `stream_chunk_builder` drops `reasoning_items`.
  - Only the last of several consecutive reasoning items is kept.
  - Tools without `strict` go out as `"strict": null`.
  - `n`, `stop`, `seed` and `logprobs` are dropped silently.
  - Routing depends on the model name, tools, effort, base URL, and a model map that LiteLLM downloads from GitHub at import.

  ([LiteLLM](./litellm-responses-support/summary.md))
- **Automatic routing doesn't cover everything the migration is for.** Tool calls at `none` stay on Chat Completions. Tool-less calls stay there too, so automatic routing alone would not unlock the hidden `max` level or reasoning summaries. LiteLLM does have explicit routes: an `openai/responses/` model prefix and a global switch. ([LiteLLM](./litellm-responses-support/summary.md), [History](./history-of-the-workaround/summary.md))
- **Public surface: one request builder, two response readers.** `build_completion_kwargs` feeds both the non-streaming tool loop and `AdapterStream`. Each reads `choices[0]` separately, and the streaming path rebuilds its final response with `litellm.stream_chunk_builder`. A per-provider routing decision placed in the request builder reaches every adapter-based feature: runs, evals, data gen and synthetic users. Extractors, embeddings and rerankers have their own LiteLLM calls and are unaffected unless the switch is global. ([Adapter](./kiln-adapter-and-public-surface/summary.md))
- **The saved trace can't hold Responses state.** `TaskRun.trace` keeps only `content`, `reasoning_content` and `tool_calls`. Reasoning items survived between tool rounds within one run, but were gone on a `prior_trace` continuation. OpenAI also says GPT-5.4+ assistant messages should keep their `phase`, or "preambles [can] be treated as final answers". The trace has nowhere to put it. ([Adapter](./kiln-adapter-and-public-surface/summary.md), [OpenAI Responses API](./openai-responses-api/summary.md))
- **`store` changes silently with the endpoint.** Responses stores every response for at least 30 days unless `store: false` is sent. Under `store: false`, replaying a reasoning item by id alone fails with "Item with id 'rs_...' not found", so reasoning has to travel as `encrypted_content`. Nothing in Kiln or the conversion layer sets `store` today. ([OpenAI Responses API](./openai-responses-api/summary.md), [LiteLLM](./litellm-responses-support/summary.md))
- **Other frameworks' bugs were about policy, not field mapping.** Each framework that moved to Responses then fixed a long run of 400 errors about orphaned reasoning items, item ids, and `store` breaking Zero Data Retention organizations. The ones that converted a chat-shaped history at call time had the longest bug tails. The pattern they converged on:
  - send items without ids unless replaying the exact prior output;
  - send function calls as full `function_call` items with `call_id`;
  - set `store` explicitly, and use `store: false` plus encrypted reasoning for stateless or ZDR use;
  - keep text and tool calls from one reply in one message.

  ([Prior art](./prior-art/summary.md))
- **Old clients constrain the rollout.** Every client since v0.19 loads one remote model list, with no version gating. Unknown fields are ignored, so adding a new routing field is safe. Changing an existing field such as `supports_function_calling` reaches clients that lack the routing code. Releases v1.0.3–v1.2.0 lock LiteLLM 1.87.1, which does not route `gpt-6*`. ([Adapter](./kiln-adapter-and-public-surface/summary.md), [History](./history-of-the-workaround/summary.md))
- **Live Chat Completions bugs found along the way.** `max` is offered on GPT-6 Astra, Sol and Luna direct, but Chat Completions rejects it, so every such run fails. OpenAI-direct runs never return reasoning text, because summaries exist only on Responses. Custom `temperature` and `top_p` are dropped silently on these models. ([History](./history-of-the-workaround/summary.md))

## Implications

- **Bridge versus native is a choice about who owns the conversion, not whether there is one.** Kiln's trace is chat-shaped, so anything replayed from it gets converted to Responses items either way. Keeping the bridge means:
  - bumping LiteLLM to at least 1.103.5;
  - passing `store`, `include` and `strict` explicitly;
  - collecting `reasoning_items` from the terminal stream chunk, since `stream_chunk_builder` drops them;
  - ignoring choice indexes on reasoning deltas;
  - routing explicitly with the `openai/responses/` prefix rather than relying on name matching.

  Going native means Kiln writes:
  - chat history → `input` items;
  - output items → `ModelResponse`;
  - Responses events → `ModelResponseStream` chunks, to keep `invoke_openai_stream`'s type;
  - its own final-response assembly and usage mapping.

  It also hits rewritten response ids and LiteLLM's logging callback, which reads `.choices`.
- **Not tested end to end:** combining two subtopics' results suggests Kiln's streaming tool loop would lose reasoning between tool rounds on the bridge, because it rebuilds each turn with `stream_chunk_builder`, which drops `reasoning_items`.
- **The spec has to decide where reasoning lives.** Within one `invoke`, Kiln can keep native output items between tool rounds. Across saved turns, it can either drop prior reasoning and send id-less items, which leaves the trace unchanged, or extend the trace type with encrypted reasoning and `phase`. That second option touches the trace contract, and it brings OpenAI's `invalid_encrypted_content` error when a user changes API keys.
- **Routing should be an explicit per-provider flag.** Prior art favors capability flags over model-name matching (LangChain is still fixing near-miss names). A new `KilnModelProvider` field is harmless to old clients. Turning tools back on for new clients without breaking v1.0.3–v1.2.0 has to be designed around the shared remote list.
- **Scope decision: tool calls only, or every call to these models?** Routing only tool calls fixes the reported bug. Routing every call is needed to offer `max` on GPT-6.1 Sol and Terra and to get reasoning summaries. Summaries would also add visible reasoning to runs and eval inputs, and may require OpenAI org verification.
- **New error cases to plan for.** These include a 403 `misalignment_policy_violation` on GPT-6 Astra with persisted reasoning (Responses only, possibly mid-stream) and different LiteLLM exception classes on the conversion path. Some ZDR users will have `store` forced false.
- **Testing.** The `respx`-based Cloudflare tests are a working template for offline `/v1/responses` wire tests. Prior art's error catalog gives the cases to cover. Watch for bare `Mock()` providers, which read a new boolean flag as truthy. No OpenAI model is in the paid streaming or return-on-tool-call lists.

## Conflicts and Uncertainty

- **Is `max` a Chat Completions limit?** OpenAI's Chat Completions reference lists `max` in the `reasoning_effort` enum, and the OpenAI subtopic found no restriction. Kiln's own direct probes (#1830, #1831, #1982) got a 400 for `max` on Chat Completions for GPT-6 Astra, Sol, Luna, 6.1 Sol and 6.1 Terra, and #1830 says `/v1/responses` accepts it. The evidence leans toward Kiln's probes: the enum is generic, the probes are per model. Responses acceptance was only seen for 6.1 Sol.
- **Tools at `none` on GPT-6.1 Terra.** The history subtopic found that the conversion layer keeps `none` with tools on Chat Completions, and said current docs allow that. OpenAI's GPT-6 guide says 6.1 Terra needs Responses for tools even though it supports `none`, and Kiln offers `none` on 6.1 Terra. So removing the flag likely brings back a 400 there. Separately, #1351 saw `none` with tools rejected on gpt-5.4 in April 2026, and today's docs say it's allowed. Neither case is verified live.
- **Does the conversion layer's `text.format.strict: false` change behavior?** Closed PR #1757, quoted by the history subtopic, said Responses defaults that `strict` to true, so the bridge weakens structured output. OpenAI's reference gives a default of `false`, and the LiteLLM subtopic notes this matches Chat Completions. Kiln sends no `strict` on Chat Completions today either. The evidence leans toward "no change from today". Whether Kiln should send `strict: true` is a design question. (Function tools do differ: omitting `strict` there means "attempt strict" on Responses. Kiln already sends `strict: false` on user tools.)
- **GPT-6 Pro on OpenAI direct.** The adapter subtopic infers that a routing flag would make direct Pro entries possible. The history subtopic (a live call in #1894) and OpenAI's docs say GPT-6 Pro ids don't exist on OpenAI, and that Pro is a `reasoning.mode: "pro"` parameter on Responses. The evidence leans toward the latter, so Pro needs a request parameter as well as routing.
- **Replaying a reasoning item with both `id` and `encrypted_content` under `store: false`.** The OpenAI subtopic says OpenAI direct accepts it, while one detailed report says Azure rejects it. Other frameworks avoid the question by sending id-less items.
- **Moving targets.**
  - OpenAI's docs disagree on the Chat Completions `store` default.
  - Returning `encrypted_content` by default dates from about July 2026.
  - One maintainer reports OpenAI may have relaxed the reasoning-pairing rule, with no OpenAI statement.
  - LiteLLM's routing rules changed in each of the last three versions Kiln pinned.
  - Kiln doesn't set `LITELLM_LOCAL_MODEL_COST_MAP`, so `mode: responses` routing and cost data can change without a Kiln release. Four GPT-6 ids are missing from the bundled map and report a cost of $0 with it.

## Gaps

- **No live OpenAI calls anywhere.** There was no API key, so all wire behavior came from local fake servers with hand-written Responses bodies. A small paid probe set would close the most important unknowns:
  - `none` plus tools on Chat Completions for gpt-5.4, gpt-5.5 and gpt-6.1-terra;
  - how OpenAI treats `"strict": null` on a function tool;
  - `include` on Chat Completions;
  - `encrypted_content` under `store: true`;
  - `max` on Responses for the GPT-6 family;
  - real text-plus-tool-call replies;
  - real streaming shapes through the bridge.
- **Streaming through the bridge was not run through Kiln end to end.** `invoke_openai_stream` and `invoke_ai_sdk_stream` were only checked with synthetic chunks. The reasoning-loss inference above needs this test.
- **Kiln's hosted chat server isn't in this repo,** so whether AI SDK events are a cross-release contract is unconfirmed.
- **Why #1562, #1757 and #1831 were closed** isn't recorded. The reason may be in Slack or Linear (KIL-618).
- **LiteLLM upstream.** No upstream issue was found for the `summary_index` choice index, the `"strict": null` default, or a `store` default, and the BerriAI GitHub API was unreachable. The research checked which releases fix bridge defects, not what else a bump past `<1.103` would change for Kiln.
- **Smaller unknowns.**
  - Why GPT-5.4 mini and nano have no thinking levels on OpenAI direct.
  - Whether OpenAI's GPT-5.4 rule covers them.
  - Whether omitting `reasoning_effort` triggers the 400. This matters less, because Kiln always sends an explicit effort.
  - Azure behavior beyond fake servers.
  - Frameworks not read: Semantic Kernel, Spring AI, LangChain4j, `llm`.

## Subtopics

- [Kiln adapter and public surface](./kiln-adapter-and-public-surface/summary.md) — the code a migration touches and the contracts it must keep. Headline: one request builder feeds two `choices[0]` readers, and the chat-format trace drops reasoning items across runs.
- [History of the workaround](./history-of-the-workaround/summary.md) — when and why the flag was set, and the current state. Headline: correct when added, stale since LiteLLM 1.87.1 and 1.102.0, but removing it now exposes the conversion layer's defects and breaks old clients.
- [LiteLLM Responses support](./litellm-responses-support/summary.md) — routing rules, parameter and reply mapping, streaming, the native call, Azure, and 19 defects with version status. Headline: the two-choice bug is fixed only from 1.103.5, and most other defects are still open.
- [OpenAI Responses API](./openai-responses-api/summary.md) — official shape differences, per-model limits, reasoning state, `store` and retention, streaming, OpenRouter and Azure. Headline: the tools rule is policy, `store` defaults to true, and stateless reasoning needs `encrypted_content`.
- [Prior art](./prior-art/summary.md) — how eight frameworks moved to Responses and what broke. Headline: the bugs came from id, reasoning and `store` policy, and chat-history converters had the longest bug tails.
