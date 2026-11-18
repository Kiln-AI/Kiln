# Reasoning replay by provider

**Date:** 2026-11-18.
**Versions:** LiteLLM 1.105.7. The code is the branch for Kiln-AI/Kiln#2001, `claude/pensive-cannon-3jnl5q`.
**Purpose:** input for the project that keeps reasoning across turns. For that project's brief, see [handoff_reasoning_across_turns.md](./handoff_reasoning_across_turns.md).

This report answers one question for every provider Kiln supports. When Kiln sends a conversation back to a model, what happens to the model's earlier reasoning?

It asks that in two situations:

1. **Within one run, between tool rounds.**
2. **Across turns, from a saved trace.** This covers multi-turn runs (`prior_trace`), `return_on_tool_call` resume and synthetic-user turns.

None of the problems below were caused by #2001. They come from Kiln's trace format and from how LiteLLM converts messages for each provider. They are not blocking for #2001.

## Method

- **Code reading.** This covers Kiln's adapter code and LiteLLM 1.105.7's per-provider request code. LiteLLM paths below are relative to `site-packages/litellm/`.
- **Offline probes.** The probes call Kiln's real `adapter_for_task`, with `respx` standing in for each provider. They capture the request body LiteLLM sends.
  - Settings went to a temp file, the fake keys were placeholders, `LITELLM_LOCAL_MODEL_COST_MAP=true` was set, and `litellm.disable_aiohttp_transport = True`. This is the same pattern as `test_cloudflare_litellm.py` and `test_openai_responses_wire.py`.
  - Each case ran three scenarios: a tool loop inside one run (capturing request 2), a `return_on_tool_call` run then a resume from `prior_trace`, and a finished answer then a new user turn from `prior_trace`.
  - Each scenario ran both non-streamed (`invoke`) and streamed (`invoke_openai_stream`). The AI SDK stream uses the same `AdapterStream` / `StreamingCompletion` path.
  - The probe scripts aren't in the repo. To rebuild them, use the same `respx` setup with each provider's native reply shape. That means OpenAI Responses `output` items with `encrypted_content`, Anthropic `thinking` blocks with `signature`, and Gemini parts with `thoughtSignature`.
- **Provider docs.** Each provider's own docs, for how it says reasoning must be replayed.
- **No paid calls in the probes.** Anything that depends on a provider's real validation is unverified, except what the paid run in [Paid results, 2026-11-18](#paid-results-2026-11-18) checked.

Evidence tags:

| Tag | Meaning |
|---|---|
| **R** | read in code |
| **O** | observed in an offline probe |
| **D** | provider docs |
| **3P** | third-party report, such as a GitHub issue |
| **I** | inferred |
| **P** | paid call with real keys, 2026-11-18 |

## How Kiln sends history back

All of these were confirmed by reading (R) and by probes (O).

- **Within a run**, Kiln keeps LiteLLM's live `Message` objects in the message list. The non-streamed path appends them in `litellm_adapter.py:341`, and the streamed path in `adapter_stream.py:245`. LiteLLM turns each one into a dict with `model_dump(exclude_none=True)` (`utils.py:8369-8384`, called from `main.py:5264`). So the provider's native fields all reach LiteLLM's provider code: `reasoning_content`, `thinking_blocks`, `reasoning_items` and `provider_specific_fields`.
- **The saved trace** keeps only `content`, `reasoning_content` and `tool_calls` on assistant messages (`litellm_adapter.py:1174-1220`). All native reasoning state is gone: encrypted items, signatures and thought signatures.
- **`MultiturnFormatter`** passes `prior_trace` through unchanged (`chat/chat_formatter.py:302-304`). A tool-result input becomes a `tool` message (318-338).
- **`sanitize_messages_for_provider`** strips only `KILN_ONLY_MESSAGE_FIELDS` (`utils/open_ai_types.py:144-175`). So `reasoning_content` is sent back for every provider. The one exception is Cerebras: there Kiln strips `reasoning_content` and `provider_specific_fields` (`strip_assistant_fields_for_cerebras`, `litellm_adapter.py:81-104`).
- **Synthetic user.** The target side continues from `new_run.trace` (`synthetic_user/drive_loop.py:157-161`, 202), the same as a multi-turn run. The synthetic user's own model gets role-swapped content with no reasoning (`synthetic_user/driver.py:103-132`).

