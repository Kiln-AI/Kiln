# Prior art

How other LLM frameworks moved OpenAI calls to the Responses API while keeping a chat-style interface, and what went wrong for them. I read source code at pinned commits (2026-10-27 to 2026-10-30) plus issues, PRs and changelogs for these frameworks:

- OpenAI Agents SDK (Python)
- Vercel AI SDK (`@ai-sdk/openai`)
- Pydantic AI
- LangChain (`ChatOpenAI`)
- LlamaIndex (`OpenAIResponses`)
- Continue (IDE agent)
- Haystack
- DSPy

## Bottom Line

Every framework that moved to Responses then shipped a long series of 400-error fixes. Nearly all of them were about **which item ids to send, what to do with reasoning items between turns, and `store`**. Mapping fields across was not where the bugs were. The ones that converted a **chat-shaped history** at call time had the longest bug tails: LangChain's original format, Continue (~100 issues), LlamaIndex. LangChain had to redesign its message format to keep item order and support more than one reasoning item.

The fixes converge on one pattern:
- send items without server ids, unless replaying the exact prior output;
- always send client function calls as full `function_call` items with `call_id`;
- set `store` explicitly, and for stateless or ZDR use set `store:false` with `include: ["reasoning.encrypted_content"]`;
- drop reasoning that cannot be replayed;
- keep text and tool calls from one reply in one assistant message.

None of the frameworks turns one reply into more than one message or choice. Inference for Kiln: whichever LiteLLM path it uses, Kiln will have to own this id, reasoning and `store` policy, because neither LiteLLM path supplies it.

## Key Findings

