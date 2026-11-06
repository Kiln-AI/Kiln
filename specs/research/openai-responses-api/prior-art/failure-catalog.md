# Failure catalog: errors other frameworks hit after moving to Responses

Each entry gives the exact error text, the cause the maintainers found, who hit it, and how they fixed it. These are useful as test cases for Kiln. Links go to the primary issue or PR. The per-framework context is in [frameworks.md](./frameworks.md).

The constraint behind most of these: when an input item carries a server-issued id (`rs_`, `msg_`, `fc_`), OpenAI checks it against what it produced or stored. Pydantic AI's maintainer put it as: the API "now requires the input to match verbatim the previous output if any IDs are included" ([pydantic-ai#3230](https://github.com/pydantic/pydantic-ai/issues/3230), 2025-10-23).

## 1. Orphan reasoning item

```
Item 'rs_...' of type 'reasoning' was provided without its required following item.
```

- **Cause.** A reasoning item with an `id` was sent without the item the model emitted right after it: a message, a function call, or a built-in tool call. Triggers seen: a client dropped a tool call (incomplete, failed validation, or user-interrupted) but kept the reasoning; built-in tool calls were not parsed or sent back; handoff or history-summary code kept a reasoning item alone; a stream was cut off after the reasoning item.
- **Hit by.** OpenAI Agents SDK ([#985](https://github.com/openai/openai-agents-python/issues/985), [#1611](https://github.com/openai/openai-agents-python/issues/1611), [#1660](https://github.com/openai/openai-agents-python/issues/1660), [#2503](https://github.com/openai/openai-agents-python/issues/2503)), Agents JS ([#929](https://github.com/openai/openai-agents-js/issues/929)), AI SDK ([#7099](https://github.com/vercel/ai/issues/7099), [#8321](https://github.com/vercel/ai/issues/8321)), Pydantic AI ([#2870](https://github.com/pydantic/pydantic-ai/issues/2870)), LangChain JS ([#9072](https://github.com/langchain-ai/langchainjs/issues/9072)), LlamaIndex ([#20333](https://github.com/run-llama/llama_index/issues/20333)), Continue (~100 issues, [PR #11785](https://github.com/continuedev/continue/pull/11785)), openclaw ([#19582](https://github.com/openclaw/openclaw/issues/19582)), Coder Blink ([#34](https://github.com/coder/blink/issues/34)).
- **Fixes used.**
  - Strip the reasoning `id`: Agents SDK `reasoning_item_id_policy="omit"` (opt-in), Pydantic AI `openai_send_reasoning_ids=False`.
  - Drop reasoning that lacks a valid successor: Continue's sanitizer, Agents SDK [PR #3207](https://github.com/openai/openai-agents-python/pull/3207).
  - Send the matching following item verbatim: Pydantic AI stores text part ids ([commit 3530dcb](https://github.com/pydantic/pydantic-ai/commit/3530dcb2c67d36428134b13a94c7e6bcedfa110e)).
  - Fall back to Chat Completions: Coder Blink.
- **Server behavior may have changed.** AI SDK #8321 was closed on 2026-08-26 as no longer reproducible: "This suggests that OpenAI changed how it handles reasoning items whose related function call is no longer present." That is one maintainer's live test, so I treat it as unconfirmed.

## 2. Function call or message missing its reasoning item

```
Item 'fc_...' of type 'function_call' was provided without its required 'reasoning' item: 'rs_...'.
Item 'msg_...' of type 'message' was provided without its required 'reasoning' item
Item 'web_search_call' was provided without its required 'reasoning' item
```

- **Cause.** The mirror of entry 1: an output item was sent with its `id`, but the reasoning item that came before it was not. Triggers seen: reasoning pruned from history while `msg_`/`fc_` ids were kept; reasoning dropped because it had no encrypted content; server-side truncation (`truncation="auto"` with `previous_response_id`) cutting between the two.
- **Hit by.** Pydantic AI ([#3230](https://github.com/pydantic/pydantic-ai/issues/3230)), AI SDK ([PR #10827](https://github.com/vercel/ai/pull/10827); changelog 216e2c9 in 4.0.93), LangChain (forum thread, and a comment on [#39635](https://github.com/langchain-ai/langchain/pull/39635)), Continue.
- **Fixes used.** Do not send `msg_`/`fc_` ids unless the reasoning before them is also sent. AI SDK sends assistant text by reference only "when they are preceded by reasoning in the same assistant message". Continue strips ids from items that follow a dropped reasoning item. LangChain's original single-slot reasoning format could not represent the item order, and the fix was the `responses/v1` format.

## 3. Item not found (store false or ZDR)

```
Item with id 'rs_...' not found. Items are not persisted when `store` is set to false. Try again with `store` set to true, or remove this item from your input.
Item with id 'rs_...' not found. Items are not persisted for Zero Data Retention organizations. Remove this item from your input and try again.
Item with id 'fc_...' not found. Items are not persisted for Zero Data Retention organizations. ...   (code: item_not_found, HTTP 404)
```

- **Cause.** A reasoning item was sent by bare id or as an `item_reference`, which needs server storage. Under `store:false`, or in a ZDR org where nothing is stored, the server cannot find it. A reasoning item that carries `encrypted_content` does not need storage.
- **Hit by.** Agents SDK ([#605](https://github.com/openai/openai-agents-python/issues/605), 2025-04), AI SDK ([#8315](https://github.com/vercel/ai/issues/8315), [#10060](https://github.com/vercel/ai/issues/10060)), LangChain ([commit 792c1a7 / #38372](https://github.com/langchain-ai/langchain/commit/792c1a743e4471990e96e818957b3299517e7255)), LlamaIndex ([#20333](https://github.com/run-llama/llama_index/issues/20333)). Apps built on the AI SDK whose default sends `store:true` plus item references also hit it: Supabase, Langfuse, Twenty, Mastra, opencode, Lightdash (links in [frameworks.md](./frameworks.md#vercel-ai-sdk-ai-sdkopenai)).
- **Fixes used.**
  - Set `store:false`, request `include: ["reasoning.encrypted_content"]`, and send full items. The AI SDK adds that `include` automatically when `store === false`.
  - Drop reasoning items that have no encrypted content: AI SDK (a71d345), LangChain, Continue, LlamaIndex (which drops all reasoning when `store=False`).
  - Omit `msg_` ids when `store=False`: LangChain.

## 4. Function call output with no matching call

```
No tool call found for function call output with call_id call_....
```

- **Cause.** A `function_call_output` was sent but its `function_call` was not, or the call was sent as an `item_reference`/`fc_` id that the server could not pair with the output's `call_id`. In the AI SDK it happened when client-executed calls were sent by reference, and again when `previousResponseId` chaining skipped them.
- **Hit by.** AI SDK ([#8216](https://github.com/vercel/ai/issues/8216), [#18537](https://github.com/vercel/ai/issues/18537), 2026-08), Continue (#8935, folded into PR #11785).
- **Fixes used.** Always send client-executed function calls as full `function_call` items with `call_id`, never by reference (AI SDK [PR #11114](https://github.com/vercel/ai/pull/11114)). Remove outputs whose call is missing (Continue).

## 5. Wrong id prefix on a function call

```
Expected an ID that begins with 'fc'
```

- **Cause.** A `msg_` id, or a framework-generated id, was put in a `function_call.id`. LangChain also filters its own `lc_`-prefixed ids because "the Responses API rejects them (expects `msg_...`)".
- **Hit by.** Continue (PR #11785), LangChain (#39209 "filter langchain-generated content block IDs").
- **Fix.** Send only server-issued ids of the right prefix, or no id at all.

## 6. Duplicate items

```
Duplicate item found with id rs_.... Remove duplicate items from your input and try again.
Duplicate item found with id fc_....
```

- **Cause.** The same stored item was sent twice: once in the replayed history and once via `previous_response_id` or a conversation; or a tool call appeared on two parts (an approval request and its later output).
- **Hit by.** AI SDK ([#10573](https://github.com/vercel/ai/issues/10573) via OpenRouter, [#13307](https://github.com/vercel/ai/issues/13307), [#15502](https://github.com/vercel/ai/issues/15502)). Pydantic AI [#5113](https://github.com/pydantic/pydantic-ai/issues/5113) is the stored-data variant: retries with `store=True` write duplicate stored conversations.
- **Fix.** Pick one state strategy per conversation, either full client-side history or server-side chaining. The Agents SDK docs say: "Mixing client-managed history with OpenAI-managed state can duplicate context unless you are deliberately reconciling both layers" ([running_agents.md](https://github.com/openai/openai-agents-python/blob/cd26bbbc52847845fde73b9952b51e62e2bcbdc0/docs/running_agents.md)).

## 7. Encrypted content rejected

```
The encrypted content for item rs_... could not be verified. Reason: Encrypted content organization_id did not match the target organization.   (code: invalid_encrypted_content)
```

- **Cause.** Encrypted reasoning is bound to the OpenAI organization that produced it. Replaying it through a different org fails. Triggers: a gateway spreading keys across orgs, key rotation, a changed base URL.
- **Hit by.** Pydantic AI ([#4608](https://github.com/pydantic/pydantic-ai/issues/4608), open; seen on about 0.05% of a high-volume workload).
- **Fixes proposed.** Retry once without reasoning ids or encrypted content ([PR #5482](https://github.com/pydantic/pydantic-ai/pull/5482), open). The maintainer refused to disable encrypted reasoning by default because of the performance cost.
- **Inference for Kiln.** Kiln users can change API keys between runs, and a saved trace replayed later as `prior_trace` could carry encrypted content from another org. If Kiln ever stores encrypted reasoning in traces, it needs this fallback.

## 8. Streaming captured the wrong snapshot of a reasoning item

- **Symptom.** No error on the first turn. On the next turn the reasoning item has no `encrypted_content`, so it is dropped (store false) or fails (entries 1 to 3).
- **Cause.** `response.output_item.added` carries an empty placeholder. The final `encrypted_content` only arrives on `response.output_item.done`. Code that captured the item at `added` lost it.
- **Hit by.** LangChain Python ([PR #39635](https://github.com/langchain-ai/langchain/pull/39635), fixed in 1.5.1, 2026-08-14), LangChain JS ([#10844](https://github.com/langchain-ai/langchainjs/issues/10844)). Continue and Haystack both handle `output_item.done` for this reason, with source comments saying so.

## 9. Other conversion bugs

- **Assistant text dropped when tool calls are present.** LlamaIndex [#21124](https://github.com/run-llama/llama_index/issues/21124): "the serializer discards the text entirely and returns only the tool call items." The reporter noted GPT-5.4 "uses these preambles as its primary reasoning-before-action mechanism".
- **Two reasoning items merged into one.** LangChain [#39715](https://github.com/langchain-ai/langchain/issues/39715) (open): adjacent summary fragments were merged without checking ids, which dropped the second item's `id` and `encrypted_content`.
- **Event-level fields sent back as item fields.** Haystack filters `item_id`, `output_index`, `summary_index`, `sequence_number` out of replayed reasoning, because the API rejects them with "Unknown parameter".
- **Reasoning with no summary.** Pydantic AI [#2862](https://github.com/pydantic/pydantic-ai/issues/2862): streaming crashed with `Cannot create a ThinkingPart with no content` on Azure, where summaries are "not guaranteed to be generated for every step/request".
- **Reasoning deltas ignored.** LlamaIndex [PR #21812](https://github.com/run-llama/llama_index/pull/21812): `response.reasoning_summary_text.delta` and `response.reasoning_text.delta` were not handled.
- **Structured output conversion.** DSPy [#8872](https://github.com/stanfordnlp/dspy/issues/8872), [#9122](https://github.com/stanfordnlp/dspy/issues/9122): a chat-style `response_format` was not converted correctly into `text.format`. LlamaIndex [discussion #21627](https://github.com/run-llama/llama_index/discussions/21627): strict schemas were missing `additionalProperties: false`.
- **Parameters with no Responses equivalent.** LangChain #38336 drops `stop`. DSPy trims `stop` on the client and drops `top_k`. The AI SDK drops `temperature`/`top_p`/logprobs for reasoning models unless effort is `none` on supported models.
- **Tool `strict` default.** The AI SDK started sending `strict: false` explicitly on Responses function tools in 4.0.77 (2026-09-25), after several earlier changes to strict defaults.
- **`phase` lost.** The AI SDK (66a374c) and Pydantic AI keep the assistant message `phase` (`commentary` / `final_answer`) and send it back. Pydantic AI's docs warn that dropping it "can cause preambles to be interpreted as final answers".
- **Built-in tool container expired.** Pydantic AI [#7461](https://github.com/pydantic/pydantic-ai/issues/7461): a replayed `code_interpreter_call` whose container had expired failed with `Expected container_id`. Out of scope for Kiln, which uses only function tools.