## Results by provider

Model counts are non-deprecated provider entries in `ml_model_list.py`.

| Provider | Tool rounds, one run | Saved-trace continuation | What goes on the wire for the earlier assistant turn | Evidence |
|---|---|---|---|---|
| **OpenAI Chat Completions** (gpt-5/5.1/5.2, o3, and any OpenAI call without tools or summaries) | Nothing to replay | Nothing to replay | Within a run: `{tool_calls, provider_specific_fields:{refusal:null}}`. From the trace: `{tool_calls}` or `{content}`. | O, D |
| **OpenAI Responses bridge** (gpt-5.4+/gpt-6 with tools or `reasoning_summary`; the Pro models) | Replayed, but see the ordering issue below | Dropped, no error | Within a run: `{"type":"reasoning","id","summary","encrypted_content"}` before `function_call`. From the trace: `message` and `function_call` only. `reasoning_content` is ignored (`completion_extras/litellm_responses_transformation/transformation.py:120-133`, 422-549). | O, R, D |
| **Azure OpenAI** (o-series, gpt-4.x) | Nothing to replay | Nothing to replay | `{tool_calls, provider_specific_fields:{refusal:null}}` | O |
| **Anthropic, adaptive thinking** (Opus 4.6+, Sonnet 4.6+, Haiku 5.5, Fable) | Non-streamed: replayed correctly. **Streamed: thinking text doubled** | Dropped. Resume gives no error per the docs, but the blocks are gone. | Non-streamed: `[thinking{text,signature}, text, tool_use]`. From the trace: `[text, tool_use]`. `anthropic_messages_pt` never reads `reasoning_content` (`litellm_core_utils/prompt_templates/factory.py:2523-2526`, 2677-2681). | O, R, D |
| **Anthropic, manual thinking** (Sonnet 4.5, Haiku 4.5, Opus 4.5; LiteLLM sends `{"type":"enabled","budget_tokens":4096}`) | Same as adaptive | **Resume may 400** (conflicting evidence). Multi-turn: dropped. | Resume: `thinking` stays enabled, and the assistant turn is `[text, tool_use]` with no thinking block. LiteLLM drops `thinking` only when `litellm.modify_params` is on (`llms/anthropic/chat/transformation.py:1924-1942`). It defaults to False, and Kiln never sets it. | O, R, D, 3P |
| **Gemini API / Vertex** | Tool-call signature correct. The summary goes back as an **unsigned thought part** | Tool-call signature survives. The summary goes back as an unsigned thought part. | `{"thought":true,"text":<reasoning_content>}` with no signature, then `{"function_call":…,"thoughtSignature":…}`. `reasoning_content` becomes a thought part at `llms/vertex_ai/gemini/transformation.py:883-887`. The tool-call signature is embedded in the tool-call id (`call_x__thought__<sig>`, `vertex_and_google_ai_studio_gemini.py:1590-1596`) and read back from it (`factory.py:1182-1220`, 1303-1311). Kiln saves the id, so resume keeps it. | O, R, D |
| **OpenRouter** (195 models, 102 with thinking) | **`reasoning_details` never reaches OpenRouter** | Plain text only | Non-streamed: `reasoning_content` at the top level, with `reasoning_details` nested under `provider_specific_fields`, so OpenRouter never sees it. Streamed: `reasoning_details` is gone entirely. Unknown response keys land in `provider_specific_fields` (`litellm_core_utils/llm_response_utils/convert_dict_to_response.py:665-669`), and the OpenRouter transform doesn't move them (`llms/openrouter/chat/transformation.py:137-160`). | O, R, D, 3P |
| **Fireworks** (DeepSeek V4.x, GLM, Kimi, MiniMax, gpt-oss) | Replayed correctly | Replayed correctly | `{tool_calls, reasoning_content}`. LiteLLM strips `thinking_blocks` and `provider_specific_fields` (`llms/fireworks_ai/chat/transformation.py:516-522`). | O, R, D |
| **Together** | Replayed correctly | Replayed correctly | `{tool_calls, reasoning_content}` (`llms/together_ai/chat/transformation.py:28`, 202-215). Whether earlier turns' reasoning is used depends on the host's chat template (I). | O, R |
| **Groq** (Qwen, gpt-oss) | Non-streamed: Groq's `reasoning` field. Streamed: `reasoning_content` | **Non-streamed: lost.** It is never saved. | Non-streamed replies are built with `ModelResponse(**json)` (`llms/openai_like/chat/transformation.py:114`), which leaves `reasoning` as a plain attribute. So Kiln saves no reasoning, and `intermediate_outputs["reasoning"]` is empty. Streaming renames the field (`llms/groq/chat/transformation.py:357-363`). | O, R, D |
| **Cerebras** | Stripped on purpose | Stripped on purpose | `{tool_calls}` | O, R |
| **Ollama / Docker Model Runner** | Ignored | Ignored | `{tool_calls, reasoning_content}`. Ollama's `/v1` endpoint reads only `reasoning` (ollama `openai/openai.go`). Docker Model Runner wasn't checked. | O, R |
| **SiliconFlow, Cloudflare, Featherless, custom OpenAI-compatible** | Replayed as `reasoning_content` | Replayed as `reasoning_content` | `{tool_calls, reasoning_content, provider_specific_fields:{refusal:null}}`. This is right for DeepSeek-style models if the host reads the field (I). | O |
| **Bedrock Converse** (no Kiln reasoning models today) | Replayed correctly (`reasoningContent` with signature) | Dropped | `factory.py:4499-4512` | O, R |