- **The default switches happened at different times and in different ways.**
  - Agents SDK: Responses-native from the start; Chat Completions is its converted path ([docs](https://github.com/openai/openai-agents-python/blob/cd26bbbc52847845fde73b9952b51e62e2bcbdc0/docs/models/index.md)).
  - AI SDK: switched in `@ai-sdk/openai` 2.0.0, 2025-07-31 ([CHANGELOG](https://github.com/vercel/ai/blob/dfed8e8234b684c3e2a0571ad1a1078c8364b44c/packages/openai/CHANGELOG.md), "switch default to openai responses api").
  - Pydantic AI: warned in 1.x, then switched in v2.0.0 on 2026-06-23 ([PR #5334](https://github.com/pydantic/pydantic-ai/pull/5334)).
  - LangChain: routes each request by features and model name. Its GPT-5.4 to 5.6 tools-plus-reasoning rule is still an open PR ([#38860](https://github.com/langchain-ai/langchain/pull/38860)), which quotes OpenAI's error `Function tools with reasoning_effort are not supported for gpt-5.6-luna in /v1/chat/completions`.
- **Orphan reasoning-item errors were the most common bug.** The error is `Item 'rs_...' of type 'reasoning' was provided without its required following item`; its mirror is `Item 'fc_/msg_...' ... without its required 'reasoning' item`. They hit the Agents SDK, AI SDK, Pydantic AI, LangChain, LlamaIndex, Continue and others. The cause is ids sent from history that no longer matched the prior output verbatim ([pydantic-ai#3230](https://github.com/pydantic/pydantic-ai/issues/3230)). Fixes: strip ids (Agents SDK `reasoning_item_id_policy="omit"`, Pydantic AI `openai_send_reasoning_ids=False`), or drop reasoning that has no valid successor (Continue [PR #11785](https://github.com/continuedev/continue/pull/11785)). See [failure-catalog.md](./failure-catalog.md).
- **Defaulting to `store:true` with item references broke Zero Data Retention organizations.** The AI SDK did this. The error was `Item with id 'rs_...' not found. Items are not persisted for Zero Data Retention organizations`. Supabase, Langfuse, Twenty, Mastra, opencode and Lightdash each fixed it with `store:false` ([vercel/ai#10060](https://github.com/vercel/ai/issues/10060)). The AI SDK now adds `include: ["reasoning.encrypted_content"]` automatically when `store` is false. LangChain documents that `store` "Defaults to `True` for the Responses API and `False` for the Chat Completions API". Switching endpoints without setting it changes data retention.
- **Reasoning between turns.**
  - Pydantic AI always requests encrypted content and replays it. Its maintainer refused to disable that by default because it "will hurt performance significantly" ([#4608](https://github.com/pydantic/pydantic-ai/issues/4608)).
  - LlamaIndex defaults to `store=False` and drops reasoning between turns.
  - LangChain drops bare reasoning under `store=False` and keeps encrypted reasoning.
  - Encrypted reasoning fails with `invalid_encrypted_content` when replayed through a different OpenAI organization.
- **Streaming lessons.**
  - Read the reasoning item at `response.output_item.done`; `.added` only has a placeholder. LangChain lost encrypted content this way ([#39635](https://github.com/langchain-ai/langchain/pull/39635)).
  - Keep `summary_index` inside the reasoning part. The AI SDK uses `${itemId}:${summary_index}` as a part id.
  - Derive `tool_calls` as the finish reason from whether a `function_call` item is present.
  - Handle reasoning items that have no summary.
  - DSPy, which calls LiteLLM's native `responses()`, does not support streaming on that path.
- **Text plus tool calls stays in one message everywhere.** LlamaIndex shipped a bug that dropped the preamble text when tool calls were present ([#21124](https://github.com/run-llama/llama_index/issues/21124)). Newer models also label message items with a `phase` (`commentary` / `final_answer`). The AI SDK and Pydantic AI keep it. Pydantic AI warns that dropping it "can cause preambles to be interpreted as final answers".
- **Parameters and schemas need explicit handling.** `stop` and `top_k` have no Responses equivalent (LangChain drops `stop`; DSPy trims on the client). The AI SDK now sends `strict: false` explicitly on Responses function tools (4.0.77). Structured output conversion to `text.format` broke in DSPy ([#9122](https://github.com/stanfordnlp/dspy/issues/9122)).

## Details

- [frameworks.md](./frameworks.md): per-framework notes covering architecture, `store` default, reasoning handling, text plus tool calls, streaming, and bugs with dates and links, plus a comparison table. Read it for the evidence behind any claim here.
- [failure-catalog.md](./failure-catalog.md): each Responses error string other frameworks hit, with cause, who hit it, and the fix used. Read it to write Kiln's test cases.
- [lessons-for-kiln.md](./lessons-for-kiln.md): ten lessons mapped to Kiln's conversion-versus-native choice, with what was seen kept apart from what I infer. Read it when drafting the spec.

## Open Questions / Gaps

- **Did OpenAI relax the reasoning-pairing rule on the server?** One AI SDK maintainer reported in 2026-08 that an orphan reasoning case no longer reproduced and suggested OpenAI changed it ([vercel/ai#8321](https://github.com/vercel/ai/issues/8321)). I found no OpenAI statement. The OpenAI subtopic should check the reasoning guide.
- **What did OpenAI's 2025-04 ZDR fix change?** An OpenAI collaborator said "Just deployed the fix for this for ZDR orgs" ([openai-agents-python#605](https://github.com/openai/openai-agents-python/issues/605)) without saying what changed.
- **Frameworks I did not read.** Microsoft Agent Framework / Semantic Kernel, Spring AI, LangChain4j and Simon Willison's `llm`.
- **Haystack's item order.** Haystack sends an assistant reply as reasoning, then function calls, then text. I did not verify whether OpenAI accepts that order when ids are present.
- **No live tests.** No calls were made against OpenAI. Everything is from source and issue threads.

## Sources

- [openai/openai-agents-python @ cd26bbb](https://github.com/openai/openai-agents-python/tree/cd26bbbc52847845fde73b9952b51e62e2bcbdc0): `openai_responses.py`, `chatcmpl_converter.py`, docs `models/index.md` and `running_agents.md`. Authoritative for the Agents SDK at v0.24.0 (2026-10-27).
- [vercel/ai @ dfed8e8](https://github.com/vercel/ai/tree/dfed8e8234b684c3e2a0571ad1a1078c8364b44c/packages/openai): `convert-to-openai-responses-input.ts`, `openai-responses-language-model.ts`, CHANGELOG. `@ai-sdk/openai` 4.0.105 (2026-10-29). Publish dates are from the npm registry.
- [pydantic/pydantic-ai @ 79e157e](https://github.com/pydantic/pydantic-ai/tree/79e157e8b7bbea20d2354740e981478dd54dbb23): `models/openai.py`, `profiles/openai.py`, docs `models/openai.md`, `changelog.md` (2026-10-30).
- [langchain-ai/langchain @ 864754c](https://github.com/langchain-ai/langchain/tree/864754c5e293fba981302408fa3e2cf2f5f2d889/libs/partners/openai): `chat_models/base.py` and `_compat.py`. `langchain-openai` 1.7.3 (2026-10-29). Also the [1.5.2a1 release notes](https://github.com/langchain-ai/langchain/releases/tag/langchain-openai%3D%3D1.5.2a1).
- [run-llama/llama_index @ 619d746](https://github.com/run-llama/llama_index/tree/619d74664e8404612038bc15a1a40c686037277c/llama-index-integrations/llms/llama-index-llms-openai): `responses.py` and `utils.py`. `llama-index-llms-openai` 0.8.3 (2026-10-14).
- [continuedev/continue `core/llm/openaiTypeConverters.ts`](https://github.com/continuedev/continue/blob/5522c6f44ca0ac3528b37244818fbfa39b5af470/core/llm/openaiTypeConverters.ts) and [PR #11785](https://github.com/continuedev/continue/pull/11785) (merged 2026-03-25).
- [deepset-ai/haystack `openai_responses.py`](https://github.com/deepset-ai/haystack/blob/4b5dd70fde2a53f1913b6856d77c6f9c1def6720/haystack/components/generators/chat/openai_responses.py) (main, 2026-10-30).
- [stanfordnlp/dspy `litellm_engine.py`](https://github.com/stanfordnlp/dspy/blob/25162c4fc05c2d2d019b0ffb5b6b2a9f315ec007/dspy/clients/engines/litellm_engine.py) (2026-10-29) and issues [#8822](https://github.com/stanfordnlp/dspy/issues/8822), [#9122](https://github.com/stanfordnlp/dspy/issues/9122).
- Issue threads, cited inline in the deep docs and dated there: Agents SDK #605, #985, #1611, #1660, #2503, PR #3207; vercel/ai #7099, #8216, #8315, #8321, #10060, #10573, #13307, #18537, PR #10827, PR #11114; pydantic-ai #2862, #2870, #3230, #4608, #5113; LangChain #35584, #38372, #39635, #39715, PR #38860; langchainjs #9072, #10844; llama_index #20333, #21124, PR #20725, PR #21812, discussion #21627.
- Downstream ZDR reports: [Supabase d29fbf6](https://github.com/supabase/supabase/commit/d29fbf6eb78deb642c7db9a48df10c6115b54b32), [Langfuse PR #16810](https://github.com/langfuse/langfuse/pull/16810), [Twenty #20877](https://github.com/twentyhq/twenty/issues/20877), [opencode #2966](https://github.com/anomalyco/opencode/issues/2966), [Lightdash #19771](https://github.com/lightdash/lightdash/issues/19771), [coder/blink #34](https://github.com/coder/blink/issues/34).
