# Lessons from prior art for Kiln's design

This file turns the evidence in [frameworks.md](./frameworks.md) and [failure-catalog.md](./failure-catalog.md) into lessons for Kiln's choice between a conversion layer (chat-shaped request converted to Responses items) and a native Responses path. Each lesson separates what the sources show from what I infer for Kiln. I did not read Kiln's code for this subtopic. Kiln facts come from the research plan: traces are stored in OpenAI chat format, `invoke_openai_stream` yields chat-completion chunks (`ModelResponseStream`), and the public interface must not change.

## 1. Three architectures exist. Converting a chat-shaped history had the longest bug tail.

**Observed.**
- **Responses items as the canonical history.** OpenAI Agents SDK. Chat Completions is the converted path, not the other way round.
- **A neutral format with Responses data attached to each part, and a separate implementation per endpoint.** AI SDK, Pydantic AI, Haystack. Item ids, encrypted reasoning and `phase` travel as per-part metadata.
- **A chat-shaped history converted to Responses at call time.** LangChain's original format, Continue, LlamaIndex, DSPy. This group has the most 400-error reports:
  - Continue: "~100+ open issues" closed by [PR #11785](https://github.com/continuedev/continue/pull/11785).
  - LlamaIndex: [discussion #21627](https://github.com/run-llama/llama_index/discussions/21627), titled "`OpenAIResponses` seems broken to a level that makes me think nobody is actually using it".
  - LangChain had to replace its single reasoning slot with ordered content blocks (`responses/v1`, the default since 1.0.0). Its compat module says the new format "retains information about response item sequencing and accommodates multiple reasoning items".

**Inference for Kiln.** Kiln's stored trace is chat-shaped, so for anything replayed from a trace Kiln is in the third group whichever LiteLLM path it uses. The bugs in that group came from the policy layer: which ids to send, what to do with reasoning, and `store`. They did not come from field renaming. Kiln will have to own that policy explicitly. The LiteLLM bridge does not remove the need, and the LiteLLM native call does not provide the policy.

## 2. One reply is one assistant message. Keep the preamble text.

**Observed.** Every framework read keeps a reply that has text plus tool calls as one assistant message (or `ModelResponse`) holding both. None turns it into more than one message or choice. The Agents SDK states the merge rule: tool calls "get attached to the *current* assistant message". LlamaIndex shipped a serializer that dropped the text when tool calls were present ([#21124](https://github.com/run-llama/llama_index/issues/21124)). The reporter said GPT-5.4 "uses these preambles as its primary reasoning-before-action mechanism".

**Inference for Kiln.** When mapping a Responses reply back to a chat-style message, put all message text and all `function_call` items into one assistant message with `content` plus `tool_calls`. Test the text-plus-tool-call case explicitly; it is where the LiteLLM bridge defect named in the plan would show up.

## 3. Send ids only when replaying the exact output. Otherwise send none.

**Observed.** The rule, per Pydantic AI's maintainer: input with ids must "match verbatim the previous output". Frameworks that sent ids from edited or rebuilt history hit entries 1, 2 and 5 of the catalog. They converged on id-less items:
- the Agents SDK's opt-in `reasoning_item_id_policy="omit"`, which may become the default;
- Pydantic AI's `openai_send_reasoning_ids=False`;
- LangChain dropping `msg_`/`rs_` ids when `store=False`;
- Continue stripping ids after a dropped reasoning item;
- the AI SDK never sending an `id` on plain client `function_call` items.

The Agents SDK uses a placeholder id for items made from chat data and strips it before calling Responses.

**Inference for Kiln.** A chat-format trace holds no `rs_`/`msg_`/`fc_` ids, so a conversion from the trace should send id-less items. That avoids the whole pairing-error family. The tool-call id Kiln stores in the chat trace is the `call_id` (`call_...`), not the item id (`fc_...`). Haystack keeps both separately for this reason. Function calls must always go out as full `function_call` items with `call_id`, followed by their `function_call_output` ([AI SDK PR #11114](https://github.com/vercel/ai/pull/11114)).

## 4. Do not rely on server storage. Set `store` explicitly.

**Observed.**
- LangChain's docstring: `store` "Defaults to `True` for the Responses API and `False` for the Chat Completions API". Moving a call from Chat Completions to Responses without setting `store` therefore changes data retention.
- The AI SDK's `store:true` default plus item references broke every ZDR organization with `Item with id ... not found. Items are not persisted for Zero Data Retention organizations`. Supabase, Langfuse, Twenty, Mastra, opencode and Lightdash each fixed it with `store:false`.
- The fix pattern is `store:false` plus `include: ["reasoning.encrypted_content"]` plus full items. The AI SDK adds the `include` automatically when `store === false`.
- LlamaIndex defaults `store=False` and drops reasoning between turns.
- Agents SDK, Pydantic AI, LangChain and Continue leave `store` unset. They then needed escape hatches or fixes for `store=false` and ZDR users.
- Langfuse's PR gives the cost of the stateless approach: "Requests carry the encrypted reasoning of earlier steps (a few KB per step)."

**Inference for Kiln.** Kiln is a local app where users bring their own OpenAI keys, and some may be in ZDR organizations. The safe default seen in prior art is `store: false` plus encrypted reasoning, with no item references and no `previous_response_id`. Whatever Kiln picks, it should send `store` explicitly, so the retention behavior does not change silently with the endpoint. The OpenAI Responses subtopic owns the retention facts.

## 5. Decide where reasoning lives: inside the tool loop, and across saved turns.

**Observed.**
- OpenAI's guidance, as quoted by frameworks, is to keep reasoning items in context during function calling. The AI SDK maintainer linked "keeping reasoning items in context" on [#8321](https://github.com/vercel/ai/issues/8321).
- Pydantic AI requests encrypted reasoning for every reasoning model and sends `reasoning.context="all_turns"` by default. Its maintainer refused to turn encrypted reasoning off by default because "it will hurt performance significantly" ([#4608](https://github.com/pydantic/pydantic-ai/issues/4608)).
- A LangChain maintainer warned that stripping reasoning means "the model will lose track of what it was doing and need to re-reason" ([#39635](https://github.com/langchain-ai/langchain/pull/39635)).
- LlamaIndex drops reasoning between turns when `store=False`. One contributor argued reasoning items "are not part of the conversational history"; a maintainer disagreed.

**Inference for Kiln.** There are two separate cases.
- **Within one `invoke` tool loop.** Kiln can keep the native output items of each round, including reasoning with encrypted content, and append the `function_call_output` items. Reasoning then survives across tool rounds without changing the saved trace format. This is the Agents SDK model applied inside one call. A conversion layer that rebuilds Responses input from chat messages on every round loses the reasoning between rounds, unless the chat message carries it.
- **Across saved turns (`prior_trace`).** The chat-format trace cannot carry encrypted reasoning unless Kiln extends it. The choices seen are: drop prior reasoning and send id-less items (LlamaIndex, LangChain `store=False` without encrypted content), or carry encrypted content in an extra field on the assistant message (Continue's `reasoning_details`, Pydantic AI's `signature`, the AI SDK's provider metadata). If Kiln stores encrypted content, it also needs the cross-organization fallback in lesson 9.

## 6. Streaming pitfalls to design for

**Observed.**
- **Capture reasoning at `response.output_item.done`, not `.added`.** The `added` event carries an empty placeholder. LangChain Python and JS both lost encrypted content this way ([#39635](https://github.com/langchain-ai/langchain/pull/39635), [langchainjs#10844](https://github.com/langchain-ai/langchainjs/issues/10844)). Continue and Haystack have comments explaining why they read `done`.
- **Summary index stays inside the reasoning part.** The AI SDK uses `${itemId}:${summary_index}` as a reasoning part id. LangChain nests `summary_index` inside a reasoning block and keeps its own outer index from `output_index`. Neither uses `summary_index` as a message or choice index.
- **`output_index` can jump.** LangChain records the first `output_index` per item id because "After several built-in tool calls the API can report a later `output_index`".
- **Finish reason is derived.** The AI SDK and Haystack report `tool_calls` when any `function_call` item is present, `length` for `max_output_tokens`, and `stop` otherwise.
- **A reasoning item may have no summary.** Pydantic AI crashed on this on Azure ([#2862](https://github.com/pydantic/pydantic-ai/issues/2862)).
- **Reasoning delta events must be handled, or reasoning disappears from the stream.** LlamaIndex [PR #21812](https://github.com/run-llama/llama_index/pull/21812).
- **An interrupted stream can leave an orphan reasoning item in history.** Coder Blink; opencode's maintainer: "the openai responses api has issues when streams are interrupted".
- DSPy's LiteLLM-native Responses path supports no streaming at all.

**Inference for Kiln.** Kiln must emit chat-completion chunks (`ModelResponseStream`) and AI SDK UI events from a Responses stream. That is the mapping LangChain does into `AIMessageChunk` and the AI SDK does into stream parts. Their choices above are the tested ones. Kiln's AI SDK event output can follow the AI SDK's own mapping of Responses events, because that protocol is the AI SDK's.

## 7. Model-name routing is brittle. Prefer explicit per-model capability flags.

**Observed.**
- LangChain routes by feature detection and model-name prefixes. It warns that "Model name can trigger Responses API routing ... independent of `base_url`".
- Its rule for GPT-5.4 to 5.6 with function tools and reasoning is still an open PR ([#38860](https://github.com/langchain-ai/langchain/pull/38860)). That PR needs a matrix: 5.6 routes by default, 5.4/5.5 only with an explicit non-`none` effort, `-chat` variants never. A reviewer found near-miss names (`gpt-5.60`, `gpt-5.55`) that a loose prefix match would misroute.
- Pydantic AI uses per-model profile flags: `openai_supports_encrypted_reasoning_content`, `openai_supports_phase`, `openai_responses_requires_store_false`, `openai_responses_supports_reasoning_context`.
- The AI SDK uses a model capability table, which drives `isReasoningModel`, logprobs support, and sampling parameters with `none` effort.

**Inference for Kiln.** Kiln's per-provider flags in `ml_model_list.py` fit the Pydantic AI and AI SDK pattern. An explicit "use Responses" flag on each OpenAI provider entry avoids the string-matching bugs LangChain is still working through. It also lets the remote model list turn the feature on per model.

## 8. Parameters with no direct Responses equivalent need an explicit policy

**Observed.** `stop` is dropped by LangChain (#38336) and trimmed on the client by DSPy. `top_k` is dropped by DSPy. `temperature`, `top_p` and logprobs are removed with warnings by the AI SDK for reasoning models unless effort is `none` on a supporting model. For function tools, `strict` is now sent explicitly as `false` by the AI SDK when unset (4.0.77). Structured output needs a real conversion to `text.format`: DSPy broke here ([#9122](https://github.com/stanfordnlp/dspy/issues/9122)), and LlamaIndex shipped strict schemas without `additionalProperties: false`.

**Inference for Kiln.** List each chat parameter Kiln sends today, and choose map, drop with a warning, or reject for each one. Test structured output and the tool `strict` setting on the Responses path; both broke in other frameworks' conversions. The LiteLLM subtopic covers how LiteLLM maps each one.

## 9. Encrypted reasoning can fail across OpenAI organizations

**Observed.** `invalid_encrypted_content` ("Encrypted content organization_id did not match the target organization") appears when encrypted reasoning is replayed through a different org ([pydantic-ai#4608](https://github.com/pydantic/pydantic-ai/issues/4608)). The proposed fix is one retry without encrypted reasoning or ids.

**Inference for Kiln.** This only matters if Kiln keeps encrypted reasoning past a single `invoke`, for example in a saved trace used later as `prior_trace` after the user changed API keys. If it does, catch this error code and retry once without the reasoning items.

## 10. Rollout: others made the switch behind a flag first, and tested converters heavily

**Observed.**
- The AI SDK switched the default in a major release (2.0.0, 2025-07-31). The ZDR and pairing errors then reached many downstream apps.
- Pydantic AI added a deprecation warning and an `openai-chat:` opt-out in 1.x (PR #5334, 2026-05-13), then flipped the default in v2.0.0 (2026-06-23).
- LangChain routes per request, and `use_responses_api=False` always wins.
- Continue's fix shipped with 22 converter unit tests. The AI SDK's Responses converter test file is about 7,200 lines, and it keeps live error fixtures such as `__fixtures__/openai-issue-18537-error.1.json`. Pydantic AI uses recorded HTTP cassettes.

**Inference for Kiln.** A per-model opt-in flag, plus a converter test suite built from the catalog's error cases, matches what worked elsewhere. The catalog cases: text plus tool calls; reasoning before a tool call; dropped tool call; interrupted stream; `store:false`; multiple reasoning items; no summary. Recorded multi-turn fixtures covering reasoning plus tools are the one case unit tests missed most often.