**Not covered:**
- huggingface: no models in the list.
- typesafe: not on LiteLLM.
- kiln_fine_tune and kiln_custom_registry: they resolve to an underlying provider.
- Claude on Vertex or Bedrock: no entries in the list.
- Docker Model Runner: not probed separately.

## Is reasoning text sent back in a form the API wasn't designed for?

Yes, for two providers:

- **Gemini API and Vertex.** The saved `reasoning_content` is a thought summary. LiteLLM sends it back as a part marked as the model's own thought, `{"thought": true, "text": …}`, with no signature. This happens within a run and on every later turn. Google carries reasoning in `thoughtSignature`. Vertex's docs say to "either include the full context (thoughts, function calls, and responses) or omit it entirely. Providing partial context can degrade model performance." (D) A Google contact, quoted in a pydantic-ai issue, said returned summaries are ignored. Another user measured them being billed as input tokens. (3P)
- **OpenRouter, for Claude, Gemini and GPT models.** `reasoning_content` goes out as OpenRouter's plain-text `reasoning` alias. For these models it's a summary with no signature or encryption. OpenRouter's docs say to use `reasoning_details` for them. (D) For DeepSeek, GLM, Kimi and MiniMax on OpenRouter, the plain-text path is the documented one.

The other providers handle it as follows:
- **Sent the way DeepSeek-style APIs expect:** Fireworks, Together, SiliconFlow, Cloudflare, Featherless and custom hosts.
- **Ignored:** OpenAI's Responses bridge, Anthropic and Bedrock.
- **Stripped:** Cerebras.
- **Read under a different name:** Ollama, which reads `reasoning`, not `reasoning_content`.

If a conversation switches models, summaries saved from OpenAI, Claude or Gemini would reach DeepSeek-style hosts as raw chain of thought. (I)

## The `return_on_tool_call` resume

- **Anthropic manual-thinking models** (Sonnet 4.5, Haiku 4.5, Opus 4.5, with thinking not `none`): possibly a 400. The resumed request has thinking enabled, and `[text, tool_use]` with no thinking block before the `tool_result` (O). The evidence conflicts:
  - For a 400: the docs say manual mode enforces a leading thinking block (D). There are 2025 reports of "Expected `thinking` or `redacted_thinking`, but found `tool_use`" through LiteLLM, including on Bedrock (3P).
  - Against: the same docs say mid-turn conflicts "degrade gracefully … silently disables thinking". Kiln also has a paid test for this exact case, `test_invoke_with_return_on_tool_call_and_resume[claude_4_5_haiku-anthropic-medium]` (`test_litellm_adapter_streaming.py:43-48`), added 2026-03-18. It passed in the 2026-11-18 paid run. (P)
  - Either way, thinking is lost for that turn.
- **Anthropic adaptive models:** no error per the docs ("Adaptive mode relaxes this"). But Anthropic requires thinking blocks to be passed back within a tool-use turn, so the resumed call loses its reasoning. (D)
- **Gemini 3 direct:** works. The signature survives inside the saved tool-call id. (O)
- **OpenAI Responses bridge:** works, but drops the reasoning items OpenAI recommends passing back. (O, D)
- **DeepSeek-style hosts:** work, because `reasoning_content` is saved.
- **OpenRouter Gemini 3:** likely broken. See possible error 2 below.
- **Groq non-streamed:** the reasoning is lost.

## Possible errors today

None of these are confirmed. The 2026-11-18 paid run reproduced none of them, but it didn't cover all of them. See [Paid results, 2026-11-18](#paid-results-2026-11-18). All four exist before #2001.

1. **Streamed Anthropic tool loops send the thinking text twice under its original signature.** (O, and checked in code)
   - When the `signature_delta` event arrives, LiteLLM's Anthropic stream handler re-emits a thinking block holding the full accumulated thinking text (`llms/anthropic/chat/handler.py:703-715`).
   - `stream_chunk_builder` then appends that text to the copy it already built from the deltas (`litellm_core_utils/streaming_chunk_builder_utils.py:715-733`).
   - This affects every Anthropic model with thinking on, in streamed runs with tools. The same code is in 1.102.0.
   - Anthropic's docs say modified thinking blocks are rejected with a 400. The server also reconstructs the thinking from the signature, so it might tolerate the change.
   - Kiln's paid `STREAMING_MODELS` tests exercise this exact path.
   - Separately, both the streamed and non-streamed paths move `text` after all thinking blocks in a `[thinking, text, thinking, tool_use]` reply. (O)
2. **OpenRouter never receives top-level `reasoning_details`.** Gemini 3 function-call signatures exist only there. Late-2025 reports show a 400: "Gemini models require OpenRouter reasoning details to be preserved in each request" (3P). If that still holds, every OpenRouter Gemini 3.x/4 tool loop fails on round 2, and so does every resume. Against that, the model-add process runs `test_tools_all_built_in_models` with default thinking on.
3. **Anthropic manual-thinking resume.** See the resume section above.
4. **OpenRouter Claude with thinking on.** Plain-text reasoning without a valid signature has produced "Invalid `signature` in `thinking` block" for other clients (3P, OpenRouter ai-sdk-provider #423). Kiln sends exactly that, within a run and across turns.

These lose quality or cache hits, but don't raise errors:
- OpenAI, Anthropic and Gemini lose reasoning across turns and on resume.
- OpenAI loses `phase`.
- Gemini gets summaries back as unsigned thought parts.
- Groq's non-streamed reasoning is never saved.
- Ollama ignores `reasoning_content`.

## OpenAI: interleaved reasoning is reordered on replay

This one is within a run on the Responses bridge. It came from the code review of #2001's `litellm_streaming.py` and from reading LiteLLM 1.105.7. It's listed here because the proper fix belongs with the reasoning project.

- **OpenAI wants the original order.** Its guidance is to pass reasoning items back "untouched", in their original order. GPT-5.4+ can produce reasoning between tool calls and around visible text within one reply.
- **LiteLLM's chat-to-Responses converter changes the order.** It puts every reasoning item of an assistant message first, then the text, then the tool calls (`completion_extras/litellm_responses_transformation/transformation.py:495-549`).
- **The streamed path replays every item, moved to the front.** It uses `StreamingCompletion`, which since #2001 puts all the terminal chunk's reasoning items back on the message. So `[reasoning A, tool call 1, reasoning B, tool call 2]` is replayed as `[A, B, call 1, call 2]`. (O, from the code review's runs)
- **The non-streamed path keeps only the last reasoning item, also moved to the front.** A later reasoning item overwrites the pending one while the reply is converted to a message (`transformation.py:763-771`). So the same reply is replayed as `[B, call 1, call 2]`. (R) This is already on `main` for GPT-5.4 Pro and GPT-5.2 Pro. #2001's companion PR, Kiln-AI/Kiln#2003, extends it to the ten models it turns tools on for.
- **Unverified:** whether OpenAI rejects either order. There are public reports of a 400 "Item 'rs_…' of type 'reasoning' was provided without its required following item" (3P). Settle it with a paid call before designing around it. #2001's paid run on 2026-11-18 didn't include this probe.
- **Why Kiln can't fix the order in place:** a chat-format assistant message can't express the original order, and LiteLLM's stream drops `item_id` and `output_index`. So restoring the order probably needs LiteLLM's native Responses path or an upstream LiteLLM fix.

## Paid results, 2026-11-18

These come from a paid run with real keys, on the same branch and LiteLLM 1.105.7. It was a partial run of the full paid suite plus targeted OpenAI tests.

- **Anthropic streaming with tools** (possible error 1, question 1): 62 passed. No error was reproduced. So either Anthropic tolerates the doubled thinking text, or the passing runs didn't produce it; the run didn't check which. (P)
- **Anthropic manual-thinking resume** (possible error 3, question 2): Haiku 4.5 passed. Sonnet 4.5 and Opus 4.5 weren't covered. (P)
- **OpenRouter Gemini 3.x with tools** (possible error 2, question 3): not covered.
- **OpenRouter Claude with thinking on** (possible error 4, question 4): 36 passed. "Invalid `signature` in `thinking` block" wasn't reproduced. (P)
- **OpenAI Responses bridge with tools:** every thinking level passed on the ten GPT-5.4+/GPT-6 models, including GPT-6.1 Terra at `none`. (P)
- **OpenAI narration plus a tool call:** passed on all ten. This confirms the lost-tool-call fix against the real API: a reply holding text and a tool call keeps its tool call. For the bug, see [summary.md](./summary.md). (P)
- **Interleaved reasoning replay** (question 9): the probe didn't run, so the question is still open.

## Questions that need a paid call

The 2026-11-18 paid run partly answered questions 1, 2 and 4, and didn't cover 3 or 9. See [Paid results, 2026-11-18](#paid-results-2026-11-18).

1. Does Anthropic reject the doubled thinking text? Run the paid `STREAMING_MODELS` tests, or one streamed tool call on Sonnet 4.5 and Opus 4.8.
2. Does a manual-thinking resume on Anthropic (Haiku 4.5, Sonnet 4.5, Opus 4.5) return a 400, or silently disable thinking? Run `RETURN_ON_TOOL_CALL_MODELS` and check the response for thinking blocks.
3. Does an OpenRouter Gemini 3.x tool loop return a 400 today? Run `test_tools_all_built_in_models[gemini_3_5_flash-openrouter]`, and a resume.
4. What does OpenRouter do with plain-text `reasoning_content` for Claude: drop it, use it, or reject it? Check with thinking on and with thinking set to `none`.
5. Are unsigned Gemini `thought:true` parts ignored, or billed? Compare input tokens with and without them.
6. Does Groq accept `reasoning` or `reasoning_content` on input assistant messages?
7. Does api.openai.com Chat Completions accept a `reasoning_content` key on assistant messages? This matters when a conversation switches models.
8. On Claude models with preserved thinking, does moving the text after the thinking blocks fail the prefix check?
9. Does OpenAI reject the reordered or partial reasoning replay described above?
10. How many cached tokens are lost across turns when reasoning is dropped? Use OpenAI's `cached_tokens`, and Anthropic's cache fields.
